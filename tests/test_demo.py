import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from viralclip.cli import main
from viralclip.collector.service import GTA_VI_GAME_ID
from viralclip.demo import create_app, prepare_registry, read_ranking


def test_demo_registry_seals_predictions_and_uses_only_pre_cutoff_observations(tmp_path):
    path = tmp_path / "ranking.sqlite3"
    prepare_registry(path)
    model = read_ranking(path, GTA_VI_GAME_ID)
    baseline = read_ranking(path, "32982")
    prepare_registry(path)
    assert read_ranking(path, GTA_VI_GAME_ID) == model
    assert model["run"]["method"] == "simulated_model"
    assert model["run"]["model_status"] == "simulated"
    assert baseline["run"]["method"] == "baseline"
    assert baseline["run"]["model_status"] == "not_trained_yet"
    assert baseline["run"]["score_version"] == "baseline:latest_views:v1"
    rows = model["predictions"]
    assert [row["rank"] for row in rows] == [1, 2, 3, 4, 5, None]
    assert [row["score"] for row in rows] == [100, 65, 51, 21, 1, None]
    assert all("latest_views" not in row for row in rows)
    # Only the 52-minute observation precedes the 60-minute cutoff.
    assert all(len(row["observation_ids"]) == 1 for row in rows)
    assert rows[0]["latest_observed_at"] < rows[0]["prediction_at"] < model["run"]["scored_at"]
    assert rows[-1]["score"] is None
    assert all("media" not in row and "scenario" not in row for row in rows)
    assert rows[0]["twitch_url"] is None
    assert rows[0]["url"] == "https://example.invalid/synthetic-clips/" + rows[0]["clip_id"]
    assert model["editors"][0]["name"] == "external editor"
    assert [row["score"] for row in baseline["predictions"]] == [100, 75, 31, 1]

    with closing(sqlite3.connect(path)) as db:
        assert db.execute(
            "SELECT latest_views FROM predictions WHERE prediction_id=?",
            (rows[0]["prediction_id"],),
        ).fetchone() == (128,)
        with pytest.raises(sqlite3.IntegrityError, match="Append-only"):
            db.execute("UPDATE predictions SET score=1")
        with pytest.raises(sqlite3.IntegrityError, match="sealed"):
            db.execute(
                """INSERT INTO predictions (run_id, clip_id, game_id, created_at, cutoff_minutes,
                   prediction_at, scored_at, feature_status, observation_ids)
                   SELECT run_id, 'extra', game_id, created_at, cutoff_minutes, prediction_at,
                          scored_at, feature_status, observation_ids FROM predictions LIMIT 1"""
            )
    collector = tmp_path / "ranking-synthetic-collector.sqlite3"
    with closing(sqlite3.connect(collector)) as db:
        names = [name for (name,) in db.execute("SELECT name FROM games")]
    assert names and all("SYNTHETIC / NOT REAL TWITCH DATA" in name for name in names)


def test_demo_seeds_a_new_fixture_revision_without_replacing_existing_runs(tmp_path, monkeypatch):
    path = tmp_path / "ranking.sqlite3"
    with monkeypatch.context() as previous:
        previous.setattr("viralclip.demo.FIXTURE_REVISION", "fixture-v1")
        prepare_registry(path)
        original = read_ranking(path, GTA_VI_GAME_ID)

    prepare_registry(path)
    assert read_ranking(path, GTA_VI_GAME_ID)["run"]["run_id"] == f"fixture-v4:{GTA_VI_GAME_ID}"
    monkeypatch.setattr("viralclip.demo.FIXTURE_REVISION", "fixture-v1")
    assert read_ranking(path, GTA_VI_GAME_ID) == original


def test_demo_rejects_an_existing_unrelated_database(tmp_path):
    path = tmp_path / "collector.sqlite3"
    with closing(sqlite3.connect(path)) as db:
        db.execute("CREATE TABLE clips (clip_id TEXT PRIMARY KEY)")
    original = path.read_bytes()
    with pytest.raises(ValueError, match="another database"):
        prepare_registry(path)
    assert path.read_bytes() == original


def test_demo_api_serves_supported_games_with_security_headers(tmp_path):
    path = tmp_path / "ranking.sqlite3"
    prepare_registry(path)
    assets = tmp_path / "dist"
    assets.mkdir()
    (assets / "index.html").write_text('<!doctype html><html lang="en"></html>', "utf-8")
    client = TestClient(create_app(path, assets))

    page = client.get("/")
    assert page.status_code == 200 and 'lang="en"' in page.text
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert page.headers["x-content-type-options"] == "nosniff"
    report = client.get("/api/ranking", params={"game_id": "32982"})
    assert report.status_code == 200
    assert report.headers["cache-control"] == "no-store"
    body = report.json()
    assert body["synthetic"] and body["run"]["game_id"] == "32982"
    assert body == read_ranking(path, "32982")
    assert client.get("/api/ranking").json()["run"]["game_id"] == GTA_VI_GAME_ID
    assert client.get("/api/ranking", params={"game_id": "unknown"}).status_code == 404
    assert client.get("/docs").status_code == 404
    assert client.get("/api/openapi.json").json()["info"]["title"] == "ViralClip Radar demo"


def test_demo_explains_an_unbuilt_front_end(tmp_path):
    path = tmp_path / "ranking.sqlite3"
    prepare_registry(path)
    client = TestClient(create_app(path, tmp_path / "missing"))
    response = client.get("/")
    assert response.status_code == 503
    assert "npm --prefix web run build" in response.text
    assert client.get("/api/ranking").status_code == 200


def test_demo_cli_does_not_load_collector_settings(monkeypatch):
    def unexpected_settings():
        pytest.fail("demo read collector settings")

    calls = []
    monkeypatch.setattr("viralclip.cli.load_settings", unexpected_settings)
    monkeypatch.setattr("viralclip.demo.run_demo", calls.append)
    assert main(["demo", "--port", "8766"]) == 0
    assert calls == [8766]
