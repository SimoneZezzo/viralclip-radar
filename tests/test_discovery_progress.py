from contextlib import closing
from datetime import UTC, datetime, timedelta, timezone

import httpx
import pytest
from test_collector import clip, make_client

from viralclip.collector.service import Collector
from viralclip.gta_vi import APPROVED_GAME_ID
from viralclip.storage.database import Database, to_utc_iso
from viralclip.twitch.client import TwitchAPIError

MINUTE = timedelta(minutes=1)
STALLED = datetime(2026, 11, 20, 23, 11, tzinfo=UTC)
NOW = datetime(2026, 11, 21, 13, 34, tzinfo=UTC)


def checkpoint(db):
    row = db.connection.execute(
        "SELECT watermark FROM discovery_checkpoints WHERE game_id = ?", (APPROVED_GAME_ID,)
    ).fetchone()
    return row[0] if row else None


def seed(db, watermark=STALLED):
    db.upsert_game(APPROVED_GAME_ID, "Grand Theft Auto VI", watermark)
    run = db.create_run(APPROVED_GAME_ID, watermark - MINUTE, watermark, watermark)
    db.finish_run(run, watermark, 1, 1, 0, 0)
    db.update_watermark(APPROVED_GAME_ID, watermark)


def window(request):
    return (
        datetime.fromisoformat(request.url.params["started_at"]),
        datetime.fromisoformat(request.url.params["ended_at"]),
    )


def mocked_client(handler, *, sleep=lambda _: None):
    def route(request):
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "fixture", "expires_in": 7200})
        assert request.url.path == "/helix/clips"
        return handler(request)

    return make_client(route, sleep=sleep)


def response(data=(), cursor=None):
    return httpx.Response(
        200, json={"data": list(data), "pagination": {"cursor": cursor} if cursor else {}}
    )


def paged_response(request, count, page_size=99):
    start, _ = window(request)
    offset = int(request.url.params.get("after", "0"))
    next_offset = min(offset + page_size, count)
    return response(
        (clip(str(i), created_at=start) for i in range(offset, next_offset)),
        str(next_offset) if next_offset < count else None,
    )


