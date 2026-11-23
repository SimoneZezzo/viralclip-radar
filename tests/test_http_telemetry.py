from __future__ import annotations

import json

import httpx
import pytest

from viralclip.cli import main
from viralclip.twitch import telemetry
from viralclip.twitch.client import TwitchAPIError, TwitchClient
from viralclip.twitch.telemetry import HttpEventLog


def test_http_retry_sequence_rate_pressure_and_secret_exclusion(tmp_path):
    calls = []
    sleeps = []
    clock = [1000.0]
    responses = iter(
        [
            httpx.ReadTimeout("private-timeout-detail"),
            httpx.ConnectError("private-network-detail"),
            httpx.Response(503, text="private-response-body"),
            httpx.Response(
                429,
                headers={"Retry-After": "7", "Ratelimit-Remaining": "1", "Ratelimit-Reset": "1010"},
            ),
            httpx.Response(
                200,
                json={"data": []},
                headers={"Ratelimit-Remaining": "0", "Ratelimit-Reset": "1020"},
            ),
            httpx.Response(
                200,
                json={"data": []},
                headers={
                    "Ratelimit-Remaining": "private-remaining-value",
                    "Ratelimit-Reset": "private-reset-value",
                },
            ),
        ]
    )

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/token"):
            assert b"private-client-secret" in request.content
            return httpx.Response(200, json={"access_token": "private-token", "expires_in": 7200})
        if request.url.path.endswith("/validate"):
            return httpx.Response(200, json={"client_id": "private-client-id"})
        item = next(responses)
        if isinstance(item, Exception):
            raise item
        return item

    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    log = HttpEventLog(tmp_path / "collector.sqlite3", None)
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = TwitchClient(
            "private-client-id",
            "private-client-secret",
            http=http,
            wall_clock=lambda: clock[0],
            sleep=sleep,
            jitter=lambda *_: 0,
            max_retries=4,
            events=log,
        )
        assert client.get_clips(game_id="private-game", after="private-cursor") == {"data": []}
        assert client.get_clips(clip_ids=["private-clip"]) == {"data": []}
    log.close()
    raw = (tmp_path / "collector.sqlite3.http.jsonl").read_text(encoding="utf-8")
    assert "private-" not in raw
    assert "https://" not in raw
    assert "Authorization" not in raw
    assert sleeps == [1, 2, 4, 8, 5]
    assert calls == ["/oauth2/token", "/oauth2/validate", *(["/helix/clips"] * 6)]
    records = [json.loads(line) for line in raw.splitlines()]
    requests = [row for row in records if row["event"] == "http_request"]
    assert [row["status"] for row in requests] == [200, 200, None, None, 503, 429, 200, 200]
    assert [row["outcome"] for row in requests[2:6]] == [
        "timeout",
        "network_error",
        "response",
        "rate_limited",
    ]
    assert all(row["duration_ms"] >= 0 and row["timestamp"].endswith("+00:00") for row in requests)
    assert requests[5]["rate_limit_remaining"] == 1
    assert requests[5]["rate_limit_reset_epoch"] == 1010
    assert requests[-1]["endpoint"] == "clip_refresh"
    assert requests[-1]["invalid_rate_limit_headers"] == [
        "rate_limit_remaining",
        "rate_limit_reset_epoch",
    ]
    assert "rate_limit_remaining" not in requests[-1]
    retries = [row for row in records if row["event"] == "http_retry"]
    assert [(row["attempt"], row["reason"]) for row in retries] == [
        (2, "timeout"),
        (3, "network_error"),
        (4, "http_5xx"),
        (5, "http_429"),
    ]
    waits = [row for row in records if row["event"] == "rate_limit_wait"]
    assert [(row["reason"], row["delay_seconds"]) for row in waits] == [
        ("http_429", 8),
        ("bucket_exhausted", 5),
    ]


def test_nonfinite_throttle_headers_do_not_disable_retry_or_future_requests():
    sleeps = []
    calls = iter(
        [
            httpx.Response(429, headers={"Retry-After": "inf", "Ratelimit-Reset": "inf"}),
            httpx.Response(
                200,
                json={"data": []},
                headers={"Ratelimit-Remaining": "0", "Ratelimit-Reset": "inf"},
            ),
            httpx.Response(200, json={"data": []}),
        ]
    )
    with httpx.Client(transport=httpx.MockTransport(lambda _: next(calls))) as http:
        client = TwitchClient(
            "fixture", "fixture", http=http, sleep=sleeps.append, jitter=lambda *_: 0
        )
        client._token = "fixture"
        client._token_expires_at = client.wall_clock() + 3600
        client._validated_at = client.wall_clock()
        assert client.get_clips(game_id="42") == {"data": []}
        assert client.get_clips(game_id="42") == {"data": []}
    assert sleeps == [1]


