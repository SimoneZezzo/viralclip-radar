"""Scheduled, verified backups and read-only collector monitoring."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from viralclip.deployment import BackupIdentityError, snapshot_manifest, verify_snapshot
from viralclip.storage.backup import backup_and_verify
from viralclip.storage.database import parse_utc
from viralclip.storage.health import CRITICAL, DEGRADED, LEVELS, read_health

DB_NAME = "viralclip.sqlite3"
MANIFEST = "manifest.json"
COLLECTOR = "viralclip-collector.service"
BACKUP = "viralclip-backup.service"
TAG = "viralclip-sqlite"
HOST = "viralclip-ovh"
STAMP = re.compile(r"[0-9]{8}T[0-9]{6}\.[0-9]{6}Z")
GIB = 1024**3


def _atomic_json(path: Path, contents: dict) -> None:
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temp = Path(stream.name)
        try:
            json.dump(contents, stream, indent=2, sort_keys=True)
        except BaseException:
            stream.close()
            temp.unlink(missing_ok=True)
            raise
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def reserve_bytes(database_bytes: int, capacity: int) -> int:
    # The backup helper stages the snapshot and one temporary restore.
    return max(capacity // 5, 2 * database_bytes + GIB)


def _file_bytes(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def _source_bytes(database: Path) -> int:
    return database.stat().st_size + _file_bytes(database.with_name(database.name + "-wal"))


def verify_mounts(database: Path, root: Path, *, writable_backup: bool) -> None:
    """Check the paths inside the service's mount namespace."""
    for suffix in ("", "-wal", "-shm"):
        path = database.with_name(database.name + suffix)
        if path.exists() and not os.statvfs(path).f_flag & os.ST_RDONLY:
            raise RuntimeError("SQLite source or sidecar mount is writable")
    if bool(os.statvfs(root).f_flag & os.ST_RDONLY) == writable_backup:
        raise RuntimeError("Backup directory mount has unexpected write permissions")
    with closing(
        sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
    ) as db:
        db.execute("PRAGMA query_only = ON")
        if db.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
            raise RuntimeError("Live database was not readable in WAL mode")
        db.execute("SELECT MAX(snapshot_id) FROM clip_snapshots").fetchone()
    if writable_backup:
        with NamedTemporaryFile(dir=root, prefix=".permission-probe-") as probe:
            probe.write(b"ok")
            probe.flush()
    print("Isolation probe passed: read-only WAL and expected backup directory access.")


def _http_rates(database: Path, now: datetime) -> str:
    log = database.with_name(database.name + ".http.jsonl")
    requests = failures = throttled = 0
    cutoff = now - timedelta(hours=1)
    for suffix in ("", ".1", ".2", ".3"):
        try:
            with log.with_name(log.name + suffix).open(encoding="utf-8") as stream:
                for line in stream:
                    try:
                        event = json.loads(line)
                        if event.get("event") != "http_request" or not (
                            cutoff <= parse_utc(event["timestamp"]) <= now
                        ):
                            continue
                        status = event.get("status")
                        requests += 1
                        failures += status is None or (isinstance(status, int) and status >= 400)
                        throttled += status == 429
                    except (AttributeError, KeyError, TypeError, ValueError):
                        continue
        except OSError:
            continue
    if not requests:
        return "No HTTP request events available in retained logs for the last hour."
    return (
        f"HTTP retained last hour: {requests} attempts, {failures} failures "
        f"({failures / requests:.1%}), {throttled} HTTP 429."
    )


def _retention(name: str, default: int) -> int:
    value = int(os.environ.get(name, default))
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


def _https_url(value: str) -> bool:
    parts = urlsplit(value)
    return bool(
        parts.scheme == "https"
        and parts.hostname
        and not (parts.username or parts.password or parts.query or parts.fragment)
    )


def _credentials_dir() -> Path:
    directory = os.environ.get("CREDENTIALS_DIRECTORY")
    if not directory:
        raise ValueError("No systemd credentials directory supplied")
    return Path(directory)


def _restic_environment() -> dict[str, str]:
    repo = os.environ.get("RESTIC_REPOSITORY", "")
    if (
        not repo.startswith("s3:")
        or not _https_url(repo[3:])
        or not urlsplit(repo[3:]).path.strip("/")
    ):
        raise ValueError("RESTIC_REPOSITORY must identify a private S3 repository over HTTPS")
    credentials = _credentials_dir()
    values = {
        key: (credentials / filename).read_text(encoding="utf-8").strip()
        for key, filename in (
            ("AWS_ACCESS_KEY_ID", "s3-access-key"),
            ("AWS_SECRET_ACCESS_KEY", "s3-secret-key"),
        )
    }
    password = credentials / "restic-password"
    if not all(values.values()) or not password.read_bytes().strip():
        raise ValueError("Empty backup credential")
    return {
        **values,
        "RESTIC_REPOSITORY": repo,
        "RESTIC_PASSWORD_FILE": str(password),
        "AWS_DEFAULT_REGION": os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    }


