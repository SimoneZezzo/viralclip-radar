from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

TARGET_AGES_SECONDS = (600, 1800, 3600, 21600, 86400)

MIGRATIONS = (
    """
    CREATE TABLE games (
        game_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        last_resolved_at TEXT NOT NULL
    );

    CREATE TABLE clips (
        clip_id TEXT PRIMARY KEY,
        game_id TEXT NOT NULL REFERENCES games(game_id),
        broadcaster_id TEXT,
        broadcaster_name TEXT,
        creator_id TEXT,
        title TEXT,
        url TEXT,
        created_at TEXT NOT NULL,
        first_seen_at TEXT NOT NULL,
        duration_seconds REAL,
        language TEXT,
        status TEXT,
        last_seen_at TEXT NOT NULL
    );
    CREATE INDEX clips_game_created_idx ON clips(game_id, created_at);

    CREATE TABLE clip_snapshots (
        snapshot_id INTEGER PRIMARY KEY,
        clip_id TEXT NOT NULL REFERENCES clips(clip_id),
        observed_at TEXT NOT NULL,
        age_seconds REAL NOT NULL,
        view_count INTEGER NOT NULL,
        source TEXT NOT NULL CHECK (source IN ('discovery', 'scheduled')),
        target_age_seconds INTEGER,
        collection_run_id INTEGER REFERENCES collection_runs(run_id),
        UNIQUE (clip_id, observed_at, source)
    );
    CREATE INDEX snapshots_clip_observed_idx ON clip_snapshots(clip_id, observed_at);
    CREATE TRIGGER clip_snapshots_no_update
    BEFORE UPDATE ON clip_snapshots
    BEGIN
        SELECT RAISE(ABORT, 'clip snapshots are append-only');
    END;
    CREATE TRIGGER clip_snapshots_no_delete
    BEFORE DELETE ON clip_snapshots
    BEGIN
        SELECT RAISE(ABORT, 'clip snapshots are append-only');
    END;

    CREATE TABLE jobs (
        job_id INTEGER PRIMARY KEY,
        clip_id TEXT NOT NULL REFERENCES clips(clip_id),
        job_type TEXT NOT NULL DEFAULT 'view_snapshot',
        target_age_seconds INTEGER NOT NULL,
        due_at TEXT NOT NULL,
        status TEXT NOT NULL CHECK (
            status IN ('pending', 'running', 'completed', 'missed', 'failed', 'unavailable')
        ),
        attempts INTEGER NOT NULL DEFAULT 0,
        last_error TEXT,
        completed_at TEXT,
        UNIQUE (clip_id, job_type, target_age_seconds)
    );
    CREATE INDEX jobs_due_idx ON jobs(status, due_at);

    CREATE TABLE collection_runs (
        run_id INTEGER PRIMARY KEY,
        game_id TEXT NOT NULL REFERENCES games(game_id),
        window_start TEXT NOT NULL,
        window_end TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        request_count INTEGER NOT NULL DEFAULT 0,
        pages_seen INTEGER NOT NULL DEFAULT 0,
        clips_seen INTEGER NOT NULL DEFAULT 0,
        new_clips INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL,
        potentially_truncated INTEGER NOT NULL DEFAULT 0,
        error_summary TEXT
    );
    CREATE INDEX runs_finished_idx ON collection_runs(finished_at);

    CREATE TABLE discovery_checkpoints (
        game_id TEXT PRIMARY KEY REFERENCES games(game_id),
        watermark TEXT NOT NULL
    );

    CREATE TABLE operational_errors (
        error_id INTEGER PRIMARY KEY,
        occurred_at TEXT NOT NULL,
        message TEXT NOT NULL
    );
    """,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_utc_iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("stored timestamps must be timezone-aware")
    return parsed.astimezone(UTC)


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connect_path = str(self.path)
        else:
            connect_path = ":memory:"
        self.connection = sqlite3.connect(connect_path, timeout=30)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute("PRAGMA busy_timeout = 30000")
        self.migrate()

    def close(self) -> None:
        self.connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connection:
            yield self.connection

    def migrate(self) -> None:
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        current = self.connection.execute(
            "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
        ).fetchone()[0]
        for version, script in enumerate(MIGRATIONS, start=1):
            if version <= current:
                continue
            applied_at = to_utc_iso(utc_now())
            escaped_applied_at = applied_at.replace("'", "''")
            try:
                self.connection.executescript(
                    "BEGIN IMMEDIATE;\n"
                    + script
                    + "\nINSERT INTO schema_migrations(version, applied_at) "
                    + f"VALUES ({version}, '{escaped_applied_at}');\nCOMMIT;"
                )
            except sqlite3.Error:
                if self.connection.in_transaction:
                    self.connection.rollback()
                raise

    def upsert_game(self, game_id: str, name: str, resolved_at: datetime) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO games(game_id, name, last_resolved_at) VALUES (?, ?, ?)
                ON CONFLICT(game_id) DO UPDATE SET
                    name = excluded.name, last_resolved_at = excluded.last_resolved_at
                """,
                (str(game_id), name, to_utc_iso(resolved_at)),
            )

    def cached_game(self, name: str, max_age_seconds: int, now: datetime) -> sqlite3.Row | None:
        row = self.connection.execute(
            "SELECT * FROM games WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        if row and (now - parse_utc(row["last_resolved_at"])).total_seconds() < max_age_seconds:
            return row
        return None

    def record_clip(
        self, clip: dict, game_id: str, observed_at: datetime, run_id: int | None
    ) -> bool:
        clip_id = str(clip["id"])
        created_at = to_utc_iso(clip["created_at"])
        seen_at = to_utc_iso(observed_at)
        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT clip_id FROM clips WHERE clip_id = ?", (clip_id,)
            ).fetchone()
            conn.execute(
                """
                INSERT INTO clips (
                    clip_id, game_id, broadcaster_id, broadcaster_name, creator_id,
                    title, url, created_at, first_seen_at, duration_seconds, language,
                    status, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(clip_id) DO UPDATE SET
                    game_id = excluded.game_id,
                    broadcaster_id = excluded.broadcaster_id,
                    broadcaster_name = excluded.broadcaster_name,
                    creator_id = excluded.creator_id,
                    title = excluded.title,
                    url = excluded.url,
                    duration_seconds = excluded.duration_seconds,
                    language = excluded.language,
                    status = excluded.status,
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    clip_id,
                    game_id,
                    clip.get("broadcaster_id"),
                    clip.get("broadcaster_name"),
                    clip.get("creator_id"),
                    clip.get("title"),
                    clip.get("url"),
                    created_at,
                    seen_at,
                    clip.get("duration"),
                    clip.get("language"),
                    None,
                    seen_at,
                ),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO clip_snapshots
                    (clip_id, observed_at, age_seconds, view_count, source, target_age_seconds,
                     collection_run_id)
                VALUES (?, ?, ?, ?, 'discovery', NULL, ?)
                """,
                (
                    clip_id,
                    seen_at,
                    max(0.0, (observed_at - clip["created_at"]).total_seconds()),
                    int(clip["view_count"]),
                    run_id,
                ),
            )
            if not existing:
                self._create_jobs(conn, clip_id, clip["created_at"], observed_at)
            return existing is None

    @staticmethod
    def _create_jobs(
        conn: sqlite3.Connection, clip_id: str, created_at: datetime, first_seen_at: datetime
    ) -> None:
        for target_age in TARGET_AGES_SECONDS:
            due = created_at + timedelta(seconds=target_age)
            late = due <= first_seen_at
            conn.execute(
                """
                INSERT OR IGNORE INTO jobs
                    (clip_id, target_age_seconds, due_at, status, last_error, completed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    clip_id,
                    target_age,
                    to_utc_iso(due),
                    "missed" if late else "pending",
                    "clip was first discovered after its target age" if late else None,
                    to_utc_iso(first_seen_at) if late else None,
                ),
            )

    def create_run(self, game_id: str, start: datetime, end: datetime, started: datetime) -> int:
        with self.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO collection_runs
                    (game_id, window_start, window_end, started_at, status)
                VALUES (?, ?, ?, ?, 'running')
                """,
                (game_id, to_utc_iso(start), to_utc_iso(end), to_utc_iso(started)),
            )
            return int(cursor.lastrowid)

    def finish_run(
        self,
        run_id: int,
        finished: datetime,
        requests: int,
        pages: int,
        seen: int,
        new: int,
        truncated: bool = False,
        error: str | None = None,
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE collection_runs SET finished_at = ?, request_count = ?,
                    pages_seen = ?, clips_seen = ?, new_clips = ?, status = ?,
                    potentially_truncated = ?, error_summary = ?
                WHERE run_id = ?
                """,
                (
                    to_utc_iso(finished),
                    requests,
                    pages,
                    seen,
                    new,
                    "error" if error else "completed",
                    int(truncated),
                    error,
                    run_id,
                ),
            )

    def update_watermark(self, game_id: str, watermark: datetime) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO discovery_checkpoints(game_id, watermark) VALUES (?, ?)
                ON CONFLICT(game_id) DO UPDATE SET watermark = excluded.watermark
                """,
                (game_id, to_utc_iso(watermark)),
            )

    def record_error(self, occurred_at: datetime, message: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO operational_errors(occurred_at, message) VALUES (?, ?)",
                (to_utc_iso(occurred_at), message),
            )

    def due_jobs(self, now: datetime, limit: int = 1000) -> list[sqlite3.Row]:
        return list(
            self.connection.execute(
                """
                SELECT j.*, c.created_at FROM jobs j JOIN clips c USING (clip_id)
                WHERE j.status IN ('pending', 'failed') AND j.due_at <= ?
                    AND j.attempts < 3
                ORDER BY j.due_at LIMIT ?
                """,
                (to_utc_iso(now), limit),
            )
        )

    def start_jobs(self, job_ids: list[int]) -> None:
        if not job_ids:
            return
        placeholders = ",".join("?" for _ in job_ids)
        with self.transaction() as conn:
            conn.execute(
                f"UPDATE jobs SET status = 'running', attempts = attempts + 1 "
                f"WHERE job_id IN ({placeholders})",
                job_ids,
            )

    def finish_jobs(
        self, job_ids: list[int], status: str, completed_at: datetime, error: str | None = None
    ) -> None:
        if not job_ids:
            return
        placeholders = ",".join("?" for _ in job_ids)
        with self.transaction() as conn:
            conn.execute(
                f"UPDATE jobs SET status = ?, completed_at = ?, last_error = ? "
                f"WHERE job_id IN ({placeholders})",
                [status, to_utc_iso(completed_at), error, *job_ids],
            )

    def add_scheduled_snapshot(
        self, clip_id: str, observed_at: datetime, view_count: int, target_age: int | None
    ) -> None:
        row = self.connection.execute(
            "SELECT created_at FROM clips WHERE clip_id = ?", (clip_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"unknown clip ID {clip_id}")
        age = max(0.0, (observed_at - parse_utc(row["created_at"])).total_seconds())
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO clip_snapshots
                    (clip_id, observed_at, age_seconds, view_count, source, target_age_seconds)
                VALUES (?, ?, ?, ?, 'scheduled', ?)
                """,
                (clip_id, to_utc_iso(observed_at), age, view_count, target_age),
            )

    def recover_running_jobs(self) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE jobs SET status = CASE WHEN attempts < 3 THEN 'pending' ELSE 'failed' END,
                    last_error = 'recovered after collector restart'
                WHERE status = 'running'
                """
            )

    def status(self, now: datetime) -> dict:
        def table_count(table: str) -> int:
            return self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

        latest = self.connection.execute(
            """
            SELECT finished_at FROM collection_runs
            WHERE status = 'completed' AND error_summary IS NULL
            ORDER BY finished_at DESC LIMIT 1
            """
        ).fetchone()
        jobs = {
            row["status"]: row["count"]
            for row in self.connection.execute(
                "SELECT status, COUNT(*) AS count FROM jobs GROUP BY status"
            )
        }
        error = self.connection.execute(
            """
            SELECT message FROM (
                SELECT error_summary AS message, COALESCE(finished_at, started_at) AS occurred_at
                FROM collection_runs WHERE error_summary IS NOT NULL
                UNION ALL
                SELECT last_error, COALESCE(completed_at, due_at)
                FROM jobs WHERE last_error IS NOT NULL
                UNION ALL
                SELECT message, occurred_at FROM operational_errors
            )
            ORDER BY occurred_at DESC LIMIT 1
            """
        ).fetchone()
        due = self.connection.execute(
            """
            SELECT COUNT(*) FROM jobs
            WHERE status IN ('pending', 'failed') AND due_at <= ? AND attempts < 3
            """,
            (to_utc_iso(now),),
        ).fetchone()[0]
        return {
            "games": table_count("games"),
            "clips": table_count("clips"),
            "snapshots": table_count("clip_snapshots"),
            "jobs": jobs,
            "due_jobs": due,
            "latest_success": latest["finished_at"] if latest else None,
            "last_error": error[0] if error else None,
        }
