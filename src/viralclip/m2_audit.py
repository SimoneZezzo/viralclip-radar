"""Read-only aggregate M2 cohort audit for the two collector databases."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import sqlite3
import stat
import sys
import time
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from contextlib import ExitStack, closing
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from viralclip import dataset, evaluation
from viralclip.dataset import CUTOFFS, Clip, Observation, Selection, candidate, outcome
from viralclip.evaluation import DAY, MATURITY, MIN_DAYS, MIN_POOL
from viralclip.storage.database import TARGET_AGES_SECONDS, parse_utc, to_utc_iso

GAMES = {"gta-v": "32982", "gta-vi": "1867279146"}
FEATURE_STATES = ("eligible", "cutoff_immature", "late_discovery", "missing_observations")
LABEL_STATES = ("valid", "immature", "missing", "unavailable", "invalid_link", "outside_window")
LANES = ("recent", "history", "retry")
SCAN_OUTCOMES = (
    "cursor_exhausted",
    "budget",
    "page_limit",
    "error",
    "pagination_anomaly",
    "known_incomplete",
)
MAX_DAYS = 366
MAX_EARLY = 4096
MAX_DISCOVERY_RUNS = 120_000
DISCOVERY_POLICY = "legacy-search-day-v1"
READINESS_DAYS = 30
DELAY_BOUNDS = tuple(sorted(set(TARGET_AGES_SECONDS) | {60 * m for m in CUTOFFS}))
LABEL_QUERY = """
SELECT c.clip_id, c.created_at, c.first_seen_at, j.job_id, j.status, j.due_at, j.completed_at,
       s.snapshot_id, s.clip_id AS snapshot_clip_id, s.source, s.observed_at, s.age_seconds,
       s.view_count, s.target_age_seconds,
       (SELECT COUNT(*) FROM clip_snapshots m
        WHERE m.clip_id=c.clip_id AND m.observed_at<=:watermark) AS observations
FROM clips c
LEFT JOIN jobs j ON j.clip_id=c.clip_id AND j.job_type='view_snapshot'
                AND j.target_age_seconds=86400
LEFT JOIN clip_snapshots s ON s.snapshot_id=j.snapshot_id
WHERE c.game_id=:game AND c.created_at>=:start AND c.created_at<:end
  AND c.first_seen_at<=:watermark
