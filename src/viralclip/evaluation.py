"""Chronological ranking evaluation over verified local dataset artifacts."""

from __future__ import annotations

import csv
import io
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from math import isfinite, log1p, log2
from pathlib import Path
from statistics import mean

from viralclip.dataset import CUTOFFS, FEATURES, HORIZON, TOLERANCE, ignored_output, write_json
from viralclip.storage.database import parse_utc, to_utc_iso

VERSION = "2b.2"
MATURITY = HORIZON + TOLERANCE
DAY = timedelta(days=1)
MIN_DAYS = 2
MIN_POOL = 10
BASELINES = ("latest_views", "observed_growth", "growth_rate", "age_normalized_views")


@dataclass(frozen=True)
class Candidate:
    clip_id: str
    game_id: str
    created: datetime
    cutoff: int
    status: str
    observation_ids: str
    scores: tuple[float | None, ...]

    @property
    def day(self) -> datetime:
        return self.created.replace(hour=0, minute=0, second=0, microsecond=0)


@dataclass(frozen=True)
class Outcome:
    status: str
    views: int | None = None
    observed: datetime | None = None
    provenance: tuple[int, int] | None = None


@dataclass(frozen=True)
class SourceWindow:
    start: datetime
    end: datetime
    watermark: datetime
    games: tuple[str, ...]
    outages: tuple[tuple[datetime, datetime], ...] = ()


@dataclass
class Inputs:
    candidates: dict[tuple[str, int], Candidate]
    outcomes: dict[str, Outcome]
    broadcasters: dict[str, str | None]
    windows: list[SourceWindow]
    outages: set[tuple[datetime, datetime]]
    fingerprints: list[dict]
    input_candidates: int
    input_outcomes: int


def _csv(data: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(data.decode("utf-8"), newline="")))


def _candidate(row: dict[str, str], window: SourceWindow) -> Candidate:
    created = parse_utc(row["created_at"])
    cutoff = int(row["cutoff_minutes"])
    prediction = created + timedelta(minutes=cutoff)
    status = row["feature_status"]
    if (
        not window.start <= created < window.end
        or (window.games and row["game_id"] not in window.games)
        or cutoff not in CUTOFFS
        or prediction != parse_utc(row["prediction_at"])
        or status not in ("eligible", "late_discovery", "missing_observations", "cutoff_immature")
        or (status == "cutoff_immature") != (prediction > window.watermark)
    ):
        raise ValueError("Candidate outside its declared cohort or prediction window")
    scores = (None,) * len(BASELINES)
    if status == "eligible":
        first = parse_utc(row["first_observed_at"])
        latest = parse_utc(row["latest_observed_at"])
        if not created <= first <= latest <= prediction:
            raise ValueError("Feature observation falls outside its prediction window")
        age = (latest - created).total_seconds()
        if float(row["latest_observation_age_seconds"]) != age:
            raise ValueError("Invalid feature observation age")
        observation_ids = tuple(int(value) for value in row["observation_ids"].split("|"))
        if (
            len(set(observation_ids)) != len(observation_ids)
            or min(observation_ids) < 1
            or len(observation_ids) != int(row["observation_count"])
            or (len(observation_ids) == 1) != (first == latest)
        ):
            raise ValueError("Invalid feature observation provenance")
        first_views = int(row["first_views"])
        views = int(row["latest_views"])
        growth, rate = (
            float(row[name]) if row[name] else None
            for name in ("observed_view_growth", "growth_views_per_minute")
        )
        if min(first_views, views) < 0 or any(
            score is not None and not isfinite(score) for score in (growth, rate)
        ):
            raise ValueError("Invalid baseline feature score")
        expected = (None, None)
        if latest > first:
            expected = (
                views - first_views,
                60 * (views - first_views) / (latest - first).total_seconds(),
            )
        if (growth, rate) != expected or (latest == first and views != first_views):
            raise ValueError("Baseline growth disagrees with its observations")
        scores = (views, growth, rate, views / max(age / 60, 1))
    return Candidate(
        row["clip_id"], row["game_id"], created, cutoff, status, row["observation_ids"], scores
    )


