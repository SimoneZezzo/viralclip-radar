"""Offline Task Scheduler definition and in-process collector controls."""

from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import subprocess
import sys
from _thread import interrupt_main
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Event, Thread
from xml.etree.ElementTree import Element, SubElement, indent, tostring

from viralclip.config import load_settings
from viralclip.dataset import ignored_output
from viralclip.storage.database import MIGRATIONS

SCHEMA_VERSION = 2
TASK_NAMESPACE = "http://schemas.microsoft.com/windows/2004/02/mit/task"
DEFAULT_GAME = "Grand Theft Auto V"


def control_directory(db_path: Path) -> Path:
    return db_path.with_name(db_path.name + ".viralclip-supervision")


def task_xml(
    python: Path, root: Path, db_path: Path, sid: str, game: str, interval: int, lookback: int
) -> bytes:
    if not re.fullmatch(r"S-1-(?:[0-9]+-)+[0-9]+", sid):
        raise ValueError("Use the Windows account SID")
    if not game.strip() or min(interval, lookback) <= 0:
        raise ValueError("Invalid expected collector settings")
    task = Element("Task", {"xmlns": TASK_NAMESPACE, "version": "1.3"})
    SubElement(
        SubElement(task, "RegistrationInfo"), "Description"
    ).text = "ViralClip Radar collector (staged disabled; see the supervision runbook)"
    trigger = SubElement(SubElement(task, "Triggers"), "BootTrigger")
    SubElement(trigger, "ExecutionTimeLimit").text = "PT0S"
    SubElement(trigger, "Delay").text = "PT30S"
    principal = SubElement(SubElement(task, "Principals"), "Principal", id="Collector")
    for key, value in (
        ("UserId", sid),
        ("LogonType", "Password"),
        ("RunLevel", "LeastPrivilege"),
    ):
        SubElement(principal, key).text = value
    settings = SubElement(task, "Settings")
    for key, value in (
        ("Enabled", "false"),
        ("MultipleInstancesPolicy", "IgnoreNew"),
        ("ExecutionTimeLimit", "PT0S"),
        ("AllowHardTerminate", "false"),
        ("DisallowStartIfOnBatteries", "false"),
        ("StopIfGoingOnBatteries", "false"),
        ("WakeToRun", "false"),
    ):
        SubElement(settings, key).text = value
    retry = SubElement(settings, "RestartOnFailure")
    SubElement(retry, "Interval").text = "PT1M"
    SubElement(retry, "Count").text = "3"
    action = SubElement(SubElement(task, "Actions", Context="Collector"), "Exec")
    SubElement(action, "Command").text = str(python)
    SubElement(action, "Arguments").text = subprocess.list2cmdline(
        [
            "-B",
            "-m",
            "viralclip.windows_supervision",
            "--db",
            str(db_path),
            "run",
            "--game",
            game,
            "--interval",
            str(interval),
            "--lookback",
            str(lookback),
        ]
    )
    SubElement(action, "WorkingDirectory").text = str(root)
    indent(task)
    return tostring(task, encoding="utf-16", xml_declaration=True)


def preflight(db_path: Path, interval: int, lookback: int) -> None:
    settings = load_settings()
    if settings.db_path.resolve() != db_path:
        raise ValueError("Configured SQLite path differs from the approved task path")
    if not settings.has_twitch_credentials:
        raise ValueError("Twitch credentials are missing in the task account environment")
    if settings.game_ids:
        raise ValueError("Additional category IDs are configured for the single-game task")
    if (settings.discovery_interval_seconds, settings.discovery_lookback_minutes) != (
        interval,
        lookback,
    ):
        raise ValueError("Discovery interval or lookback differs from the approved task settings")
    if len(MIGRATIONS) != SCHEMA_VERSION or not db_path.is_file():
        raise ValueError("Approved collector schema or existing database is missing")
    with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
        db.execute("PRAGMA query_only = ON")
        migrations = db.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        if migrations != [(n,) for n in range(1, SCHEMA_VERSION + 1)]:
            raise ValueError("Database schema differs from the approved task schema")
        if db.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
            raise ValueError("Approved task requires an existing WAL database")


def is_paused(marker: Path) -> bool:
    try:
        marker.stat()
    except FileNotFoundError:
        return False
    return True


