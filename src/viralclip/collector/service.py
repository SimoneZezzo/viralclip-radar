from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from viralclip.storage.database import Database, to_utc_iso, utc_now
from viralclip.twitch.client import TwitchAPIError, TwitchClient

GTA_VI_GAME_ID = "1867279146"
DISCOVERY_BUDGET = 20
MINUTE = timedelta(minutes=1)
OVERLAP = timedelta(minutes=5)
GTA_VI_WINDOW = timedelta(minutes=5)


class Collector:
    def __init__(
        self,
        database: Database,
        twitch: TwitchClient,
        *,
        lookback_minutes: int = 30,
        clock: Callable[[], datetime] = utc_now,
    ):
        self.database = database
        self.twitch = twitch
        self.lookback_minutes = lookback_minutes
        self.clock = clock
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
        end = self.clock().astimezone(UTC).replace(second=0, microsecond=0)
        start = end - timedelta(minutes=self.lookback_minutes)
        row = self.database.connection.execute(
            "SELECT watermark FROM discovery_checkpoints WHERE game_id = ?", (game_id,)
        ).fetchone()
        checkpoint = datetime.fromisoformat(row["watermark"]) if row else None
        if checkpoint is not None:
            start = min(start, checkpoint - OVERLAP)
        budget = [DISCOVERY_BUDGET]
        if game_id == GTA_VI_GAME_ID:
            frontier = self._uncovered_start(game_id, start, checkpoint)
            count, covered = self._discover_prefix(
                game_id, frontier, end, budget, advance_after=checkpoint or frontier
            )
            if covered == end and start < frontier and budget[0] > 0:
                # Refresh prior coverage only after attempting the outstanding interval.
                repeated, _ = self._discover_prefix(game_id, start, frontier, budget)
                count += repeated
            return count
        if checkpoint is None:
            self.database.update_watermark(game_id, start + OVERLAP)
        count, complete = self._discover_window(game_id, start, end, budget)
        if complete:
            self.database.update_watermark(game_id, end)
        return count

    def _uncovered_start(
        self, game_id: str, start: datetime, checkpoint: datetime | None
    ) -> datetime:
        first = self.database.connection.execute(
            "SELECT window_start FROM collection_runs WHERE game_id = ? ORDER BY run_id LIMIT 1",
            (game_id,),
        ).fetchone()
        if checkpoint is None:
            # Retain the first attempted interval if a startup run never completed.
            return min(start, datetime.fromisoformat(first[0])) if first else start
        if first and checkpoint != datetime.fromisoformat(first[0]) + OVERLAP:
            return checkpoint
        # The older collector seeded a checkpoint five minutes into its initial
        # window before making any request. Reuse only its completed prefix.
        frontier = checkpoint - OVERLAP
        for window in self.database.connection.execute(
            """
            SELECT window_start, window_end FROM collection_runs
            WHERE game_id = ? AND status = 'completed' AND potentially_truncated = 0
              AND error_summary IS NULL AND window_end > ? AND window_start < ?
            ORDER BY window_start
            """,
            (game_id, to_utc_iso(frontier), to_utc_iso(checkpoint)),
        ):
            if datetime.fromisoformat(window["window_start"]) > frontier:
                break
            frontier = max(frontier, datetime.fromisoformat(window["window_end"]))
            if frontier >= checkpoint:
                return checkpoint
        return frontier

    def _discover_prefix(
        self,
        game_id: str,
        start: datetime,
        end: datetime,
        budget: list[int],
        *,
        advance_after: datetime | None = None,
    ) -> tuple[int, datetime]:
        width = GTA_VI_WINDOW
        previous = self.database.connection.execute(
            """
            SELECT window_end, status FROM collection_runs
            WHERE game_id = ? AND window_start = ? AND status IN ('completed','partial')
              AND request_count > 0
            ORDER BY run_id DESC LIMIT 1
            """,
            (game_id, to_utc_iso(start)),
        ).fetchone()
        if previous and previous["status"] == "partial":
            prior_span = datetime.fromisoformat(previous["window_end"]) - start
            width = min(width, max(MINUTE, (prior_span // (2 * MINUTE)) * MINUTE))
        count = 0
        while start < end and budget[0] > 0:
            stop = min(start + width, end)
            found, complete = self._discover_window(game_id, start, stop, budget, subdivide=False)
            count += found
            if complete:
                start = stop
                if advance_after is not None and start > advance_after:
                    self.database.update_watermark(game_id, start)
            elif stop - start > MINUTE:
                width = max(MINUTE, ((stop - start) // (2 * MINUTE)) * MINUTE)
            else:
                # A saturated minute remains explicitly incomplete.
                break
        return count, start

    def _discover_window(
        self,
        game_id: str,
        start: datetime,
        end: datetime,
        budget: list[int],
        *,
        subdivide: bool = True,
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
            if subdivide and truncated and span >= 120 and budget[0] > 0:
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