def _outcome(row: dict[str, str], clip: Candidate, watermark: datetime) -> Outcome:
    status = row["outcome_status"]
    if status not in (
        "valid",
        "immature",
        "unavailable",
        "missing",
        "invalid_link",
        "outside_window",
    ):
        raise ValueError("Unknown outcome status")
    if (status == "immature") != (clip.created + MATURITY > watermark):
        raise ValueError("Outcome maturity disagrees with the source watermark")
    if status != "valid":
        if row["views_24h"]:
            raise ValueError("Excluded outcome contains a view label")
        return Outcome(status)
    observed = parse_utc(row["label_observed_at"])
    views = int(row["views_24h"])
    if (
        not clip.created + HORIZON <= observed <= clip.created + MATURITY
        or views < 0
        or not row["label_job_id"]
        or not row["label_snapshot_id"]
        or float(row["label_age_seconds"]) != (observed - clip.created).total_seconds()
    ):
        raise ValueError("Invalid 24-hour label")
    return Outcome(
        status, views, observed, (int(row["label_job_id"]), int(row["label_snapshot_id"]))
    )


def read_inputs(directories: list[Path]) -> Inputs:
    inputs = Inputs({}, {}, {}, [], set(), [], 0, 0)
    clip_identity: dict[str, Candidate] = {}
    candidate_times: dict[tuple[str, int], datetime] = {}
    outcome_times: dict[str, datetime] = {}
    broadcaster_times: dict[str, datetime] = {}
    for directory in directories:
        raw_manifest = (directory / "manifest.json").read_bytes()
        manifest = json.loads(raw_manifest)
        if (
            manifest["extraction_version"] not in ("2a.1", "2a.2")
            or manifest["cutoffs_minutes"] != list(CUTOFFS)
            or not set(FEATURES) <= set(manifest["model_feature_columns"])
            or manifest["rules"]["label_window_age_seconds_inclusive"] != [86400, 86700]
        ):
            raise ValueError("Unsupported dataset manifest")
        names = {"candidates.csv", "outcomes.csv", "dataset.csv", "coverage.json"}
        if manifest["extraction_version"] == "2a.2":
            names.add("broadcasters.csv")
        contents = {}
        for name in sorted(names):
            data = (directory / name).read_bytes()
            if sha256(data).hexdigest() != manifest["sha256"][name]:
                raise ValueError(f"Dataset hash mismatch for {name}")
            contents[name] = data
        window = SourceWindow(
            parse_utc(manifest["creation_start_inclusive"]),
            parse_utc(manifest["creation_end_exclusive"]),
            parse_utc(manifest["source_watermark"]),
            tuple(manifest["game_ids_filter"]),
        )
        if window.start >= window.end:
            raise ValueError("Invalid dataset creation interval")
        inputs.fingerprints.append(
            {
                "path": str(directory),
                "version": manifest["extraction_version"],
                "manifest_sha256": sha256(raw_manifest).hexdigest(),
                "artifact_sha256": {name: manifest["sha256"][name] for name in sorted(names)},
                "watermark": to_utc_iso(window.watermark),
            }
        )
        outages = []
        for outage in json.loads(contents["coverage.json"])["outages"]:
            start, end = parse_utc(outage["start"]), parse_utc(outage["end"])
            if start >= end:
                raise ValueError("Invalid declared outage interval")
            inputs.outages.add((start, end))
            outages.append((start, end))

        local: dict[tuple[str, int], Candidate] = {}
        for row in _csv(contents["candidates.csv"]):
            candidate = _candidate(row, window)
            key = (candidate.clip_id, candidate.cutoff)
            if key in local:
                raise ValueError("Repeated clip and cutoff within one dataset")
            local[key] = candidate
            identity = clip_identity.setdefault(candidate.clip_id, candidate)
            if (identity.created, identity.game_id) != (candidate.created, candidate.game_id):
                raise ValueError("Overlapping datasets disagree on clip identity")
            previous = inputs.candidates.get(key)
            if (
                previous
                and previous != candidate
                and (previous.status != "cutoff_immature" and candidate.status != "cutoff_immature")
            ):
                raise ValueError("Overlapping datasets disagree on point-in-time features")
            if key not in candidate_times or window.watermark >= candidate_times[key]:
                inputs.candidates[key] = candidate
                candidate_times[key] = window.watermark

        local_ids = {i for i, _ in local}
        games = window.games or tuple(sorted({row.game_id for row in local.values()}))
        inputs.windows.append(
            SourceWindow(window.start, window.end, window.watermark, games, tuple(outages))
        )
        outcomes = _csv(contents["outcomes.csv"])
        if (
            len(local) != len(local_ids) * len(CUTOFFS)
            or len(outcomes) != len(local_ids)
            or {r["clip_id"] for r in outcomes} != local_ids
        ):
            raise ValueError("Incomplete clip, cutoff or outcome keys")
        inputs.input_candidates += len(local)
        inputs.input_outcomes += len(outcomes)
        for row in outcomes:
            clip_id = row["clip_id"]
            outcome = _outcome(row, clip_identity[clip_id], window.watermark)
            previous = inputs.outcomes.get(clip_id)
            if (
                previous
                and previous.status == "valid"
                and outcome.status == "valid"
                and outcome != previous
            ):
                raise ValueError("Overlapping datasets disagree on a valid label")
            if previous and previous.status == "valid":
                continue
            if (
                outcome.status == "valid"
                or previous is None
                or window.watermark > outcome_times[clip_id]
            ):
                inputs.outcomes[clip_id] = outcome
                outcome_times[clip_id] = window.watermark
            elif window.watermark == outcome_times[clip_id] and outcome != previous:
                raise ValueError(
                    "Overlapping datasets disagree on an outcome at the same watermark"
                )

        if "broadcasters.csv" in contents:
            broadcasters = _csv(contents["broadcasters.csv"])
            if (
                len(broadcasters) != len(local_ids)
                or {r["clip_id"] for r in broadcasters} != local_ids
            ):
                raise ValueError("Incomplete broadcaster audit keys")
            for row in broadcasters:
                clip_id = row["clip_id"]
                token = row["broadcaster_token"] or None
                if (
                    broadcaster_times.get(clip_id) == window.watermark
                    and inputs.broadcasters[clip_id] != token
                ):
                    raise ValueError("Broadcaster audit values disagree at the same watermark")
                if (
                    clip_id not in broadcaster_times
                    or window.watermark >= broadcaster_times[clip_id]
                ):
                    inputs.broadcasters[clip_id] = token
                    broadcaster_times[clip_id] = window.watermark
    return inputs