"""


class AuditError(Exception):
    """A stable error code safe to include in the aggregate report."""


def deny_fs_writes() -> None:
    # Same Landlock ABI and write restrictions as docs/phase0-inspect.sh.
    if platform.machine() not in ("x86_64", "aarch64"):
        raise AuditError("landlock_architecture_unsupported")
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    rights = ctypes.c_uint64((1 << 1) | sum(1 << n for n in range(4, 15)))
    fd = libc.syscall(444, ctypes.byref(rights), ctypes.c_size_t(8), 0)
    if fd < 0:
        raise AuditError("landlock_abi_3_unavailable")
    try:
        if libc.prctl(38, ctypes.c_ulong(1), 0, 0, 0) != 0 or libc.syscall(446, fd, 0) != 0:
            raise AuditError("landlock_enforcement_failed")
    finally:
        os.close(fd)


def file_identity(path: Path) -> tuple[int, int]:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or path.resolve() != path:
        raise AuditError("unsafe_database_or_sidecar_path")
    return info.st_dev, info.st_ino


def open_snapshot(stack: ExitStack, path: Path, deadline: float) -> sqlite3.Connection:
    path = path.absolute()
    identity = file_identity(path)
    with path.open("rb") as stream:
        header = stream.read(100)
    if header[:16] != b"SQLite format 3\0":
        raise AuditError("invalid_sqlite_header")
    wal = header[18:20] == b"\x02\x02"
    sidecars = [path.with_name(path.name + suffix) for suffix in ("-wal", "-shm", "-journal")]
    if sys.platform == "linux" and wal:
        sidecar_ids = [file_identity(sidecar) for sidecar in sidecars[:2]]
        if os.path.lexists(sidecars[2]):
            raise AuditError("rollback_journal_present")
    elif wal or any(os.path.lexists(sidecar) for sidecar in sidecars):
        raise AuditError("live_or_unsealed_source_requires_linux_landlock")
    else:
        sidecar_ids = []

    check_deadline(deadline)
    db = stack.enter_context(
        closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2))
    )
    db.row_factory = sqlite3.Row
    db.set_progress_handler(lambda: time.monotonic() >= deadline, 10_000)
    db.execute("PRAGMA query_only=ON")
    db.execute("PRAGMA temp_store=MEMORY")
    db.execute("PRAGMA cache_size=-8192")
    db.execute("PRAGMA trusted_schema=OFF")
    db.execute("BEGIN")
    if db.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] != 2:
        raise AuditError("unsupported_schema")
    if file_identity(path) != identity or (
        sidecar_ids and [file_identity(sidecar) for sidecar in sidecars[:2]] != sidecar_ids
    ):
        raise AuditError("database_identity_changed")
    return db


def check_deadline(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise AuditError("deadline_exceeded")


def midnight(value: datetime) -> datetime:
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


@dataclass(frozen=True)
class Source:
    db: sqlite3.Connection
    clips: int
    observations: int
    latest: datetime | None
    max_snapshot_id: int | None
    first_day: datetime | None

    @classmethod
    def inspect(cls, db: sqlite3.Connection, game: str) -> Source:
        for table in ("games", "clips", "collection_runs", "discovery_checkpoints"):
            if db.execute(
                f"SELECT 1 FROM {table} WHERE game_id IS NOT ? LIMIT 1", (game,)
            ).fetchone():
                raise AuditError("unexpected_game_id")
        clips, first_clip = db.execute("SELECT COUNT(*), MIN(created_at) FROM clips").fetchone()
        observations, latest, max_id = db.execute(
            "SELECT COUNT(*), MAX(observed_at), MAX(snapshot_id) FROM clip_snapshots"
        ).fetchone()
        first_run = db.execute("SELECT MIN(window_start) FROM collection_runs").fetchone()[0]
        if (clips or first_run is not None) and not db.execute(
            "SELECT 1 FROM games WHERE game_id=?", (game,)
        ).fetchone():
            raise AuditError("missing_game_identity")
        first = min((parse_utc(t) for t in (first_clip, first_run) if t is not None), default=None)
        latest = parse_utc(latest) if latest is not None else None
        if observations and (
            not clips
            or latest is None
            or latest > datetime.now(UTC)
            or db.execute("""
                SELECT 1 FROM clip_snapshots s
                WHERE NOT EXISTS (SELECT 1 FROM clips c WHERE c.clip_id=s.clip_id) LIMIT 1
            """).fetchone()
        ):
            raise AuditError("invalid_observation_source")
        return cls(db, clips, observations, latest, max_id, midnight(first) if first else None)

    def counts(self, watermark: datetime | None) -> dict:
        counts = {"clips_at_snapshot": self.clips, "observations_at_snapshot": self.observations}
        if watermark is None:
            return counts | {"clips_at_watermark": None, "observations_at_watermark": None}
        clips = self.db.execute(
            "SELECT COUNT(*) FROM clips WHERE first_seen_at<=?", (to_utc_iso(watermark),)
        ).fetchone()[0]
        observations = self.observations
        if watermark != self.latest:
            observations = self.db.execute(
                "SELECT COUNT(*) FROM clip_snapshots WHERE observed_at<=?", (to_utc_iso(watermark),)
            ).fetchone()[0]
        return counts | {
            "clips_at_watermark": clips,
            "observations_at_watermark": observations,
            "clips_first_seen_after_watermark": self.clips - clips,
        }


@dataclass
class Pool:
    labels: Counter = field(default_factory=Counter)
    cutoffs: dict[int, Counter] = field(default_factory=lambda: {m: Counter() for m in CUTOFFS})
    matched: int = 0
    observations: int = 0
    discovery_delays: Counter = field(default_factory=Counter)
    elapsed_targets: Counter = field(default_factory=Counter)
    first_value: int | None = None
    varied: bool = False

    def add(
        self, rows: list[dict], label: dict, observations: int, delay_bin: int, due_targets: int
    ) -> None:
        self.observations += observations
        self.discovery_delays[delay_bin] += 1
        self.elapsed_targets[due_targets] += 1
        status = label["outcome_status"]
        self.labels[status] += 1
        for row in rows:
            counts = self.cutoffs[row["cutoff_minutes"]]
            counts[row["feature_status"]] += 1
            if row["feature_status"] == "eligible":
                counts["two_observations"] += row["observation_count"] >= 2
                counts["fresh_within_5m"] += row["staleness_seconds"] <= 300
                counts["eligible_mature"] += status != "immature"
                counts[f"outcome:{status}"] += 1
                counts["eligible_valid_label"] += status == "valid"
                counts["eligible_valid_two_observations"] += (
                    status == "valid" and row["observation_count"] >= 2
                )
                counts["eligible_valid_fresh_within_5m"] += (
                    status == "valid" and row["staleness_seconds"] <= 300
                )
        if status == "valid" and all(row["feature_status"] == "eligible" for row in rows):
            self.matched += 1
            if self.first_value is None:
                self.first_value = label["views_24h"]
            self.varied |= self.first_value != label["views_24h"]

    def report(self) -> dict:
        clips = sum(self.labels.values())
        mature = clips - self.labels["immature"]
        return {
            "clips": clips,
            "observations": self.observations,
            "mature_outcomes": mature,
            "valid_labels": self.labels["valid"],
            "valid_label_fraction_of_mature": fraction(self.labels["valid"], mature),
            "outcome_status": {key: self.labels[key] for key in LABEL_STATES},
            "matched_all_cutoffs": self.matched,
            "matched_all_cutoffs_fraction_of_mature": fraction(self.matched, mature),
            "matched_outcomes_varied": self.varied,
            "discovery_delay_bins": [
                {"upper_inclusive_seconds": bound, "clips": self.discovery_delays[index]}
                for index, bound in enumerate((*DELAY_BOUNDS, None))
            ],
            "cutoffs": {str(m): cutoff_report(counts) for m, counts in self.cutoffs.items()},
        }


def fraction(num: int, denom: int) -> float | None:
    return num / denom if denom else None


def cutoff_report(counts: Counter) -> dict:
    elapsed = sum(counts[key] for key in FEATURE_STATES if key != "cutoff_immature")
    return {
        "feature_status": {key: counts[key] for key in FEATURE_STATES},
        "elapsed_cutoffs": elapsed,
        "eligible_fraction_of_elapsed": fraction(counts["eligible"], elapsed),
        "missing_feature_fraction_of_elapsed": fraction(elapsed - counts["eligible"], elapsed),
        "eligible_mature_outcomes": counts["eligible_mature"],
        "matched_at_cutoff": counts["eligible_valid_label"],
        "matched_fraction_of_elapsed": fraction(counts["eligible_valid_label"], elapsed),
        "outcome_status_among_eligible": {key: counts[f"outcome:{key}"] for key in LABEL_STATES},
        "valid_label_fraction_of_eligible_mature": fraction(
            counts["eligible_valid_label"], counts["eligible_mature"]
        ),
        "eligible_two_observations": counts["two_observations"],
        "eligible_fresh_within_5m": counts["fresh_within_5m"],
        "labeled_two_observations": counts["eligible_valid_two_observations"],
        "labeled_fresh_within_5m": counts["eligible_valid_fresh_within_5m"],
    }


def audit_clips(
    db: sqlite3.Connection,
    game: str,
    start: datetime,
    end: datetime,
    watermark: datetime,
    deadline: float,
) -> tuple[Pool, dict[datetime, Pool]]:
    total = Pool()
    daily = defaultdict(Pool)
    parameters = {
        "game": game,
        "start": to_utc_iso(start),
        "end": to_utc_iso(end),
        "watermark": to_utc_iso(watermark),
    }
    for row in db.execute(LABEL_QUERY, parameters):
        check_deadline(deadline)
        clip = Clip(
            row["clip_id"],
            game,
            parse_utc(row["created_at"]),
            parse_utc(row["first_seen_at"]),
            None,
        )
        if clip.first_seen < clip.created:
            raise AuditError("first_seen_before_creation")
        snapshots = [
            Observation(i, parse_utc(at), views)
            for i, at, views in db.execute(
                """
                SELECT snapshot_id, observed_at, view_count FROM clip_snapshots
                WHERE clip_id=? AND observed_at BETWEEN ? AND ?
                ORDER BY observed_at, snapshot_id LIMIT ?
                """,
                (
                    clip.clip_id,
                    to_utc_iso(clip.first_seen),
                    to_utc_iso(min(watermark, clip.created + timedelta(minutes=max(CUTOFFS)))),
                    MAX_EARLY + 1,
                ),
            )
        ]
        if len(snapshots) > MAX_EARLY:
            raise AuditError("early_observation_limit_exceeded")
        label = outcome(clip, row if row["job_id"] is not None else None, watermark)
        rows = [candidate(clip, snapshots, m, watermark, ()) for m in CUTOFFS]
        delay_bin = bisect_left(DELAY_BOUNDS, (clip.first_seen - clip.created).total_seconds())
        due = bisect_right(TARGET_AGES_SECONDS, (watermark - clip.created).total_seconds())
        total.add(rows, label, row["observations"], delay_bin, due)
        daily[midnight(clip.created)].add(rows, label, row["observations"], delay_bin, due)
    return total, daily


def daily_discoveries(db, game: str, start: str, end: str, watermark: str) -> dict[str, int]:
    return dict(
        db.execute(
            """
            SELECT substr(first_seen_at,1,10), COUNT(*) FROM clips
            WHERE game_id=? AND first_seen_at>=? AND first_seen_at<? AND first_seen_at<=?
            GROUP BY substr(first_seen_at,1,10)
            """,
            (game, start, end, watermark),
        )
    )


def daily_scheduled_jobs(db, game: str, start: str, end: str, watermark: str) -> dict:
    daily = defaultdict(lambda: defaultdict(Counter))
    rows = db.execute(
        """
        SELECT substr(c.created_at,1,10) AS day, j.target_age_seconds,
               CASE
                   WHEN j.completed_at IS NULL OR j.completed_at>:watermark
                       THEN 'no_observation_at_watermark'
                   WHEN j.status='missed' THEN 'missed_before_discovery'
                   WHEN j.status='unavailable' THEN 'unavailable'
                   WHEN j.status='completed' AND s.clip_id=c.clip_id AND s.source='scheduled'
                        AND s.observed_at=j.completed_at AND s.observed_at>=j.due_at
                        AND (s.target_age_seconds IS NULL OR s.target_age_seconds=j.target_age_seconds)
                       THEN 'recorded'
                   WHEN j.status='completed' THEN 'invalid_link'
                   ELSE 'no_observation_at_watermark'
               END AS result, COUNT(*)
        FROM clips c JOIN jobs j ON j.clip_id=c.clip_id AND j.job_type='view_snapshot'
        LEFT JOIN clip_snapshots s ON s.snapshot_id=j.snapshot_id
        WHERE c.game_id=:game AND c.created_at>=:start AND c.created_at<:end
          AND c.first_seen_at<=:watermark AND j.due_at<=:watermark
          AND j.target_age_seconds IN (600,1800,3600,21600,86400)
        GROUP BY day, j.target_age_seconds, result
        """,
        {"game": game, "start": start, "end": end, "watermark": watermark},
    )
    for day, target, status, count in rows:
        daily[day][str(target)][status] = count
    return daily


def scheduled_report(pool: Pool, jobs: dict) -> dict:
    result = {}
    for index, target in enumerate(TARGET_AGES_SECONDS, 1):
        expected = sum(count for elapsed, count in pool.elapsed_targets.items() if elapsed >= index)
        counts = jobs.get(str(target), Counter())
        result[str(target)] = {
            "expected_due": expected,
            "job_rows_due": counts.total(),
            "without_due_job_row": max(0, expected - counts.total()),
            **counts,
        }
    return result


def append_interval(spans: list[tuple[datetime, datetime]], start: datetime, end: datetime) -> None:
    if spans and start <= spans[-1][1]:
        spans[-1] = spans[-1][0], max(spans[-1][1], end)
    else:
        spans.append((start, end))


def seconds(spans: list[tuple[datetime, datetime]]) -> float:
    return sum((end - start).total_seconds() for start, end in spans)


@dataclass
class DiscoveryDay:
    spans: dict[str, list] = field(default_factory=lambda: defaultdict(list))
    runs: Counter = field(default_factory=Counter)

    def report(self) -> dict:
        verified = self.spans["legacy_success"]
        combined = []
        for start, end in sorted(verified + self.spans["problem"]):
            append_interval(combined, start, end)
        return {
            "seconds_by_evidence": {key: seconds(spans) for key, spans in self.spans.items()},
            "attempted_seconds": seconds(self.spans["attempted"]),
            "legacy_success_seconds": seconds(verified),
            "unscanned_seconds": 86400 - seconds(self.spans["attempted"]),
            "unresolved_problem_seconds": seconds(combined) - seconds(verified),
            "known_incomplete_seconds": seconds(self.spans["known_incomplete"]),
            "runs_by_kind": dict(self.runs),
        }


def discovery(
    db: sqlite3.Connection,
    game: str,
    start: datetime,
    end: datetime,
    watermark: datetime,
    deadline: float,
) -> tuple[dict[datetime, DiscoveryDay], dict]:
    ledger = (
        db.execute("""
        SELECT 1 FROM sqlite_schema WHERE type='table' AND name='gta_vi_scan_attempts'
    """).fetchone()
        is not None
    )
    extra = "a.lane, a.outcome" if ledger else "NULL, NULL"
    join = "LEFT JOIN gta_vi_scan_attempts a USING (run_id)" if ledger else ""
    daily = defaultdict(DiscoveryDay)
    lane_watermarks = dict.fromkeys(LANES)
    usable_watermarks = dict.fromkeys(LANES)
    lane_outcomes = {lane: Counter() for lane in LANES}
    rows = db.execute(
        f"""
        SELECT r.window_start, r.window_end, r.status, r.potentially_truncated,
               r.error_summary IS NOT NULL, r.request_count, r.pages_seen, {extra}
        FROM collection_runs r {join}
        WHERE r.game_id=? AND r.finished_at<=? AND r.window_start<? AND r.window_end>?
        ORDER BY r.window_start LIMIT ?
        """,
        (game, to_utc_iso(watermark), to_utc_iso(end), to_utc_iso(start), MAX_DISCOVERY_RUNS + 1),
    )
    for index, row in enumerate(rows):
        check_deadline(deadline)
        if index == MAX_DISCOVERY_RUNS:
            raise AuditError("discovery_run_limit_exceeded")
        left, right, status, flagged, error, requested, pages, lane, result = row
        left, right = parse_utc(left), parse_utc(right)
        if left >= right or (status == "scanned" and lane is None):
            raise AuditError("invalid_discovery_window_or_ledger")
        kinds = []
        if requested > 0:
            kinds.append("attempted")
        if lane is not None:
            if lane not in LANES or result not in SCAN_OUTCOMES:
                raise AuditError("invalid_discovery_lane_or_outcome")
            lane_outcomes[lane][result] += 1
            if requested > 0:
                previous = lane_watermarks[lane]
                lane_watermarks[lane] = max(previous, right) if previous else right
                if pages > 0 and result != "error":
                    previous = usable_watermarks[lane]
                    usable_watermarks[lane] = max(previous, right) if previous else right
                    kinds.append("usable_structural_attempt")
            kinds.append(f"{lane}:{result}")
            if result == "known_incomplete":
                kinds.append("known_incomplete")
        elif status == "completed" and not flagged and not error and requested > 0:
            kinds.append("legacy_success")
        if status == "error" or error:
            kinds.extend(("error", "problem"))
        elif status == "partial" or flagged:
            kinds.extend(("partial", "problem"))
        left, right = max(left, start), min(right, end)
        while left < right:
            check_deadline(deadline)
            day = midnight(left)
            stop = min(day + DAY, right)
            for kind in kinds:
                append_interval(daily[day].spans[kind], left, stop)
                daily[day].runs[kind] += 1
            left = stop
    checkpoint = db.execute(
        "SELECT watermark FROM discovery_checkpoints WHERE game_id=?", (game,)
    ).fetchone()
    return daily, {
        "structural_ledger_present": ledger,
        "stored_legacy_checkpoint_at_snapshot": to_utc_iso(parse_utc(checkpoint[0]))
        if checkpoint
        else None,
        "lane_window_end_max_in_audit": {
            lane: to_utc_iso(value) if value else None for lane, value in lane_watermarks.items()
        },
        "lane_usable_window_end_max_in_audit": {
            lane: to_utc_iso(value) if value else None for lane, value in usable_watermarks.items()
        },
        "lane_run_outcomes_in_audit": lane_outcomes,
        "twitch_population_completeness": "UNKNOWN",
    }


def discovery_exclusions(windows: dict) -> list[str]:
    reasons = []
    if windows["known_incomplete_seconds"] or windows["unresolved_problem_seconds"]:
        reasons.append("unresolved_discovery_problem")
    if windows["legacy_success_seconds"] < DAY.total_seconds():
        reasons.append("insufficient_discovery_coverage_evidence")
    return reasons


def day_exclusions(day: datetime, watermark: datetime, outages, windows: dict) -> list[str]:
    maturity = day + DAY + MATURITY
    reasons = []
    if maturity > watermark:
        reasons.append("utc_day_not_fully_mature")
    if any(start < maturity and stop > day for start, stop in outages):
        reasons.append("declared_outage_in_creation_or_observation_period")
    return reasons + discovery_exclusions(windows)


def primary_discovery_evidence(
    db: sqlite3.Connection, selection: Selection, watermark: datetime, games: tuple[str, ...]
) -> dict:
    # Runs in the export's read transaction, at the exact feature/label watermark.
    deadline = time.monotonic() + 15
    result = {"policy": DISCOVERY_POLICY, "status": "VERIFIED", "game_days": []}
    db.set_progress_handler(lambda: time.monotonic() >= deadline, 10_000)
    try:
        for game in sorted(set(games)):
            days, _ = discovery(db, game, selection.start, selection.end, watermark, deadline)
            for day, evidence in sorted(days.items()):
                if (
                    selection.start <= day
                    and day + DAY <= selection.end
                    and not day_exclusions(day, watermark, selection.outages, evidence.report())
                ):
                    result["game_days"].append({"game_id": game, "day_utc": day.date().isoformat()})
    except (AuditError, sqlite3.Error, ValueError) as exc:
        return result | {"status": "UNKNOWN", "game_days": [], "reason": error_code(exc, deadline)}
    finally:
        db.set_progress_handler(None, 0)
    return result


def split_options(days: list[datetime], matched: list[int], deadline: float) -> dict:
    targets = {"software": ((MIN_DAYS,) * 3, 0), "experiment": ((7, 3, 7), 500)}
    result = {
        name: {
            "required_days": dict(zip(("train", "validation", "test"), minimum, strict=True)),
            "required_test_matched": labels,
            "feasible_boundary_pairs": 0,
            "example": None,
        }
        for name, (minimum, labels) in targets.items()
    }
    if len(days) < 2:
        return result

    best = {}
    prefix = [0]
    for count in matched:
        prefix.append(prefix[-1] + count)
    validation = days[0] + DAY
    while validation < days[-1]:
        check_deadline(deadline)
        train = bisect_right(days, validation - DAY - MATURITY)
        val_start = bisect_left(days, validation)
        test = validation + DAY
        while test <= days[-1]:
            val = max(0, bisect_right(days, test - DAY - MATURITY) - val_start)
            test_start = bisect_left(days, test)
            counts = (train, val, len(days) - test_start)
            labels = prefix[-1] - prefix[test_start]
            for name, (minimum, min_labels) in targets.items():
                day_gap = sum(
                    max(0, want - have) for want, have in zip(minimum, counts, strict=True)
                )
                label_gap = max(0, min_labels - labels)
                result[name]["feasible_boundary_pairs"] += day_gap == label_gap == 0
                rank = (day_gap, label_gap, -sum(counts), -labels)
                if name not in best or rank < best[name]:
                    best[name] = rank
                    result[name]["example"] = {
                        "validation_start": to_utc_iso(validation),
                        "test_start": to_utc_iso(test),
                        "days": dict(zip(("train", "validation", "test"), counts, strict=True)),
                        "matched": {
                            "train": prefix[train],
                            "validation": prefix[val_start + val] - prefix[val_start],
                            "test": labels,
                        },
                    }
            test += DAY
        validation += DAY
    return result


def audit_game(
    source: Source,
    game: str,
    start: datetime,
    end: datetime,
    watermark: datetime,
    outages: list[tuple[datetime, datetime]],
    deadline: float,
) -> dict:
    pool, daily = audit_clips(source.db, game, start, end, watermark, deadline)
    coverage, ledger = discovery(source.db, game, start, end, watermark, deadline)
    bounds = to_utc_iso(start), to_utc_iso(end), to_utc_iso(watermark)
    discoveries = daily_discoveries(source.db, game, *bounds)
    jobs = daily_scheduled_jobs(source.db, game, *bounds)
    days, matched, report = [], [], []
    day = start
    while day < end:
        check_deadline(deadline)
        cohort = daily.get(day, Pool())
        windows = coverage.get(day, DiscoveryDay()).report()
        mature = day + DAY + MATURITY <= watermark
        reasons = day_exclusions(day, watermark, outages, windows)
        if not cohort.labels:
            reasons.append("no_clips")
        elif not cohort.labels["valid"]:
            reasons.append("no_valid_labels")
        if cohort.matched < MIN_POOL:
            reasons.append("insufficient_matched_labels")
        elif not cohort.varied:
            reasons.append("no_matched_label_variation")
        if cohort.labels["invalid_link"]:
            reasons.append("invalid_label_links")
        if not reasons:
            days.append(day)
            matched.append(cohort.matched)
        day_key = day.date().isoformat()
        report.append(
            {
                "day_utc": day_key,
                "fully_mature_at": to_utc_iso(day + DAY + MATURITY),
                "fully_mature": mature,
                "admissible": not reasons,
                "exclusion_reasons": reasons,
                "first_seen_this_utc_day": discoveries.get(day_key, 0),
                "scheduled_jobs_due_by_target_seconds": scheduled_report(
                    cohort, jobs.get(day_key, {})
                ),
                "discovery": windows,
                **cohort.report(),
            }
        )
        day += DAY

    splits = split_options(days, matched, deadline)
    if pool.labels["invalid_link"]:
        decision, reason = "NO-GO", "invalid_label_links_in_audit_range"
    elif splits["software"]["feasible_boundary_pairs"]:
        decision, reason = "GO", "software_minimum_met"
    else:
        decision, reason = "PARTIAL", "insufficient_admissible_split"
    return {
        "status": "VERIFIED",
        "decision": decision,
        "decision_reason": reason,
        "cohort_watermark": to_utc_iso(watermark),
        "totals": source.counts(watermark),
        "cohort": pool.report(),
        "discovery": ledger,
        "days": report,
        "admissible_days": len(days),
        "matched_all_cutoffs_on_admissible_days": sum(matched),
        "matched_fraction_on_admissible_days_of_mature": fraction(
            sum(matched), sum(pool.labels.values()) - pool.labels["immature"]
        ),
        "splits": splits,
        "declared_outages": [[to_utc_iso(a), to_utc_iso(b)] for a, b in outages],
    }


def error_code(exc: Exception, deadline: float) -> str:
    if isinstance(exc, AuditError):
        return str(exc)
    if (
        time.monotonic() >= deadline
        or getattr(exc, "sqlite_errorcode", None) == sqlite3.SQLITE_INTERRUPT
    ):
        return "deadline_exceeded"
    if isinstance(exc, FileNotFoundError):
        return "database_or_required_sidecar_missing"
    if isinstance(exc, PermissionError):
        return "filesystem_access_denied"
    if isinstance(exc, (ValueError, TypeError, OverflowError)):
        return "invalid_stored_data"
    return "sqlite_or_filesystem_read_error"


AUDIT_EXCEPTIONS = (AuditError, OSError, sqlite3.Error, ValueError, TypeError, OverflowError)


def failed(game: str, reason: str) -> dict:
    return {
        "game_id": GAMES[game],
        "status": "UNKNOWN",
        "decision": "NO-GO",
        "decision_reason": reason,
    }


def readiness_sample(db: sqlite3.Connection, game: str) -> tuple[int, datetime]:
    if [r[0] for r in db.execute("SELECT game_id FROM games")] != [game]:
        raise AuditError("unexpected_game_id")
    row = db.execute(
        """
        SELECT s.snapshot_id,s.observed_at,c.game_id
        FROM clip_snapshots s LEFT JOIN clips c USING(clip_id)
        ORDER BY s.snapshot_id DESC LIMIT 1
        """
    ).fetchone()
    if row is None:
        raise AuditError("no_observation_watermark")
    snapshot_id, observed, actual_game = row
    watermark = parse_utc(observed)
    if watermark > datetime.now(UTC) or game != actual_game:
        raise AuditError("invalid_observation_source")
    return snapshot_id, watermark


def readiness_game(db, game, start, end, watermark, outages, deadline) -> dict:
    daily, ledger = discovery(db, game, start, end, watermark, deadline)
    days = []
    possible = []
    for offset in range((end - start).days):
        day = start + offset * DAY
        windows = daily.get(day, DiscoveryDay()).report()
        reasons = day_exclusions(day, watermark, outages, windows)
        if not reasons:
            possible.append(day)
        days.append(
            {
                "day_utc": day.date().isoformat(),
                "fully_mature_at": to_utc_iso(day + DAY + MATURITY),
                "calendar_candidate": not reasons,
                "exclusion_reasons": reasons,
                "discovery": windows,
            }
        )
    pairs = split_options(possible, [0] * len(possible), deadline)["software"][
        "feasible_boundary_pairs"
    ]
    return {
        "days": days,
        "discovery": ledger,
        "calendar_candidates": len(possible),
        "potential_split_pairs": pairs,
        "matched_and_validated_days": None,
        "next_action": "AUDIT_SEALED_SOURCES" if pairs else "WAIT_FOR_COVERED_MATURE_DAYS",
    }


def add_readiness(args: argparse.Namespace, payload: dict, deadline: float) -> dict:
    reports = payload["games"]
    payload["mode"] = "readiness"
    with ExitStack() as stack:
        sources = {}
        for game, path in zip(GAMES, (args.gta_v, args.gta_vi), strict=True):
            try:
                db = open_snapshot(stack, path, deadline)
                sources[game] = db, *readiness_sample(db, GAMES[game])
            except AUDIT_EXCEPTIONS as exc:
                reports[game] = failed(game, error_code(exc, deadline))
        common = min(s[2] for s in sources.values()) if len(sources) == len(GAMES) else None
        if common:
            payload.update(common_watermark=to_utc_iso(common), watermark_status="COMMON")
        for game, (db, snapshot_id, observed) in sources.items():
            watermark = common or observed
            end = args.end or midnight(watermark) + DAY
            start = args.start or end - READINESS_DAYS * DAY
            try:
                if not 0 < (end - start).days <= MAX_DAYS:
                    raise AuditError("invalid_or_oversized_audit_range")
                reports[game] = {
                    "game_id": GAMES[game],
                    "status": "VERIFIED",
                    "decision": "PARTIAL",
                    "decision_reason": "calendar_prerequisites_only",
                    "max_snapshot_id_at_snapshot": snapshot_id,
                    "cohort_watermark": to_utc_iso(watermark),
                    "watermark_basis": "common_latest_appended"
                    if common
                    else "individual_latest_appended",
                    **readiness_game(
                        db, GAMES[game], start, end, watermark, args.outage[game], deadline
                    ),
                }
                if common is None:
                    reports[game]["next_action"] = "VERIFY_BOTH_SOURCES"
            except AUDIT_EXCEPTIONS as exc:
                reports[game] = failed(game, error_code(exc, deadline))
        for game, (db, _, observed) in sources.items():
            if args.quality_day is None or reports[game]["status"] != "VERIFIED":
                continue
            try:
                if db.execute("PRAGMA journal_mode").fetchone()[0] == "wal":
                    raise AuditError("quality_probe_requires_sealed_source")
                day = args.quality_day
                pool, _ = audit_clips(db, GAMES[game], day, day + DAY, common or observed, deadline)
                reports[game]["quality_day"] = {
                    "status": "VERIFIED",
                    "day_utc": day.date().isoformat(),
                    **pool.report(),
                }
            except AUDIT_EXCEPTIONS as exc:
                reports[game]["quality_day"] = {
                    "status": "UNKNOWN",
                    "reason": error_code(exc, deadline),
                }
    return payload


def run_audit(args: argparse.Namespace) -> dict:
    started = datetime.now(UTC)
    deadline = time.monotonic() + args.timeout
    payload = {
        "version": 1,
        "sample_started_at": to_utc_iso(started),
        "common_watermark": None,
        "watermark_status": "UNKNOWN",
        "games": {},
    }
    reports = payload["games"]
    try:
        if sys.platform == "linux":
            deny_fs_writes()
        elif sys.platform != "win32":
            raise AuditError("unsupported_filesystem_guard_platform")
        if args.verify_support:
            hashes = [
                hashlib.sha256(
                    Path(module.__file__).read_bytes().replace(b"\r\n", b"\n")
                ).hexdigest()
                for module in (dataset, evaluation)
            ]
            if hashes != args.verify_support:
                raise AuditError("support_module_hash_mismatch")
    except AUDIT_EXCEPTIONS as exc:
        reports.update({game: failed(game, error_code(exc, deadline)) for game in GAMES})
        return payload

    if getattr(args, "readiness", False):
        return add_readiness(args, payload, deadline)

    with ExitStack() as stack:
        sources = {}
        # Pin both read transactions before scanning either database.
        opened = {}
        for game, path in zip(GAMES, (args.gta_v, args.gta_vi), strict=True):
            try:
                opened[game] = open_snapshot(stack, path, deadline)
            except AUDIT_EXCEPTIONS as exc:
                reports[game] = failed(game, error_code(exc, deadline))
        for game, db in opened.items():
            try:
                sources[game] = Source.inspect(db, GAMES[game])
            except AUDIT_EXCEPTIONS as exc:
                reports[game] = failed(game, error_code(exc, deadline))

        latest = {game: src.latest for game, src in sources.items() if src.latest is not None}
        common = min(latest.values()) if len(latest) == len(GAMES) else None
        if common is not None:
            payload.update(common_watermark=to_utc_iso(common), watermark_status="COMMON")
        first_day = min((s.first_day for s in sources.values() if s.first_day), default=None)
        for game, source in sources.items():
            details = {
                "game_id": GAMES[game],
                "source_schema": 2,
                "individual_watermark": to_utc_iso(source.latest) if source.latest else None,
                "max_snapshot_id_at_snapshot": source.max_snapshot_id,
            }
            watermark = common or source.latest
            if watermark is None:
                reports[game] = details | {
                    "status": "UNKNOWN",
                    "decision": "PARTIAL",
                    "decision_reason": "no_observation_watermark",
                    "totals": source.counts(None),
                    "cohort": None,
                    "days": None,
                    "splits": None,
                }
                continue
            start = args.start or first_day or midnight(watermark)
            end = args.end or midnight(watermark) + DAY
            try:
                if not 0 < (end - start).days <= MAX_DAYS:
                    raise AuditError("invalid_or_oversized_audit_range")
                reports[game] = (
                    details
                    | {
                        "creation_start": to_utc_iso(start),
                        "creation_end_exclusive": to_utc_iso(end),
                        "watermark_basis": "common" if common else "individual_only",
                    }
                    | audit_game(
                        source, GAMES[game], start, end, watermark, args.outage[game], deadline
                    )
                )
            except AUDIT_EXCEPTIONS as exc:
                reports[game] = details | failed(game, error_code(exc, deadline))
    return payload


def utc_day(value: str) -> datetime:
    return datetime.combine(date.fromisoformat(value), datetime.min.time(), tzinfo=UTC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gta-v", type=Path, required=True)
    parser.add_argument("--gta-vi", type=Path, required=True)
    parser.add_argument("--start", type=utc_day, help="Inclusive UTC creation date, YYYY-MM-DD")
    parser.add_argument("--end", type=utc_day, help="Exclusive UTC creation date, YYYY-MM-DD")
    parser.add_argument("--outage", nargs=3, action="append", metavar=("GAME", "START", "END"))
    parser.add_argument("--timeout", type=int, default=30, help="Overall audit deadline in seconds")
    parser.add_argument(
        "--readiness", action="store_true", help="Scan coverage and maturity prerequisites only"
    )
    parser.add_argument(
        "--quality-day",
        type=utc_day,
        help="Optional single UTC day of clip metrics on sealed sources",
    )
    parser.add_argument(
        "--verify-support", nargs=2, metavar=("DATASET_SHA256", "EVALUATION_SHA256")
    )
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 120:
        parser.error("--timeout must be between 1 and 120 seconds")
    if args.start and args.end and not 0 < (args.end - args.start).days <= MAX_DAYS:
        parser.error("UTC creation interval must contain between 1 and 366 days")
    if args.quality_day is not None and not args.readiness:
        parser.error("--quality-day requires --readiness")
    outages = {game: [] for game in GAMES}
    try:
        for game, start, end in args.outage or []:
            a, b = parse_utc(start), parse_utc(end)
            if a >= b:
                raise ValueError
            outages[game].append((a, b))
    except (KeyError, ValueError):
        parser.error("--outage requires gta-v or gta-vi and increasing offset-aware timestamps")
    args.outage = outages
    report = run_audit(args)
    for game, summary in report["games"].items():
        print(
            f"{game}: {summary['decision']} ({summary['decision_reason']}); "
            f"admissible UTC days: {summary.get('admissible_days', 'UNKNOWN')}",
            file=sys.stderr,
        )
    print(json.dumps(report, indent=2, allow_nan=False))
    return 2 if any(r["decision"] == "NO-GO" for r in report["games"].values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