def supervise(
    marker: Path,
    start: Callable[[], int],
    record: Callable[..., None],
    *,
    poll_seconds: float = 1,
) -> int:
    """Run one collector attempt. Task Scheduler owns restart policy."""
    if is_paused(marker):
        record("paused", exit_code=0)
        return 0

    finished = Event()
    pause_seen = Event()
    monitor_failed = Event()

    def monitor() -> None:
        while not finished.wait(poll_seconds):
            try:
                paused = is_paused(marker)
            except OSError:
                monitor_failed.set()
                interrupt_main()
                return
            if paused:
                pause_seen.set()
                interrupt_main()
                return

    watcher = Thread(target=monitor, name="collector-pause", daemon=True)
    record("starting")
    watcher.start()
    try:
        try:
            exit_code = start()
        finally:
            finished.set()
            watcher.join()
    except KeyboardInterrupt:
        exit_code = 0
    except Exception as exc:  # noqa: BLE001
        record("collector_exception", error_type=type(exc).__name__, exit_code=1)
        return 1

    if monitor_failed.is_set():
        record("pause_monitor_failed", exit_code=1)
        return 1
    if exit_code == 0 and pause_seen.is_set():
        record("paused", exit_code=0)
        return 0
    if exit_code == 0:
        record("unexpected_clean_exit", exit_code=1)
        return 1
    record("collector_failed", exit_code=exit_code)
    return exit_code


def _run(db_path: Path, game: str, interval: int, lookback: int) -> int:
    if sys.platform != "win32":
        raise ValueError("The scheduled runner is intended for Windows")
    from viralclip.cli import main as collector_main

    directory = control_directory(db_path)
    directory.mkdir(parents=True, exist_ok=True)
    with closing(
        RotatingFileHandler(
            directory / "lifecycle.jsonl",
            maxBytes=512 * 1024,
            backupCount=2,
            encoding="utf-8",
        )
    ) as handler:

        def record(event: str, **fields: object) -> None:
            payload = json.dumps(
                {"timestamp": datetime.now(UTC).isoformat(), "event": event, **fields}
            )
            handler.handle(
                logging.LogRecord("viralclip.supervision", logging.INFO, "", 0, payload, (), None)
            )

        def start() -> int:
            try:
                preflight(db_path, interval, lookback)
            except (OSError, ValueError, sqlite3.Error):
                record("preflight_failed", exit_code=2)
                return 2
            return collector_main(["--db", str(db_path), "collect", "--game", game, "--loop"])

        return supervise(directory / "pause", start, record)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path, help="approved local database path")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "preflight", "run"):
        options = commands.add_parser(command)
        if command != "preflight":
            options.add_argument("--game", default=DEFAULT_GAME)
        options.add_argument("--interval", default=300, type=int, help="expected discovery seconds")
        options.add_argument("--lookback", default=30, type=int, help="expected lookback minutes")
        if command == "prepare":
            options.add_argument("--sid", required=True)
            options.add_argument("--output", required=True, type=Path)
    commands.add_parser("pause")
    commands.add_parser("resume")
    commands.add_parser("state")
    args = parser.parse_args(argv)
    try:
        db_path = args.db.resolve()
        if str(db_path).startswith("\\\\"):
            raise ValueError("Use a local database path")
        directory = control_directory(db_path)
        marker = directory / "pause"
        if args.command == "prepare":
            payload = task_xml(
                Path(sys.executable),
                Path.cwd(),
                db_path,
                args.sid,
                args.game,
                args.interval,
                args.lookback,
            )
            output = ignored_output(args.output)
            output.mkdir(parents=True, exist_ok=False)
            with (output / "collector.xml").open("xb") as stream:
                stream.write(payload)
            print("Disabled Task Scheduler XML generated. No task was registered.")
        elif args.command == "preflight":
            preflight(db_path, args.interval, args.lookback)
            print("Database, schema, credential presence and collector settings match.")
        elif args.command == "run":
            return _run(db_path, args.game, args.interval, args.lookback)
        elif args.command == "pause":
            directory.mkdir(parents=True, exist_ok=True)
            marker.touch()
            print("Persistent pause requested. Wait for the collector to exit.")
        elif args.command == "resume":
            marker.unlink(missing_ok=True)
            print("Pause cleared. No collector was launched.")
        else:
            print("Supervision is paused." if is_paused(marker) else "Supervision is unpaused.")
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"Supervision error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
