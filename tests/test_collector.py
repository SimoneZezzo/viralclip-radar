from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from viralclip.collector.service import Collector
from viralclip.config import load_settings
from viralclip.storage.database import Database
from viralclip.twitch.client import TwitchAPIError, TwitchClient

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


def clip(clip_id: str = "clip-1", *, created_at: datetime = NOW, views: int = 17) -> dict:
    return {
        "id": clip_id,
        "broadcaster_id": "broadcaster-1",
        "broadcaster_name": "Streamer",
        "creator_id": "creator-1",
        "title": "A clip",
        "url": f"https://clips.twitch.tv/{clip_id}",
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "view_count": views,
        "language": "en",
        "duration": 30.5,
    }


def make_client(handler, *, sleep=lambda _delay: None) -> TwitchClient:
    def validated_handler(request):
        if request.url.path.endswith("/oauth2/validate"):
            return httpx.Response(200, json={"client_id": "client-id", "expires_in": 3600})
        return handler(request)

    return TwitchClient(
        "client-id",
        "client-secret",
        http=httpx.Client(transport=httpx.MockTransport(validated_handler)),
        sleep=sleep,
        jitter=lambda _low, _high: 0,
    )


def test_game_lookup_exact_match_and_missing_category(tmp_path: Path) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "test-token", "expires_in": 3600})
        return httpx.Response(200, json={"data": [{"id": "42", "name": "Grand Theft Auto V"}]})

    database = Database(tmp_path / "test.sqlite3")
    twitch = make_client(handler)
    collector = Collector(database, twitch, clock=lambda: NOW)
    assert collector.resolve_game("Grand Theft Auto V") == "42"
    with pytest.raises(TwitchAPIError, match="category not found"):
        collector.resolve_game("Grand Theft Auto VI")
    assert len(calls) == 3
    database.close()
    twitch.http.close()


def test_credentials_loaded_from_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TWITCH_CLIENT_ID", "from-env")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "secret-from-env")
    monkeypatch.setenv("VIRALCLIP_DB_PATH", str(tmp_path / "db.sqlite3"))
    settings = load_settings()
    assert settings.client_id == "from-env"
    assert settings.client_secret == "secret-from-env"
    assert settings.db_path == tmp_path / "db.sqlite3"


def test_401_refreshes_token_once_and_retries_request() -> None:
    token_count = 0
    clip_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_count, clip_count
        if request.url.path.endswith("/oauth2/token"):
            token_count += 1
            return httpx.Response(
                200, json={"access_token": f"token-{token_count}", "expires_in": 3600}
            )
        clip_count += 1
        if clip_count == 1:
            return httpx.Response(401)
        return httpx.Response(200, json={"data": [], "pagination": {}})

    twitch = make_client(handler)
    twitch.get_clips(game_id="42")
    assert token_count == 2
    assert clip_count == 2
    twitch.http.close()


def test_overlapping_discovery_preserves_first_seen_and_appends_snapshots(
    tmp_path: Path,
) -> None:
    current = [NOW]
    response_views = [5, 12]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        return httpx.Response(
            200, json={"data": [clip(views=response_views.pop(0))], "pagination": {}}
        )

    database = Database(tmp_path / "db.sqlite3")
    database.upsert_game("42", "GTA", NOW)
    twitch = make_client(handler)
    collector = Collector(database, twitch, clock=lambda: current[0])
    collector.discover("42")
    first_seen = database.connection.execute(
        "SELECT first_seen_at FROM clips WHERE clip_id = 'clip-1'"
    ).fetchone()[0]
    current[0] += timedelta(minutes=5)
    collector.discover("42")
    snapshots = database.connection.execute(
        "SELECT view_count FROM clip_snapshots WHERE clip_id = 'clip-1' ORDER BY snapshot_id"
    ).fetchall()
    assert [row["view_count"] for row in snapshots] == [5, 12]
    assert database.connection.execute("SELECT COUNT(*) FROM clips").fetchone()[0] == 1
    assert (
        database.connection.execute(
            "SELECT first_seen_at FROM clips WHERE clip_id = 'clip-1'"
        ).fetchone()[0]
        == first_seen
    )
    database.close()
    twitch.http.close()