def test_gta_vi_dense_backlog_advances_without_repeating_broad_window(tmp_path, monkeypatch):
    now = NOW
    requests = []

    def handler(request):
        assert request.url.params["game_id"] == APPROVED_GAME_ID
        start, end = window(request)
        requests.append((start, end))
        return paged_response(request, 120 * ((end - start) // MINUTE))

    twitch = mocked_client(handler)
    with closing(Database(tmp_path / "gta-vi.sqlite3")) as db, twitch.http:
        seed(db)
        # Bulk cases omit clip writes. Smaller cases exercise real SQLite writes.
        monkeypatch.setattr(db, "record_clip", lambda *args: False)
        collector = Collector(db, twitch, lookback_minutes=10, clock=lambda: now)
        watermarks = [to_utc_iso(STALLED)]
        queried_windows = []
        for _ in range(2):
            requests.clear()
            collector.discover(APPROVED_GAME_ID)
            watermarks.append(checkpoint(db))
            assert 0 < len(requests) <= 20
            queried_windows.extend(requests)
            now += 5 * MINUTE
        runs = db.connection.execute(
            "SELECT status, pages_seen FROM collection_runs WHERE run_id > 1 ORDER BY run_id"
        ).fetchall()
        assert watermarks == [
            to_utc_iso(STALLED),
            to_utc_iso(STALLED + 10 * MINUTE),
            to_utc_iso(STALLED + 22 * MINUTE),
        ], [tuple(run) for run in runs]
        assert all(run["pages_seen"] for run in runs)
        assert all(end - start <= 5 * MINUTE for start, end in queried_windows)


@pytest.mark.parametrize(
    ("clips", "cursors"), [(0, [None]), (43, [None]), (100, [None]), (137, [None, "100"])]
)
def test_short_window_follows_cursor_and_replays_overlap(tmp_path, clips, cursors):
    frontier = NOW - 5 * MINUTE
    forward = []
    overlap = []

    def handler(request):
        bounds = window(request)
        assert request.url.params["first"] == "100"
        if bounds == (frontier, NOW):
            forward.append(request.url.params.get("after"))
            return paged_response(request, clips, page_size=100)
        overlap.append(bounds)
        return response()

    twitch = mocked_client(handler)
    with closing(Database(tmp_path / "gta-vi.sqlite3")) as db, twitch.http:
        seed(db, frontier)
        local_now = NOW.astimezone(timezone(timedelta(hours=2))) + timedelta(seconds=59)
        collector = Collector(db, twitch, lookback_minutes=10, clock=lambda: local_now)
        assert collector.discover(APPROVED_GAME_ID) == clips
        assert checkpoint(db) == to_utc_iso(NOW)
        assert forward == cursors
        assert overlap == [(NOW - 10 * MINUTE, frontier)]


@pytest.mark.parametrize(("clips_per_minute", "progresses"), [(500, True), (950, False)])
def test_dense_first_slice_narrows_across_cycles_and_restart(
    tmp_path, monkeypatch, clips_per_minute, progresses
):
    path = tmp_path / "gta-vi.sqlite3"
    requests = []

    def handler(request):
        start, end = window(request)
        requests.append((start, end))
        return paged_response(request, clips_per_minute * ((end - start) // MINUTE))

    twitch = mocked_client(handler)
    with closing(Database(path)) as db, twitch.http:
        seed(db)
        monkeypatch.setattr(db, "record_clip", lambda *args: False)
        Collector(db, twitch, lookback_minutes=10, clock=lambda: NOW).discover(APPROVED_GAME_ID)
        assert checkpoint(db) == to_utc_iso(STALLED)
        assert len(requests) == 20
        assert list(dict.fromkeys(requests)) == [
            (STALLED, STALLED + 5 * MINUTE),
            (STALLED, STALLED + 2 * MINUTE),
        ]
        assert (
            db.connection.execute(
                "SELECT COUNT(*) FROM collection_runs WHERE request_count=0"
            ).fetchone()[0]
            == 0
        )

    requests.clear()
    twitch = mocked_client(handler)
    with closing(Database(path)) as db, twitch.http:
        monkeypatch.setattr(db, "record_clip", lambda *args: False)
        collector = Collector(db, twitch, lookback_minutes=10, clock=lambda: NOW + 5 * MINUTE)
        collector.discover(APPROVED_GAME_ID)
        assert requests[0] == (STALLED, STALLED + MINUTE)
        assert len(requests) <= 20
        if progresses:
            assert checkpoint(db) == to_utc_iso(STALLED + 3 * MINUTE)
        else:
            assert checkpoint(db) == to_utc_iso(STALLED)
            assert set(requests) == {(STALLED, STALLED + MINUTE)}
            assert (
                db.connection.execute(
                    "SELECT status FROM collection_runs ORDER BY run_id DESC LIMIT 1"
                ).fetchone()[0]
                == "partial"
            )


def test_restart_reuses_completed_prefix_after_budget_runs_out_mid_pagination(
    tmp_path, monkeypatch
):
    path = tmp_path / "gta-vi.sqlite3"
    requested = []

    def handler(request):
        start, end = window(request)
        requested.append((start, end))
        return paged_response(request, 140 * ((end - start) // MINUTE))

    twitch = mocked_client(handler)
    with closing(Database(path)) as db, twitch.http:
        seed(db)
        monkeypatch.setattr(db, "record_clip", lambda *args: False)
        Collector(db, twitch, lookback_minutes=10, clock=lambda: NOW).discover(APPROVED_GAME_ID)
        assert len(requested) == 20
        assert checkpoint(db) == to_utc_iso(STALLED + 10 * MINUTE)
        last = db.connection.execute(
            "SELECT status, pages_seen FROM collection_runs ORDER BY run_id DESC LIMIT 1"
        ).fetchone()
        assert tuple(last) == ("partial", 4)

    requested.clear()
    twitch = mocked_client(handler)
    with closing(Database(path)) as db, twitch.http:
        monkeypatch.setattr(db, "record_clip", lambda *args: False)
        Collector(db, twitch, lookback_minutes=10, clock=lambda: NOW + 5 * MINUTE).discover(
            APPROVED_GAME_ID
        )
        assert requested[0] == (STALLED + 10 * MINUTE, STALLED + 12 * MINUTE)
        assert checkpoint(db) > to_utc_iso(STALLED + 10 * MINUTE)


@pytest.mark.parametrize("failure", ["rate_limit", "timeout"])
def test_error_keeps_completed_prefix_and_retries_first_gap(tmp_path, failure):
    frontier = NOW - 10 * MINUTE
    later = frontier + 5 * MINUTE
    failing = True
    requests = []
    waits = []

    def handler(request):
        start, _ = window(request)
        requests.append(start)
        if failing and start == later:
            if failure == "rate_limit":
                return httpx.Response(429, headers={"Retry-After": "2"})
            raise httpx.ReadTimeout("synthetic timeout", request=request)
        return response()

    twitch = mocked_client(handler, sleep=waits.append)
    twitch.max_retries = 1
    with closing(Database(tmp_path / "gta-vi.sqlite3")) as db, twitch.http:
        seed(db, frontier)
        collector = Collector(db, twitch, lookback_minutes=10, clock=lambda: NOW)
        with pytest.raises(TwitchAPIError):
            collector.discover(APPROVED_GAME_ID)
        assert checkpoint(db) == to_utc_iso(later)
        assert requests == [frontier, later, later]
        assert waits == ([2] if failure == "rate_limit" else [1])
        run = db.connection.execute(
            "SELECT status, pages_seen FROM collection_runs ORDER BY run_id DESC LIMIT 1"
        ).fetchone()
        assert tuple(run) == ("error", 0)
        requests.clear()
        failing = False
        collector.discover(APPROVED_GAME_ID)
        assert requests[0] == later
        assert checkpoint(db) == to_utc_iso(NOW)


def test_legacy_seed_and_disconnected_completed_window_do_not_hide_gap(tmp_path):
    start = NOW - 10 * MINUTE
    legacy_checkpoint = start + 5 * MINUTE
    gap = start + MINUTE
    windows = []

    def handler(request):
        windows.append(window(request))
        if windows[-1][0] == gap:
            return httpx.Response(400)
        return response()

    twitch = mocked_client(handler)
    with closing(Database(tmp_path / "gta-vi.sqlite3")) as db, twitch.http:
        db.upsert_game(APPROVED_GAME_ID, "Grand Theft Auto VI", start)
        db.update_watermark(APPROVED_GAME_ID, legacy_checkpoint)
        parent = db.create_run(APPROVED_GAME_ID, start, NOW, NOW)
        db.finish_run(parent, NOW, 10, 10, 900, 0, truncated=True)
        prefix = db.create_run(APPROVED_GAME_ID, start, gap, NOW)
        db.finish_run(prefix, NOW, 1, 1, 0, 0)
        suffix = db.create_run(APPROVED_GAME_ID, legacy_checkpoint - MINUTE, legacy_checkpoint, NOW)
        db.finish_run(suffix, NOW, 1, 1, 0, 0)
        with pytest.raises(TwitchAPIError):
            Collector(db, twitch, lookback_minutes=10, clock=lambda: NOW).discover(APPROVED_GAME_ID)
        assert windows == [(gap, gap + 5 * MINUTE)]
        assert checkpoint(db) == to_utc_iso(legacy_checkpoint)


def test_first_window_error_survives_restart_without_a_seeded_checkpoint(tmp_path):
    path = tmp_path / "gta-vi.sqlite3"
    start = NOW - 10 * MINUTE
    twitch = mocked_client(lambda _: httpx.Response(400))
    with closing(Database(path)) as db, twitch.http:
        db.upsert_game(APPROVED_GAME_ID, "Grand Theft Auto VI", NOW)
        with pytest.raises(TwitchAPIError):
            Collector(db, twitch, lookback_minutes=10, clock=lambda: NOW).discover(APPROVED_GAME_ID)
        assert checkpoint(db) is None

    windows = []

    def handler(request):
        windows.append(window(request))
        return response()

    twitch = mocked_client(handler)
    with closing(Database(path)) as db, twitch.http:
        later = NOW + 5 * MINUTE
        Collector(db, twitch, lookback_minutes=10, clock=lambda: later).discover(APPROVED_GAME_ID)
        assert windows[0][0] == start
        assert checkpoint(db) == to_utc_iso(later)


def test_shared_boundary_deduplicates_clip_and_preserves_first_seen(tmp_path):
    frontier = NOW - 10 * MINUTE
    boundary = frontier + 5 * MINUTE
    windows = []

    def handler(request):
        start, end = window(request)
        windows.append((start, end))
        return response([clip(created_at=boundary)] if start <= boundary <= end else [])

    twitch = mocked_client(handler)
    with closing(Database(tmp_path / "gta-vi.sqlite3")) as db, twitch.http:
        seed(db, frontier)
        collector = Collector(db, twitch, lookback_minutes=10, clock=lambda: NOW)
        assert collector.discover(APPROVED_GAME_ID) == 1
        assert windows[:2] == [(frontier, boundary), (boundary, NOW)]
        assert db.connection.execute("SELECT first_seen_at FROM clips").fetchall()[0][
            0
        ] == to_utc_iso(NOW)
        assert db.connection.execute("SELECT COUNT(*) FROM clips").fetchone()[0] == 1
        assert db.connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 5


def test_due_jobs_keep_priority_before_and_between_discovery_pages(tmp_path):
    now = NOW
    frontier = NOW - 5 * MINUTE
    calls = []
    created_first = NOW - timedelta(minutes=11)
    created_second = NOW - timedelta(minutes=10) + timedelta(seconds=1)

    def handler(request):
        nonlocal now
        params = request.url.params
        if "id" in params:
            name = params["id"]
            calls.append(name)
            created = created_first if name == "initial-due" else created_second
            return response([clip(name, created_at=created)])
        if window(request)[0] != frontier:
            return response()
        if "after" in params:
            calls.append("page-2")
            return response()
        calls.append("page-1")
        now += timedelta(seconds=2)
        return response(cursor="more")

    twitch = mocked_client(handler)
    with closing(Database(tmp_path / "gta-vi.sqlite3")) as db, twitch.http:
        seed(db, frontier)
        for name, created in (("initial-due", created_first), ("became-due", created_second)):
            db.record_clip(
                Collector._parse_clip(clip(name, created_at=created)),
                APPROVED_GAME_ID,
                created,
                None,
            )
        Collector(db, twitch, lookback_minutes=10, clock=lambda: now).discover(APPROVED_GAME_ID)
        assert calls == ["initial-due", "page-1", "became-due", "page-2"]
        assert (
            db.connection.execute("SELECT COUNT(*) FROM jobs WHERE status='completed'").fetchone()[
                0
            ]
            == 2
        )


def test_gta_v_keeps_existing_catch_up_window_and_overlap(tmp_path):
    windows = []

    def handler(request):
        assert request.url.params["game_id"] == "32982"
        windows.append(window(request))
        return response()

    twitch = mocked_client(handler)
    with closing(Database(tmp_path / "gta-v.sqlite3")) as db, twitch.http:
        db.upsert_game("32982", "Grand Theft Auto V", STALLED)
        db.update_watermark("32982", STALLED)
        Collector(db, twitch, clock=lambda: NOW).discover("32982")
        assert windows == [(STALLED - 5 * MINUTE, NOW)]


def test_gta_v_recursive_split_keeps_checkpoint_when_a_child_is_incomplete(tmp_path, monkeypatch):
    frontier = NOW - 5 * MINUTE
    start = frontier - 5 * MINUTE

    def handler(request):
        begin, end = window(request)
        return paged_response(request, 120 * ((end - begin) // MINUTE))

    twitch = mocked_client(handler)
    with closing(Database(tmp_path / "gta-v.sqlite3")) as db, twitch.http:
        db.upsert_game("32982", "Grand Theft Auto V", frontier)
        db.update_watermark("32982", frontier)
        monkeypatch.setattr(db, "record_clip", lambda *args: False)
        Collector(db, twitch, lookback_minutes=10, clock=lambda: NOW).discover("32982")
        rows = db.connection.execute(
            """SELECT window_start, window_end, status, pages_seen
               FROM collection_runs ORDER BY run_id"""
        )
        assert [tuple(row) for row in rows] == [
            (to_utc_iso(start), to_utc_iso(NOW), "partial", 10),
            (to_utc_iso(start), to_utc_iso(frontier), "completed", 7),
            (to_utc_iso(frontier), to_utc_iso(NOW), "partial", 3),
        ]
        assert db.connection.execute("SELECT watermark FROM discovery_checkpoints").fetchone()[
            0
        ] == to_utc_iso(frontier)
