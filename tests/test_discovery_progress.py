from contextlib import closing
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from test_collector import clip, make_client

from viralclip.collector.service import Collector
from viralclip.config import GtaViOverlap
from viralclip.deployment import _check_schema, _open_read_only
from viralclip.gta_vi import APPROVED_GAME_ID
from viralclip.storage.database import Database, to_utc_iso
from viralclip.storage.discovery import (
    BUCKET,
    bucket_start,
    ensure_scan_ledger,
    historical_retry,
    scan_progress,
)
from viralclip.storage.health import read_health
from viralclip.twitch.client import TwitchAPIError

MINUTE = timedelta(minutes=1)
STALLED = datetime(2026, 11, 20, 23, 19, tzinfo=UTC)
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


def attempts(db):
    return [
        tuple(row)
        for row in db.connection.execute(
            """
            SELECT s.lane, s.outcome, r.window_start, r.window_end, r.request_count,
                   r.clips_seen, s.pertinent, r.unique_clips, s.repeated, r.status
            FROM gta_vi_scan_attempts s JOIN collection_runs r USING (run_id) ORDER BY run_id
            """
        )
    ]


@pytest.mark.parametrize(
    ("rows", "distinct", "inside"), [(982, 798, 117), (984, 835, 107), (991, 805, 104)]
)
def test_raw_saturation_with_duplicates_does_not_claim_coverage(tmp_path, rows, distinct, inside):
    aligned = bucket_start(STALLED)
    data = [clip(f"outside-{i}", created_at=aligned) for i in range(distinct - inside)]
    data += [clip(f"inside-{i}", created_at=STALLED) for i in range(inside)]
    pages = []
    offset = 0
    for index in range(10):
        take = distinct // 10 + (index < distinct % 10)
        page = data[offset : offset + take]
        offset += take
        pages.append(page + [data[0]] * (min(100, rows - index * 100) - take))

    def handler(request):
        assert window(request) == (aligned, aligned + BUCKET)
        page = int(request.url.params.get("after", 0))
        return response(pages[page], str(page + 1))

    twitch = mocked_client(handler)
    with closing(Database(tmp_path / "vi.sqlite3")) as db, twitch.http:
        seed(db)
        ensure_scan_ledger(db.connection)
        collector = Collector(db, twitch, clock=lambda: NOW)
        assert (
            collector._scan_gta_vi(APPROVED_GAME_ID, STALLED, STALLED + MINUTE, "history", 10)
            == inside
        )
        assert attempts(db)[0][1:] == (
            "page_limit",
            to_utc_iso(STALLED),
            to_utc_iso(STALLED + MINUTE),
            10,
            rows,
            inside,
            inside,
            rows - distinct,
            "partial",
        )
        assert checkpoint(db) == to_utc_iso(STALLED)


def test_saturated_terminal_page_is_still_partial(tmp_path):
    twitch = mocked_client(lambda request: paged_response(request, 1000, page_size=100))
    with closing(Database(tmp_path / "vi.sqlite3")) as db, twitch.http:
        seed(db)
        ensure_scan_ledger(db.connection)
        start = bucket_start(NOW)
        Collector(db, twitch, clock=lambda: NOW)._scan_gta_vi(
            APPROVED_GAME_ID, start, NOW, "recent", 10
        )
        row = attempts(db)[0]
        assert row[1] == "page_limit"
        assert row[4:8] == (10, 1000, 1000, 1000)
        assert row[-1] == "partial"


def test_wrong_category_does_not_write_clips_or_move_frontier(tmp_path):
    item = clip("wrong-game", created_at=bucket_start(NOW)) | {"game_id": "32982"}
    twitch = mocked_client(lambda _: response([item]))
    with closing(Database(tmp_path / "vi.sqlite3")) as db, twitch.http:
        seed(db)
        with pytest.raises(TwitchAPIError, match="different game category"):
            Collector(db, twitch, clock=lambda: NOW).discover(APPROVED_GAME_ID)
        assert db.connection.execute("SELECT count(*) FROM clips").fetchone()[0] == 0
        assert attempts(db)[0][1] == "error"
        assert scan_progress(db.connection, APPROVED_GAME_ID) == (None, None)


