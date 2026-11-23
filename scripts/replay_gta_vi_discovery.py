"""Compare GTA VI discovery policies on deterministic synthetic Helix responses."""

from __future__ import annotations

import argparse
import json
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from viralclip.collector import service
from viralclip.config import GtaViOverlap
from viralclip.storage.database import Database
from viralclip.storage.discovery import BUCKET, bucket_start
from viralclip.twitch.client import TwitchClient

EPOCH = datetime(2026, 11, 20, 23, tzinfo=UTC)
GAME = service.GTA_VI_GAME_ID
MINUTE = timedelta(minutes=1)
HALF = 5 * MINUTE
CUTOFFS = (10, 30, 35, 60, 65)
SCENARIOS = ("minute_bounds", "rounded_bounds", "persistent_omissions")
STRATEGIES = ("A", "B", "C")


class ReplayHelix:
    parse_data = staticmethod(TwitchClient.parse_data)
    parse_cursor = staticmethod(TwitchClient.parse_cursor)

    def __init__(self, scenario: str, request_ms: int, density: int):
        self.scenario = scenario
        self.request_cost = timedelta(milliseconds=request_ms)
        self.now = EPOCH
        self.requests = 0
        self.clips = []
        for minute in range(30):
            for index in range(density):
                created = EPOCH + minute * MINUTE + timedelta(seconds=index % 60)
                payload = {
                    "id": f"{minute}-{index}",
                    "game_id": GAME,
                    "created_at": created.isoformat(),
                    "view_count": 10_000 - minute * density - index,
                }
                delay = (0, 0, 0, 0, 2, 2, 12, 38)[index % 8]
                permanently_omitted = scenario == "persistent_omissions" and index % 20 == 0
                self.clips.append((created, created + delay * MINUTE, payload, permanently_omitted))

    def get_clips(self, *, game_id, started_at, ended_at, after, extra_timeout=None):
        assert game_id == GAME
        assert extra_timeout is None or extra_timeout > self.request_cost.total_seconds()
        self.requests += 1
        self.now += self.request_cost
        # The rounded case models the documented live counterexample, without replaying private IDs.
        if self.scenario == "rounded_bounds" and ended_at - started_at < BUCKET:
            started_at = bucket_start(started_at)
            ended_at = started_at + BUCKET
        candidates = [
            row
            for created, visible, row, hidden in self.clips
            if started_at <= created < ended_at and visible <= self.now and not hidden
        ]
        ranked = sorted(candidates, key=lambda row: -row["view_count"])[:1000]
        offset = int(after or 0)
        next_offset = offset + 100
        return {
            "data": ranked[offset:next_offset],
            "pagination": {"cursor": str(next_offset)} if next_offset < len(ranked) else {},
        }


class ReplayCollector(service.Collector):
    def __init__(self, db, twitch, *, split: bool, pages: int):
        super().__init__(
            db,
            twitch,
            clock=lambda: twitch.now,
            monotonic=lambda: (twitch.now - EPOCH).total_seconds(),
            gta_vi_overlap=GtaViOverlap(pages=pages),
        )
        self.split = split

    def collect_due_snapshots(self):
        # This isolates discovery. Refresh and transport retries are excluded from the estimate.
        return 0

    def _scan_gta_vi(self, game_id, start, end, lane, budget, *, query_window=None, extra_pages=0):
        if lane != "recent" or not self.split:
            return super()._scan_gta_vi(
                game_id,
                start,
                end,
                lane,
                budget,
                query_window=query_window,
                extra_pages=extra_pages,
            )
        query_start = bucket_start(start)
        midpoint = query_start + HALF
        if end <= midpoint:
            return super()._scan_gta_vi(
                game_id, start, end, lane, budget, query_window=(query_start, midpoint)
            )
        # Prioritize the newest half, reserve the other half's pages, and preserve the
        # original preceding-bucket overlap and separate history allocation.
        newest = super()._scan_gta_vi(
            game_id,
            midpoint,
            end,
            lane,
            (budget + 1) // 2,
            query_window=(midpoint, query_start + BUCKET),
        )
        oldest = super()._scan_gta_vi(
            game_id, start, midpoint, lane, budget // 2, query_window=(query_start, midpoint)
        )
        return newest + oldest


def run(scenario: str, strategy: str, request_ms: int, density: int, path: Path) -> dict:
    helix = ReplayHelix(scenario, request_ms, density)
    maximum_pages = 10 if strategy == "B" else 7
    cycle_counts = []
    start_wall = perf_counter()
    with closing(Database(path)) as db:
        db.upsert_game(GAME, "Synthetic GTA VI", EPOCH)
        db.update_watermark(GAME, EPOCH)
        collector = ReplayCollector(db, helix, split=strategy == "C", pages=maximum_pages)
        for minute in range(0, 116, 5):
            helix.now = EPOCH + minute * MINUTE + timedelta(seconds=30)
            before = helix.requests
            collector.discover(GAME)
            cycle_counts.append(helix.requests - before)
        q = db.connection.execute
        delays = [
            (datetime.fromisoformat(first) - datetime.fromisoformat(created)).total_seconds()
            for created, first in q("SELECT created_at,first_seen_at FROM clips ORDER BY clip_id")
        ]
        outcomes = dict(q("SELECT outcome,COUNT(*) FROM gta_vi_scan_attempts GROUP BY outcome"))
        distinct_across_runs = q("SELECT SUM(unique_clips) FROM collection_runs").fetchone()[0]
        repeats_on_wire = q("SELECT SUM(repeated) FROM gta_vi_scan_attempts").fetchone()[0]
        checkpoint = q("SELECT watermark FROM discovery_checkpoints").fetchone()[0]
    delays.sort()
    found = len(delays)
    return {
        "scenario": scenario,
        "strategy": strategy,
        "fixture_reference": len(helix.clips),
        "unique_found": found,
        "unfound": len(helix.clips) - found,
        "by_cutoff_minutes": {m: sum(delay <= m * 60 for delay in delays) for m in CUTOFFS},
        "latency_seconds_p50_p95_max": (
            [round(delays[(found * p + 99) // 100 - 1], 2) for p in (50, 95, 100)] if delays else []
        ),
        "discovery_pages": {
            "total": sum(cycle_counts),
            "max": max(cycle_counts),
            "mean": round(sum(cycle_counts) / len(cycle_counts), 2),
            "cycles": cycle_counts,
        },
        "estimated_max_http_seconds_per_cycle": round(max(cycle_counts) * request_ms / 1000, 2),
        "local_replay_seconds": round(perf_counter() - start_wall, 2),
        "outcomes": outcomes,
        "ids_reobserved_across_runs": distinct_across_runs - found,
        "wire_duplicate_rows_within_runs": repeats_on_wire,
        "legacy_checkpoint_unchanged": datetime.fromisoformat(checkpoint) == EPOCH,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--density", type=int, default=120, choices=range(1, 201), metavar="1–200")
    parser.add_argument(
        "--request-ms", type=int, default=250, choices=range(1, 1001), metavar="1–1000"
    )
    args = parser.parse_args()
    with TemporaryDirectory(prefix="viralclip-gta-vi-replay-") as directory:
        report = [
            run(
                scenario,
                strategy,
                args.request_ms,
                args.density,
                Path(directory) / f"{scenario}-{strategy}.db",
            )
            for scenario in SCENARIOS
            for strategy in STRATEGIES
        ]
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
