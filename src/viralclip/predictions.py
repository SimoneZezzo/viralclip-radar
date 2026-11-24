"""Append-only live ranking registry kept apart from the collector database."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from viralclip.dataset import CUTOFFS, Selection, candidate, outcome, read_source
from viralclip.storage.database import parse_utc, to_utc_iso, utc_now

APPLICATION_ID = 0x56435250
BASELINE_VERSION = "baseline:latest_views:v1"
NOT_TRAINED = "not_trained_yet"
POOL_STATUSES = ("eligible", "missing_observations")
PENDING_JOB_STATUSES = ("pending", "running")

SCHEMA = """
CREATE TABLE IF NOT EXISTS ranking_runs (
    run_id TEXT PRIMARY KEY,
    game_id TEXT NOT NULL,
    pool_day TEXT NOT NULL,
    cutoff_minutes INTEGER NOT NULL,
    scored_at TEXT NOT NULL,
    source_watermark TEXT NOT NULL,
    score_version TEXT NOT NULL,
    model_status TEXT NOT NULL CHECK (model_status IN ('trained', 'not_trained_yet')),
    pool_size INTEGER NOT NULL CHECK (pool_size > 0),
    CHECK (scored_at >= source_watermark)
);
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES ranking_runs(run_id) DEFERRABLE INITIALLY DEFERRED,
    clip_id TEXT NOT NULL,
    game_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    cutoff_minutes INTEGER NOT NULL,
    prediction_at TEXT NOT NULL,
    scored_at TEXT NOT NULL,
    feature_status TEXT NOT NULL,
    score INTEGER CHECK (score BETWEEN 1 AND 100),
    rank INTEGER CHECK (rank > 0),
    latest_views INTEGER,
    latest_observed_at TEXT,
    observation_ids TEXT NOT NULL,
    CHECK ((score IS NULL) = (rank IS NULL)),
    CHECK (scored_at >= prediction_at),
    CHECK (latest_observed_at IS NULL OR latest_observed_at <= prediction_at),
    UNIQUE (run_id, clip_id),
    UNIQUE (run_id, rank)
);
CREATE TABLE IF NOT EXISTS prediction_outcomes (
    outcome_id INTEGER PRIMARY KEY,
    prediction_id INTEGER NOT NULL UNIQUE REFERENCES predictions(prediction_id),
    linked_at TEXT NOT NULL,
    source_watermark TEXT NOT NULL,
    outcome_status TEXT NOT NULL,
    label_job_id INTEGER,
    label_snapshot_id INTEGER,
    label_observed_at TEXT,
    views_24h INTEGER,
    CHECK ((outcome_status = 'valid') = (views_24h IS NOT NULL))
);
CREATE TRIGGER IF NOT EXISTS ranking_run_no_update
BEFORE UPDATE ON ranking_runs BEGIN SELECT RAISE(ABORT, 'Append-only registry'); END;
CREATE TRIGGER IF NOT EXISTS ranking_run_no_delete
BEFORE DELETE ON ranking_runs BEGIN SELECT RAISE(ABORT, 'Append-only registry'); END;
CREATE TRIGGER IF NOT EXISTS prediction_no_update
BEFORE UPDATE ON predictions BEGIN SELECT RAISE(ABORT, 'Append-only registry'); END;
CREATE TRIGGER IF NOT EXISTS prediction_no_delete
BEFORE DELETE ON predictions BEGIN SELECT RAISE(ABORT, 'Append-only registry'); END;
CREATE TRIGGER IF NOT EXISTS outcome_no_update
BEFORE UPDATE ON prediction_outcomes BEGIN SELECT RAISE(ABORT, 'Append-only registry'); END;
CREATE TRIGGER IF NOT EXISTS outcome_no_delete
BEFORE DELETE ON prediction_outcomes BEGIN SELECT RAISE(ABORT, 'Append-only registry'); END;
CREATE TRIGGER IF NOT EXISTS ranking_run_insert_guard
BEFORE INSERT ON ranking_runs
WHEN EXISTS (SELECT 1 FROM ranking_runs WHERE run_id = NEW.run_id)
  OR NEW.pool_size != (SELECT count(*) FROM predictions WHERE run_id = NEW.run_id)
