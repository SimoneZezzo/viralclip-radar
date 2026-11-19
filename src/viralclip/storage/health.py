"""Read-only operational metrics from a consistent SQLite snapshot."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timedelta
from math import ceil
from pathlib import Path
from statistics import median

from viralclip.storage.database import TARGET_AGES_SECONDS, parse_utc, to_utc_iso, utc_now

HEALTHY, DEGRADED, CRITICAL = range(3)
LEVELS = ("HEALTHY", "DEGRADED", "CRITICAL")
RECENT = timedelta(hours=1)
EARLY_TARGETS = TARGET_AGES_SECONDS[:3]


def _age(now: datetime, timestamp: str) -> float:
    seconds = (now - parse_utc(timestamp)).total_seconds()
    if seconds < 0:
        raise ValueError("future timestamp")
    return seconds


def _discovery(
    db: sqlite3.Connection,
    now: datetime,
    since: str,
    interval_seconds: int,
    lines: list[str],
    alerts: list[tuple[int, str]],
) -> None:
    last_success = db.execute(
        """
        SELECT MAX(finished_at) FROM collection_runs
        WHERE status = 'completed' AND potentially_truncated = 0 AND error_summary IS NULL
        """
    ).fetchone()[0]
    label = f"{last_success} ({_age(now, last_success):.1f}s ago)" if last_success else "never"
    lines.append(f"Last successful discovery: {label}")
    categories = db.execute(
        """
        SELECT g.game_id, c.watermark,
               MAX(CASE WHEN r.status = 'completed' AND r.potentially_truncated = 0
                         AND r.error_summary IS NULL THEN r.finished_at END) AS last_success,
               COUNT(*) FILTER (WHERE r.finished_at >= ? AND r.status = 'completed'
                         AND r.potentially_truncated = 0 AND r.error_summary IS NULL) AS complete,
               COUNT(*) FILTER (WHERE r.finished_at >= ? AND r.status = 'partial') AS partial,
               COUNT(*) FILTER (WHERE r.finished_at >= ? AND r.status = 'error') AS errors,
               COUNT(*) FILTER (WHERE r.status = 'running') AS running,
               COUNT(*) FILTER (WHERE r.finished_at >= ? AND r.potentially_truncated = 1)
                   AS truncated,
               COUNT(*) FILTER (WHERE r.finished_at >= ?
                         AND (r.status IN ('partial', 'error') OR r.potentially_truncated = 1)
                         AND (c.watermark IS NULL OR r.window_end > c.watermark)) AS unresolved
        FROM games g
        LEFT JOIN discovery_checkpoints c USING (game_id)
        LEFT JOIN collection_runs r USING (game_id)
        GROUP BY g.game_id
        ORDER BY g.game_id
        """,
        (since,) * 5,
    ).fetchall()
    if not categories:
        alerts.append((DEGRADED, "No discovery categories recorded yet."))
    for row in categories:
        game = f"Category {row['game_id']!r}"
        success = row["last_success"]
        watermark = row["watermark"]
        success_age = _age(now, success) if success else None
        watermark_age = _age(now, watermark) if watermark else None
        lines.append(
            f"{game}: last success {success or 'never'}, checkpoint {watermark or 'none'}; "
            f"last hour: {row['complete']} complete, {row['partial']} partial, "
            f"{row['truncated']} flagged truncated, {row['errors']} errors, "
            f"{row['unresolved']} incomplete beyond checkpoint; {row['running']} running"
        )
        if success_age is None or watermark_age is None:
            alerts.append((DEGRADED, f"{game} has no successful discovery or checkpoint yet."))
        known_ages = [age for age in (success_age, watermark_age) if age is not None]
        oldest = max(known_ages, default=0)
        if oldest > max(1800, 6 * interval_seconds):
            alerts.append((CRITICAL, f"{game} discovery or checkpoint is critically stale."))
        elif oldest > max(600, 2 * interval_seconds):
            alerts.append((DEGRADED, f"{game} discovery or checkpoint is stale."))
        if row["unresolved"] or row["errors"]:
            alerts.append((DEGRADED, f"{game} has recent unresolved discovery or run errors."))
    lines.append("Completed windows describe API searches, not exhaustive clip coverage.")


def _jobs(
    db: sqlite3.Connection,
    now: datetime,
    cutoff: str,
    lines: list[str],
    alerts: list[tuple[int, str]],
) -> None:
    rows = db.execute(
        """
        SELECT status, COUNT(*) AS total,
               COUNT(*) FILTER (WHERE due_at <= ? AND status IN ('pending','running','failed'))
                   AS overdue,
               MIN(CASE WHEN due_at <= ? AND status IN ('pending','running','failed')
                   THEN due_at END) AS oldest_due,
               COUNT(*) FILTER (WHERE status = 'failed' AND attempts >= 3) AS exhausted,
               COUNT(*) FILTER (WHERE julianday(due_at) IS NULL) AS invalid_due
        FROM jobs GROUP BY status
        """,
        (cutoff, cutoff),
    ).fetchall()
    totals = {row["status"]: row["total"] for row in rows}
    overdue = sum(row["overdue"] for row in rows)
    exhausted = sum(row["exhausted"] for row in rows)
    oldest_age = max((_age(now, row["oldest_due"]) for row in rows if row["oldest_due"]), default=0)
    failed = totals.get("failed", 0)
    lines.append(
        f"Jobs: {totals.get('pending', 0)} pending, {totals.get('running', 0)} running, "
        f"{totals.get('completed', 0)} completed"
    )
    lines.append(
        f"Overdue jobs: {overdue} (pending/running/failed); maximum overdue age: {oldest_age:.1f}s"
    )
    lines.append(
        f"Missed at discovery: {totals.get('missed', 0)}; "
        f"unavailable in refresh: {totals.get('unavailable', 0)}; "
        f"execution failures: {failed} ({exhausted} exhausted)"
    )
    if any(row["invalid_due"] for row in rows):
        raise ValueError("invalid job due time")
    if oldest_age > 900 or exhausted:
        alerts.append((CRITICAL, "Job overdue over 15m or retry attempts exhausted."))
    elif oldest_age > 300 or failed:
        alerts.append((DEGRADED, "Job overdue over 5m or execution failure awaiting retry."))


def _observations(
    db: sqlite3.Connection,
    now: datetime,
    since: str,
    cutoff: str,
    lines: list[str],
    alerts: list[tuple[int, str]],
) -> None:
    lateness: dict[int, list[float]] = defaultdict(list)
    for row in db.execute(
        """
        SELECT j.target_age_seconds, j.due_at, j.completed_at, s.observed_at,
               (s.clip_id = j.clip_id AND s.source = 'scheduled') AS valid_link
        FROM jobs j LEFT JOIN clip_snapshots s USING (snapshot_id)
        WHERE j.status = 'completed'
          AND (j.completed_at >= ? OR julianday(j.completed_at) IS NULL)
        """,
        (since,),
    ):
        observed = row["observed_at"]
        if not row["valid_link"] or observed != row["completed_at"]:
            raise ValueError("invalid snapshot linkage")
        delay = (parse_utc(observed) - parse_utc(row["due_at"])).total_seconds()
        if delay < 0 or _age(now, observed) > RECENT.total_seconds():
            raise ValueError("invalid scheduled observation time")
        lateness[row["target_age_seconds"]].append(delay)

    lines.append("Scheduled observation lateness (jobs completed in the last hour):")
    for target in TARGET_AGES_SECONDS:
        samples = sorted(lateness[target])
        if not samples:
            lines.append(f"  {target // 60}m: no samples")
            continue
        p95 = samples[ceil(0.95 * len(samples)) - 1]
        lines.append(
            f"  {target // 60}m: n={len(samples)}, median={median(samples):.1f}s, P95={p95:.1f}s"
        )
        if p95 > 300:
            alerts.append((DEGRADED, f"{target // 60}m target P95 lateness exceeds 5m."))

    lines.append("Early coverage (all due jobs, actual observations by strict target age):")
    coverage = db.execute(
        """
        SELECT j.target_age_seconds, COUNT(*) AS total,
               SUM(EXISTS (
                   SELECT 1 FROM clip_snapshots s
                   WHERE s.clip_id = j.clip_id AND s.observed_at BETWEEN c.created_at AND j.due_at
               )) AS covered,
               SUM(j.status = 'missed') AS missed,
               SUM(j.status = 'unavailable') AS unavailable
        FROM jobs j JOIN clips c USING (clip_id)
        WHERE j.target_age_seconds IN (?, ?, ?) AND j.due_at <= ?
        GROUP BY j.target_age_seconds
        """,
        (*EARLY_TARGETS, cutoff),
    )
    by_target = {row["target_age_seconds"]: row for row in coverage}
    for target in EARLY_TARGETS:
        row = by_target.get(target)
        if row is None:
            lines.append(f"  {target // 60}m: no due jobs")
            continue
        total, covered = row["total"], row["covered"]
        lines.append(
            f"  {target // 60}m: {covered}/{total} observed ({covered / total:.1%}), "
            f"{total - covered} missing; scheduled job outcomes: "
            f"{row['missed']} missed at discovery, {row['unavailable']} unavailable"
        )


def read_health(
    path: Path, interval_seconds: int, *, now: datetime | None = None
) -> tuple[int, list[str]]:
    """Return the severity and report lines without opening the collector's writer."""
    try:
        uri = path.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=2)
    except (OSError, RuntimeError, ValueError, sqlite3.Error):
        return CRITICAL, ["Cannot open the database read-only. Check the path and permissions."]

    lines = []
    alerts: list[tuple[int, str]] = []
    try:
        with closing(connection) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only = ON")
            db.execute("BEGIN")
            counts = db.execute(
                "SELECT (SELECT COUNT(*) FROM clips), (SELECT COUNT(*) FROM clip_snapshots)"
            ).fetchone()
            # Sample the clock after the first SELECT pins the WAL snapshot.
            now = utc_now() if now is None else now
            cutoff = to_utc_iso(now)
            since = to_utc_iso(now - RECENT)
            lines.append(f"Checked at {cutoff} (UTC)")
            lines.append(f"Total clips: {counts[0]}; total observations: {counts[1]}")
            _discovery(db, now, since, interval_seconds, lines, alerts)
            _jobs(db, now, cutoff, lines, alerts)
            _observations(db, now, since, cutoff, lines, alerts)
            count = db.execute(
                "SELECT COUNT(*) FROM operational_errors WHERE occurred_at >= ?", (since,)
            ).fetchone()[0]
            lines.append(f"Operational errors recorded in the last hour: {count}")
            if count:
                alerts.append((DEGRADED, "Recent operational errors recorded."))
                for error in db.execute(
                    """
                    SELECT error_id, occurred_at,
                           CASE
                               WHEN lower(message) LIKE '%oauth%'
                                 OR lower(message) LIKE '%token validation%'
                                   THEN 'authentication'
                               WHEN lower(message) LIKE '%rate limit%' OR message LIKE '%HTTP 429%'
                                   THEN 'rate limit'
                               WHEN lower(message) LIKE '%network%' THEN 'network'
                               WHEN message LIKE '%HTTP %' THEN 'HTTP request'
                               ELSE 'unclassified'
                           END AS category
                    FROM operational_errors WHERE occurred_at >= ?
                    ORDER BY occurred_at DESC, error_id DESC LIMIT 5
                    """,
                    (since,),
                ):
                    timestamp = to_utc_iso(parse_utc(error["occurred_at"]))
                    lines.append(
                        f"  Error #{error['error_id']} at {timestamp} ({error['category']})"
                    )
    except sqlite3.Error:
        message = (
            "Cannot read collector health. The database may be busy, invalid, "
            "uninitialized, or missing the current collector schema."
        )
        return CRITICAL, [message]
    except (TypeError, ValueError, OverflowError):
        return CRITICAL, ["Cannot calculate collector health from malformed database records."]
    severity = max((level for level, _ in alerts), default=HEALTHY)
    lines.extend(f"{LEVELS[level]}: {reason}" for level, reason in alerts)
    return severity, lines
