"""Synthetic HTTP/SQLite regressions for the independent integrity audit."""

import sqlite3
from datetime import timedelta

import httpx
import pytest
from test_collector import NOW, clip, make_client

from viralclip.collector.service import Collector
from viralclip.storage.database import MIGRATIONS, Database, to_utc_iso
from viralclip.twitch.client import TwitchAPIError, TwitchClient


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "audit.sqlite3")
    database.upsert_game("42", "GTA", NOW)
    yield database
    database.close()


def client_for(handler):
    def route(request):
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "synthetic", "expires_in": 7200})
        return handler(request)

    return make_client(route)


def test_page_survives_later_failure_and_checkpoint_does_not_advance(db):
    def handler(request):
        if request.url.params.get("after"):
            return httpx.Response(503)
        assert "id" not in request.url.params
        assert request.url.params["first"] == "100"
        return httpx.Response(200, json={"data": [clip()], "pagination": {"cursor": "next"}})

    twitch = client_for(handler)
    collector = Collector(db, twitch, clock=lambda: NOW)
    with pytest.raises(TwitchAPIError):
        collector.discover("42")
    assert db.status(NOW)["snapshots"] == 1
    assert db.connection.execute("SELECT status FROM collection_runs").fetchone()[0] == "error"
    checkpoint = db.connection.execute("SELECT watermark FROM discovery_checkpoints").fetchone()[0]
    assert checkpoint < to_utc_iso(NOW)
    twitch.http.close()


def test_saturation_without_cursor_is_flagged_and_children_cannot_skip_gap(db, monkeypatch):
    monkeypatch.setattr(db, "record_clip", lambda *args: False)

    def handler(request):
        # Enough results to signal the approximate API ceiling, even with no cursor.
        return httpx.Response(200, json={"data": [clip(str(i)) for i in range(900)]})

    twitch = client_for(handler)
    collector = Collector(db, twitch, clock=lambda: NOW)
    collector.discover("42")
    rows = db.connection.execute("SELECT * FROM collection_runs").fetchall()
    assert rows[0]["potentially_truncated"] == 1
    assert sum(r["request_count"] for r in rows) <= 20
    assert db.connection.execute("SELECT watermark FROM discovery_checkpoints").fetchone()[
        0
    ] < to_utc_iso(NOW)
    twitch.http.close()


@pytest.mark.parametrize("payload", [{}, {"data": None}, {"data": {}}, {"data": [None]}])
def test_malformed_refresh_is_failed_not_unavailable(db, payload):
    db.record_clip(Collector._parse_clip(clip()), "42", NOW, None)
    twitch = client_for(lambda _: httpx.Response(200, json=payload))
    collector = Collector(db, twitch, clock=lambda: NOW + timedelta(minutes=11))
    assert collector.collect_due_snapshots() == 0
    job = db.connection.execute("SELECT * FROM jobs WHERE target_age_seconds=600").fetchone()
    assert job["status"] == "failed"
    assert db.status(NOW)["snapshots"] == 1
    twitch.http.close()


def test_snapshot_and_completion_roll_back_together(db):
    db.record_clip(Collector._parse_clip(clip()), "42", NOW, None)
    job_id = db.connection.execute("SELECT job_id FROM jobs LIMIT 1").fetchone()[0]
    db.connection.executescript("""
        CREATE TRIGGER simulate_disk_failure BEFORE UPDATE ON jobs
        WHEN NEW.status = 'completed' BEGIN SELECT RAISE(ABORT, 'injected failure'); END;
    """)
    with pytest.raises(sqlite3.IntegrityError, match="injected failure"):
        db.add_scheduled_snapshot("clip-1", NOW + timedelta(minutes=11), 25, 600, [job_id])
    assert db.status(NOW)["snapshots"] == 1
    assert (
        db.connection.execute("SELECT snapshot_id FROM jobs WHERE job_id=?", (job_id,)).fetchone()[
            0
        ]
        is None
    )


def test_full_http_flow_restart_and_delayed_snapshot(tmp_path):
    current = [NOW]
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("/search/categories"):
            return httpx.Response(200, json={"data": [{"id": "42", "name": "GTA"}]})
        if request.url.params.get_list("id"):
            assert "game_id" not in request.url.params
            return httpx.Response(200, json={"data": [clip(views=91)]})
        return httpx.Response(200, json={"data": [clip()], "pagination": {}})

    twitch = client_for(handler)
    path = tmp_path / "restart.sqlite3"
    first = Database(path)
    Collector(first, twitch, clock=lambda: current[0]).collect_cycle(("GTA",))
    job = first.connection.execute(
        "SELECT job_id FROM jobs WHERE target_age_seconds=600"
    ).fetchone()[0]
    first.start_jobs([job])
    first.close()
    current[0] += timedelta(minutes=65)
    second = Database(path)
    collector = Collector(second, twitch, clock=lambda: current[0])
    assert collector.collect_due_snapshots() == 3
    assert collector.collect_due_snapshots() == 0
    scheduled = second.connection.execute(
        "SELECT * FROM clip_snapshots WHERE source='scheduled'"
    ).fetchall()
    assert len(scheduled) == 1
    assert scheduled[0]["age_seconds"] == 3900
    assert scheduled[0]["observed_at"] == to_utc_iso(current[0])
    assert scheduled[0]["target_age_seconds"] is None
    jobs = second.connection.execute("SELECT * FROM jobs WHERE status='completed'").fetchall()
    assert {j["target_age_seconds"] for j in jobs} == {600, 1800, 3600}
    assert all(j["snapshot_id"] == scheduled[0]["snapshot_id"] for j in jobs)
    assert second.status(current[0])["clips"] == 1
    assert second.connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 5
    second.close()
    twitch.http.close()


