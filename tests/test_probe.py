from __future__ import annotations

from datetime import UTC, datetime

from viralclip.probe import MAX_PAGES, WINDOWS, probe_volume
from viralclip.twitch.client import TwitchClient


class FakeClient:
    """Two pages of 100 clips per window; one window never ends, one stops at the cap."""

    def __init__(self):
        self.calls = []

    def get_clips(self, *, game_id, started_at, ended_at, after=None):
        self.calls.append((game_id, started_at, ended_at, after))
        endless = started_at.hour == 21  # the first window: 22:00 minus the 2h lag, minus 1h
        capped = started_at.hour == 18  # the second window ends exactly at the page cap
        page = int(after or 0) + 1
        more = endless or (page < MAX_PAGES if capped else page < 2)
        data = [{"broadcaster_id": f"b{page % 3}"} for _ in range(100)]
        return {"data": data, "pagination": {"cursor": str(page)} if more else {}}

    parse_data = staticmethod(TwitchClient.parse_data)
    parse_cursor = staticmethod(TwitchClient.parse_cursor)


def test_probe_samples_eight_windows_and_flags_truncation():
    client = FakeClient()
    result = probe_volume(client, "509658", now=datetime(2026, 11, 25, 0, 30, tzinfo=UTC))
    assert result["truncated_windows"] == 2  # a cap reached without a cursor still counts
    assert result["requests"] == 2 * MAX_PAGES + 2 * (WINDOWS - 2)
    assert result["sampled_clips"] == 100 * result["requests"]
    assert result["estimated_clips_per_day"] == result["sampled_clips"] * 3
    starts = sorted({call[1] for call in client.calls})
    assert len(starts) == WINDOWS and starts[-1] == datetime(2026, 11, 24, 21, tzinfo=UTC)
    assert all(call[2] <= datetime(2026, 11, 24, 22, tzinfo=UTC) for call in client.calls)
