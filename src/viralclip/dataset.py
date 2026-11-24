"""Versioned, measurement-time dataset extraction from a read-only SQLite snapshot."""

from __future__ import annotations

import csv
import json
import sqlite3
import subprocess
from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from math import isclose, log1p
from pathlib import Path

from viralclip.storage.database import parse_utc, to_utc_iso

VERSION = "2a.3"
CUTOFFS = (30, 35, 60, 65)
HORIZON = timedelta(hours=24)
TOLERANCE = timedelta(minutes=5)
FEATURES = (
    "first_views",
    "latest_views",
    "log1p_first_views",
    "log1p_latest_views",
    "first_observation_age_seconds",
    "latest_observation_age_seconds",
    "discovery_delay_seconds",
    "staleness_seconds",
    "observation_count",
    "observed_view_growth",
    "growth_views_per_minute",
)
CANDIDATE_COLUMNS = (
    "clip_id",
    "game_id",
    "created_at",
    "cutoff_minutes",
    "prediction_at",
    "feature_status",
    "outage_overlap",
    "observation_ids",
    "first_observed_at",
    "latest_observed_at",
    *FEATURES,
)
OUTCOME_COLUMNS = (
    "clip_id",
    "outcome_status",
    "label_job_id",
    "label_snapshot_id",
    "label_observed_at",
    "label_age_seconds",
    "views_24h",
)


@dataclass(frozen=True)
class Selection:
    start: datetime
    end: datetime
    games: tuple[str, ...] = ()
    watermark: datetime | None = None
    outages: tuple[tuple[datetime, datetime], ...] = ()


@dataclass(frozen=True)
class Clip:
    clip_id: str
    game_id: str
    created: datetime
    first_seen: datetime
    broadcaster_id: str | None


@dataclass(frozen=True)
class Observation:
    snapshot_id: int
    observed: datetime
    views: int


@dataclass(frozen=True)
class Source:
    watermark: datetime
    latest_observed_at: datetime
    max_snapshot_id: int
    schema: int
    clips: list[Clip]
    observations: dict[str, list[Observation]]
    jobs: dict[str, sqlite3.Row]
    primary_discovery: dict


def read_source(path: Path, selection: Selection) -> Source:
    from viralclip.m2_audit import primary_discovery_evidence

    if selection.start >= selection.end or any(a >= b for a, b in selection.outages):
        raise ValueError("Creation and outage windows must have start before end")
    uri = path.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=2)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only = ON")
        db.execute("BEGIN")
        schema = db.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        if schema != 2:
            raise ValueError("Dataset extraction requires collector schema v2")
        latest, max_id = db.execute(
            "SELECT MAX(observed_at), MAX(snapshot_id) FROM clip_snapshots"
        ).fetchone()
        if latest is None:
            raise ValueError("No observed data is available to freeze a source watermark")
        latest = parse_utc(latest)
        watermark = selection.watermark if selection.watermark is not None else latest
        if watermark > latest:
            raise ValueError("Requested watermark is later than the latest stored observation")
        selection_sql = """
            SELECT clip_id, game_id, created_at, first_seen_at, broadcaster_id FROM clips
            WHERE created_at >= ? AND created_at < ? AND first_seen_at <= ?
        """
        parameters = [
            to_utc_iso(selection.start),
            to_utc_iso(selection.end),
            to_utc_iso(watermark),
        ]
        if selection.games:
            placeholders = ", ".join("?" for _ in selection.games)
            selection_sql += f" AND game_id IN ({placeholders})"
            parameters.extend(selection.games)
        clips = [
            Clip(i, g, parse_utc(c), parse_utc(f), b)
            for i, g, c, f, b in db.execute(
                selection_sql + " ORDER BY created_at, clip_id", parameters
            )
        ]
        observations = {}
        jobs = {}
        for clip in clips:
            observations[clip.clip_id] = [
                Observation(i, parse_utc(o), v)
                for i, o, v in db.execute(
                    """
                    SELECT snapshot_id, observed_at, view_count FROM clip_snapshots
                    WHERE clip_id = ? AND observed_at BETWEEN ? AND ?
                    ORDER BY observed_at, snapshot_id
                    """,
                    (
                        clip.clip_id,
                        to_utc_iso(max(clip.created, clip.first_seen)),
                        to_utc_iso(min(watermark, clip.created + timedelta(minutes=max(CUTOFFS)))),
                    ),
                )
            ]
            if clip.created + HORIZON + TOLERANCE <= watermark:
                jobs[clip.clip_id] = db.execute(
                    """
                    SELECT j.job_id, j.status, j.due_at, j.completed_at, j.attempts,
                           s.snapshot_id, s.clip_id AS snapshot_clip_id, s.source,
                           s.observed_at, s.age_seconds, s.view_count, s.target_age_seconds
                    FROM jobs j LEFT JOIN clip_snapshots s USING (snapshot_id)
                    WHERE j.clip_id = ? AND j.job_type = 'view_snapshot'
                      AND j.target_age_seconds = 86400
                    """,
                    (clip.clip_id,),
                ).fetchone()
        games = selection.games or tuple(sorted({clip.game_id for clip in clips}))
        primary_discovery = primary_discovery_evidence(db, selection, watermark, games)
    return Source(watermark, latest, max_id, schema, clips, observations, jobs, primary_discovery)


