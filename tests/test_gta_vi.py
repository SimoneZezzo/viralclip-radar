from __future__ import annotations

import configparser
import os
from pathlib import Path

import httpx
import pytest
from test_collector import NOW

from viralclip import gta_vi
from viralclip.storage.database import Database
from viralclip.twitch.client import TwitchClient


@pytest.mark.parametrize("reverse_id", [gta_vi.APPROVED_GAME_ID, "12345"])
def test_helix_verifies_exact_name_then_returned_id(reverse_id):
    queries = []

    def handler(request):
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "fixture", "expires_in": 7200})
        if request.url.path.endswith("/validate"):
            return httpx.Response(200, json={"client_id": "fixture-id"})
        assert request.url.host == "api.twitch.tv"
        assert request.url.path == "/helix/games"
        queries.append(dict(request.url.params))
        result_id = gta_vi.APPROVED_GAME_ID if "name" in request.url.params else reverse_id
        return httpx.Response(200, json={"data": [{"id": result_id, "name": gta_vi.NAME}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = TwitchClient("fixture-id", "fixture-secret", http=http)
        if reverse_id == gta_vi.APPROVED_GAME_ID:
            assert gta_vi.resolve(client) == gta_vi.APPROVED_GAME_ID
        else:
            with pytest.raises(ValueError, match="disagreed"):
                gta_vi.resolve(client)
    assert queries == [{"name": gta_vi.NAME}, {"id": gta_vi.APPROVED_GAME_ID}]


@pytest.mark.parametrize(
    "data",
    [[], [{"id": "32982", "name": gta_vi.NAME}], [{"id": "2", "name": "Grand Theft Auto V"}]],
)
def test_resolver_rejects_missing_and_wrong_categories(data):
    with pytest.raises(ValueError):
        gta_vi._exact_match(data)


@pytest.fixture
def pilot(tmp_path, monkeypatch):
    state = tmp_path / "pilot"
    db = state / gta_vi.DB_NAME
    env = {
        "PYTHON_DOTENV_DISABLED": "1",
        "VIRALCLIP_GTA_VI_GAME_ID": gta_vi.APPROVED_GAME_ID,
        "VIRALCLIP_DB_PATH": str(db),
        "VIRALCLIP_HTTP_LOG_DIR": str(state),
        "VIRALCLIP_GAMES": "",
        "VIRALCLIP_GAME_IDS": "",
        "DISCOVERY_INTERVAL_SECONDS": "300",
        "DISCOVERY_LOOKBACK_MINUTES": "10",
        "TWITCH_CLIENT_ID": "fixture",
        "TWITCH_CLIENT_SECRET": "fixture",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return state, db


def test_pilot_dispatches_only_pinned_game_with_existing_database(pilot, monkeypatch):
    state, path = pilot
    with pytest.raises(ValueError, match="Initialize"):
        gta_vi._preflight(state, gta_vi.APPROVED_GAME_ID)
    assert not path.exists()
    Database(path).close()
    before = path.read_bytes()
    calls = []
    monkeypatch.setattr(gta_vi, "collector", lambda args: calls.append(args) or 0)
    assert gta_vi.main(["run", "--state", str(state)]) == 0
    assert calls == [["--db", str(path), "collect", "--game-id", gta_vi.APPROVED_GAME_ID, "--loop"]]
    assert path.read_bytes() == before


def test_preflight_rejects_id_drift_and_donor_alias(pilot, tmp_path, monkeypatch):
    state, path = pilot
    donor_path = tmp_path / "gta-v.sqlite3"
    donor = Database(donor_path)
    donor.upsert_game("32982", "Grand Theft Auto V", NOW)
    donor.close()
    state.mkdir()
    os.link(donor_path, path)
    with pytest.raises(ValueError, match="Initialize"):
        gta_vi._preflight(state, gta_vi.APPROVED_GAME_ID)
    path.unlink()
    Database(path).close()
    with pytest.raises(ValueError, match="approved Helix result"):
        gta_vi._preflight(state, "12345")
    monkeypatch.setenv("DISCOVERY_LOOKBACK_MINUTES", "30")
    with pytest.raises(ValueError, match="pilot settings"):
        gta_vi._preflight(state, gta_vi.APPROVED_GAME_ID)


def test_unit_has_separate_paths_and_activation_marker():
    deploy = Path(__file__).resolve().parents[1] / "deploy"
    unit = configparser.ConfigParser(interpolation=None)
    unit.read(deploy / "viralclip-gta-vi.service")
    assert unit["Unit"]["ConditionPathExists"] == "/etc/viralclip/gta-vi-authorized"
    assert unit["Service"]["User"] == unit["Service"]["StateDirectory"] == "viralclip-gta-vi"
    assert unit["Service"]["EnvironmentFile"] == "/etc/viralclip/gta-vi.env"
    assert unit["Service"]["CPUQuota"] == "35%"
    assert "viralclip.gta_vi run" in unit["Service"]["ExecStart"]