def test_view_order_warning_does_not_stop_real_collector_pagination(tmp_path, caplog):
    start = bucket_start(NOW)

    def handler(request):
        if not request.url.params.get("after"):
            return response(
                [
                    clip("low", created_at=start) | {"view_count": 8},
                    clip("high", created_at=start) | {"view_count": 10},
                ],
                "next",
            )
        return response([clip("another", created_at=start) | {"view_count": 11}])

    twitch = mocked_client(handler)
    with closing(Database(tmp_path / "vi.sqlite3")) as db, twitch.http:
        seed(db)
        ensure_scan_ledger(db.connection)
        collector = Collector(db, twitch, clock=lambda: NOW)
        assert collector._scan_gta_vi(APPROVED_GAME_ID, start, NOW, "recent", 10) == 3
        assert attempts(db)[0][1] == "cursor_exhausted"
        assert attempts(db)[0][4] == 2
        assert "within_page=1 between_pages=1" in caplog.text


@pytest.mark.parametrize(
    ("pages", "budget_expires", "expected"), [(7, False, 7), (10, False, 9), (10, True, 7)]
)
def test_extra_overlap_extends_only_its_cursor_within_the_time_budget(
    tmp_path, pages, budget_expires, expected
):
    previous = bucket_start(NOW) - BUCKET
    visited = []
    ticks = iter((0.0, 2.0)) if budget_expires else iter([0.0] * 10)

    def handler(request):
        start, _ = window(request)
        visited.append(start)
        return paged_response(request, 900, page_size=100) if start == previous else response()

    twitch = mocked_client(handler)
    with closing(Database(tmp_path / "vi.sqlite3")) as db, twitch.http:
        seed(db)
        Collector(
            db,
            twitch,
            clock=lambda: NOW,
            monotonic=lambda: next(ticks),
            gta_vi_overlap=GtaViOverlap(pages, 1),
        ).discover(APPROVED_GAME_ID)
        assert visited.count(previous) == expected
        assert len(visited) == expected + 2  # Current and historical allocations remain available.
        overlap = next(row for row in attempts(db) if row[2] == to_utc_iso(previous))
        assert overlap[1] == ("cursor_exhausted" if expected == 9 else "budget")
        assert checkpoint(db) == to_utc_iso(STALLED)


def test_recent_discovery_continues_past_gap_and_survives_restart(tmp_path):
    path = tmp_path / "vi.sqlite3"
    now = NOW
    calls = []

    def handler(request):
        assert request.url.params["game_id"] == APPROVED_GAME_ID
        start, end = window(request)
        calls.append(start)
        if start >= bucket_start(now) - BUCKET:
            data = [clip(f"fresh-{now.isoformat()}", created_at=now - timedelta(seconds=2))]
            return response(data if start == bucket_start(now) else [])
        offset = int(request.url.params.get("after", "0"))
        return response(
            [clip(f"old-{start.isoformat()}-{offset}", created_at=end - MINUTE)], str(offset + 1)
        )

    for i in range(2):
        twitch = mocked_client(handler)
        with closing(Database(path)) as db, twitch.http:
            if i == 0:
                seed(db)
            assert Collector(db, twitch, clock=lambda now=now: now).discover(APPROVED_GAME_ID) >= 1
            recent, history = scan_progress(db.connection, APPROVED_GAME_ID)
            assert recent == now
            assert history == STALLED + MINUTE + i * BUCKET
            assert checkpoint(db) == to_utc_iso(STALLED)
            assert len(calls) == 5
            assert calls[0] == bucket_start(now)
            gap = next(row for row in attempts(db) if row[2] == to_utc_iso(STALLED))
            assert gap[0:2] == ("history", "budget")
            assert (
                db.connection.execute(
                    "SELECT count(*) FROM clips WHERE clip_id LIKE 'fresh-%'"
                ).fetchone()[0]
                == i + 1
            )
        calls.clear()
        now += 5 * MINUTE
    _, lines = read_health(path, 300, now=now)
    assert any("coverage uncertified" in line for line in lines)
    assert any("legacy checkpoint " + to_utc_iso(STALLED) in line for line in lines)


