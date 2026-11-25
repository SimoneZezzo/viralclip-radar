from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from contextlib import closing
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from test_collector import clip

from viralclip import predictions
from viralclip.challenger import SCORE_VERSION, c1_row_score
from viralclip.collector.service import Collector
from viralclip.demo import CUTOFF, DAY, GAMES, prepare_registry
from viralclip.predictions import BASELINE_VERSION, rank_pool
from viralclip.publish import GRACE_SECONDS, main, publish
from viralclip.storage.database import Database

SCORED = DAY + timedelta(days=1)
PUBLISHED = SCORED + timedelta(hours=2)


@pytest.fixture
def registry(tmp_path, monkeypatch):
    path = tmp_path / "fixtures.sqlite3"
    monkeypatch.setattr(predictions, "utc_now", lambda: SCORED)
    prepare_registry(path)
    return path


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def game(public, game_id):
    """The game file the live index points to."""
    rankings = public / "rankings"
    entry = next(g for g in read(rankings / "index.json")["games"] if g["id"] == game_id)
    assert re.fullmatch(rf"{game_id}-[0-9a-f]{{16}}\.json", entry["file"])
    return read(rankings / entry["file"])


def test_public_schema_and_freshness_use_only_registry(registry, tmp_path):
    # The publisher must also work when the collector is unavailable.
    registry.with_name("fixtures-synthetic-collector.sqlite3").unlink()
    public = tmp_path / "site"
    rankings = public / "rankings"
    later = PUBLISHED.astimezone(timezone(timedelta(hours=2)))
    index = publish(registry, public, GAMES, published_at=later)
    assert read(rankings / "index.json") == index
    assert index == {
        "published_at": "2026-11-23T02:00:00.000000Z",
        "games": [
            {
                "id": key,
                "name": name,
                "scored_at": "2026-11-23T00:00:00.000000Z",
                "file": entry["file"],
            }
            for (key, name), entry in zip(GAMES.items(), index["games"], strict=True)
        ],
    }
    baseline = game(public, "32982")
    assert baseline == {
        "game_id": "32982",
        "game_name": "GTA V",
        "pool_day": "2026-11-22",
        "cutoff_minutes": 60,
        "scored_at": index["games"][1]["scored_at"],
        "published_at": index["published_at"],
        "score_version": BASELINE_VERSION,
        "model_status": "not_trained_yet",
        "method_label": "latest_views baseline · no validated model for this game",
        "synthetic": True,
        "pool_size": 4,
        "clips": baseline["clips"],
    }
    clips = baseline["clips"]
    assert [row["rank"] for row in clips] == [1, 2, 3, 4]
    assert [row["score"] for row in clips] == [100, 75, 31, 1]
    assert clips[0] == {
        "rank": 1,
        "clip_id": "demo-32982-01",
        "score": 100,
        "prediction_at": "2026-11-22T19:04:00.000000Z",
        "url": None,
        "title": None,
    }
    simulated = game(public, next(iter(GAMES)))
    assert simulated["method_label"].startswith("Simulated model")
    assert simulated["pool_size"] == 6
    assert [p["rank"] for p in simulated["clips"]] == [1, 2, 3, 4, 5]


def test_latest_sealed_run_preserves_title_but_disables_fixture_links(registry, tmp_path):
    collector = registry.with_name("fixtures-synthetic-collector.sqlite3")
    with closing(sqlite3.connect(registry)) as db:
        # Exercise additive registry columns while keeping previous runs readable.
        db.execute(
            "ALTER TABLE predictions ADD COLUMN url TEXT DEFAULT 'https://clips.twitch.tv/X'"
        )
        db.execute("ALTER TABLE predictions ADD COLUMN title TEXT DEFAULT 'Stored title'")
    rank_pool(
        collector,
        registry,
        "32982",
        DAY,
        CUTOFF,
        scored_at=SCORED + timedelta(hours=1),
        scorer=c1_row_score,
        score_version=SCORE_VERSION,
        model_status="trained",
    )
    public = tmp_path / "public"
    publish(registry, public, {"32982": "Selected"}, published_at=PUBLISHED)
    rankings = public / "rankings"
    names = sorted(p.name for p in rankings.iterdir())
    assert len(names) == 2 and names[0].startswith("32982-") and names[1] == "index.json"
    result = game(public, "32982")
    assert result["score_version"] == SCORE_VERSION
    assert result["method_label"] == "c1 · staleness projection"
    assert result["game_name"] == "Selected"
    assert result["synthetic"]
    assert all(row["url"] is None for row in result["clips"])
    assert result["clips"][0]["title"] == "Stored title"


@pytest.mark.parametrize(
    ("run_id", "stored", "expected"),
    [
        (None, None, "https://clips.twitch.tv/Slug%20%2F%3F%23%25%C3%A9"),
        (
            None,
            "https://www.twitch.tv/a/clip/StoredSlug",
            "https://www.twitch.tv/a/clip/StoredSlug",
        ),
        ("fixture:baseline", "https://www.twitch.tv/a/clip/StoredSlug", None),
        ("synthetic:baseline", None, None),
    ],
)
def test_stored_and_derived_links_are_only_for_non_fixture_runs(
    registry, tmp_path, run_id, stored, expected
):
    collector = tmp_path / "mock.sqlite3"
    clip_id = "Slug /?#%é"
    with closing(Database(collector)) as writer:
        writer.upsert_game("42", "Mock game", DAY)
        row = Collector._parse_clip(clip(clip_id, created_at=DAY))
        writer.record_clip(row, "42", DAY + timedelta(minutes=CUTOFF), None)
    if stored:
        with closing(sqlite3.connect(registry)) as db:
            db.execute(
                "ALTER TABLE predictions ADD COLUMN url TEXT "
                "DEFAULT 'https://www.twitch.tv/a/clip/StoredSlug'"
            )
    rank_pool(collector, registry, "42", DAY, CUTOFF, scored_at=SCORED, run_id=run_id)
    public = tmp_path / "site"
    publish(registry, public, {"42": "Mock game"}, published_at=PUBLISHED)
    result = game(public, "42")
    assert result["synthetic"] is (expected is None)
    assert result["clips"][0]["url"] == expected


