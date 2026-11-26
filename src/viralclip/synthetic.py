"""Synthetic collector data and an end-to-end offline dry run.

Everything here is SYNTHETIC / NOT REAL TWITCH DATA. The generator writes a collector
database through the normal storage API, so exports, the benchmark and the ranking
registry run on it exactly as they would on a sealed private copy.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from math import exp, log
from pathlib import Path
from random import Random

from viralclip.benchmark import run_benchmark
from viralclip.collector.service import GTA_VI_GAME_ID
from viralclip.dataset import Selection, extract, ignored_output, write_json
from viralclip.evaluation import MATURITY
from viralclip.predictions import link_outcomes, rank_pool, read_run
from viralclip.storage.database import TARGET_AGES_SECONDS, Database, to_utc_iso

LABEL = "SYNTHETIC / NOT REAL TWITCH DATA"
DAY = timedelta(days=1)
HORIZON_SECONDS = 86400
SEED = 20261124
# The preliminary 60-minute calendar: train, validation and test creation days.
CALENDAR = {
    "train": (datetime(2026, 11, 24, tzinfo=UTC), datetime(2026, 11, 25, tzinfo=UTC)),
    "validation": (datetime(2026, 11, 28, tzinfo=UTC), datetime(2026, 11, 29, tzinfo=UTC)),
    "test": (datetime(2026, 12, 2, tzinfo=UTC), datetime(2026, 12, 3, tzinfo=UTC)),
}


def views_at(final: int, tau: float, age_seconds: float) -> int:
    """Monotone saturating view curve that reaches `final` at 24 hours."""
    if age_seconds <= 0:
        return 0
    scale = 1 - exp(-HORIZON_SECONDS / tau)
    return int(final * (1 - exp(-age_seconds / tau)) / scale)


def generate(
    path: Path,
    days: list[datetime],
    *,
    game_id: str = GTA_VI_GAME_ID,
    clips_per_day: int = 240,
    channels: int = 120,
    seed: int = SEED,
) -> datetime:
    """Write a new synthetic collector database and return its source watermark.

    Each clip gets a channel effect, a lognormal 24-hour total and a growth time
    constant, so early views are informative without being decisive. Discovery
    delays leave some clips late; a few scheduled jobs stay pending or become
    unavailable, so missing and unavailable outcomes stay distinct from zero views.
    """
    if path.exists():
        raise ValueError("The synthetic collector path must be new")
    rng = Random(seed)
    channel_effect = [rng.gauss(0, 1) for _ in range(channels)]
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = Database(path)
    try:
        writer.upsert_game(game_id, f"Synthetic game ({LABEL})", min(days))
        for day in sorted(days):
            for index in range(clips_per_day):
                channel = rng.randrange(channels)
                created = day + timedelta(seconds=rng.uniform(0, 86340))
                final = max(1, round(exp(3.5 + channel_effect[channel] + rng.gauss(0, 1.1))))
                tau = exp(rng.gauss(log(10800), 0.8))
                delay = rng.expovariate(1 / 720)
                seen = created + timedelta(seconds=delay)
                clip_id = f"synthetic-{day:%Y%m%d}-{index:04d}"
                raw = {
                    "id": clip_id,
                    "created_at": created,
                    "view_count": views_at(final, tau, delay),
                    "broadcaster_id": f"synthetic-channel-{channel:03d}",
                    "broadcaster_name": f"synthetic_channel_{channel:03d}",
                    "title": f"Clip {index}",
                    "duration": round(rng.uniform(10, 60), 1),
                    "language": "en",
                }
                writer.record_clip(raw, game_id, seen, None)
                jobs = dict(
                    writer.connection.execute(
                        "SELECT target_age_seconds, job_id FROM jobs "
                        "WHERE clip_id = ? AND status = 'pending'",
                        (clip_id,),
                    ).fetchall()
                )
                for target in TARGET_AGES_SECONDS:
                    if target not in jobs:
                        continue
                    draw = rng.random()
                    if draw < 0.02:
                        continue  # Left pending: the outcome stays missing.
                    due = created + timedelta(seconds=target)
                    if draw < 0.03:
                        writer.finish_jobs([jobs[target]], "unavailable", due)
                        continue
                    observed = due + timedelta(seconds=rng.uniform(0.5, 5))
                    age = (observed - created).total_seconds()
                    writer.add_scheduled_snapshot(
                        clip_id, observed, views_at(final, tau, age), target, [jobs[target]]
                    )
        # A final observation outside the selection makes every outcome window mature.
        watermark = max(days) + DAY + MATURITY + timedelta(minutes=1)
        writer.record_clip(
            {"id": "synthetic-watermark", "created_at": watermark, "view_count": 0},
            game_id,
            watermark,
            None,
        )
    finally:
        writer.close()
    return watermark


def dry_run(
    output: Path, *, clips_per_day: int = 240, seed: int = SEED, game_id: str = GTA_VI_GAME_ID
) -> dict:
    """Run export, benchmark, ranking registry and outcome linking on synthetic data."""
    output = ignored_output(output)
    output.mkdir(parents=True)
    days = [day for pair in CALENDAR.values() for day in pair]
    collector = output / "synthetic-collector.sqlite3"
    watermark = generate(collector, days, game_id=game_id, clips_per_day=clips_per_day, seed=seed)
    start, end = min(days), max(days) + DAY
    extract(collector, Selection(start, end, (game_id,)), output / "dataset")
    report = run_benchmark(
        [output / "dataset"],
        output / "benchmark",
        CALENDAR["validation"][0],
        CALENDAR["test"][0],
        game_id=game_id,
        cohort="observed-at-cutoff",
    )
    registry = output / "registry.sqlite3"
    runs = []
    for day in CALENDAR["test"]:
        # Daily replay: one run per pool, scored just after the day's last 60-minute
        # cutoff. Features respect each clip's cutoff, but clips created early in the day
        # may already have a 24-hour observation by then, so this is not a test of live
        # timeliness; the count below makes that explicit.
        cutoff_watermark = day + DAY + timedelta(minutes=61)
        run = rank_pool(
            collector,
            registry,
            game_id,
            day,
            60,
            watermark=cutoff_watermark,
            scored_at=cutoff_watermark,
        )
        run["ranked_with_24h_outcome_already_observed"] = _outcomes_before(
            collector, registry, run["run_id"], cutoff_watermark
        )
        runs.append(run)
    outcomes = link_outcomes(collector, registry, watermark=watermark, linked_at=watermark)
    summary = {
        "label": LABEL,
        "seed": seed,
        "clips_per_day": clips_per_day,
        "calendar": {split: [to_utc_iso(day) for day in pair] for split, pair in CALENDAR.items()},
        "source_watermark": to_utc_iso(watermark),
        "benchmark_status": report["status"],
        "benchmark_reasons": report["reasons"],
        # Primary endpoint shape: T1 top-50 overlap at 60 minutes on the test days.
        "test_top50_overlap_macro_mean": _test_overlap(report),
        "registry_mode": "daily replay",
        "registry_runs": runs,
        "outcomes": outcomes,
    }
    write_json(output / "summary.json", summary)
    return summary


def _test_overlap(report: dict) -> dict[str, float | None]:
    """Test-day top-50 overlap per method, or {} when the benchmark scored no test day."""
    metrics = report.get("by_cutoff_minutes", {}).get(60, {}).get("metrics", {})
    overlap = metrics.get("test", {}).get("views_24h", {}).get(50, {}).get("overlap", {})
    return {method: values["macro_mean"] for method, values in overlap.get("methods", {}).items()}


def _outcomes_before(collector: Path, registry: Path, run_id: str, scored_at: datetime) -> int:
    """Count ranked clips whose 24-hour job had already completed when the run was scored."""
    clips = [
        row["clip_id"]
        for row in read_run(registry, run_id)["predictions"]
        if row["rank"] is not None
    ]
    if not clips:
        return 0
    uri = collector.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        db.execute("PRAGMA query_only = ON")
        placeholders = ",".join("?" for _ in clips)
        return db.execute(
            f"""
            SELECT count(*) FROM jobs
            WHERE target_age_seconds = 86400 AND status = 'completed'
              AND completed_at <= ? AND clip_id IN ({placeholders})
            """,
            [to_utc_iso(scored_at), *clips],
        ).fetchone()[0]


def summary_lines(summary: dict) -> list[str]:
    overlap = summary["test_top50_overlap_macro_mean"]
    lines = [
        f"{summary['label']}: seed {summary['seed']}, {summary['clips_per_day']} clips per day",
        f"Benchmark: {summary['benchmark_status']}",
        *summary["benchmark_reasons"],
        "Test top-50 overlap (views_24h, 60m): "
        + (
            ", ".join(f"{method} {value:.3f}" for method, value in sorted(overlap.items()))
            if overlap
            else "not scored"
        ),
    ]
    lines += [
        f"Registry {run['run_id']} ({summary['registry_mode']}): "
        f"{run['scored']}/{run['pool_size']} scored, "
        f"{run['ranked_with_24h_outcome_already_observed']} already had a 24h observation"
        for run in summary["registry_runs"]
    ]
    lines.append(
        f"Outcomes linked: {summary['outcomes']['linked']} {summary['outcomes']['by_status']}"
    )
    return lines
