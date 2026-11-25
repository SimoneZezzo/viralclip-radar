"""Estimate a candidate category's daily clip volume before starting a collector.

Read-only Helix sampling with no database: one-hour windows every three hours over the
last day, paged up to a cap. Helix lists a window's clips by views, so a window that
hits the page cap is reported as truncated and its count is a lower bound.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from viralclip.twitch.client import TwitchClient

WINDOWS = 8
SPACING = timedelta(hours=3)
WINDOW = timedelta(hours=1)
INDEXING_LAG = timedelta(hours=2)
MAX_PAGES = 10
# GTA VI on 2026-11-25: about 600 MB/day for about 145k new clips/day, all tables and indexes.
BYTES_PER_CLIP = 4_100


def probe_volume(client: TwitchClient, game_id: str, now: datetime | None = None) -> dict:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    end = now.replace(minute=0, second=0, microsecond=0) - INDEXING_LAG
    clips, broadcasters, truncated, requests = 0, set(), 0, 0
    for index in range(WINDOWS):
        stop = end - index * SPACING
        cursor, pages = None, 0
        while True:
            payload = client.get_clips(
                game_id=game_id, started_at=stop - WINDOW, ended_at=stop, after=cursor
            )
            requests += 1
            pages += 1
            data = client.parse_data(payload)
            clips += len(data)
            broadcasters.update(row.get("broadcaster_id") for row in data)
            cursor = client.parse_cursor(payload)
            if not cursor or not data:
                break
            if pages == MAX_PAGES:
                truncated += 1
                break
    broadcasters.discard(None)
    per_day = clips * (timedelta(days=1) / WINDOW) / WINDOWS  # sampled hours scaled to a day
    return {
        "game_id": game_id,
        "sampled_clips": clips,
        "estimated_clips_per_day": round(per_day),
        "distinct_broadcasters_sampled": len(broadcasters),
        "truncated_windows": truncated,
        "estimated_mb_per_day": round(per_day * BYTES_PER_CLIP / 1e6, 1),
        "requests": requests,
    }
