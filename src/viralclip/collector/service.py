from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from viralclip.storage.database import Database, utc_now
from viralclip.twitch.client import TwitchAPIError, TwitchClient


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

    def _whole_minute_window(self, game_id: str, now: datetime) -> tuple[datetime, datetime]:
        now = now.astimezone(UTC).replace(second=0, microsecond=0)
        start = now - timedelta(minutes=self.lookback_minutes)
        checkpoint = self.database.connection.execute(
            "SELECT watermark FROM discovery_checkpoints WHERE game_id = ?", (game_id,)
        ).fetchone()
        if checkpoint:
            watermark = datetime.fromisoformat(checkpoint["watermark"])
            start = min(start, watermark - timedelta(minutes=5))
        return start, now

    def discover(self, game_id: str) -> int:
        start, end = self._whole_minute_window(game_id, self.clock())
        return self._discover_window(game_id, start, end, [20])

    def _discover_window(
        self, game_id: str, start: datetime, end: datetime, budget: list[int]
    ) -> int:
        run_id = self.database.create_run(game_id, start, end, self.clock())
        pages = 0
        requests = 0
        all_clips: list[tuple[dict, datetime]] = []
        truncated = False
        try:
            cursor = None
            while budget[0] > 0:
                payload = self.twitch.get_clips(
                    game_id=game_id, started_at=start, ended_at=end, after=cursor
                )
                requests += 1
                budget[0] -= 1
                pages += 1
                page = payload.get("data", [])
                if not isinstance(page, list):
                    raise TwitchAPIError("Twitch returned an invalid clips list")
                page_observed_at = self.clock()
                all_clips.extend((clip, page_observed_at) for clip in page)
                cursor = payload.get("pagination", {}).get("cursor")
                if not cursor:
                    break
                if pages >= 10:
                    truncated = True
                    break
            else:
                truncated = True

            new_count = 0
            for raw_clip, observed_at in all_clips:
                clip = self._parse_clip(raw_clip)
                if self.database.record_clip(clip, game_id, observed_at, run_id):
                    new_count += 1
            self.database.finish_run(
                run_id, self.clock(), requests, pages, len(all_clips), new_count, truncated
            )

            span = (end - start).total_seconds()
            if truncated and span >= 120 and budget[0] > 0:
                midpoint = start + (end - start) / 2
                midpoint = midpoint.replace(second=0, microsecond=0)
                if start < midpoint < end:
                    first = self._discover_window(game_id, start, midpoint, budget)
                    second = self._discover_window(game_id, midpoint, end, budget)
                    return new_count + first + second
            if not truncated:
                self.database.update_watermark(game_id, end)
            return new_count
        except Exception as exc:
            self.database.finish_run(
                run_id, self.clock(), requests, pages, len(all_clips), 0, truncated, str(exc)
            )
            raise

    @staticmethod
    def _parse_clip(raw: dict) -> dict:
        try:
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
                results = {
                    str(item["id"]): item
                    for item in payload.get("data", [])
                    if isinstance(item, dict) and "id" in item
                }
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
                        clip_id, observed_at, parsed["view_count"], target
                    )
                except (TwitchAPIError, ValueError) as exc:
                    self.database.finish_jobs(ids, "failed", observed_at, str(exc))
                    continue
                self.database.finish_jobs(ids, "completed", observed_at)
                completed += len(ids)
        return completed

    def collect_cycle(self, games: tuple[str, ...], game_ids: tuple[str, ...] = ()) -> None:
        self.collect_due_snapshots()
        for name in games:
            self.discover(self.resolve_game(name))
        for game_id in game_ids:
            if not self.database.connection.execute(
                "SELECT 1 FROM games WHERE game_id = ?", (game_id,)
            ).fetchone():
                self.database.upsert_game(game_id, game_id, self.clock())
            self.discover(game_id)