BEGIN SELECT RAISE(ABORT, 'Run already sealed or incomplete'); END;
CREATE TRIGGER IF NOT EXISTS prediction_insert_guard
BEFORE INSERT ON predictions
WHEN EXISTS (SELECT 1 FROM ranking_runs WHERE run_id = NEW.run_id)
BEGIN SELECT RAISE(ABORT, 'Run already sealed'); END;
"""


def relative_scores(outputs: list[float | None]) -> list[int | None]:
    """Map method outputs to 1-100 within one pool; equal outputs share the top score."""
    scored = [value for value in outputs if value is not None]
    if not scored:
        return [None] * len(outputs)
    highest, lowest = max(scored), min(scored)
    return [
        None
        if value is None
        else 100
        if highest == lowest
        else 1 + round(99 * (value - lowest) / (highest - lowest))
        for value in outputs
    ]


def _connect_registry(registry: Path, collector: Path) -> sqlite3.Connection:
    registry = registry.resolve()
    if registry == collector.resolve():
        raise ValueError("The prediction registry must be separate from the collector database")
    registry.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(registry)
    try:
        db.execute("PRAGMA foreign_keys=ON")
        application_id = db.execute("PRAGMA application_id").fetchone()[0]
        occupied = db.execute("SELECT 1 FROM sqlite_schema LIMIT 1").fetchone()
        if application_id != APPLICATION_ID and (application_id != 0 or occupied):
            raise ValueError("The registry path is already used by another database")
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(f"BEGIN IMMEDIATE;\nPRAGMA application_id={APPLICATION_ID};\n{SCHEMA}")
        db.commit()
    except BaseException:
        db.close()
        raise
    return db


def ignored_registry(path: Path) -> Path:
    """Require a Git-ignored registry path, because real-data predictions stay private."""
    path = path.resolve()
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "--", path.as_posix()],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise ValueError("The prediction registry must be in a Git-ignored repository path")
    return path


def _pool_day(day: datetime) -> datetime:
    day = day.astimezone(UTC)
    if (day.hour, day.minute, day.second, day.microsecond) != (0, 0, 0, 0):
        raise ValueError("The pool day must start at UTC midnight")
    return day


def rank_pool(
    collector: Path,
    registry: Path,
    game_id: str,
    day: datetime,
    cutoff: int,
    *,
    watermark: datetime | None = None,
    scored_at: datetime | None = None,
) -> dict:
    """Score one game x UTC day x cutoff pool with the declared baseline and seal the run."""
    if cutoff not in CUTOFFS:
        raise ValueError(f"Cutoff must be one of {CUTOFFS}")
    day = _pool_day(day)
    source = read_source(collector, Selection(day, day + timedelta(days=1), (game_id,), watermark))
    scored_at = scored_at or utc_now()
    if scored_at < source.watermark:
        raise ValueError("Scoring time precedes the source watermark")
    rows = [
        row
        for clip in source.clips
        if (
            row := candidate(clip, source.observations[clip.clip_id], cutoff, source.watermark, ())
        )["feature_status"]
        in POOL_STATUSES
    ]
    if not rows:
        raise ValueError("No clip in this pool was observed by its cutoff")
    rows.sort(
        key=lambda row: (row["latest_views"] is None, -(row["latest_views"] or 0), row["clip_id"])
    )
    scores = relative_scores([row["latest_views"] for row in rows])
    stamp = to_utc_iso(scored_at)
    run_id = f"{game_id}:{day.date().isoformat()}:{cutoff}m:{stamp}"
    with closing(_connect_registry(registry, collector)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        db.executemany(
            """
            INSERT INTO predictions (
                run_id, clip_id, game_id, created_at, cutoff_minutes, prediction_at, scored_at,
                feature_status, score, rank, latest_views, latest_observed_at, observation_ids
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id,
                    row["clip_id"],
                    game_id,
                    row["created_at"],
                    cutoff,
                    row["prediction_at"],
                    stamp,
                    row["feature_status"],
                    score,
                    rank if score is not None else None,
                    row["latest_views"],
                    row["latest_observed_at"],
                    json.dumps(
                        [int(i) for i in row["observation_ids"].split("|")]
                        if row["observation_ids"]
                        else []
                    ),
                )
                for rank, (row, score) in enumerate(zip(rows, scores, strict=True), 1)
            ],
        )
        db.execute(
            "INSERT INTO ranking_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                game_id,
                day.date().isoformat(),
                cutoff,
                stamp,
                to_utc_iso(source.watermark),
                BASELINE_VERSION,
                NOT_TRAINED,
                len(rows),
            ),
        )
    return {
        "run_id": run_id,
        "score_version": BASELINE_VERSION,
        "model_status": NOT_TRAINED,
        "pool_size": len(rows),
        "scored": sum(score is not None for score in scores),
        "source_watermark": to_utc_iso(source.watermark),
    }


