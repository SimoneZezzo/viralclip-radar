"""Bounded systemd monitor for the two live SQLite collectors."""

from __future__ import annotations

import argparse
import os
import sqlite3
import stat
import subprocess
import time
from contextlib import closing
from datetime import timedelta
from pathlib import Path

from viralclip.operations import _service_state
from viralclip.storage.database import to_utc_iso, utc_now
from viralclip.storage.discovery import BUCKET, bucket_start, history_start
from viralclip.storage.health import CRITICAL, DEGRADED, HEALTHY, _age, _discovery, _queue_alerts

UNKNOWN = 3
LEVELS = ("HEALTHY", "DEGRADED", "UNHEALTHY", "UNKNOWN")
PROFILES = {
    "viralclip": (
        "viralclip-collector.service",
        "32982",
        Path("/var/lib/viralclip-radar/viralclip.sqlite3"),
    ),
    "viralclip-gta-vi": (
        "viralclip-gta-vi.service",
        "1867279146",
        Path("/var/lib/viralclip-gta-vi/gta-vi.sqlite3"),
    ),
}
LOOKBACK = timedelta(minutes=15)
OBSERVATION_LIMIT = 16_384


def require_read_only_mount(path: Path) -> None:
    if not hasattr(os, "statvfs") or not hasattr(os, "ST_RDONLY"):
        raise OSError("read-only mount checks unavailable")
    for suffix in ("", "-wal", "-shm"):
        state = path.with_name(path.name + suffix)
        meta = state.lstat()
        if (
            not stat.S_ISREG(meta.st_mode)
            or meta.st_nlink != 1
            or state.resolve() != state
            or not os.statvfs(state).f_flag & os.ST_RDONLY
        ):
            raise ValueError("SQLite source isolation check failed")


def _storage(path: Path, alerts: list, lines: list) -> None:
    if not hasattr(os, "statvfs"):
        raise OSError("filesystem capacity checks unavailable")
    disk = os.statvfs(path.parent)
    if not disk.f_blocks or not disk.f_files:
        raise ValueError("missing filesystem capacity")
    free = disk.f_bavail / disk.f_blocks
    inodes = disk.f_favail / disk.f_files
    lines.append(f"Disk: {free:.1%} available; inodes: {inodes:.1%} available.")
    if free < 0.10 or inodes < 0.05:
        alerts.append((CRITICAL, "Disk below 10% or inodes below 5%."))
    elif free < 0.15 or inodes < 0.10:
        alerts.append((DEGRADED, "Disk below 15% or inodes below 10%."))


def _process(state: dict, alerts: list, lines: list) -> tuple[int, int] | None:
    if state["LoadState"] != "loaded":
        raise ValueError("collector unit unavailable")
    active, sub = state["ActiveState"], state["SubState"]
    pid, started = int(state["MainPID"]), int(state["ExecMainStartTimestampMonotonic"])
    restarts, boot = int(state["NRestarts"]), state["UnitFileState"]
    lines.append(
        f"Collector: {active}/{sub}, PID {pid}, start monotonic {started}us, "
        f"automatic restarts {restarts}, boot {boot}."
    )
    if active in ("inactive", "failed", "deactivating"):
        alerts.append((CRITICAL, "Collector is stopped or failed."))
        return None
    if active == "activating":
        alerts.append((DEGRADED, "Collector is starting."))
        return None
    if active != "active" or sub != "running" or pid <= 0 or started <= 0:
        raise ValueError("incomplete active process state")
    if boot != "enabled":
        alerts.append((DEGRADED, "Persistent boot enablement is not confirmed."))
    if restarts and time.monotonic() - started / 1_000_000 < LOOKBACK.total_seconds():
        alerts.append((DEGRADED, "Collector restarted recently."))
    return pid, started


def _lane_backlog(db: sqlite3.Connection, game: str, now, lines: list, alerts: list) -> None:
    previous = bucket_start(now) - BUCKET
    frontier = history_start(db, game, previous)
    waiting, retried, last_retry = db.execute(
        """
        WITH retries AS (
            SELECT r.window_start, r.window_end, MAX(r.finished_at) AS last_retry
            FROM gta_vi_scan_attempts a JOIN collection_runs r USING(run_id)
            WHERE r.game_id=? AND a.lane='retry' GROUP BY r.window_start,r.window_end
        ), incomplete AS (
            SELECT DISTINCT r.window_start,r.window_end
            FROM gta_vi_scan_attempts a JOIN collection_runs r USING(run_id)
            WHERE r.game_id=? AND a.lane='history' AND a.outcome<>'cursor_exhausted'
        )
        SELECT COUNT(*) FILTER (WHERE retries.last_retry IS NULL),
               COUNT(*) FILTER (WHERE retries.last_retry IS NOT NULL), MAX(retries.last_retry)
        FROM incomplete LEFT JOIN retries USING(window_start,window_end)
        """,
        (game, game),
    ).fetchone()
    lag = max(0, (previous - frontier).total_seconds())
    lines.append(
        f"History sweep lag: {lag:.0f}s; incomplete history windows: "
        f"{waiting} without retry, {retried} with retry; last retry {last_retry or 'none'}."
    )
    if lag:
        lines.append("History sweep takes priority over retry.")
        latest = db.execute(
            """SELECT MAX(r.finished_at) FROM gta_vi_scan_attempts a
               JOIN collection_runs r USING(run_id)
               WHERE r.game_id=? AND a.lane='history' AND r.pages_seen>0 AND a.outcome<>'error'""",
            (game,),
        ).fetchone()[0]
        if latest is None or _age(now, latest) > LOOKBACK.total_seconds():
            alerts.append((DEGRADED, "History sweep has backlog and no recent usable attempt."))


