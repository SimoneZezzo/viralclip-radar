"""Read-only service preflight and standalone SQLite transfer verification."""

from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from hashlib import file_digest
from pathlib import Path

from viralclip.config import load_settings
from viralclip.storage.backup import validate
from viralclip.storage.database import MIGRATIONS

SCHEMA_VERSION = 2


def _open_read_only(database: Path) -> sqlite3.Connection:
    return sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)


def _check_schema(reader: sqlite3.Connection) -> None:
    history = reader.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    if len(MIGRATIONS) != SCHEMA_VERSION or history != [(1,), (2,)]:
        raise ValueError("Database and checkout must both match approved schema v2")


def preflight(database: Path) -> None:
    """Decline startup if the migrated DB or approved service settings are absent."""
    settings = load_settings()
    if not database.is_file() or database.resolve() != settings.db_path.resolve():
        raise ValueError("The approved database is missing or differs from VIRALCLIP_DB_PATH")
    if not settings.has_twitch_credentials:
        raise ValueError("Twitch credential fields are missing")
    if settings.game_ids or (
        settings.discovery_interval_seconds,
        settings.discovery_lookback_minutes,
    ) != (300, 30):
        raise ValueError("Category IDs, cadence, or lookback differ from the approved GTA V setup")
    with closing(_open_read_only(database)) as reader:
        reader.execute("PRAGMA query_only = ON")
        _check_schema(reader)
        # The transferred backup uses DELETE; the collector enables WAL on startup.
        if reader.execute("PRAGMA journal_mode").fetchone()[0] not in ("delete", "wal"):
            raise ValueError("Expected a standalone transfer or a WAL collector database")
        reader.execute("SELECT snapshot_id FROM jobs LIMIT 1").fetchone()


def snapshot_manifest(database: Path) -> dict[str, object]:
    database = database.resolve()
    if any(
        database.with_name(database.name + suffix).exists()
        for suffix in ("-wal", "-shm", "-journal")
    ):
        raise ValueError("Use a standalone SQLite online backup with no sidecars")
    with closing(_open_read_only(database)) as reader:
        reader.execute("PRAGMA query_only = ON")
        reader.execute("BEGIN")
        if reader.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
            raise ValueError("Use a standalone SQLite online backup in DELETE journal mode")
        _check_schema(reader)
        outstanding = reader.execute(
            """
            SELECT status, target_age_seconds, COUNT(*), MIN(due_at), MAX(due_at)
            FROM jobs WHERE status IN ('pending', 'running', 'failed')
            GROUP BY status, target_age_seconds ORDER BY status, target_age_seconds
            """
        ).fetchall()
    metrics = validate(database)
    with database.open("rb") as stream:
        digest = file_digest(stream, "sha256").hexdigest()
    return {
        "manifest_version": 1,
        "sha256": digest,
        "bytes": database.stat().st_size,
        "metrics": metrics,
        "outstanding_jobs": [
            {
                "status": state,
                "target_age_seconds": target,
                "count": count,
                "earliest_due_at": earliest,
                "latest_due_at": latest,
            }
            for state, target, count, earliest, latest in outstanding
        ],
    }


def verify_snapshot(database: Path, manifest_path: Path) -> None:
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))
    if snapshot_manifest(database) != expected:
        raise ValueError(
            "Transfer SHA-256, size, or database metrics differ from the source manifest"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("preflight", "manifest", "verify"):
        command = commands.add_parser(name)
        command.add_argument("database", type=Path)
        if name == "verify":
            command.add_argument("expected_manifest", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "preflight":
            preflight(args.database)
            print("Collector settings and existing database passed read-only preflight.")
        elif args.command == "manifest":
            print(json.dumps(snapshot_manifest(args.database), indent=2, sort_keys=True))
        else:
            verify_snapshot(args.database, args.expected_manifest)
            print(
                "Transfer matches the source manifest and passes integrity and relationship checks."
            )
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f"Deployment check failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