def link_outcomes(
    collector: Path,
    registry: Path,
    *,
    watermark: datetime | None = None,
    linked_at: datetime | None = None,
) -> dict:
    """Attach settled 24h outcomes to unlinked predictions without touching the predictions."""
    with closing(_connect_registry(registry, collector)) as db:
        pending = db.execute(
            """
            SELECT p.prediction_id, p.clip_id, p.game_id, r.pool_day
            FROM predictions p JOIN ranking_runs r USING (run_id)
            LEFT JOIN prediction_outcomes o USING (prediction_id)
            WHERE o.prediction_id IS NULL
            ORDER BY p.prediction_id
            """
        ).fetchall()
    pools: dict[tuple[str, str], list[tuple]] = {}
    for row in pending:
        pools.setdefault((row[2], row[3]), []).append(row)
    linked_at = linked_at or utc_now()
    records = []
    counts: dict[str, int] = {}
    for (game_id, pool_day), rows in sorted(pools.items()):
        day = parse_utc(f"{pool_day}T00:00:00Z")
        source = read_source(
            collector, Selection(day, day + timedelta(days=1), (game_id,), watermark)
        )
        if linked_at < source.watermark:
            raise ValueError("Link time precedes the source watermark")
        clips = {clip.clip_id: clip for clip in source.clips}
        for prediction_id, clip_id, *_ in rows:
            clip = clips.get(clip_id)
            if clip is None:
                counts["deferred"] = counts.get("deferred", 0) + 1
                continue
            job = source.jobs.get(clip_id)
            result = outcome(clip, job, source.watermark)
            status = result["outcome_status"]
            if status == "immature" or (
                status == "missing" and _may_still_settle(job, source.watermark)
            ):
                counts["deferred"] = counts.get("deferred", 0) + 1
                continue
            counts[status] = counts.get(status, 0) + 1
            records.append(
                (
                    prediction_id,
                    to_utc_iso(linked_at),
                    to_utc_iso(source.watermark),
                    status,
                    result["label_job_id"],
                    result["label_snapshot_id"],
                    result["label_observed_at"],
                    result["views_24h"],
                )
            )
    with closing(_connect_registry(registry, collector)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        db.executemany(
            """
            INSERT INTO prediction_outcomes (
                prediction_id, linked_at, source_watermark, outcome_status, label_job_id,
                label_snapshot_id, label_observed_at, views_24h
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            records,
        )
    return {"linked": len(records), "by_status": dict(sorted(counts.items()))}


def _may_still_settle(job: sqlite3.Row | None, watermark: datetime) -> bool:
    if job is None:
        return False
    if job["status"] in PENDING_JOB_STATUSES:
        return True
    completed = job["completed_at"]
    return completed is not None and parse_utc(completed) > watermark


def shortlist(registry: Path, game_id: str, pool_day: str, cutoff: int, k: int = 10) -> dict:
    """Return the top-K records of the latest sealed run for one pool, read-only."""
    if k <= 0:
        raise ValueError("K must be positive")
    with closing(sqlite3.connect(f"{registry.resolve().as_uri()}?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        if db.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID:
            raise ValueError("Not a prediction registry")
        run = db.execute(
            """
            SELECT * FROM ranking_runs WHERE game_id=? AND pool_day=? AND cutoff_minutes=?
            ORDER BY scored_at DESC, run_id DESC LIMIT 1
            """,
            (game_id, pool_day, cutoff),
        ).fetchone()
        if run is None:
            raise ValueError("No sealed run for this pool")
        rows = db.execute(
            """
            SELECT prediction_id, clip_id, prediction_at, score, rank, latest_observed_at,
                   observation_ids
            FROM predictions WHERE run_id=? AND rank IS NOT NULL AND rank <= ?
            ORDER BY rank
            """,
            (run["run_id"], k),
        ).fetchall()
    return {
        "run": dict(run),
        "predictions": [
            dict(row) | {"observation_ids": json.loads(row["observation_ids"])} for row in rows
        ],
    }