def test_late_discovery_marks_old_targets_missed_without_backdating(tmp_path: Path) -> None:
    database = Database(tmp_path / "db.sqlite3")
    database.upsert_game("42", "GTA", NOW)
    created = NOW - timedelta(hours=2)
    database.record_clip(Collector._parse_clip(clip(created_at=created)), "42", NOW, None)
    jobs = database.connection.execute(
        "SELECT target_age_seconds, status FROM jobs ORDER BY target_age_seconds"
    ).fetchall()
    assert [(row["target_age_seconds"], row["status"]) for row in jobs] == [
        (600, "missed"),
        (1800, "missed"),
        (3600, "missed"),
        (21600, "pending"),
        (86400, "pending"),
    ]
    snapshot = database.connection.execute(
        "SELECT observed_at, age_seconds FROM clip_snapshots"
    ).fetchone()
    assert snapshot["observed_at"].endswith("Z")
    assert snapshot["age_seconds"] == 7200
    database.close()


def test_due_snapshot_batches_under_one_hundred_and_handles_unordered_results(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "db.sqlite3")
    database.upsert_game("42", "GTA", NOW)
    clip_ids = [f"clip-{index}" for index in range(101)]
    for clip_id in clip_ids:
        database.record_clip(Collector._parse_clip(clip(clip_id)), "42", NOW, None)

    requested_batches = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        ids = request.url.params.get_list("id")
        requested_batches.append(ids)
        return httpx.Response(
            200,
            json={
                "data": [
                    clip(clip_id, views=100 + int(clip_id.split("-")[1]))
                    for clip_id in reversed(ids)
                ]
            },
        )

    twitch = make_client(handler)
    collector = Collector(database, twitch, clock=lambda: NOW + timedelta(minutes=11))
    assert collector.collect_due_snapshots() == 101
    assert len(requested_batches) == 2
    assert max(map(len, requested_batches)) <= 100
    stored = database.connection.execute(
        "SELECT clip_id, view_count FROM clip_snapshots WHERE source = 'scheduled'"
    ).fetchall()
    assert {row["clip_id"] for row in stored} == set(clip_ids)
    assert {row["clip_id"]: row["view_count"] for row in stored} == {
        clip_id: 100 + int(clip_id.split("-")[1]) for clip_id in clip_ids
    }
    database.close()
    twitch.http.close()


def test_429_waits_for_retry_after_and_retries() -> None:
    clips_attempts = 0
    delays = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal clips_attempts
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        clips_attempts += 1
        if clips_attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        return httpx.Response(200, json={"data": []})

    twitch = make_client(handler, sleep=delays.append)
    twitch.get_clips(game_id="42")
    assert delays == [7.0]
    assert clips_attempts == 2
    twitch.http.close()


def test_5xx_retries_with_bounded_backoff() -> None:
    clip_attempts = 0
    delays = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal clip_attempts
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        clip_attempts += 1
        if clip_attempts == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"data": []})

    twitch = make_client(handler, sleep=delays.append)
    twitch.get_clips(game_id="42")
    assert delays == [1.0]
    assert clip_attempts == 2
    twitch.http.close()


def test_oauth_5xx_retries_without_exposing_credentials() -> None:
    token_attempts = 0
    delays = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_attempts
        if request.url.path.endswith("/oauth2/token"):
            token_attempts += 1
            if token_attempts == 1:
                return httpx.Response(503)
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        return httpx.Response(200, json={"data": []})

    twitch = make_client(handler, sleep=delays.append)
    twitch.get_clips(game_id="42")
    assert token_attempts == 2
    assert delays == [1.0]
    twitch.http.close()