def candidate(
    clip: Clip,
    observations: list[Observation],
    cutoff: int,
    watermark: datetime,
    outages: tuple[tuple[datetime, datetime], ...],
) -> dict:
    prediction = clip.created + timedelta(minutes=cutoff)
    row = dict.fromkeys(CANDIDATE_COLUMNS)
    row.update(
        clip_id=clip.clip_id,
        game_id=clip.game_id,
        created_at=to_utc_iso(clip.created),
        cutoff_minutes=cutoff,
        prediction_at=to_utc_iso(prediction),
        outage_overlap=any(clip.created < end and prediction > start for start, end in outages),
    )
    if prediction > watermark:
        row["feature_status"] = "cutoff_immature"
        return row
    if clip.first_seen > prediction:
        row.update(feature_status="late_discovery", observation_count=0)
        return row

    eligible = {}
    for observation in observations:
        if max(clip.created, clip.first_seen) <= observation.observed <= prediction:
            if type(observation.views) is not int or observation.views < 0:
                raise ValueError("Invalid early observation view count")
            previous = eligible.get(observation.observed)
            if previous is None or observation.snapshot_id < previous.snapshot_id:
                eligible[observation.observed] = observation
    measurements = [eligible[instant] for instant in sorted(eligible)]
    row.update(
        discovery_delay_seconds=(clip.first_seen - clip.created).total_seconds(),
        observation_count=len(measurements),
        feature_status="eligible" if measurements else "missing_observations",
    )
    if not measurements:
        return row
    first, latest = measurements[0], measurements[-1]
    row.update(
        observation_ids="|".join(str(o.snapshot_id) for o in measurements),
        first_observed_at=to_utc_iso(first.observed),
        latest_observed_at=to_utc_iso(latest.observed),
        first_views=first.views,
        latest_views=latest.views,
        log1p_first_views=log1p(first.views),
        log1p_latest_views=log1p(latest.views),
        first_observation_age_seconds=(first.observed - clip.created).total_seconds(),
        latest_observation_age_seconds=(latest.observed - clip.created).total_seconds(),
        staleness_seconds=(prediction - latest.observed).total_seconds(),
    )
    if len(measurements) > 1:
        delta = latest.views - first.views
        elapsed = (latest.observed - first.observed).total_seconds()
        row.update(observed_view_growth=delta, growth_views_per_minute=60 * delta / elapsed)
    return row


