"""Optional GTA VI scan ledger. The core schema and legacy checkpoint stay at v2."""

from datetime import datetime, timedelta
from sqlite3 import Connection

from viralclip.storage.database import to_utc_iso

BUCKET = timedelta(minutes=10)


def bucket_start(instant: datetime) -> datetime:
    return instant.replace(minute=instant.minute // 10 * 10, second=0, microsecond=0)


def ensure_scan_ledger(db: Connection) -> None:
    with db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS gta_vi_scan_attempts (
                run_id INTEGER PRIMARY KEY REFERENCES collection_runs(run_id),
                lane TEXT NOT NULL CHECK (lane IN ('recent', 'history', 'retry')),
                outcome TEXT NOT NULL CHECK (outcome IN (
                    'cursor_exhausted', 'budget', 'page_limit', 'error',
                    'pagination_anomaly', 'known_incomplete'
                )),
                pertinent INTEGER NOT NULL CHECK (pertinent >= 0),
                repeated INTEGER NOT NULL CHECK (repeated >= 0)
            )
            """
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS gta_vi_scan_lane ON gta_vi_scan_attempts(lane, run_id)"
        )


def scan_progress(db: Connection, game_id: str) -> tuple[datetime | None, datetime | None]:
    watermarks = []
    for lane in ("recent", "history"):
        end = db.execute(
            """
            SELECT MAX(r.window_end) FROM gta_vi_scan_attempts s
            JOIN collection_runs r USING (run_id)
            WHERE s.lane = ? AND r.game_id = ? AND r.request_count > 0
            """,
            (lane, game_id),
        ).fetchone()[0]
        watermarks.append(datetime.fromisoformat(end) if end else None)
    return tuple(watermarks)


def history_start(db: Connection, game_id: str, fallback: datetime) -> datetime:
    """Resume the contiguous attempt sweep. The retry lane never moves it."""
    _, frontier = scan_progress(db, game_id)
    if frontier:
        return frontier
    anchor = db.execute(
        "SELECT watermark FROM discovery_checkpoints WHERE game_id = ?", (game_id,)
    ).fetchone()
    if anchor:
        return datetime.fromisoformat(anchor[0])
    earliest = db.execute(
        "SELECT MIN(window_start) FROM collection_runs WHERE game_id = ?", (game_id,)
    ).fetchone()[0]
    return min(fallback, datetime.fromisoformat(earliest)) if earliest else fallback


def historical_retry(
    db: Connection, game_id: str, cutoff: datetime, older_than: datetime
) -> tuple[datetime, datetime] | None:
    row = db.execute(
        """
        SELECT r.window_start, r.window_end FROM gta_vi_scan_attempts s
        JOIN collection_runs r USING (run_id)
        WHERE r.game_id = ? AND s.lane = 'history' AND s.outcome <> 'cursor_exhausted'
          AND r.window_end <= ? AND r.finished_at <= ?
          AND NOT EXISTS (
              SELECT 1 FROM gta_vi_scan_attempts t JOIN collection_runs done USING (run_id)
              WHERE t.lane = 'retry' AND done.game_id = r.game_id
                AND done.window_start = r.window_start AND done.window_end = r.window_end
          )
        ORDER BY r.window_start LIMIT 1
        """,
        (game_id, to_utc_iso(cutoff), to_utc_iso(older_than)),
    ).fetchone()
    return (datetime.fromisoformat(row[0]), datetime.fromisoformat(row[1])) if row else None