def _restic(args: list[str], *, cwd: Path | None = None) -> None:
    result = subprocess.run(
        ["/usr/bin/restic", "--no-cache", *args],
        cwd=cwd,
        env=_restic_environment(),
        capture_output=True,
        check=False,
        timeout=3600,
    )
    if result.returncode != 0:
        # Raw subprocess output can include repository URLs and credentials.
        raise RuntimeError(f"restic {args[0]} failed with exit code {result.returncode}")


def _local_retention(root: Path, keep: int) -> None:
    bundles = sorted(
        (
            item
            for item in root.iterdir()
            if STAMP.fullmatch(item.name) and item.is_dir() and not item.is_symlink()
        ),
        reverse=True,
    )
    for bundle in bundles[keep:]:
        files = list(bundle.iterdir())
        if {p.name for p in files} == {DB_NAME, MANIFEST} and all(
            p.is_file() and not p.is_symlink() for p in files
        ):
            for path in files:
                path.unlink()
            bundle.rmdir()


def run_backup(
    database: Path,
    root: Path,
    now: datetime,
    *,
    expected_game_id: str,
    restic: Callable[..., None] = _restic,
) -> None:
    if not expected_game_id or expected_game_id != expected_game_id.strip():
        raise BackupIdentityError("A nonempty expected game ID is required")
    local = _retention("VIRALCLIP_LOCAL_KEEP", 2)
    daily = _retention("VIRALCLIP_REMOTE_DAILY", 7)
    weekly = _retention("VIRALCLIP_REMOTE_WEEKLY", 4)
    root.mkdir(parents=True, exist_ok=True)
    capacity, _, free = shutil.disk_usage(root)
    if free < reserve_bytes(_source_bytes(database), capacity):
        raise RuntimeError("Insufficient free space for a backup and restore verification")
    bundle = root / now.astimezone(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    if bundle.exists():
        raise ValueError("Backup bundle already exists")
    with TemporaryDirectory(prefix=".incoming-", dir=root) as directory:
        staged = Path(directory) / "verified"
        staged.mkdir()
        backup_and_verify(database, staged / DB_NAME)
        manifest = snapshot_manifest(staged / DB_NAME, expected_game_id=expected_game_id)
        _atomic_json(staged / MANIFEST, manifest)
        staged.rename(bundle)
    status = {"timestamp": now.astimezone(UTC).isoformat(), "bundle": bundle.name}
    _atomic_json(root / "latest-local.json", status)
    print(f"Local backup verified: {bundle.name}", flush=True)
    restic(["backup", "--host", HOST, "--tag", TAG, DB_NAME, MANIFEST], cwd=bundle)
    _atomic_json(root / "latest-offsite.json", status)
    print(f"Encrypted off-server upload completed: {bundle.name}", flush=True)
    restic(
        [
            "forget",
            "--host",
            HOST,
            "--tag",
            TAG,
            "--group-by",
            "host,tags",
            "--keep-daily",
            str(daily),
            "--keep-weekly",
            str(weekly),
            "--prune",
        ]
    )
    _local_retention(root, local)


def restore_latest(
    output: Path, *, expected_game_id: str, restic: Callable[..., None] = _restic
) -> None:
    if not expected_game_id or expected_game_id != expected_game_id.strip():
        raise BackupIdentityError("A nonempty expected game ID is required")
    output.mkdir(parents=True, exist_ok=False)
    restic(["restore", "latest", "--host", HOST, "--tag", TAG, "--target", str(output.resolve())])
    manifests = list(output.rglob(MANIFEST))
    if len(manifests) != 1:
        raise ValueError("Expected one restored SQLite manifest")
    database = manifests[0].with_name(DB_NAME)
    verify_snapshot(database, manifests[0], expected_game_id=expected_game_id)
    rehearsal = output / "rehearsal.sqlite3"
    backup_and_verify(database, rehearsal)
    print(f"Verified restored snapshot: {database}")
    print(f"Verified rehearsal copy: {rehearsal}")


def _service_state(name: str) -> dict[str, str]:
    result = subprocess.run(
        [
            "systemctl",
            "show",
            name,
            "-p",
            "LoadState",
            "-p",
            "ActiveState",
            "-p",
            "SubState",
            "-p",
            "MainPID",
            "-p",
            "NRestarts",
            "-p",
            "ExecMainStartTimestampMonotonic",
            "-p",
            "UnitFileState",
            "-p",
            "Result",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def monitor(
    database: Path,
    root: Path,
    now: datetime,
    *,
    collector_unit: str = COLLECTOR,
    backup_unit: str = BACKUP,
    service: Callable[[str], dict[str, str]] = _service_state,
) -> tuple[int, list[str]]:
    severity, lines = read_health(database, 300)
    lines.append(_http_rates(database, now))
    try:
        collector = service(collector_unit)
        backup = service(backup_unit)
        if (
            collector.get("ActiveState") != "active"
            or collector.get("SubState") != "running"
            or int(collector.get("MainPID", 0)) <= 0
        ):
            severity = CRITICAL
            lines.append("Collector service is not running.")
        if backup.get("ActiveState") == "failed" or backup.get("Result", "success") != "success":
            severity = max(severity, DEGRADED)
            lines.append("The last backup service attempt failed.")
    except (OSError, ValueError, subprocess.SubprocessError):
        severity = CRITICAL
        lines.append("Could not read systemd status.")

    try:
        capacity, _, free = shutil.disk_usage(database.parent)
        database_bytes = _source_bytes(database)
    except OSError:
        severity = CRITICAL
        lines.append("Could not measure collector database storage.")
    else:
        reserve = reserve_bytes(database_bytes, capacity)
        lines.append(
            f"Storage: {free} bytes free of {capacity}; SQLite plus WAL: {database_bytes} bytes."
        )
        if free < capacity // 10:
            severity = CRITICAL
            lines.append("Free disk is below 10%.")
        elif free < reserve:
            severity = max(severity, DEGRADED)
            lines.append(f"Free disk is below the backup reserve ({reserve} bytes).")

    for kind in ("local", "offsite"):
        try:
            marker = json.loads((root / f"latest-{kind}.json").read_text(encoding="utf-8"))
            age = now - parse_utc(marker["timestamp"])
            name = marker["bundle"]
            if age < timedelta(0) or not STAMP.fullmatch(name):
                raise ValueError("Invalid backup marker")
            if kind == "local" and not all(
                (root / name / filename).is_file() for filename in (DB_NAME, MANIFEST)
            ):
                raise ValueError("Local backup files are missing")
        except (OSError, ValueError, TypeError, KeyError):
            severity = CRITICAL
            lines.append(f"No valid {kind} backup success marker.")
        else:
            lines.append(f"Last {kind} backup: {marker['timestamp']}.")
            if age > timedelta(hours=48):
                severity = CRITICAL
            elif age > timedelta(hours=30):
                severity = max(severity, DEGRADED)
            if age > timedelta(hours=30):
                lines.append(f"The {kind} backup is stale.")
    return severity, lines


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _heartbeat(severity: int) -> None:
    url = (_credentials_dir() / "alert-url").read_text(encoding="utf-8").strip()
    if not url:
        return
    if not _https_url(url):
        raise ValueError("Alert URL must use HTTPS and have no embedded credentials or query")
    endpoint = url if severity == 0 else url.rstrip("/") + "/fail"
    request = Request(endpoint, data=LEVELS[severity].encode("ascii"), method="POST")
    with build_opener(_NoRedirect()).open(request, timeout=10):
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("backup", "monitor", "probe"):
        options = commands.add_parser(command)
        options.add_argument("--database", type=Path, required=True)
        options.add_argument("--backup-dir", type=Path, required=True)
        if command == "probe":
            options.add_argument("--writable-backup", action="store_true")
        if command == "backup":
            options.add_argument("--expected-game-id", required=True)
        if command == "monitor":
            options.add_argument("--collector-unit", default=COLLECTOR)
            options.add_argument("--backup-unit", default=BACKUP)
    commands.add_parser("init-remote")
    commands.add_parser("check-remote")
    restore = commands.add_parser("restore-latest")
    restore.add_argument("output", type=Path)
    restore.add_argument("--expected-game-id", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            run_backup(
                args.database,
                args.backup_dir,
                datetime.now(UTC),
                expected_game_id=args.expected_game_id,
            )
        elif args.command == "probe":
            verify_mounts(args.database, args.backup_dir, writable_backup=args.writable_backup)
        elif args.command == "monitor":
            severity, lines = monitor(
                args.database,
                args.backup_dir,
                datetime.now(UTC),
                collector_unit=args.collector_unit,
                backup_unit=args.backup_unit,
            )
            print(f"Operations health: {LEVELS[severity]}")
            print("\n".join(lines))
            try:
                _heartbeat(severity)
            except (OSError, ValueError):
                print("External heartbeat delivery failed.", file=sys.stderr)
                return CRITICAL
            return severity
        elif args.command == "init-remote":
            _restic(["init"])
            print("Encrypted off-server repository initialized.")
        elif args.command == "check-remote":
            _restic(["check"])
            print("Off-server repository check passed.")
        else:
            restore_latest(args.output, expected_game_id=args.expected_game_id)
    except (OSError, ValueError, RuntimeError, sqlite3.Error, subprocess.SubprocessError) as exc:
        # Don't render generic exception messages, which may contain private paths or URLs.
        detail = (
            str(exc) if type(exc) in (RuntimeError, BackupIdentityError) else type(exc).__name__
        )
        print(f"Operations command failed: {detail}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