def ranking_metrics(order: list[str], views: dict[str, int], k: int) -> dict:
    """Score one complete game/day candidate pool."""
    ideal = sorted(views.values(), reverse=True)
    relevant_cutoff = ideal[(len(ideal) + 9) // 10 - 1]
    relevant = {clip for clip, value in views.items() if value >= relevant_cutoff}
    top = order[:k]
    hits = len(relevant.intersection(top))
    ideal_dcg = _dcg(ideal[:k])
    return {
        "k": len(top),
        "relevant": len(relevant),
        "precision_at_k": hits / len(top),
        "recall_at_k": hits / len(relevant),
        "ndcg_at_k": _dcg([views[clip] for clip in top]) / ideal_dcg if ideal_dcg else None,
    }


def _dcg(values: list[int]) -> float:
    return sum(log1p(value) / log2(rank + 2) for rank, value in enumerate(values))


def _day_is_covered(
    day: datetime, game: str, windows: list[SourceWindow], deadline: datetime | None
) -> bool:
    windows = [window for window in windows if game in window.games]
    if any(
        start < day + DAY + MATURITY and end > day
        for window in windows
        for start, end in window.outages
    ):
        return False
    cursor = day
    for window in sorted(windows, key=lambda w: w.start):
        if window.start > cursor:
            return False
        watermark = min(window.watermark, deadline) if deadline is not None else window.watermark
        cursor = max(cursor, min(window.end, watermark - MATURITY))
        if cursor >= day + DAY:
            return True
    return False


def _period(
    rows: list[Candidate], inputs: Inputs, label_deadline: datetime | None
) -> tuple[dict, dict[int, dict[str, Candidate]], set[str], set[tuple[str, datetime]]]:
    eligible = {cutoff: {} for cutoff in CUTOFFS}
    counts = {}
    all_games_days = {(row.game_id, row.day) for row in rows}
    covered_days = {
        (game, day)
        for game, day in all_games_days
        if _day_is_covered(day, game, inputs.windows, label_deadline)
    }
    for cutoff in CUTOFFS:
        candidates = [r for r in rows if r.cutoff == cutoff]
        features = [r for r in candidates if r.status == "eligible"]
        states = Counter()
        embargoed = 0
        for row in features:
            outcome = inputs.outcomes[row.clip_id]
            if label_deadline is not None and row.created + MATURITY > label_deadline:
                states["embargoed_at_period_boundary"] += 1
                embargoed += outcome.status == "valid"
            else:
                states[outcome.status] += 1
                if outcome.status == "valid":
                    eligible[cutoff][row.clip_id] = row
        counts[cutoff] = {
            "candidates": len(candidates),
            "feature_status": dict(Counter(r.status for r in candidates)),
            "eligible_features": len(features),
            "label_status_among_eligible": dict(states),
            "eligible_with_label": len(eligible[cutoff]),
            "embargoed_valid_outcomes": embargoed,
            "label_coverage": len(eligible[cutoff]) / len(features) if features else None,
            "mature_eligible_features": len(features)
            - states["immature"]
            - states["embargoed_at_period_boundary"],
            "missing_scores_among_eligible": {
                method: sum(r.scores[i] is None for r in features)
                for i, method in enumerate(BASELINES)
            },
            "outage_exposed_candidates": sum(_outage_exposed(row, inputs) for row in candidates),
            "labeled_population": _population(eligible[cutoff].values(), inputs),
        }
    matched = set.intersection(*(set(rows_by_id) for rows_by_id in eligible.values()))
    reference = eligible[CUTOFFS[0]]
    grouped = defaultdict(list)
    for clip_id in sorted(matched):
        row = reference[clip_id]
        game_day = (row.game_id, row.day)
        if game_day in covered_days:
            grouped[game_day].append(clip_id)
    rankable = {
        key
        for key, ids in grouped.items()
        if len(ids) >= MIN_POOL and len({inputs.outcomes[i].views for i in ids}) > 1
    }
    for cutoff in CUTOFFS:
        counts[cutoff]["matched_population"] = _population(
            [eligible[cutoff][clip_id] for clip_id in sorted(matched)], inputs
        )
    report = {
        "unique_clips": len({row.clip_id for row in rows}),
        "observed_creation_days": sorted({day.date().isoformat() for _, day in all_games_days}),
        "covered_mature_creation_days": sorted({day.date().isoformat() for _, day in covered_days}),
        "rankable_creation_days": sorted({day.date().isoformat() for _, day in rankable}),
        "rankable_game_day_pools": len(rankable),
        "rankable_creation_days_by_game": {
            game: sorted(day.date().isoformat() for key, day in rankable if key == game)
            for game in sorted({key for key, _ in all_games_days})
        },
        "matched_labeled_clips": len(matched),
        "by_cutoff_minutes": counts,
    }
    return report, eligible, matched, rankable


def _outage_exposed(row: Candidate, inputs: Inputs) -> bool:
    return any(
        row.created < end and row.created + timedelta(minutes=row.cutoff) > start
        for window in inputs.windows
        if row.game_id in window.games
        for start, end in window.outages
    )


def _population(rows, inputs: Inputs) -> dict:
    rows = list(rows)
    tokens = Counter(inputs.broadcasters.get(r.clip_id) for r in rows)
    unknown = tokens.pop(None, 0)
    top = [count for _, count in tokens.most_common(10)]
    return {
        "clips": len(rows),
        "outage_exposed": sum(_outage_exposed(row, inputs) for row in rows),
        "missing_scores": {
            method: sum(r.scores[i] is None for r in rows) for i, method in enumerate(BASELINES)
        },
        "broadcaster_concentration": {
            "clips_with_audit_record": sum(r.clip_id in inputs.broadcasters for r in rows),
            "unknown_clips": unknown,
            "distinct_known": len(tokens),
            "top_1_clips": top[0] if top else None,
            "top_10_clips": sum(top) if top else None,
        },
    }


def _scores(period, inputs: Inputs, k: int) -> dict:
    _, eligible, matched, rankable = period
    result = {}
    for cutoff, candidates in eligible.items():
        result[cutoff] = {}
        for population in ("cutoff_eligible", "matched"):
            pools = defaultdict(list)
            for row in candidates.values():
                game_day = (row.game_id, row.day)
                if game_day in rankable and (
                    population == "cutoff_eligible" or row.clip_id in matched
                ):
                    pools[game_day].append(row)
            metrics = []
            for (game, day), pool in sorted(pools.items()):
                views = {row.clip_id: inputs.outcomes[row.clip_id].views for row in pool}
                methods = {}
                for i, method in enumerate(BASELINES):
                    ordered = sorted(
                        pool,
                        key=lambda r: (r.scores[i] is None, -(r.scores[i] or 0), r.clip_id),
                    )
                    methods[method] = ranking_metrics([r.clip_id for r in ordered], views, k)
                metrics.append(
                    {
                        "game_id": game,
                        "day_utc": day.date().isoformat(),
                        "clips": len(pool),
                        "metrics": methods,
                    }
                )
            result[cutoff][population] = {
                "pools": metrics,
                "ranked_clips": sum(pool["clips"] for pool in metrics),
                "macro_average": {
                    method: {
                        metric: mean(pool["metrics"][method][metric] for pool in metrics)
                        for metric in ("precision_at_k", "recall_at_k", "ndcg_at_k")
                    }
                    for method in BASELINES
                },
            }
    return result


def evaluate(
    inputs: Inputs, validation_start: datetime | None, test_start: datetime | None, k: int
) -> dict:
    if k < 1:
        raise ValueError("K must be positive")
    if (validation_start is None) != (test_start is None) or (
        validation_start is not None
        and (
            validation_start >= test_start
            or any(
                t != t.replace(hour=0, minute=0, second=0, microsecond=0)
                for t in (validation_start, test_start)
            )
        )
    ):
        raise ValueError("Supply both boundaries as increasing UTC midnights")
    rows = list(inputs.candidates.values())
    games = sorted(
        {row.game_id for row in rows} | {game for w in inputs.windows for game in w.games}
    )
    overall = _period(rows, inputs, None)[0]
    periods = {}
    metrics = {}
    reasons = []
    if validation_start is None:
        days = overall["rankable_creation_days_by_game"]
        reasons.extend(
            f"Game {game} needs at least {3 * MIN_DAYS} rankable mature UTC days before embargoes"
            for game in games
            if len(days.get(game, ())) < 3 * MIN_DAYS
        )
        if not games:
            reasons.append("No game cohorts are present")
        if reasons:
            status = "INSUFFICIENT DATA"
        else:
            reasons.append("Predeclare validation and test start dates")
            status = "SPLIT BOUNDARIES REQUIRED"
    else:
        periods = {
            "train": _period(
                [r for r in rows if r.created < validation_start], inputs, validation_start
            ),
            "validation": _period(
                [r for r in rows if validation_start <= r.created < test_start], inputs, test_start
            ),
            "test": _period([r for r in rows if r.created >= test_start], inputs, None),
        }
        for name, period in periods.items():
            days = period[0]["rankable_creation_days_by_game"]
            for game in games:
                n = len(days.get(game, ()))
                if n < MIN_DAYS:
                    reasons.append(
                        f"{name}, game {game} has {n} rankable mature UTC days after embargo; needs {MIN_DAYS}"
                    )
        if not games:
            reasons.append("No game cohorts are present")
        status = "INSUFFICIENT DATA" if reasons else "EVALUATED"
        if not reasons:
            metrics = {name: _scores(periods[name], inputs, k) for name in ("validation", "test")}
    return {
        "status": status,
        "reasons": reasons,
        "overall": overall,
        "periods": {name: period[0] for name, period in periods.items()},
        "metrics": metrics,
        "deduplication": {
            "input_candidate_rows": inputs.input_candidates,
            "unique_candidate_rows": len(rows),
            "duplicate_candidate_rows_removed": inputs.input_candidates - len(rows),
            "duplicate_clip_occurrences_removed": inputs.input_outcomes - len(inputs.outcomes),
        },
        "declared_outages": [
            {"start": to_utc_iso(start), "end": to_utc_iso(end)}
            for start, end in sorted(inputs.outages)
        ],
        "declared_outages_by_game": {
            game: [
                {"start": to_utc_iso(start), "end": to_utc_iso(end)}
                for start, end in sorted(
                    {
                        outage
                        for window in inputs.windows
                        if game in window.games
                        for outage in window.outages
                    }
                )
            ]
            for game in games
        },
        "coverage_basis": "Declared extraction windows and outages. Discovery admission requires the M2 audit.",
    }


def run_evaluation(
    directories: list[Path],
    output: Path,
    validation_start: datetime | None,
    test_start: datetime | None,
    k: int,
) -> dict:
    output = ignored_output(output)
    inputs = read_inputs(directories)
    report = evaluate(inputs, validation_start, test_start, k)
    manifest = {
        "evaluation_version": VERSION,
        "datasets": inputs.fingerprints,
        "settings": {
            "cutoffs_minutes": list(CUTOFFS),
            "k": k,
            "validation_start": to_utc_iso(validation_start) if validation_start else None,
            "test_start": to_utc_iso(test_start) if test_start else None,
            "label_maturity_seconds": int(MATURITY.total_seconds()),
            "min_rankable_days_per_period": MIN_DAYS,
            "min_matched_labels_per_pool": MIN_POOL,
        },
        "rules": {
            "splits": "UTC creation dates, one split per clip; maturity by the next split boundary.",
            "populations": "Valid labeled cutoff rows or their intersection; identical game/day keys.",
            "rankable_pool": "Full mature covered game/day, minimum matched labels and varied outcomes.",
            "relevance": "Top ceil(10% of pool) by observed 24h views, including boundary ties.",
            "precision_recall": "Hits / min(K, population) and hits / relevant count, respectively.",
            "ndcg": "DCG with log1p(24h views) gains and log2(rank+1) discounts, divided by ideal DCG.",
            "aggregation": "Unweighted mean across game/day pools.",
            "scores": dict(
                zip(
                    BASELINES,
                    (
                        "Latest eligible views.",
                        "Latest minus first eligible views.",
                        "Observed growth per actual elapsed minute.",
                        "Latest eligible views divided by max(1, actual observation age in minutes).",
                    ),
                    strict=True,
                )
            ),
            "ties_and_missing": "Descending score, missing scores last, then ascending clip ID.",
        },
        "status": report["status"],
        "sample_counts": {
            name: {
                cutoff: {
                    key: counts[key]
                    for key in ("candidates", "eligible_features", "eligible_with_label")
                }
                for cutoff, counts in period["by_cutoff_minutes"].items()
            }
            for name, period in {"overall": report["overall"], **report["periods"]}.items()
        },
    }
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "evaluation.json", report)
    manifest["evaluation_sha256"] = sha256((output / "evaluation.json").read_bytes()).hexdigest()
    write_json(output / "manifest.json", manifest)
    return report
