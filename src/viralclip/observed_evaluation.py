"""Offline ranking of GTA VI clips already discovered at prediction time."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from statistics import mean, median
from tempfile import TemporaryDirectory

from viralclip.collector.service import GTA_VI_GAME_ID
from viralclip.dataset import CUTOFFS, ignored_output, write_json
from viralclip.evaluation import (
    BASELINES,
    DAY,
    MATURITY,
    MIN_DAYS,
    MIN_POOL,
    Candidate,
    Inputs,
    Outcome,
    rank_candidates,
    ranking_metrics,
    read_candidate_exports,
    read_export_outcomes,
    source_windows_cover_day,
    validate_split_boundaries,
)
from viralclip.storage.database import to_utc_iso

MODE = "observed-at-cutoff"
POLICY = "observed-at-cutoff-v1"
MAIN_CUTOFF = 60
K = 10
SPLITS = ("train", "validation", "test")
TARGET_DAYS = (7, 3, 7)
TARGET_TEST_LABELS = 500
LABEL_STATES = ("valid", "immature", "missing", "unavailable", "outside_window", "invalid_link")
METRICS = ("precision_at_k", "recall_at_k", "ndcg_at_k")
PoolKey = tuple[datetime, int]
Orders = tuple[tuple[Candidate, ...], ...]


def _freeze(candidates: dict[tuple[str, int], Candidate]) -> dict[PoolKey, Orders]:
    pools: dict[PoolKey, list[Candidate]] = defaultdict(list)
    for row in candidates.values():
        if row.status in ("eligible", "missing_observations"):
            pools[row.day, row.cutoff].append(row)
    return {
        key: tuple(tuple(rank_candidates(pool, index)) for index in range(len(BASELINES)))
        for key, pool in pools.items()
    }


def _write_recommendations(path: Path, frozen: dict[PoolKey, Orders]) -> None:
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("day_utc", "cutoff_minutes", "baseline", "position", "clip_id", "score"))
        for (day, cutoff), orders in sorted(frozen.items()):
            for index, order in enumerate(orders):
                for position, row in enumerate(order[:K], 1):
                    writer.writerow(
                        (
                            day.date().isoformat(),
                            cutoff,
                            BASELINES[index],
                            position,
                            row.clip_id,
                            row.scores[index],
                        )
                    )


def _day_scope(
    inputs: Inputs, validation_start: datetime | None, test_start: datetime | None
) -> dict[datetime, tuple[str | None, list[str]]]:
    days = set()
    for window in inputs.windows:
        day = window.start.replace(hour=0, minute=0, second=0, microsecond=0)
        while day < window.end:
            days.add(day)
            day += DAY

    scope = {}
    for day in sorted(days):
        split, deadline = None, None
        if validation_start is not None:
            if day < validation_start:
                split, deadline = "train", validation_start
            elif test_start is not None and day < test_start:
                split, deadline = "validation", test_start
            else:
                split = "test"
        horizon_end = day + DAY + MATURITY
        reasons = []
        if not source_windows_cover_day(day, inputs.windows, mature=False):
            reasons.append("incomplete_utc_creation_day")
        elif not source_windows_cover_day(day, inputs.windows):
            reasons.append("day_not_fully_mature_at_source_watermark")
        if any(start < horizon_end and end > day for start, end in inputs.outages):
            reasons.append("declared_outage_in_creation_or_label_window")
        if deadline is not None and horizon_end > deadline:
            reasons.append("embargo_at_split_boundary")
        scope[day] = (split, reasons)
    return scope


def _pool_report(
    orders: Orders,
    discovered: Counter,
    outcomes: dict[str, Outcome],
    exclusion: list[str],
    cutoff: int,
) -> dict:
    cohort = orders[0]
    labels = Counter(outcomes[row.clip_id].status for row in cohort)
    label_values = {
        outcomes[row.clip_id].views for row in cohort if outcomes[row.clip_id].status == "valid"
    }
    ages = [row.latest_age_seconds for row in cohort if row.latest_age_seconds is not None]
    reasons = list(exclusion)
    if labels["valid"] < MIN_POOL:
        reasons.append("insufficient_valid_labels")
    if len(label_values) < 2:
        reasons.append("insufficient_label_variation")
    top10 = {}
    for index, order in enumerate(orders):
        recommendation = order[:K]
        has_score = [row.scores[index] is not None for row in recommendation]
        has_label = [outcomes[row.clip_id].status == "valid" for row in recommendation]
        top10[BASELINES[index]] = {
            "positions": len(recommendation),
            "valid_scores": sum(has_score),
            "valid_labels": sum(has_label),
            "valid_score_and_label": sum(
                score and label for score, label in zip(has_score, has_label, strict=True)
            ),
        }
    age_summary = {"min": min(ages), "median": median(ages), "max": max(ages)} if ages else None
    staleness = (
        {
            "min": 60 * cutoff - age_summary["max"],
            "median": 60 * cutoff - age_summary["median"],
            "max": 60 * cutoff - age_summary["min"],
        }
        if age_summary
        else None
    )
    return {
        "cohort_size": len(cohort),
        "features_valid": discovered["eligible"],
        "features_missing": discovered["missing_observations"],
        "latest_measurement_age_seconds": age_summary,
        "latest_measurement_staleness_seconds": staleness,
        "late_discoveries_at_watermark": discovered["late_discovery"],
        "immature_predictions_at_watermark": discovered["cutoff_immature"],
        "label_status": {state: labels[state] for state in LABEL_STATES},
        "top10_trivial": 0 < len(cohort) <= K,
        "top10": top10,
        "exclusion_reasons": reasons,
    }


def _pool_metrics(orders: Orders, outcomes: dict[str, Outcome]) -> dict:
    views = {
        row.clip_id: outcomes[row.clip_id].views
        for row in orders[0]
        if outcomes[row.clip_id].status == "valid"
    }
    methods = {}
    for method, order in zip(BASELINES, orders, strict=True):
        labeled_order = [row.clip_id for row in order if row.clip_id in views]
        methods[method] = ranking_metrics(labeled_order, views, K) | {
            "top10_clip_ids": labeled_order[:K]
        }
    metrics = {
        "label_denominator": len(views),
        "top10_trivial": len(views) <= K,
        "baselines": methods,
    }
    return {
        "labeled_subset": metrics,
        "full_cohort": metrics if len(views) == len(orders[0]) else None,
    }


def _macro_metrics(days: list[dict]) -> dict:
    result = {}
    for population in ("labeled_subset", "full_cohort"):
        pools = [
            day["metrics"][population] for day in days if day["metrics"][population] is not None
        ]
        result[population] = {
            "days": len(pools),
            "label_denominator": sum(pool["label_denominator"] for pool in pools),
            "macro_average": {
                method: {
                    metric: mean(pool["baselines"][method][metric] for pool in pools)
                    for metric in METRICS
                }
                for method in BASELINES
            }
            if pools
            else {},
        }
    return result


def _cutoff_report(
    inputs: Inputs,
    frozen: dict[PoolKey, Orders],
    scope: dict[datetime, tuple[str | None, list[str]]],
    discovered: dict[PoolKey, Counter],
    cutoff: int,
    has_splits: bool,
) -> dict:
    days = []
    rankable: dict[str | None, list[tuple[datetime, dict]]] = defaultdict(list)
    empty_orders = ((),) * len(BASELINES)
    for day, (split, exclusion) in scope.items():
        key = (day, cutoff)
        pool = _pool_report(
            frozen.get(key, empty_orders),
            discovered.get(key, Counter()),
            inputs.outcomes,
            exclusion,
            cutoff,
        )
        row = {
            "day_utc": day.date().isoformat(),
            "split": split,
            **pool,
        }
        days.append(row)
        if not pool["exclusion_reasons"]:
            rankable[split].append((day, row))

    day_counts = {split: len(rankable[split]) for split in SPLITS} if has_splits else {}
    test_labels = (
        sum(row["label_status"]["valid"] for _, row in rankable["test"]) if has_splits else None
    )
    if has_splits:
        reasons = [
            f"{cutoff}m {split}: {day_counts[split]} rankable UTC days after embargo, requires {MIN_DAYS}"
            for split in SPLITS
            if day_counts[split] < MIN_DAYS
        ]
        status = "INSUFFICIENT DATA" if reasons else "EVALUATED"
    elif len(rankable[None]) < len(SPLITS) * MIN_DAYS:
        status = "INSUFFICIENT DATA"
        reasons = [
            f"{cutoff}m: requires at least {len(SPLITS) * MIN_DAYS} rankable UTC days before embargo"
        ]
    else:
        status = "SPLIT BOUNDARIES REQUIRED"
        reasons = [f"{cutoff}m: supply predeclared validation and test starts"]

    metrics = {}
    if status == "EVALUATED":
        for split in ("validation", "test"):
            for day, row in rankable[split]:
                row["metrics"] = _pool_metrics(frozen[day, cutoff], inputs.outcomes)
            metrics[split] = _macro_metrics([row for _, row in rankable[split]])
    return {
        "status": status,
        "reasons": reasons,
        "rankable_days": sum(len(rows) for rows in rankable.values()),
        "rankable_days_by_split": day_counts,
        "valid_test_labels": test_labels,
        "target_met": (
            all(
                day_counts[split] >= target
                for split, target in zip(SPLITS, TARGET_DAYS, strict=True)
            )
            and test_labels >= TARGET_TEST_LABELS
        )
        if has_splits
        else None,
        "days": days,
        "metrics": metrics,
    }


def run_observed_evaluation(
    directories: list[Path],
    output: Path,
    validation_start: datetime | None,
    test_start: datetime | None,
    k: int,
) -> dict:
    if k != K:
        raise ValueError("Observed-at-cutoff evaluation uses K=10")
    validate_split_boundaries(validation_start, test_start)
    output = ignored_output(output)
    inputs, exports = read_candidate_exports(directories, observed_game=GTA_VI_GAME_ID)
    frozen = _freeze(inputs.candidates)

    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".observed-", dir=output.parent) as staging:
        directory = Path(staging) / "report"
        directory.mkdir()
        _write_recommendations(directory / "recommendations.csv", frozen)
        read_export_outcomes(inputs, exports)
        discovered: dict[PoolKey, Counter] = defaultdict(Counter)
        for row in inputs.candidates.values():
            discovered[row.day, row.cutoff][row.status] += 1
        scope = _day_scope(inputs, validation_start, test_start)
        cutoffs = {
            cutoff: _cutoff_report(
                inputs, frozen, scope, discovered, cutoff, validation_start is not None
            )
            for cutoff in CUTOFFS
        }
        settings = {
            "cohort": MODE,
            "cohort_policy": POLICY,
            "game_id": GTA_VI_GAME_ID,
            "main_cutoff_minutes": MAIN_CUTOFF,
            "cutoffs_minutes": list(CUTOFFS),
            "k": K,
            "validation_start": to_utc_iso(validation_start) if validation_start else None,
            "test_start": to_utc_iso(test_start) if test_start else None,
            "label_maturity_seconds": int(MATURITY.total_seconds()),
            "min_rankable_days_per_split": MIN_DAYS,
            "min_valid_labels_per_day": MIN_POOL,
            "target_days_by_split": dict(zip(SPLITS, TARGET_DAYS, strict=True)),
            "target_valid_test_labels": TARGET_TEST_LABELS,
        }
        report = settings | {
            "status": cutoffs[MAIN_CUTOFF]["status"],
            "reasons": cutoffs[MAIN_CUTOFF]["reasons"],
            "never_discovered_clips": "UNKNOWN",
            "watermarks": sorted({to_utc_iso(window.watermark) for window in inputs.windows}),
            "declared_outages": [
                {"start": to_utc_iso(start), "end": to_utc_iso(end)}
                for start, end in sorted(inputs.outages)
            ],
            "by_cutoff_minutes": cutoffs,
        }
        write_json(directory / "evaluation.json", report)
        write_json(
            directory / "manifest.json",
            {
                "settings": settings,
                "status": report["status"],
                "datasets": inputs.fingerprints,
                "sha256": {
                    name: sha256((directory / name).read_bytes()).hexdigest()
                    for name in ("evaluation.json", "recommendations.csv")
                },
            },
        )
        directory.rename(output)
    return report