def test_rate_limit_remaining_defers_next_request_until_reset() -> None:
    now = [1000.0]
    delays = []
    api_requests = 0

    def sleep(seconds: float) -> None:
        delays.append(seconds)
        now[0] += seconds

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal api_requests
        if request.url.path.endswith("/oauth2/validate"):
            return httpx.Response(200, json={"client_id": "client-id", "expires_in": 3600})
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        api_requests += 1
        headers = {"Ratelimit-Remaining": "0", "Ratelimit-Reset": "1010"}
        return httpx.Response(200, json={"data": []}, headers=headers)

    twitch = TwitchClient(
        "client-id",
        "client-secret",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=sleep,
        jitter=lambda _low, _high: 0,
        wall_clock=lambda: now[0],
    )
    twitch.get_clips(game_id="42")
    twitch.get_clips(game_id="42")
    assert delays == [10.0]
    assert api_requests == 2
    twitch.http.close()


def test_unavailable_clip_is_not_recorded_as_zero(tmp_path: Path) -> None:
    database = Database(tmp_path / "db.sqlite3")
    database.upsert_game("42", "GTA", NOW)
    database.record_clip(Collector._parse_clip(clip()), "42", NOW, None)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        return httpx.Response(200, json={"data": []})

    twitch = make_client(handler)
    collector = Collector(database, twitch, clock=lambda: NOW + timedelta(minutes=11))
    collector.collect_due_snapshots()
    assert (
        database.connection.execute(
            "SELECT COUNT(*) FROM clip_snapshots WHERE source = 'scheduled'"
        ).fetchone()[0]
        == 0
    )
    assert (
        database.connection.execute(
            "SELECT status FROM jobs WHERE target_age_seconds = 600"
        ).fetchone()[0]
        == "unavailable"
    )
    database.close()
    twitch.http.close()


def test_discovery_uses_persisted_watermark_after_a_long_gap(tmp_path: Path) -> None:
    database = Database(tmp_path / "db.sqlite3")
    database.upsert_game("42", "GTA", NOW)
    database.update_watermark("42", NOW - timedelta(hours=4))
    requested_start = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        requested_start.append(request.url.params["started_at"])
        return httpx.Response(200, json={"data": [], "pagination": {}})

    twitch = make_client(handler)
    Collector(database, twitch, clock=lambda: NOW).discover("42")
    assert requested_start == ["2026-11-16T07:55:00Z"]
    database.close()
    twitch.http.close()


def test_restart_recovers_running_jobs_without_duplicates(tmp_path: Path) -> None:
    database = Database(tmp_path / "db.sqlite3")
    database.upsert_game("42", "GTA", NOW)
    database.record_clip(Collector._parse_clip(clip()), "42", NOW, None)
    job = database.connection.execute(
        "SELECT job_id FROM jobs WHERE target_age_seconds = 600"
    ).fetchone()[0]
    database.start_jobs([job])
    database.close()
    restarted = Database(tmp_path / "db.sqlite3")
    Collector(restarted, make_client(lambda _: httpx.Response(200, json={"data": []})))
    assert (
        restarted.connection.execute("SELECT status FROM jobs WHERE job_id = ?", (job,)).fetchone()[
            0
        ]
        == "pending"
    )
    assert restarted.connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 5
    restarted.close()


def test_snapshots_cannot_be_updated_or_deleted(tmp_path: Path) -> None:
    database = Database(tmp_path / "db.sqlite3")
    database.upsert_game("42", "GTA", NOW)
    database.record_clip(Collector._parse_clip(clip()), "42", NOW, None)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        database.connection.execute(
            "UPDATE clip_snapshots SET view_count = 0 WHERE clip_id = 'clip-1'"
        )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        database.connection.execute("DELETE FROM clip_snapshots WHERE clip_id = 'clip-1'")
    assert (
        database.connection.execute(
            "SELECT view_count FROM clip_snapshots WHERE clip_id = 'clip-1'"
        ).fetchone()[0]
        == 17
    )
    database.close()


def test_status_is_local_and_timestamps_require_timezone(tmp_path: Path) -> None:
    database = Database(tmp_path / "db.sqlite3")
    assert database.status(NOW)["clips"] == 0
    with pytest.raises(ValueError, match="timezone-aware"):
        from viralclip.storage.database import to_utc_iso

        to_utc_iso(datetime(2026, 11, 16))
    database.close()