def test_republish_never_rewrites_live_files_and_replaces_the_index_last(
    registry, tmp_path, monkeypatch
):
    public = tmp_path / "site"
    ranks = public / "rankings"
    publish(registry, public, GAMES, published_at=SCORED)
    first = {g["id"]: g["file"] for g in read(ranks / "index.json")["games"]}
    live = {name: (ranks / name).read_bytes() for name in [*first.values(), "index.json"]}
    replaced = []
    replace = os.replace

    def inspect_replace(src, dst):
        with pytest.raises(ValueError, match="Publish in progress"):
            publish(registry, public, GAMES, published_at=PUBLISHED)
        assert src.parent.parent == ranks
        # Until the index moves, every file the live index names is untouched.
        assert dst.name == "index.json" or dst.name not in live
        assert {name: (ranks / name).read_bytes() for name in live} == live
        replace(src, dst)
        replaced.append(dst.name)

    monkeypatch.setattr(os, "replace", inspect_replace)
    second = publish(registry, public, {"32982": "GTA V"}, published_at=PUBLISHED)
    new_file = second["games"][0]["file"]
    assert replaced == [new_file, "index.json"]
    assert game(public, "32982")["published_at"] == "2026-11-23T02:00:00.000000Z"
    # The previous generation stays for readers holding the old index.
    assert sorted(p.name for p in ranks.iterdir()) == sorted(
        [*first.values(), new_file, "index.json"]
    )
    monkeypatch.setattr(os, "replace", replace)
    (ranks / "1-00000000000000ff.json").write_text("{}", encoding="utf-8")  # interrupted run
    (ranks / "2-00000000000000ff.json").write_text("{}", encoding="utf-8")  # still in grace
    old = time.time() - GRACE_SECONDS - 60
    for name in [*first.values(), "1-00000000000000ff.json"]:
        os.utime(ranks / name, (old, old))
    third = publish(
        registry, public, {"32982": "GTA V"}, published_at=PUBLISHED + timedelta(days=1)
    )
    assert sorted(p.name for p in ranks.iterdir()) == sorted(
        {new_file, third["games"][0]["file"], "2-00000000000000ff.json", "index.json"}
    )


def test_cleanup_failure_does_not_fail_a_completed_publication(registry, tmp_path, monkeypatch):
    public = tmp_path / "site"
    ranks = public / "rankings"
    ranks.mkdir(parents=True)
    stale = ranks / "1-00000000000000ff.json"
    stale.write_text("{}", encoding="utf-8")
    old = time.time() - GRACE_SECONDS - 60
    os.utime(stale, (old, old))
    unlink = Path.unlink

    def locked(path, *args, **kwargs):
        if path == stale:
            raise PermissionError(32, "The file is in use")  # Windows sharing violation
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", locked)
    index = publish(registry, public, {"32982": "GTA V"}, published_at=PUBLISHED)
    assert read(ranks / "index.json") == index and stale.exists()


def test_failed_selection_preserves_previous_publication(registry, tmp_path):
    public = tmp_path / "site"
    ranks = public / "rankings"
    publish(registry, public, GAMES, published_at=SCORED)
    before = {p.name: p.read_bytes() for p in ranks.iterdir()}
    with pytest.raises(ValueError, match="No sealed run for game 999"):
        publish(registry, public, {"32982": "Renamed", "999": "Unknown"}, published_at=PUBLISHED)
    assert {p.name: p.read_bytes() for p in ranks.iterdir()} == before


@pytest.mark.parametrize("games", [{}, {"../42": "Game"}, {"index": "Game"}, {"42": " "}])
def test_invalid_selection(registry, tmp_path, games):
    with pytest.raises(ValueError):
        publish(registry, tmp_path / "site", games)


def test_rejects_wrong_database_unsafe_output_or_invalid_time(registry, tmp_path):
    public = tmp_path / "site"
    with pytest.raises(ValueError, match="Not a prediction registry"):
        publish(registry.with_name("fixtures-synthetic-collector.sqlite3"), public, GAMES)
    with pytest.raises(ValueError, match="outside"):
        publish(registry, registry.parent, GAMES)
    with pytest.raises(ValueError, match="timezone-aware"):
        publish(registry, public, GAMES, published_at=datetime(2026, 12, 1))
    with pytest.raises(ValueError, match="precedes scoring"):
        publish(registry, public, GAMES, published_at=datetime(2026, 11, 22, tzinfo=UTC))


def test_cli_repeatable_game(registry, tmp_path, capsys):
    public = tmp_path / "site"
    args = ["--registry", str(registry), "--output", str(public)]
    for key, name in GAMES.items():
        args.extend(["--game", f"{key}={name}"])
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out) == read(public / "rankings/index.json")
    with pytest.raises(SystemExit):
        main([*args, "--game", "32982=Duplicate"])