def test_second_collector_rejected_but_status_available(db):
    db.acquire_collector_lock()
    other = Database(db.path)
    try:
        with pytest.raises(ValueError, match="Another collector"):
            other.acquire_collector_lock()
        assert other.status(NOW)["clips"] == 0
    finally:
        other.close()


def test_additive_migration_preserves_existing_measurements(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(MIGRATIONS[0])
    conn.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT)")
    conn.execute("INSERT INTO schema_migrations VALUES (1, ?)", (to_utc_iso(NOW),))
    conn.execute("INSERT INTO games VALUES ('42', 'GTA', ?)", (to_utc_iso(NOW),))
    conn.execute(
        "INSERT INTO clips(clip_id,game_id,created_at,first_seen_at,last_seen_at) VALUES ('legacy','42',?,?,?)",
        [to_utc_iso(NOW)] * 3,
    )
    conn.execute(
        "INSERT INTO clip_snapshots(clip_id,observed_at,age_seconds,view_count,source) VALUES ('legacy',?,0,17,'discovery')",
        (to_utc_iso(NOW),),
    )
    conn.commit()
    conn.close()
    migrated = Database(path)
    assert migrated.connection.execute("SELECT view_count FROM clip_snapshots").fetchone()[0] == 17
    assert (
        migrated.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 2
    )
    assert migrated.connection.execute("PRAGMA foreign_key_check").fetchall() == []
    migrated.close()


@pytest.mark.parametrize(
    "payload", [{}, [], {"access_token": None}, {"access_token": "x", "expires_in": -1}]
)
def test_invalid_oauth_response_is_safe(payload):
    twitch = make_client(lambda _: httpx.Response(200, json=payload))
    with pytest.raises(TwitchAPIError, match="invalid token response"):
        twitch.get_clips(game_id="42")
    twitch.http.close()


