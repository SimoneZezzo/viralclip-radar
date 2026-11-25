"""Versioned benchmark for observed-at-cutoff and audited primary cohorts."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from hashlib import sha256
from math import log1p
from pathlib import Path
from random import Random
from statistics import mean
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
    _day_is_covered,
    _dcg,
    rank_candidates,
    ranking_metrics,
    read_candidate_exports,
    read_export_outcomes,
    validate_split_boundaries,
)

VERSION = "benchmark-v1"
KS = (10, 50)
MAIN_CUTOFF = 60
SPLITS = ("train", "validation", "test")
TARGET_DAYS = dict(zip(SPLITS, (7, 3, 7), strict=True))
TARGET_TEST_LABELS = 500
RESAMPLES = 2000
SEED = 20261124
LATEST_VIEWS = BASELINES.index("latest_views")
Orders = dict[str, list[Candidate]]
Frozen = dict[tuple[datetime, int], Orders]
Scorable = tuple[dict, Orders, dict[str, int]]


def freeze(inputs: Inputs, game_id: str, cohort: str) -> Frozen:
    pools: dict[tuple[datetime, int], list[Candidate]] = defaultdict(list)
    for row in inputs.candidates.values():
        if (
            row.game_id == game_id
            and row.status in ("eligible", "missing_observations")
            and (cohort != "primary" or row.clip_id in inputs.primary_candidates)
        ):
            pools[row.day, row.cutoff].append(row)
    return {
        key: {method: rank_candidates(pool, index) for index, method in enumerate(BASELINES)}
        for key, pool in pools.items()
    }


def write_recommendations(path: Path, frozen: Frozen, game_id: str) -> list[dict]:
    order_digests = []
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(
            ("game_id", "day_utc", "cutoff_minutes", "baseline", "position", "clip_id", "score")
        )
        for (day, cutoff), orders in sorted(frozen.items()):
            for index, (method, order) in enumerate(orders.items()):
                day_utc = day.date().isoformat()
                order_ids = json.dumps(
                    [row.clip_id for row in order], ensure_ascii=False, separators=(",", ":")
                ).encode("utf-8")
                order_digests.append(
                    {
                        "day_utc": day_utc,
                        "cutoff_minutes": cutoff,
                        "baseline": method,
                        "positions": len(order),
                        "clip_ids_sha256": sha256(order_ids).hexdigest(),
                    }
                )
                for position, row in enumerate(order[: max(KS)], 1):
                    writer.writerow(
                        (
                            game_id,
                            day_utc,
                            cutoff,
                            method,
                            position,
                            row.clip_id,
                            row.scores[index],
                        )
                    )
    return order_digests


def top_overlap(
    orders: Orders, target: dict[str, int] | dict[str, float], labeled: dict[str, int], k: int
) -> dict:
    values = sorted(target.values(), reverse=True)
    size = min(k, len(values))
    relevant = {clip for clip, value in target.items() if size and value >= values[size - 1]}
    methods = {}
    for method, order in orders.items():
        ids = [row.clip_id for row in order]
        frozen_top = ids[:k]
        top = [clip for clip in ids if clip in target][:k]
        methods[method] = {
            "overlap": len(relevant.intersection(top)) / size if size else None,
            "frozen_overlap": (
                len(relevant.intersection(frozen_top)) / len(frozen_top) if size else None
            ),
            "frozen_positions": len(frozen_top),
            "frozen_valid_labels": sum(clip in labeled for clip in frozen_top),
            "frozen_defined_targets": sum(clip in target for clip in frozen_top),
        }
    return {
        "target_count": len(values),
        "effective_k": size,
        "true_top_k_with_ties": len(relevant),
        "random_expected_overlap": len(relevant) / len(values) if size else None,
        "ideal_overlap": 1.0 if size else None,
        "methods": methods,
    }


def pool_metrics(orders: Orders, views: dict[str, int]) -> dict:
    growth = {
        row.clip_id: log1p(views[row.clip_id]) - log1p(row.scores[LATEST_VIEWS])
        for row in orders["latest_views"]
        if row.clip_id in views and row.scores[LATEST_VIEWS] is not None
    }
    result = {
        name: {k: top_overlap(orders, target, views, k) for k in KS}
        for name, target in (("views_24h", views), ("post_cutoff_log_growth", growth))
    }
    ideal = _dcg(sorted(views.values(), reverse=True)[:50])
    for method, order in orders.items():
        ids = [row.clip_id for row in order if row.clip_id in views]
        result["views_24h"][50]["methods"][method]["ndcg_at_50"] = (
            _dcg([views[clip] for clip in ids[:50]]) / ideal if ideal else None
        )
        legacy = ranking_metrics(ids, views, 10)
        result["views_24h"][10]["methods"][method].update(
            {name: legacy[name] for name in ("precision_at_k", "recall_at_k", "ndcg_at_k")}
        )
    return result


def interval(values: list[float], samples: list[list[int]]) -> list[float]:
    estimates = sorted(sum(values[index] for index in sample) / len(sample) for sample in samples)
    bounds = []
    for probability in (0.025, 0.975):
        position = probability * (len(estimates) - 1)
        lower = int(position)
        bounds.append(
            estimates[lower] + (position - lower) * (estimates[lower + 1] - estimates[lower])
        )
    return bounds


def summarize(pools: list[dict], metric: str, *, formal_test: bool) -> dict:
    pools = [pool for pool in pools if pool["methods"]["latest_views"][metric] is not None]
    if not pools:
        return {"days": 0, "methods": {}}
    days = len(pools)
    rng = Random(SEED)
    samples = [rng.choices(range(days), k=days) for _ in range(RESAMPLES)]
    reference = [pool["methods"]["latest_views"][metric] for pool in pools]
    methods = {}
    for method in pools[0]["methods"]:
        values = [pool["methods"][method][metric] for pool in pools]
        differences = [value - base for value, base in zip(values, reference, strict=True)]
        paired_ci = interval(differences, samples)
        methods[method] = {
            "macro_mean": mean(values),
            "ci95": interval(values, samples),
            "paired_difference_from_latest_views": mean(differences),
            "paired_ci95": paired_ci,
            "beats_latest_views": (
                paired_ci[0] > 0 if formal_test and days >= TARGET_DAYS["test"] else None
            ),
        }
    return {"days": days, "methods": methods}


def score_split(pools: list[Scorable], *, formal_test: bool) -> dict:
    for row, orders, views in pools:
        row["metrics"] = pool_metrics(orders, views)
    result = {}
    for target in ("views_24h", "post_cutoff_log_growth"):
        result[target] = {}
        for k in KS:
            daily = [row["metrics"][target][k] for row, _, _ in pools]
            metrics = ["overlap", "frozen_overlap"]
            if target == "views_24h":
                metrics.extend(
                    ("ndcg_at_50",) if k == 50 else ("precision_at_k", "recall_at_k", "ndcg_at_k")
                )
            result[target][k] = {
                metric: summarize(daily, metric, formal_test=formal_test) for metric in metrics
            }
    return result


def cutoff_report(
    inputs: Inputs,
    frozen: Frozen,
    game_id: str,
    cohort: str,
    cutoff: int,
    validation_start: datetime | None,
    test_start: datetime | None,
) -> dict:
    by_split: dict[str, list[Scorable]] = {name: [] for name in SPLITS}
    days = []
    calendar = set()
    for window in inputs.windows:
        if game_id in window.games:
            day = window.start.replace(hour=0, minute=0, second=0, microsecond=0)
            while day < window.end:
                calendar.add(day)
                day += DAY
    for day in sorted(calendar):
        orders = frozen.get((day, cutoff))
        cohort_rows = orders["latest_views"] if orders else ()
        split, deadline = "test", None
        if validation_start is not None:
            if day < validation_start:
                split, deadline = "train", validation_start
            elif day < test_start:
                split, deadline = "validation", test_start
        views = {
            row.clip_id: inputs.outcomes[row.clip_id].views
            for row in cohort_rows
            if inputs.outcomes[row.clip_id].status == "valid"
            and (cohort != "primary" or row.clip_id in inputs.primary_clips)
        }
        exclusions = []
        if deadline is not None and day + DAY + MATURITY > deadline:
            exclusions.append("embargo_at_split_boundary")
        if not _day_is_covered(day, game_id, inputs.windows, deadline):
            exclusions.append("incomplete_immature_or_outage_day")
        if len(views) < MIN_POOL:
            exclusions.append("insufficient_valid_labels")
        if len(set(views.values())) < 2:
            exclusions.append("insufficient_label_variation")
        row = {
            "day_utc": day.date().isoformat(),
            "split": split if validation_start else None,
            "cohort_size": len(cohort_rows),
            "valid_labels": len(views),
            "exclusions": exclusions,
        }
        days.append(row)
        if orders and not exclusions:
            by_split[split].append((row, orders, views))
    counts = {split: len(pools) for split, pools in by_split.items()}
    valid_test_labels = sum(row["valid_labels"] for row, _, _ in by_split["test"])
    if validation_start is None:
        status = (
            "SPLIT BOUNDARIES REQUIRED" if counts["test"] >= 3 * MIN_DAYS else "INSUFFICIENT DATA"
        )
        return {"status": status, "days": days, "metrics": {}}
    status = "INSUFFICIENT DATA"
    metrics = {}
    if min(counts.values()) >= MIN_DAYS:
        formal = (
            all(counts[s] >= TARGET_DAYS[s] for s in SPLITS)
            and valid_test_labels >= TARGET_TEST_LABELS
        )
        status = "EVALUATED" if formal else "MECHANISM ONLY"
        metrics = {
            split: score_split(by_split[split], formal_test=formal and split == "test")
            for split in ("validation", "test")
        }
    return {
        "status": status,
        "days": days,
        "rankable_days_by_split": counts,
        "valid_test_labels": valid_test_labels,
        "metrics": metrics,
    }


def run_benchmark(
    directories: list[Path],
    output: Path,
    validation_start: datetime | None,
    test_start: datetime | None,
    *,
    game_id: str,
    cohort: str,
    version: str = VERSION,
    extend: Callable[[Frozen], Frozen] | None = None,
    annotate: Callable[[dict], None] | None = None,
) -> dict:
    validate_split_boundaries(validation_start, test_start)
    output = ignored_output(output)
    inputs, exports = read_candidate_exports(directories, benchmark=True)
    if not any(game_id in export.window.games for export in exports):
        raise ValueError(f"No input export covers game {game_id}")
    frozen = freeze(inputs, game_id, cohort)
    if extend is not None:
        frozen = extend(frozen)
    settings = {
        "benchmark_protocol": version,
        "cohort": cohort,
        "game_id": game_id,
        "validation_start": validation_start.isoformat() if validation_start else None,
        "test_start": test_start.isoformat() if test_start else None,
        "main_cutoff_minutes": MAIN_CUTOFF,
        "k_values": list(KS),
        "label_maturity_seconds": int(MATURITY.total_seconds()),
        "min_rankable_days_per_split": MIN_DAYS,
        "min_valid_labels_per_day": MIN_POOL,
        "bootstrap": {"seed": SEED, "resamples": RESAMPLES, "unit": "UTC day"},
        "target_days_by_split": TARGET_DAYS,
        "target_valid_test_labels": TARGET_TEST_LABELS,
        "primary_endpoint": (
            {"target": "views_24h", "k": 50, "cutoff_minutes": MAIN_CUTOFF}
            if game_id == GTA_VI_GAME_ID and cohort == "observed-at-cutoff"
            else None
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".benchmark-", dir=output.parent) as staging:
        directory = Path(staging) / "report"
        directory.mkdir()
        order_digests = write_recommendations(directory / "recommendations.csv", frozen, game_id)
        write_json(directory / "frozen_orders.json", {"orders": order_digests})
        read_export_outcomes(inputs, exports)
        cutoffs = {
            cutoff: cutoff_report(
                inputs, frozen, game_id, cohort, cutoff, validation_start, test_start
            )
            for cutoff in CUTOFFS
        }
        status = cutoffs[MAIN_CUTOFF]["status"]
        reasons = {
            "INSUFFICIENT DATA": ["60m: fewer than the required rankable UTC days"],
            "SPLIT BOUNDARIES REQUIRED": ["Supply predeclared validation and test starts"],
            "MECHANISM ONLY": ["Formal evaluation requires 7/3/7 days and 500 valid test labels"],
            "EVALUATED": [],
        }
        report = settings | {
            "status": status,
            "reasons": reasons[status],
            "by_cutoff_minutes": cutoffs,
            "never_discovered_clips": "UNKNOWN",
        }
        if annotate is not None:
            annotate(report)
        write_json(directory / "evaluation.json", report)
        write_json(
            directory / "manifest.json",
            {
                "evaluation_version": version,
                "settings": settings,
                "datasets": inputs.fingerprints,
                "status": status,
                "sha256": {
                    name: sha256((directory / name).read_bytes()).hexdigest()
                    for name in ("evaluation.json", "recommendations.csv", "frozen_orders.json")
                },
            },
        )
        directory.rename(output)
    return report
