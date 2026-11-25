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


class BackupIdentityError(ValueError):
    """The backed-up category could not be verified against the approved ID."""


def _open_read_only(database: Path) -> sqlite3.Connection:
    return sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)


def _check_schema(reader: sqlite3.Connection) -> None:
    history = reader.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    if len(MIGRATIONS) != SCHEMA_VERSION or history != [(1,), (2,)]:
        raise ValueError("Database and checkout must both match approved schema v2")


def preflight(database: Path, game_id: str | None = None) -> None:
    """Decline startup if the migrated DB or approved service settings are absent.

    Without `game_id` this checks the GTA V collector. With it, a catalog collector must
    configure exactly that category, keep the GTA V cadence and hold no other game.
    """
    settings = load_settings()
    if not database.is_file() or database.resolve() != settings.db_path.resolve():
        raise ValueError("The approved database is missing or differs from VIRALCLIP_DB_PATH")
    if not settings.has_twitch_credentials:
        raise ValueError("Twitch credential fields are missing")
    expected_ids = (game_id,) if game_id else ()
    if game_id is not None and not game_id.isdigit():
        raise ValueError("A catalog game ID must be numeric")
    # The collector also reads VIRALCLIP_GAMES by name, so a catalog service must leave it empty.
    if (
        (game_id is not None and settings.games)
        or settings.game_ids != expected_ids
        or (
            settings.discovery_interval_seconds,
            settings.discovery_lookback_minutes,
        )
        != (300, 30)
    ):
        raise ValueError("Category IDs, cadence, or lookback differ from the approved setup")
    with closing(_open_read_only(database)) as reader:
        reader.execute("PRAGMA query_only = ON")
        _check_schema(reader)
        if game_id is not None:
            games = {row[0] for row in reader.execute("SELECT game_id FROM games")}
            if games - {game_id}:
                raise ValueError("The catalog database holds another game")
        # The transferred backup uses DELETE; the collector enables WAL on startup.
        if reader.execute("PRAGMA journal_mode").fetchone()[0] not in ("delete", "wal"):
            raise ValueError("Expected a standalone transfer or a WAL collector database")
        reader.execute("SELECT snapshot_id FROM jobs LIMIT 1").fetchone()


def _check_game_identity(reader: sqlite3.Connection, expected_game_id: str) -> None:
    if not expected_game_id or expected_game_id != expected_game_id.strip():
        raise BackupIdentityError("A nonempty expected game ID is required")
    games = reader.execute("SELECT game_id FROM games LIMIT 2").fetchall()
    if len(games) != 1:
        raise BackupIdentityError("Backup database must contain exactly one game ID")
    if games[0][0] != expected_game_id:
        raise BackupIdentityError("Backup database does not contain the expected game ID")
    for table in ("clips", "collection_runs", "discovery_checkpoints"):
        if reader.execute(
            f"SELECT 1 FROM {table} WHERE game_id IS NOT ? LIMIT 1", (expected_game_id,)
        ).fetchone():
            raise BackupIdentityError(
                "Backup database contains category records outside the expected game ID"
            )
    has_evidence = reader.execute(
        """
        SELECT EXISTS (SELECT 1 FROM clips) OR EXISTS (
            SELECT 1 FROM collection_runs WHERE status = 'completed' AND finished_at IS NOT NULL
            AND potentially_truncated = 0 AND error_summary IS NULL AND pages_seen > 0
        )
        """
    ).fetchone()[0]
    if not has_evidence:
        raise BackupIdentityError(
            "Backup database has no clips or successful discovery to verify its game ID"
        )


def snapshot_manifest(database: Path, *, expected_game_id: str | None = None) -> dict[str, object]:
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
        if expected_game_id is not None:
            _check_game_identity(reader, expected_game_id)
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
    manifest: dict[str, object] = {
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
    if expected_game_id is not None:
        manifest.update(manifest_version=2, game_id=expected_game_id)
    return manifest


def _unique_manifest_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise ValueError("Backup manifest contains duplicate keys")
    return fields


def verify_snapshot(
    database: Path, manifest_path: Path, *, expected_game_id: str | None = None
) -> None:
    expected = json.loads(
        manifest_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_manifest_fields
    )
    version = expected.get("manifest_version") if isinstance(expected, dict) else None
    if type(version) is not int or version not in (1, 2):
        raise ValueError("Unknown or missing backup manifest version")
    if version == 2 and (not expected_game_id or expected.get("game_id") != expected_game_id):
        raise BackupIdentityError(
            "Backup manifest game ID must match an independently supplied expected game ID"
        )

    actual = snapshot_manifest(database, expected_game_id=expected_game_id)
    if version == 1 and expected_game_id is not None:
        # Legacy bundles carry their identity in SQLite. Keep the original manifest contract.
        actual["manifest_version"] = 1
        del actual["game_id"]
    if json.dumps(actual, sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError(
            "Transfer SHA-256, size, or database metrics differ from the source manifest"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("preflight", "manifest", "verify"):
        command = commands.add_parser(name)
        command.add_argument("database", type=Path)
        if name == "preflight":
            command.add_argument("--game-id", help="catalog collector category ID")
        if name in ("manifest", "verify"):
            command.add_argument("--expected-game-id", help="approved category ID for this backup")
        if name == "verify":
            command.add_argument("expected_manifest", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "preflight":
            preflight(args.database, args.game_id)
            print("Collector settings and existing database passed read-only preflight.")
        elif args.command == "manifest":
            manifest = snapshot_manifest(args.database, expected_game_id=args.expected_game_id)
            print(json.dumps(manifest, indent=2, sort_keys=True))
        else:
            verify_snapshot(
                args.database, args.expected_manifest, expected_game_id=args.expected_game_id
            )
            print(
                "Transfer matches the source manifest and passes integrity and relationship checks."
            )
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f"Deployment check failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