def test_token_validation_hourly_and_token_expiry():
    now = [1000.0]
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "x", "expires_in": 7200})
        if request.url.path.endswith("/validate"):
            return httpx.Response(200, json={"client_id": "id"})
        return httpx.Response(200, json={"data": []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        twitch = TwitchClient("id", "secret", http=http, wall_clock=lambda: now[0])
        twitch.get_clips(game_id="42")
        twitch.get_clips(game_id="42")
        now[0] += 3601
        twitch.get_clips(game_id="42")
        now[0] += 3601
        twitch.get_clips(game_id="42")
    assert paths.count("/oauth2/token") == 2
    assert paths.count("/oauth2/validate") == 3


def test_rate_limit_respects_later_header_and_never_zero_delay():
    twitch = make_client(lambda _: httpx.Response(200))
    twitch.wall_clock = lambda: 1000
    response = httpx.Response(429, headers={"Retry-After": "0", "Ratelimit-Reset": "1010"})
    assert twitch._retry_delay(response, 0) == 10
    assert twitch._retry_delay(httpx.Response(429, headers={"Retry-After": "0"}), 0) >= 1
    twitch.http.close()


def test_status_cli_without_credentials(monkeypatch, tmp_path, capsys):
    from viralclip.cli import main

    monkeypatch.setenv("TWITCH_CLIENT_ID", "")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "")
    assert main(["--db", str(tmp_path / "status.sqlite3"), "status"]) == 0
    assert "Clips: 0" in capsys.readouterr().out


@pytest.mark.parametrize("views", [-1, None, True, "17"])
def test_invalid_counts_are_not_measurements(views):
    with pytest.raises(TwitchAPIError):
        Collector._parse_clip(clip(views=views))


def test_failed_jobs_have_delay_and_bounded_attempts(db):
    db.record_clip(Collector._parse_clip(clip()), "42", NOW, None)
    current = [NOW + timedelta(minutes=11)]
    twitch = client_for(lambda _: httpx.Response(200, json={"data": None}))
    collector = Collector(db, twitch, clock=lambda: current[0])
    for attempt in range(1, 4):
        collector.collect_due_snapshots()
        row = db.connection.execute("SELECT * FROM jobs WHERE target_age_seconds=600").fetchone()
        assert row["attempts"] == attempt
        collector.collect_due_snapshots()
        assert (
            db.connection.execute(
                "SELECT attempts FROM jobs WHERE target_age_seconds=600"
            ).fetchone()[0]
            == attempt
        )
        current[0] += timedelta(seconds=31)
    assert db.due_jobs(current[0]) == []
    twitch.http.close()


def test_search_exact_category_on_second_page(db):
    def handler(request):
        if request.url.params.get("after") == "second":
            return httpx.Response(200, json={"data": [{"id": "43", "name": "Wanted"}]})
        return httpx.Response(
            200, json={"data": [{"id": "44", "name": "Other"}], "pagination": {"cursor": "second"}}
        )

    twitch = client_for(handler)
    assert Collector(db, twitch, clock=lambda: NOW).resolve_game("Wanted") == "43"
    twitch.http.close()


def test_repeated_401_is_bounded():
    calls = []
    twitch = client_for(lambda request: calls.append(request) or httpx.Response(401))
    with pytest.raises(TwitchAPIError, match="401"):
        twitch.get_clips(game_id="42")
    assert len(calls) == 2
    twitch.http.close()


def test_network_retry_is_bounded():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("synthetic failure", request=request)

    twitch = client_for(handler)
    with pytest.raises(TwitchAPIError, match="network request failed"):
        twitch.get_clips(game_id="42")
    assert len(calls) == 4
    twitch.http.close()


def test_snapshot_tick_runs_between_discovery_intervals(monkeypatch, tmp_path):
    from viralclip import cli

    monkeypatch.setenv("TWITCH_CLIENT_ID", "synthetic-id")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "synthetic-secret")
    calls = []
    elapsed = [1000.0]

    class FakeCollector:
        def __init__(self, *args, **kwargs):
            pass

        def collect_cycle(self, *args):
            calls.append("discovery")

        def collect_due_snapshots(self):
            calls.append("snapshots")

    def sleep(seconds):
        assert seconds <= 5
        elapsed[0] += seconds
        if elapsed[0] >= 1015:
            raise KeyboardInterrupt

    monkeypatch.setattr(cli, "Collector", FakeCollector)
    monkeypatch.setattr(cli.time, "sleep", sleep)
    monkeypatch.setattr(cli.time, "monotonic", lambda: elapsed[0])
    assert (
        cli.main(["--db", str(tmp_path / "loop.sqlite3"), "collect", "--game", "GTA", "--loop"])
        == 0
    )
    assert calls == ["discovery", "snapshots", "snapshots"]


def test_bad_category_does_not_starve_other_categories(db):
    twitch = client_for(lambda _: httpx.Response(200, json={"data": []}))
    collector = Collector(db, twitch, clock=lambda: NOW)
    with pytest.raises(TwitchAPIError, match="category collection"):
        collector.collect_cycle(("missing category",), ("42",))
    assert db.connection.execute("SELECT COUNT(*) FROM collection_runs").fetchone()[0] == 1
    twitch.http.close()


def test_successful_clip_pagination_uses_cursor_and_actual_page_times(db):
    current = [NOW]

    def handler(request):
        current[0] += timedelta(seconds=2)
        if request.url.params.get("after") == "next":
            return httpx.Response(200, json={"data": [clip("second")], "pagination": {}})
        return httpx.Response(200, json={"data": [clip()], "pagination": {"cursor": "next"}})

    twitch = client_for(handler)
    assert Collector(db, twitch, clock=lambda: current[0]).discover("42") == 2
    rows = db.connection.execute(
        "SELECT observed_at,age_seconds FROM clip_snapshots ORDER BY snapshot_id"
    ).fetchall()
    assert [r["age_seconds"] for r in rows] == [2, 4]
    run = db.connection.execute("SELECT * FROM collection_runs").fetchone()
    assert (run["pages_seen"], run["unique_clips"], run["new_clips"], run["status"]) == (
        2,
        2,
        2,
        "completed",
    )
    twitch.http.close()


def test_impossible_age_rejected_without_any_rows(db):
    with pytest.raises(ValueError, match="creation is after observation"):
        db.record_clip(
            Collector._parse_clip(clip(created_at=NOW + timedelta(seconds=1))), "42", NOW, None
        )
    assert db.status(NOW)["clips"] == 0


@pytest.mark.parametrize(
    "kwargs",
    [{}, {"game_id": "42", "clip_ids": ["a"]}, {"clip_ids": []}, {"clip_ids": ["a"] * 101}],
)
def test_invalid_selectors_rejected_without_http(kwargs):
    def handler(request):
        pytest.fail("invalid selector must not make an HTTP request")

    twitch = make_client(handler)
    with pytest.raises(ValueError):
        twitch.get_clips(**kwargs)
    twitch.http.close()
