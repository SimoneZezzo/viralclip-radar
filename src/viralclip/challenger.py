"""Frozen challenger c1: project the latest views to the cutoff with the observed rate."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from random import Random
from statistics import mean

from viralclip.benchmark import KS, RESAMPLES, SEED, Frozen, interval, run_benchmark
from viralclip.evaluation import BASELINES, rank_candidates

VERSION = "c1-v1"
SCORE_VERSION = "c1:staleness-projection:v1"
METHOD = "c1"
_VIEWS, _RATE = BASELINES.index("latest_views"), BASELINES.index("growth_rate")


def c1_score(
    views: float | None, rate: float | None, staleness_seconds: float | None
) -> float | None:
    """None without an eligible observation; latest views when no rate exists."""
    if views is None:
        return None
    if rate is None:
        return float(views)
    return max(0.0, views + rate * staleness_seconds / 60)


def c1_row_score(row: dict) -> float | None:
    """Registry scorer for a cutoff feature row from `dataset.candidate`."""
    return c1_score(
        row.get("latest_views"), row.get("growth_views_per_minute"), row.get("staleness_seconds")
    )


def add_c1(frozen: Frozen) -> Frozen:
    """Append c1 to every frozen pool, leaving the four baseline orders unchanged."""
    extended = {}
    for key, orders in frozen.items():
        cutoff = key[1]
        scored = {}
        for row in orders["latest_views"]:
            staleness = (
                cutoff * 60 - row.latest_age_seconds if row.latest_age_seconds is not None else None
            )
            score = c1_score(row.scores[_VIEWS], row.scores[_RATE], staleness)
            scored[row.clip_id] = replace(row, scores=(*row.scores, score))
        result = {
            method: [scored[row.clip_id] for row in order] for method, order in orders.items()
        }
        result[METHOD] = rank_candidates(list(scored.values()), len(BASELINES))
        extended[key] = result
    return extended


def compare_with_strongest(report: dict) -> None:
    """Secondary c1 comparison: paired test difference against the best validation baseline."""
    for block in report["by_cutoff_minutes"].values():
        if not block["metrics"]:
            continue
        for k in KS:
            validation = block["metrics"]["validation"]["views_24h"][k]["overlap"]["methods"]
            if not validation:
                continue
            strongest = max(BASELINES, key=lambda method: validation[method]["macro_mean"])
            daily = [
                day["metrics"]["views_24h"][k]["methods"]
                for day in block["days"]
                if day["split"] == "test" and "metrics" in day
            ]
            differences = [
                methods[METHOD]["overlap"] - methods[strongest]["overlap"]
                for methods in daily
                if methods["latest_views"]["overlap"] is not None
            ]
            if not differences:
                continue
            rng = Random(SEED)
            samples = [
                rng.choices(range(len(differences)), k=len(differences)) for _ in range(RESAMPLES)
            ]
            block.setdefault("c1_vs_strongest_validation_baseline", {})[k] = {
                "baseline": strongest,
                "days": len(differences),
                "paired_difference": mean(differences),
                "paired_ci95": interval(differences, samples),
            }


def run_c1(
    directories: list[Path],
    output: Path,
    validation_start: datetime | None,
    test_start: datetime | None,
    *,
    game_id: str,
    cohort: str,
) -> dict:
    return run_benchmark(
        directories,
        output,
        validation_start,
        test_start,
        game_id=game_id,
        cohort=cohort,
        version=VERSION,
        extend=add_c1,
        annotate=compare_with_strongest,
    )