def test_cursor_exhaustion_with_sixty_known_omissions_is_partial(tmp_path):
    twitch = mocked_client(lambda _: response())
    with closing(Database(tmp_path / "vi.sqlite3")) as db, twitch.http:
        seed(db)
        ensure_scan_ledger(db.connection)
        for n in range(60):
            db.record_clip(
                Collector._parse_clip(clip(str(n), created_at=STALLED)), APPROVED_GAME_ID, NOW, None
            )
        Collector(db, twitch, clock=lambda: NOW)._scan_gta_vi(
            APPROVED_GAME_ID, STALLED, STALLED + MINUTE, "history", 3
        )
        assert attempts(db)[0][1] == "known_incomplete"
        assert attempts(db)[0][-1] == "partial"
        assert scan_progress(db.connection, APPROVED_GAME_ID) == (None, STALLED + MINUTE)
        assert checkpoint(db) == to_utc_iso(STALLED)


def test_recent_and_history_budgets_are_independent(tmp_path):
    def handler(request):
        start, _ = window(request)
        page = int(request.url.params.get("after", "0"))
        return response([clip(f"{start}-{page}", created_at=start)], str(page + 1))

    twitch = mocked_client(handler)
    with closing(Database(tmp_path / "vi.sqlite3")) as db, twitch.http:
        seed(db)
        Collector(db, twitch, clock=lambda: NOW).discover(APPROVED_GAME_ID)
        assert [(row[0], row[1], row[4]) for row in attempts(db)] == [
            ("recent", "page_limit", 10),
            ("recent", "budget", 7),
            ("history", "budget", 3),
        ]
        assert scan_progress(db.connection, APPROVED_GAME_ID) == (NOW, STALLED + MINUTE)


@pytest.mark.parametrize(
    ("kind", "outcome", "requests", "raw", "pertinent", "unique", "dups"),
    [
        ("legitimate", "cursor_exhausted", 2, 5, 4, 2, 2),
        ("repeated_cursor", "pagination_anomaly", 2, 5, 4, 2, 2),
        ("no_progress", "pagination_anomaly", 2, 4, 3, 1, 2),
        ("outside_query", "pagination_anomaly", 1, 1, 0, 0, 0),
    ],
)
def test_filter_and_deduplicate_without_certifying_coverage(
    tmp_path,
    kind,
    outcome,
    requests,
    raw,
    pertinent,
    unique,
    dups,
):
    def handler(request):
        if kind == "outside_query":
            return response([clip("bad", created_at=STALLED - BUCKET)])
        first = clip("same", created_at=STALLED)
        if "after" not in request.url.params:
            return response([first, first, clip("out", created_at=STALLED - MINUTE)], "one")
        if kind == "no_progress":
            return response([first], "two")
        return response(
            [first, clip("new", created_at=STALLED)], "one" if kind == "repeated_cursor" else None
        )

    twitch = mocked_client(handler)
    with closing(Database(tmp_path / "vi.sqlite3")) as db, twitch.http:
        seed(db)
        ensure_scan_ledger(db.connection)
        Collector(db, twitch, clock=lambda: NOW)._scan_gta_vi(
            APPROVED_GAME_ID, STALLED, STALLED + MINUTE, "history", 3
        )
        record = attempts(db)[0]
        assert record[1] == outcome
        assert record[4:9] == (requests, raw, pertinent, unique, dups)
        assert record[-1] == ("scanned" if outcome == "cursor_exhausted" else "partial")
        assert db.connection.execute("SELECT count(*) FROM clip_snapshots").fetchone()[0] == unique
        assert checkpoint(db) == to_utc_iso(STALLED)


