"""Create a SQLite online backup and verify a temporary restore."""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from viralclip.config import load_settings


def _reader(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)


def online_copy(source: Path, destination: Path) -> None:
    """Copy committed data through SQLite, reserving a new destination exclusively."""
    with closing(_reader(source)) as reader:
        reader.execute("PRAGMA query_only = ON")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.touch(exist_ok=False)
        deadline = time.monotonic() + 60

        def check_deadline(status: int, _remaining: int, _total: int) -> None:
            if status != sqlite3.SQLITE_DONE and time.monotonic() >= deadline:
                raise TimeoutError("Online copy did not finish within 60 seconds")

        try:
            with closing(sqlite3.connect(destination, timeout=2)) as writer:
                reader.backup(writer, pages=128, sleep=0.05, progress=check_deadline)
                if writer.execute("PRAGMA journal_mode = DELETE").fetchone()[0] != "delete":
                    raise ValueError("Could not finalize the destination as a standalone database")
        except (sqlite3.Error, OSError, ValueError):
            destination.unlink(missing_ok=True)
            raise


def validate(path: Path) -> dict[str, object]:
    with closing(_reader(path)) as reader:
        reader.execute("PRAGMA query_only = ON")
        reader.execute("BEGIN")
        if reader.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("SQLite integrity_check failed")
        if reader.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("SQLite foreign_key_check failed")
        tables = (
            "games",
            "clips",
            "clip_snapshots",
            "jobs",
            "collection_runs",
            "discovery_checkpoints",
            "operational_errors",
        )
        metrics: dict[str, object] = {
            table: reader.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables
        }
        jobs = reader.execute(
            """
            SELECT COUNT(*) FROM jobs j LEFT JOIN clip_snapshots s USING (snapshot_id)
            WHERE (j.status = 'completed' AND (
                s.snapshot_id IS NULL OR s.clip_id <> j.clip_id OR s.source <> 'scheduled'
                OR j.completed_at IS NOT s.observed_at OR s.observed_at < j.due_at
            )) OR (j.status <> 'completed' AND j.snapshot_id IS NOT NULL)
            """
        ).fetchone()[0]
        unlinked = reader.execute(
            """
            SELECT COUNT(*) FROM clip_snapshots
            WHERE source = 'scheduled' AND snapshot_id NOT IN (
                SELECT snapshot_id FROM jobs WHERE snapshot_id IS NOT NULL
            )
            """
        ).fetchone()[0]
        schedules = reader.execute(
            """
            SELECT COUNT(*) FROM clips c WHERE (
                SELECT COUNT(DISTINCT target_age_seconds) FROM jobs j
                WHERE j.clip_id = c.clip_id AND j.job_type = 'view_snapshot'
                  AND j.target_age_seconds IN (600, 1800, 3600, 21600, 86400)
            ) <> 5
            """
        ).fetchone()[0]
        if jobs or unlinked or schedules:
            raise ValueError(
                f"Invalid job links: {jobs}, unlinked snapshots: {unlinked}, "
                f"clips missing scheduled targets: {schedules}"
            )
        metrics["schema_version"] = reader.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()[0]
        metrics["job_status_counts"] = dict(
            reader.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")
        )
        metrics["linked_24h_jobs"] = reader.execute(
            "SELECT COUNT(*) FROM jobs WHERE target_age_seconds = 86400 AND status = 'completed'"
        ).fetchone()[0]
        metrics["latest_observation_utc"] = reader.execute(
            "SELECT MAX(observed_at) FROM clip_snapshots"
        ).fetchone()[0]
        metrics["latest_successful_discovery_utc"] = reader.execute(
            """
            SELECT MAX(finished_at) FROM collection_runs
            WHERE status = 'completed' AND error_summary IS NULL AND potentially_truncated = 0
            """
        ).fetchone()[0]
        return metrics


def backup_and_verify(source: Path, destination: Path) -> dict[str, object]:
    online_copy(source, destination)
    snapshot = validate(destination)
    with TemporaryDirectory(prefix="restore-check-", dir=destination.parent) as directory:
        restored = Path(directory) / "restored.sqlite3"
        online_copy(destination, restored)
        if validate(restored) != snapshot:
            raise ValueError("Restored metrics differ from the validated backup")
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="new backup file in an ignored directory")
    parser.add_argument("--source", type=Path, help="defaults to the configured collector database")
    args = parser.parse_args()
    try:
        source = args.source if args.source is not None else load_settings().db_path
        metrics = backup_and_verify(source, args.destination)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f"Backup verification failed: {exc}\n")
    print(json.dumps(metrics, indent=2))
    print("Backup and temporary restore passed integrity, foreign-key and relationship checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