def sample_database(db: sqlite3.Connection, game: str, now, lines: list, alerts: list) -> None:
    cutoff, since = to_utc_iso(now), to_utc_iso(now - LOOKBACK)
    hour = to_utc_iso(now - timedelta(hours=1))
    schema = db.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
    if schema != 2 or [r[0] for r in db.execute("SELECT game_id FROM games")] != [game]:
        raise ValueError("unsupported schema or unexpected category")
    _discovery(db, now, hour, 300, lines, alerts)
    if game == "1867279146":
        if db.execute("SELECT 1 FROM sqlite_schema WHERE name='gta_vi_scan_attempts'").fetchone():
            _lane_backlog(db, game, now, lines, alerts)
        else:
            alerts.append((UNKNOWN, "GTA VI structural discovery ledger is unavailable."))

    overdue, oldest = db.execute(
        """SELECT COUNT(*), MIN(due_at) FROM jobs
           WHERE status IN ('pending','running','failed') AND due_at<=?""",
        (cutoff,),
    ).fetchone()
    failed, exhausted = db.execute(
        "SELECT COUNT(*), COUNT(*) FILTER (WHERE attempts>=3) FROM jobs WHERE status='failed'"
    ).fetchone()
    age = _age(now, oldest) if oldest else 0
    _queue_alerts(age, failed, exhausted, alerts)
    completed = db.execute(
        """SELECT COUNT(*) FROM jobs WHERE status='completed' AND due_at>=?
           AND due_at<=? AND completed_at BETWEEN ? AND ?""",
        (since, cutoff, since, cutoff),
    ).fetchone()[0]
    lines.append(
        f"Queue: {overdue} overdue (oldest {age:.1f}s), {failed} failed "
        f"({exhausted} exhausted); {completed} completed of jobs due in the last 15m."
    )

    total, fresh, scheduled, latest, latest_scheduled = db.execute(
        """SELECT COUNT(*), COUNT(*) FILTER (WHERE observed_at BETWEEN ? AND ?),
                  COUNT(*) FILTER (WHERE source='scheduled' AND observed_at BETWEEN ? AND ?),
                  MAX(observed_at), MAX(observed_at) FILTER (WHERE source='scheduled')
           FROM (SELECT source,observed_at FROM clip_snapshots ORDER BY snapshot_id DESC LIMIT ?)""",
        (since, cutoff, since, cutoff, OBSERVATION_LIMIT),
    ).fetchone()
    if latest:
        _age(now, latest)
    qualifier = "at least " if total == OBSERVATION_LIMIT else ""
    lines.append(
        f"Observations in last 15m: {qualifier}{fresh} ({scheduled} scheduled in tail); "
        f"latest {latest or 'none'}; latest scheduled in tail {latest_scheduled or 'none'}."
    )
    if overdue and age > 300 and not scheduled:
        alerts.append(
            (DEGRADED, "Due jobs have accumulated without recent scheduled observations.")
        )
    errors = db.execute(
        "SELECT COUNT(*) FROM operational_errors WHERE occurred_at BETWEEN ? AND ?",
        (since, cutoff),
    ).fetchone()[0]
    lines.append(f"Operational errors in last 15m: {errors}.")
    if errors >= 2:
        alerts.append((DEGRADED, "Repeated recent operational errors."))


def _read(path: Path, game: str, lines: list, alerts: list) -> None:
    require_read_only_mount(path)
    deadline = time.monotonic() + 15
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
        db.row_factory = sqlite3.Row
        db.set_progress_handler(lambda: time.monotonic() >= deadline, 10_000)
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA temp_store=MEMORY")
        db.execute("PRAGMA cache_size=-4096")
        db.execute("BEGIN")
        if db.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
            raise ValueError("expected WAL mode")
        db.execute("SELECT MAX(snapshot_id) FROM clip_snapshots").fetchone()
        evidence, observed_alerts = [], []
        sample_database(db, game, utc_now(), evidence, observed_alerts)
        lines.extend(evidence)
        alerts.extend(observed_alerts)


def monitor(unit: str, game: str, path: Path) -> tuple[int, list[str]]:
    lines, alerts = [], []
    try:
        before = _process(_service_state(unit), alerts, lines)
    except (OSError, KeyError, ValueError, subprocess.SubprocessError):
        before = None
        alerts.append((UNKNOWN, "Systemd process state unavailable."))
    try:
        _storage(path, alerts, lines)
    except (OSError, ValueError):
        alerts.append((UNKNOWN, "Filesystem capacity unavailable."))
    if before is not None:
        try:
            _read(path, game, lines, alerts)
        except (OSError, ValueError, TypeError, RuntimeError, sqlite3.Error):
            alerts.append((UNKNOWN, "SQLite snapshot, mount isolation or deadline unavailable."))
        try:
            after_alerts = []
            after = _process(_service_state(unit), after_alerts, [])
            if after != before:
                alerts.extend(after_alerts)
                alerts.append((DEGRADED, "Process changed during this sample."))
        except (OSError, KeyError, ValueError, subprocess.SubprocessError):
            alerts.append((UNKNOWN, "Process continuity could not be verified."))
    levels = {level for level, _ in alerts}
    severity = CRITICAL if CRITICAL in levels else max(levels, default=HEALTHY)
    return severity, lines + [f"{LEVELS[level]}: {message}" for level, message in alerts]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=PROFILES)
    level, lines = monitor(*PROFILES[parser.parse_args().profile])
    print(f"Collector reliability: {LEVELS[level]}", flush=True)
    for line in lines:
        print(line)
    return level


if __name__ == "__main__":
    raise SystemExit(main())