def outcome(clip: Clip, job: sqlite3.Row | None, watermark: datetime) -> dict:
    row = dict.fromkeys(OUTCOME_COLUMNS)
    row["clip_id"] = clip.clip_id
    due = clip.created + HORIZON
    if due + TOLERANCE > watermark:
        row["outcome_status"] = "immature"
    elif job is None or job["status"] not in ("completed", "unavailable"):
        row["outcome_status"] = "missing"
    else:
        try:
            completed = parse_utc(job["completed_at"])
            if completed > watermark:
                row["outcome_status"] = "missing"
            elif job["status"] == "unavailable":
                row["outcome_status"] = (
                    "unavailable" if job["snapshot_id"] is None else "invalid_link"
                )
            else:
                observed = parse_utc(job["observed_at"])
                age = (observed - clip.created).total_seconds()
                if (
                    job["snapshot_clip_id"] != clip.clip_id
                    or job["source"] != "scheduled"
                    or observed != completed
                    or parse_utc(job["due_at"]) != due
                    or job["target_age_seconds"] not in (None, int(HORIZON.total_seconds()))
                    or not isclose(job["age_seconds"], age, rel_tol=0, abs_tol=1e-6)
                    or type(job["view_count"]) is not int
                    or job["view_count"] < 0
                ):
                    row["outcome_status"] = "invalid_link"
                elif not due <= observed <= due + TOLERANCE:
                    row["outcome_status"] = "outside_window"
                else:
                    row.update(
                        outcome_status="valid",
                        label_job_id=job["job_id"],
                        label_snapshot_id=job["snapshot_id"],
                        label_age_seconds=age,
                        label_observed_at=to_utc_iso(observed),
                        views_24h=job["view_count"],
                    )
        except (TypeError, ValueError, OverflowError):
            row["outcome_status"] = "invalid_link"
    return row


def _coverage(candidates: list[dict], outcomes: dict[str, dict], clips: dict[str, Clip]) -> dict:
    eligible = [r for r in candidates if r["feature_status"] == "eligible"]
    labeled = [r for r in eligible if outcomes[r["clip_id"]]["outcome_status"] == "valid"]
    broadcasters = Counter(clips[r["clip_id"]].broadcaster_id for r in labeled)
    unknown = broadcasters.pop(None, 0) + broadcasters.pop("", 0)
    top = broadcasters.most_common(10)
    return {
        "candidates": len(candidates),
        "feature_status": dict(Counter(r["feature_status"] for r in candidates)),
        "eligible": len(eligible),
        "labeled": len(labeled),
        "labeled_with_two_or_more_observations": sum(r["observation_count"] >= 2 for r in labeled),
        "labeled_observed_in_final_five_minutes": sum(
            r["staleness_seconds"] <= 300 for r in labeled
        ),
        "eligible_outcome_status": dict(
            Counter(outcomes[r["clip_id"]]["outcome_status"] for r in eligible)
        ),
        "eligible_without_growth": sum(r["observed_view_growth"] is None for r in eligible),
        "outage_overlap_candidates": sum(r["outage_overlap"] for r in candidates),
        "outage_overlap_labeled": sum(r["outage_overlap"] for r in labeled),
        "broadcaster_concentration_labeled": {
            "distinct_known": len(broadcasters),
            "unknown_clips": unknown,
            "top_1_clips": top[0][1] if top else 0,
            "top_10_clips": sum(n for _, n in top),
        },
    }


def _outage_coverage(source: Source, selection: Selection, outcomes: dict[str, dict]) -> list[dict]:
    windows = []
    for start, end in selection.outages:
        groups: dict[str, Counter] = {
            "known_before_gap": Counter(),
            "discovered_after_gap": Counter(),
            "discovered_during_gap": Counter(),
        }
        for clip in source.clips:
            if not any(start < clip.created + timedelta(minutes=m) < end for m in (10, 30, 60)):
                continue
            group = "discovered_during_gap"
            if clip.first_seen <= start:
                group = "known_before_gap"
            elif clip.first_seen >= end:
                group = "discovered_after_gap"
            groups[group][outcomes[clip.clip_id]["outcome_status"]] += 1
        windows.append(
            {
                "start": to_utc_iso(start),
                "end": to_utc_iso(end),
                "early_target_overlap_outcomes": {
                    name: dict(counts) for name, counts in groups.items()
                },
            }
        )
    return windows


def _csv(path: Path, columns: tuple[str, ...], rows: list[dict]) -> None:
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def ignored_output(output: Path) -> Path:
    output = output.resolve()
    if output.exists():
        raise ValueError("Dataset output must be a new directory")
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "--", output.as_posix() + "/"],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise ValueError("Dataset output must be in a Git-ignored repository directory")
    return output