@pytest.mark.parametrize("failure", ["timeout", "http", "invalid_pagination", "invalid_data"])
def test_interrupted_pagination_records_error_with_bounded_retries(tmp_path, failure):
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return response([clip("fresh", created_at=bucket_start(NOW))], "one")
        if failure == "timeout":
            raise httpx.ReadTimeout("fixture")
        if failure == "http":
            return httpx.Response(503)
        if failure == "invalid_data":
            return httpx.Response(200, json={"data": {}})
        return httpx.Response(200, json={"data": [], "pagination": []})

    twitch = mocked_client(handler)
    with closing(Database(tmp_path / "vi.sqlite3")) as db, twitch.http:
        seed(db)
        with pytest.raises(TwitchAPIError):
            Collector(db, twitch, clock=lambda: NOW).discover(APPROVED_GAME_ID)
        assert len(requests) == (2 if failure.startswith("invalid_") else 5)
        assert attempts(db)[0][0:2] == ("recent", "error")
        assert attempts(db)[0][4:8] == (2, 1, 1, 1)
        assert checkpoint(db) == to_utc_iso(STALLED)


def test_unexpected_discovery_exception_finalizes_run_and_preserves_error(tmp_path, monkeypatch):
    twitch = mocked_client(lambda _: response())
    with closing(Database(tmp_path / "vi.sqlite3")) as db, twitch.http:
        seed(db)
        collector = Collector(db, twitch, clock=lambda: NOW)

        def fail(*_args):
            raise RuntimeError("internal detail")

        monkeypatch.setattr(collector, "collect_due_snapshots", fail)
        with pytest.raises(RuntimeError, match="internal detail"):
            collector.discover(APPROVED_GAME_ID)
        assert attempts(db)[0][:2] == ("recent", "error")
        assert (
            db.connection.execute(
                "SELECT error_summary FROM collection_runs WHERE status='error'"
            ).fetchone()[0]
            == "RuntimeError"
        )
        assert scan_progress(db.connection, APPROVED_GAME_ID) == (None, None)


def test_failed_history_window_is_revisited_next_cycle(tmp_path):
    history_calls = []
    fail_history = True

    def handler(request):
        start, _ = window(request)
        if start == bucket_start(STALLED):
            history_calls.append(start)
            if fail_history:
                return httpx.Response(503)
        return response()

    twitch = mocked_client(handler)
    with closing(Database(tmp_path / "vi.sqlite3")) as db, twitch.http:
        seed(db)
        collector = Collector(db, twitch, clock=lambda: NOW)
        with pytest.raises(TwitchAPIError):
            collector.discover(APPROVED_GAME_ID)
        assert scan_progress(db.connection, APPROVED_GAME_ID)[1] is None
        assert attempts(db)[-1][:2] == ("history", "error")
        before = len(history_calls)
        fail_history = False
        collector.discover(APPROVED_GAME_ID)
        assert len(history_calls) == before + 1
        assert attempts(db)[-1][:3] == ("history", "cursor_exhausted", to_utc_iso(STALLED))
        assert scan_progress(db.connection, APPROVED_GAME_ID)[1] == bucket_start(STALLED) + BUCKET
        assert checkpoint(db) == to_utc_iso(STALLED)