@pytest.mark.parametrize("refresh_fails", [False, True])
def test_oauth_refresh_after_401_and_invalid_response(refresh_fails):
    events = []
    token_requests = 0
    clip_requests = 0

    def handler(request):
        nonlocal token_requests, clip_requests
        if request.url.path.endswith("/token"):
            token_requests += 1
            if token_requests == 2 and refresh_fails:
                return httpx.Response(200, json={"access_token": "secret-malformed-payload"})
            return httpx.Response(200, json={"access_token": "secret-token", "expires_in": 7200})
        if request.url.path.endswith("/validate"):
            return httpx.Response(200, json={"client_id": "id"})
        clip_requests += 1
        return httpx.Response(401 if clip_requests == 1 else 200, json={"data": []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = TwitchClient("id", "secret", http=http, events=events.append)
        if refresh_fails:
            with pytest.raises(TwitchAPIError, match="invalid token response"):
                client.get_clips(game_id="42")
        else:
            assert client.get_clips(game_id="42") == {"data": []}
    refresh = [row for row in events if row["event"] == "oauth_refresh"]
    assert [(row["reason"], row["outcome"]) for row in refresh] == [
        ("initial", "attempt"),
        ("initial", "success"),
        ("unauthorized", "attempt"),
        ("unauthorized", "failure" if refresh_fails else "success"),
    ]
    assert token_requests == 2
    assert clip_requests == (1 if refresh_fails else 2)
    assert "secret-" not in json.dumps(events)


@pytest.mark.parametrize("sink", ["disabled", "callback", "invalid_directory", "write_failure"])
def test_logging_failures_preserve_requests_and_retries(tmp_path, monkeypatch, capsys, sink):
    paths = []
    sleeps = []

    def handler(request):
        paths.append(request.url.path)
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "token", "expires_in": 7200})
        if request.url.path.endswith("/validate"):
            return httpx.Response(200, json={"client_id": "id"})
        return httpx.Response(503 if len(paths) == 3 else 200, json={"data": []})

    def fail(*_args):
        raise OSError("sensitive diagnostic")

    directory = tmp_path / "log-dir"
    if sink == "invalid_directory":
        directory.touch()
    if sink == "write_failure":
        monkeypatch.setattr(telemetry._QuietRotatingHandler, "_open", fail)
    log = HttpEventLog(
        tmp_path / "collector.sqlite3", "off" if sink == "disabled" else str(directory)
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = TwitchClient(
            "id",
            "secret",
            http=http,
            events=fail if sink == "callback" else log,
            sleep=sleeps.append,
            jitter=lambda *_: 0,
        )
        assert client.get_clips(game_id="42") == {"data": []}
    log.close()
    assert paths == ["/oauth2/token", "/oauth2/validate", "/helix/clips", "/helix/clips"]
    assert sleeps == [1]
    assert not list(tmp_path.rglob("*.jsonl"))
    assert capsys.readouterr().err == ""


def test_rotation_retains_complete_records_and_caps_backups(tmp_path, monkeypatch):
    handler = telemetry._QuietRotatingHandler

    def small_handler(*args, **kwargs):
        assert kwargs["backupCount"] == 3
        assert kwargs["maxBytes"] == 5 * 1024 * 1024
        kwargs["maxBytes"] = 256
        return handler(*args, **kwargs)

    monkeypatch.setattr(telemetry, "_QuietRotatingHandler", small_handler)
    directory = tmp_path / "logs"
    log = HttpEventLog(tmp_path / "collector.sqlite3", str(directory))
    assert not directory.exists()
    for attempt in range(30):
        log({"event": "http_request", "endpoint": "clip_refresh", "attempt": attempt})
    log.close()
    files = sorted(directory.iterdir())
    assert len(files) == 4
    assert all(file.stat().st_size <= 256 for file in files)
    rows = [
        json.loads(line) for file in files for line in file.read_text(encoding="utf-8").splitlines()
    ]
    assert min(row["attempt"] for row in rows) > 0
    assert max(row["attempt"] for row in rows) == 29


def test_collect_cli_uses_configured_log_directory(tmp_path, monkeypatch):
    def handler(request):
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "fixture-token", "expires_in": 7200})
        if request.url.path.endswith("/validate"):
            return httpx.Response(200, json={"client_id": "fixture-id"})
        return httpx.Response(200, json={"data": []})

    logs = tmp_path / "logs"
    monkeypatch.setenv("TWITCH_CLIENT_ID", "fixture-id")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "fixture-secret")
    monkeypatch.setenv("VIRALCLIP_HTTP_LOG_DIR", str(logs))
    monkeypatch.setenv("VIRALCLIP_GAMES", "")
    database = tmp_path / "synthetic.sqlite3"
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        monkeypatch.setattr(
            "viralclip.cli.TwitchClient", lambda *args, **kw: TwitchClient(*args, http=http, **kw)
        )
        assert main(["--db", str(database), "collect", "--game-id", "42", "--once"]) == 0
    rows = [
        json.loads(line)
        for line in (logs / "synthetic.sqlite3.http.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [row["endpoint"] for row in rows if row["event"] == "http_request"] == [
        "oauth_token",
        "oauth_validate",
        "clip_discovery",
    ]