def extract(path: Path, selection: Selection, output: Path) -> dict:
    output = ignored_output(output)
    source = read_source(path, selection)
    clips = {c.clip_id: c for c in source.clips}
    candidates = [
        candidate(c, source.observations[c.clip_id], cutoff, source.watermark, selection.outages)
        for c in source.clips
        for cutoff in CUTOFFS
    ]
    outcomes = {
        c.clip_id: outcome(c, source.jobs.get(c.clip_id), source.watermark) for c in source.clips
    }
    labeled = [
        r | {k: v for k, v in outcomes[r["clip_id"]].items() if k != "clip_id"}
        for r in candidates
        if r["feature_status"] == "eligible" and outcomes[r["clip_id"]]["outcome_status"] == "valid"
    ]
    status = Counter(r["outcome_status"] for r in outcomes.values())
    coverage = {
        "unique_clips": len(clips),
        "mature_outcomes": len(clips) - status["immature"],
        "outcome_status": dict(status),
        "outages": _outage_coverage(source, selection, outcomes),
        "primary_discovery": source.primary_discovery,
        "by_cutoff_minutes": {
            m: _coverage([r for r in candidates if r["cutoff_minutes"] == m], outcomes, clips)
            for m in CUTOFFS
        },
    }
    manifest = {
        "extraction_version": VERSION,
        "source_schema_version": source.schema,
        "source_watermark": to_utc_iso(source.watermark),
        "source_latest_observation_at_read": to_utc_iso(source.latest_observed_at),
        "source_max_snapshot_id_at_read": source.max_snapshot_id,
        "creation_start_inclusive": to_utc_iso(selection.start),
        "creation_end_exclusive": to_utc_iso(selection.end),
        "game_ids_filter": list(selection.games),
        "cutoffs_minutes": list(CUTOFFS),
        "model_feature_columns": list(FEATURES),
        "rules": {
            "cohort": "Stored game ID and UTC creation window; first_seen_at <= source watermark.",
            "feature_time": "Cutoff must have elapsed. Actual observations on or before prediction_at.",
            "deduplication": "One snapshot per clip and instant; smallest snapshot ID wins.",
            "label_window_age_seconds_inclusive": [86400, 86700],
            "maturity": "The entire label window must have elapsed at the source watermark.",
            "label": "Same-clip scheduled snapshot linked by completed 24h job; matching completion timestamp and actual age.",
            "missing": "CSV nulls are blank; modeled rows require both eligible features and a valid outcome.",
            "outage": "Declared windows are audit annotations only; bounds are in coverage.json.",
            "timing_limit": "Source records measurement time, without independent commit timestamps.",
        },
        "provenance": {
            "candidate_key": ["clip_id", "cutoff_minutes"],
            "observations": "candidates.csv observation_ids in timestamp order, separated by |",
            "outcomes": "outcomes.csv records the linked job, snapshot and timestamp for valid labels",
            "broadcasters": "broadcasters.csv contains local audit-only pseudonyms, never model inputs",
        },
    }
    output.mkdir(parents=True, exist_ok=False)
    _csv(output / "candidates.csv", CANDIDATE_COLUMNS, candidates)
    _csv(output / "outcomes.csv", OUTCOME_COLUMNS, list(outcomes.values()))
    _csv(output / "dataset.csv", CANDIDATE_COLUMNS + OUTCOME_COLUMNS[1:], labeled)
    _csv(
        output / "broadcasters.csv",
        ("clip_id", "broadcaster_token"),
        [
            {
                "clip_id": c.clip_id,
                "broadcaster_token": sha256(
                    f"viralclip:broadcaster:{c.broadcaster_id}".encode()
                ).hexdigest()
                if c.broadcaster_id
                else None,
            }
            for c in source.clips
        ],
    )
    write_json(output / "coverage.json", coverage)
    manifest["sha256"] = {
        name: sha256((output / name).read_bytes()).hexdigest()
        for name in (
            "candidates.csv",
            "outcomes.csv",
            "dataset.csv",
            "coverage.json",
            "broadcasters.csv",
        )
    }
    write_json(output / "manifest.json", manifest)
    return coverage
