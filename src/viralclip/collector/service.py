from __future__ import annotations

import logging
import time
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from viralclip.config import DEFAULT_GTA_VI_OVERLAP, GTA_VI_OVERLAP_PAGES, GtaViOverlap
from viralclip.storage.database import Database, to_utc_iso, utc_now
from viralclip.storage.discovery import (
    BUCKET,
    bucket_start,
    ensure_scan_ledger,
    historical_retry,
    history_start,
)
from viralclip.twitch.client import TwitchAPIError, TwitchClient, TwitchRequestDeferred
from viralclip.twitch.clip_pages import view_order_warnings

GTA_VI_GAME_ID = "1867279146"
DISCOVERY_BUDGET = 20
OVERLAP = timedelta(minutes=5)
GTA_VI_RECENT_PAGES = 10
GTA_VI_HISTORY_PAGES = DISCOVERY_BUDGET - GTA_VI_RECENT_PAGES - GTA_VI_OVERLAP_PAGES
GTA_VI_RETRY_DELAY = timedelta(minutes=30)
HELIX_CLIP_RESULT_LIMIT = 1000
LOG = logging.getLogger(__name__)


class Collector:
    def __init__(
        self,
        database: Database,
        twitch: TwitchClient,
        *,
        lookback_minutes: int = 30,
        clock: Callable[[], datetime] = utc_now,
        monotonic: Callable[[], float] = time.monotonic,
        gta_vi_overlap: GtaViOverlap = DEFAULT_GTA_VI_OVERLAP,
        overlap_events: Callable[[dict[str, object]], None] | None = None,
    ):
        self.database = database
        self.twitch = twitch
        self.lookback_minutes = lookback_minutes
        self.clock = clock
        self.monotonic = monotonic
        self.gta_vi_overlap = gta_vi_overlap
        self.overlap_events = overlap_events
        self.database.acquire_collector_lock()
        self.database.recover_running_jobs()

    def resolve_game(self, name: str) -> str:
        now = self.clock()
        cached = self.database.cached_game(name, 30 * 86400, now)
        if cached:
            return cached["game_id"]
        matches = self.twitch.search_categories(name)
        exact = next(
            (item for item in matches if item.get("name", "").casefold() == name.casefold()),
            None,
        )
        if exact is None:
            raise TwitchAPIError(f"Twitch category not found: {name}")
        game_id = str(exact["id"])
        self.database.upsert_game(game_id, exact["name"], now)
        return game_id

    def discover(self, game_id: str) -> int:
        now = self.clock().astimezone(UTC)
        if game_id == GTA_VI_GAME_ID:
            return self._discover_gta_vi(game_id, now)
        end = now.replace(second=0, microsecond=0)
        start = end - timedelta(minutes=self.lookback_minutes)
        row = self.database.connection.execute(
            "SELECT watermark FROM discovery_checkpoints WHERE game_id = ?", (game_id,)
        ).fetchone()
        checkpoint = datetime.fromisoformat(row["watermark"]) if row else None
        if checkpoint is not None:
            start = min(start, checkpoint - OVERLAP)
        budget = [DISCOVERY_BUDGET]
        if checkpoint is None:
            self.database.update_watermark(game_id, start + OVERLAP)
        count, complete = self._discover_window(game_id, start, end, budget)
        if complete:
            self.database.update_watermark(game_id, end)
        return count

    def _discover_gta_vi(self, game_id: str, now: datetime) -> int:
        db = self.database.connection
        ensure_scan_ledger(db)
        current = bucket_start(now)
        previous = current - BUCKET
        frontier = history_start(db, game_id, previous)
        count = 0
        if now > current:
            count += self._scan_gta_vi(game_id, current, now, "recent", GTA_VI_RECENT_PAGES)
        count += self._scan_gta_vi(
            game_id,
            previous,
            current,
            "recent",
            GTA_VI_OVERLAP_PAGES,
            extra_pages=self.gta_vi_overlap.pages - GTA_VI_OVERLAP_PAGES,
        )
        if frontier < previous:
            end = min(bucket_start(frontier) + BUCKET, previous)
            count += self._scan_gta_vi(game_id, frontier, end, "history", GTA_VI_HISTORY_PAGES)
        else:
            retry = historical_retry(db, game_id, previous, now - GTA_VI_RETRY_DELAY)
            if retry:
                count += self._scan_gta_vi(game_id, *retry, "retry", GTA_VI_HISTORY_PAGES)
        return count

    def _scan_gta_vi(
        self,
        game_id: str,
        start: datetime,
        end: datetime,
        lane: str,
        budget: int,
        *,
        query_window: tuple[datetime, datetime] | None = None,
        extra_pages: int = 0,
    ) -> int:
        aligned_start = bucket_start(start)
        query_start, query_end = query_window or (aligned_start, aligned_start + BUCKET)
        if (
            not query_start <= start < end <= query_end
            or any(
                stamp.utcoffset() != timedelta(0) or stamp.second or stamp.microsecond
                for stamp in (query_start, query_end)
            )
            or not 0 < budget <= budget + extra_pages <= GTA_VI_RECENT_PAGES
        ):
            raise ValueError("Invalid discovery window or page budget")
        run = self.database.create_run(game_id, start, end, self.clock())
        cursor = None
        cursors: set[str] = set()
        wire_ids: dict[str, datetime] = {}
        unique_ids: set[str] = set()
        requested = pages = raw = pertinent = repeated = new = 0
        last_views = None
        rank_warnings: Counter = Counter()
        outcome = "page_limit" if budget == GTA_VI_RECENT_PAGES else "budget"

        def report_extra(page_number: int, result: str, **details: object) -> None:
            if self.overlap_events is not None:
                try:
                    self.overlap_events(
                        {
                            "event": "gta_vi_overlap_page",
                            "run_id": run,
                            "page": page_number,
                            "result": result,
                            **details,
                        }
                    )
                except Exception:  # noqa: BLE001
                    LOG.warning("GTA VI overlap page telemetry unavailable")

        def finish(error_summary: str | None = None) -> None:
            self.database.finish_run(
                run,
                self.clock(),
                requested,
                pages,
                raw,
                new,
                truncated=outcome not in ("cursor_exhausted", "error"),
                error=error_summary,
                unique=len(unique_ids),
                scan=(lane, outcome, pertinent, repeated),
            )
            if rank_warnings:
                LOG.warning(
                    "GTA VI discovery view order warning lane=%s within_page=%d between_pages=%d",
                    lane,
                    rank_warnings["view_order_in_page"],
                    rank_warnings["view_order_between_pages"],
                )

        try:
            deadline = None
            for index in range(budget + extra_pages):
                if index == budget:
                    deadline = self.monotonic() + self.gta_vi_overlap.extra_seconds
                self.collect_due_snapshots()
                timeout = None if deadline is None else deadline - self.monotonic()
                if timeout is not None and timeout <= 0:
                    report_extra(index + 1, "time_budget")
                    LOG.warning("GTA VI overlap extra pages stopped at their time budget")
                    break
                requested += 1
                try:
                    payload = self.twitch.get_clips(
                        game_id=game_id,
                        started_at=query_start,
                        ended_at=query_end,
                        after=cursor,
                        extra_timeout=timeout,
                    )
                except TwitchRequestDeferred:
                    requested -= 1
                    report_extra(index + 1, "auth_or_rate_budget")
                    LOG.warning("GTA VI overlap extra page deferred for Twitch auth or rate budget")
                    break
                page = self.twitch.parse_data(payload)
                if any(item.get("game_id", game_id) != game_id for item in page):
                    raise TwitchAPIError("Twitch discovery returned a different game category")
                pages += 1
                observed_at = self.clock()
                raw += len(page)
                prior_unique, prior_new = len(unique_ids), new
                new_wire_ids = False
                outside_query = False
                parsed = [self._parse_clip(item) for item in page]
                order, last_views = view_order_warnings(
                    (clip["view_count"] for clip in parsed), last_views
                )
                rank_warnings.update(order)
                for clip in parsed:
                    clip_id = clip["id"]
                    created = clip["created_at"]
                    if clip_id in wire_ids:
                        if wire_ids[clip_id] != created:
                            raise TwitchAPIError(
                                "Twitch discovery clip creation changed across pages"
                            )
                        repeated += 1
                    else:
                        wire_ids[clip_id] = created
                        new_wire_ids = True
                    if not query_start <= created < query_end:
                        outside_query = True
                    if start <= created < end:
                        pertinent += 1
                        if clip_id not in unique_ids:
                            unique_ids.add(clip_id)
                            new += self.database.record_clip(clip, game_id, observed_at, run)
                cursor = self.twitch.parse_cursor(payload)
                if index >= budget:
                    report_extra(
                        index + 1,
                        "received",
                        observed_at=to_utc_iso(observed_at),
                        additional_ids=len(unique_ids) - prior_unique,
                        new_to_db=new - prior_new,
                    )
                if outside_query or (cursor and (cursor in cursors or not new_wire_ids)):
                    outcome = "pagination_anomaly"
                    break
                if not cursor:
                    known = self.database.connection.execute(
                        """
                        SELECT clip_id FROM clips
                        WHERE game_id = ? AND created_at >= ? AND created_at < ?
                        """,
                        (game_id, to_utc_iso(start), to_utc_iso(end)),
                    )
                    if any(row[0] not in unique_ids for row in known):
                        outcome = "known_incomplete"
                    elif raw >= HELIX_CLIP_RESULT_LIMIT:
                        outcome = "page_limit"
                    else:
                        outcome = "cursor_exhausted"
                    break
                cursors.add(cursor)
        except Exception as exc:
            outcome = "error"
            finish(str(exc) if isinstance(exc, TwitchAPIError) else type(exc).__name__)
            raise
        finish()
        return new

    def _discover_window(
        self,
        game_id: str,
        start: datetime,
        end: datetime,
        budget: list[int],
    ) -> tuple[int, bool]:
        run_id = self.database.create_run(game_id, start, end, self.clock())
        pages = 0
        requests = 0
        seen = 0
        unique_ids: set[str] = set()
        new_count = 0
        truncated = False
        try:
            cursor = None
            while budget[0] > 0:
                self.collect_due_snapshots()
                requests += 1
                budget[0] -= 1
                payload = self.twitch.get_clips(
                    game_id=game_id, started_at=start, ended_at=end, after=cursor
                )
                pages += 1
                page = self.twitch.parse_data(payload)
                page_observed_at = self.clock()
                seen += len(page)
                for raw_clip in page:
                    clip = self._parse_clip(raw_clip)
                    unique_ids.add(clip["id"])
                    if self.database.record_clip(clip, game_id, page_observed_at, run_id):
                        new_count += 1
                cursor = self.twitch.parse_cursor(payload)
                if seen >= 900:
                    truncated = True
                    break
                if not cursor:
                    break
                if pages >= 10:
                    truncated = True
                    break
            else:
                truncated = True

            self.database.finish_run(
                run_id,
                self.clock(),
                requests,
                pages,
                seen,
                new_count,
                truncated,
                unique=len(unique_ids),
            )

            span = (end - start).total_seconds()
            if truncated and span >= 120 and budget[0] > 0:
                midpoint = start + (end - start) / 2
                midpoint = midpoint.replace(second=0, microsecond=0)
                if start < midpoint < end:
                    first, left_complete = self._discover_window(game_id, start, midpoint, budget)
                    second, right_complete = self._discover_window(game_id, midpoint, end, budget)
                    return new_count + first + second, left_complete and right_complete
            return new_count, not truncated
        except Exception as exc:
            self.database.finish_run(
                run_id,
                self.clock(),
                requests,
                pages,
                seen,
                new_count,
                truncated,
                str(exc),
                unique=len(unique_ids),
            )
            raise

    @staticmethod
    def _parse_clip(raw: dict) -> dict:
        try:
            if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not raw["id"]:
                raise ValueError("invalid clip ID")
            if type(raw.get("view_count")) is not int or raw["view_count"] < 0:
                raise ValueError("invalid view count")
            created_at = datetime.fromisoformat(raw["created_at"])
            if created_at.tzinfo is None or created_at.utcoffset() is None:
                raise ValueError("created_at must include a timezone")
            return {
                "id": str(raw["id"]),
                "created_at": created_at.astimezone(UTC),
                "view_count": int(raw["view_count"]),
                "broadcaster_id": str(raw["broadcaster_id"]) if raw.get("broadcaster_id") else None,
                "broadcaster_name": raw.get("broadcaster_name"),
                "creator_id": str(raw["creator_id"]) if raw.get("creator_id") else None,
                "title": raw.get("title"),
                "url": raw.get("url"),
                "duration": float(raw["duration"]) if raw.get("duration") is not None else None,
                "language": raw.get("language"),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise TwitchAPIError("Twitch returned a clip with invalid required fields") from exc

    def collect_due_snapshots(self) -> int:
        due = self.database.due_jobs(self.clock())
        grouped: dict[str, list] = {}
        for job in due:
            grouped.setdefault(job["clip_id"], []).append(job)
        clip_ids = list(grouped)
        completed = 0
        for offset in range(0, len(clip_ids), 100):
            batch = clip_ids[offset : offset + 100]
            batch_jobs = [job for clip_id in batch for job in grouped[clip_id]]
            job_ids = [int(job["job_id"]) for job in batch_jobs]
            self.database.start_jobs(job_ids)
            try:
                payload = self.twitch.get_clips(clip_ids=batch)
                page = self.twitch.parse_data(payload)
                if any(not isinstance(item.get("id"), str) or not item["id"] for item in page):
                    raise TwitchAPIError("Twitch returned invalid clip IDs")
                results = {str(item["id"]): item for item in page}
            except TwitchAPIError as exc:
                self.database.finish_jobs(job_ids, "failed", self.clock(), str(exc))
                continue

            observed_at = self.clock()
            for clip_id in batch:
                clip_jobs = grouped[clip_id]
                ids = [int(job["job_id"]) for job in clip_jobs]
                raw_clip = results.get(clip_id)
                if raw_clip is None:
                    self.database.finish_jobs(
                        ids, "unavailable", observed_at, "clip omitted from Twitch response"
                    )
                    continue
                try:
                    parsed = self._parse_clip(raw_clip)
                    target = (
                        int(clip_jobs[0]["target_age_seconds"]) if len(clip_jobs) == 1 else None
                    )
                    self.database.add_scheduled_snapshot(
                        clip_id, observed_at, parsed["view_count"], target, ids
                    )
                except (TwitchAPIError, ValueError) as exc:
                    self.database.finish_jobs(ids, "failed", observed_at, str(exc))
                    continue
                completed += len(ids)
        return completed

    def collect_cycle(self, games: tuple[str, ...], game_ids: tuple[str, ...] = ()) -> None:
        self.collect_due_snapshots()
        errors = []
        for name in games:
            try:
                self.discover(self.resolve_game(name))
            except TwitchAPIError as exc:
                self.database.record_error(self.clock(), str(exc))
                errors.append(exc)
        for game_id in game_ids:
            if not self.database.connection.execute(
                "SELECT 1 FROM games WHERE game_id = ?", (game_id,)
            ).fetchone():
                self.database.upsert_game(game_id, game_id, self.clock())
            try:
                self.discover(game_id)
            except TwitchAPIError as exc:
                self.database.record_error(self.clock(), str(exc))
                errors.append(exc)
        if errors:
            raise TwitchAPIError(f"{len(errors)} category collection(s) failed; first: {errors[0]}")