def test_historical_retry_after_sweep_is_bounded(tmp_path):
    now = NOW
    prior = bucket_start(now) - BUCKET
    blocked = prior - BUCKET
    calls = []

    def handler(request):
        if "id" in request.url.params:
            return response(
                [clip(name, created_at=blocked) for name in request.url.params.get_list("id")]
            )
        start, _ = window(request)
        calls.append(start)
        if start == blocked and calls.count(blocked) <= 3:
            offset = int(request.url.params.get("after", 0))
            return response([clip(str(offset), created_at=blocked)], str(offset + 1))
        if start == blocked:
            return response([clip(str(n), created_at=blocked) for n in range(4)])
        return response()

    twitch = mocked_client(handler)
    with closing(Database(tmp_path / "vi.sqlite3")) as db, twitch.http:
        seed(db, blocked)
        collector = Collector(db, twitch, clock=lambda: now)
        collector.discover(APPROVED_GAME_ID)
        assert attempts(db)[-1][0:2] == ("history", "budget")
        assert historical_retry(db.connection, APPROVED_GAME_ID, prior, now) == (blocked, prior)
        now += timedelta(minutes=31)
        # The contiguous historical pass runs before any retry.
        while scan_progress(db.connection, APPROVED_GAME_ID)[1] < bucket_start(now) - BUCKET:
            collector.discover(APPROVED_GAME_ID)
        collector.discover(APPROVED_GAME_ID)
        assert attempts(db)[-1][0:2] == ("retry", "cursor_exhausted")
        assert historical_retry(db.connection, APPROVED_GAME_ID, prior, now) is None
        assert checkpoint(db) == to_utc_iso(blocked)


def test_graceful_stop_partial_run_is_recovered_without_progress(tmp_path):
    path = tmp_path / "vi.sqlite3"

    def stop(_):
        raise KeyboardInterrupt

    twitch = mocked_client(stop)
    with closing(Database(path)) as db, twitch.http:
        seed(db)
        with pytest.raises(KeyboardInterrupt):
            Collector(db, twitch, clock=lambda: NOW).discover(APPROVED_GAME_ID)
        assert scan_progress(db.connection, APPROVED_GAME_ID) == (None, None)
        assert not attempts(db)
        run = db.connection.execute("SELECT max(run_id) FROM collection_runs").fetchone()[0]

    twitch = mocked_client(lambda _: response())
    with closing(Database(path)) as db, twitch.http:
        Collector(db, twitch, clock=lambda: NOW).discover(APPROVED_GAME_ID)
        assert (
            db.connection.execute(
                "SELECT status FROM collection_runs WHERE run_id=?", (run,)
            ).fetchone()[0]
            == "error"
        )
        assert scan_progress(db.connection, APPROVED_GAME_ID)[0] == NOW
        with closing(_open_read_only(path)) as read:
            _check_schema(read)
            assert read.execute("PRAGMA foreign_key_check").fetchall() == []


def test_due_observations_precede_discovery_pages(tmp_path):
    now = NOW
    calls = []
    made = {
        "due": NOW - timedelta(minutes=11),
        "later": NOW - timedelta(minutes=10) + timedelta(seconds=1),
    }

    def handler(request):
        nonlocal now
        if "id" in request.url.params:
            name = request.url.params["id"]
            calls.append(name)
            return response([clip(name, created_at=made[name])])
        if window(request)[0] != bucket_start(NOW):
            return response()
        if "after" in request.url.params:
            calls.append("page-2")
            return response()
        calls.append("page-1")
        now += timedelta(seconds=2)
        return response([clip("fresh", created_at=bucket_start(NOW))], "more")

    twitch = mocked_client(handler)
    with closing(Database(tmp_path / "vi.sqlite3")) as db, twitch.http:
        seed(db)
        for name, created in made.items():
            db.record_clip(
                Collector._parse_clip(clip(name, created_at=created)),
                APPROVED_GAME_ID,
                created,
                None,
            )
        Collector(db, twitch, clock=lambda: now).discover(APPROVED_GAME_ID)
        assert calls == ["due", "page-1", "later", "page-2"]
        assert (
            db.connection.execute("SELECT count(*) FROM jobs WHERE status='completed'").fetchone()[
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
        assert (
            db.connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name='gta_vi_scan_attempts'"
            ).fetchone()
            is None
        )


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
