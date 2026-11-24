from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from datetime import timedelta
from pathlib import Path

import pytest
from test_collector import NOW, clip

from viralclip import cli
from viralclip.collector.service import Collector
from viralclip.predictions import (
    BASELINE_VERSION,
    NOT_TRAINED,
    ignored_registry,
    link_outcomes,
    rank_pool,
    relative_scores,
    shortlist,
)
from viralclip.storage.database import Database

MINUTE = timedelta(minutes=1)
DAY_START = NOW.replace(hour=0)
DAY = DAY_START.date().isoformat()


@pytest.fixture
def source(tmp_path):
    writer = Database(tmp_path / "collector.sqlite3")
    writer.upsert_game("42", "Synthetic", NOW)
    seen(writer, "a", MINUTE, 2)
    seen(writer, "a", 60 * MINUTE, 50)
    seen(writer, "a", 61 * MINUTE, 999)
    seen(writer, "b", 5 * MINUTE, 10)
    seen(writer, "late", 70 * MINUTE, 5000)
    yield writer
    writer.close()


def seen(db, name, offset, views):
    db.record_clip(Collector._parse_clip(clip(name, views=views)), "42", NOW + offset, None)


def rows(registry, sql, *params):
    with closing(sqlite3.connect(registry)) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute(sql, params)]


def test_relative_scores_cover_spread_ties_and_missing_outputs():
    assert relative_scores([50, 10, None]) == [100, 1, None]
    assert relative_scores([7, 7]) == [100, 100]
    assert relative_scores([None]) == [None]


def test_rank_records_a_sealed_baseline_run_from_pre_cutoff_observations(source, tmp_path):
    registry = tmp_path / "registry" / "predictions.sqlite3"
    result = rank_pool(source.path, registry, "42", DAY_START, 60, scored_at=NOW + 3 * MINUTE * 60)

    assert result["model_status"] == NOT_TRAINED
    assert result["score_version"] == BASELINE_VERSION
    assert (result["pool_size"], result["scored"]) == (2, 2)
    run = rows(registry, "SELECT * FROM ranking_runs")[0]
    assert run["source_watermark"] <= run["scored_at"]
    predictions = rows(registry, "SELECT * FROM predictions ORDER BY rank")
    assert [(p["clip_id"], p["rank"], p["score"]) for p in predictions] == [
        ("a", 1, 100),
        ("b", 2, 1),
    ]
    # The 61-minute observation and the late-discovered clip stay out of the 60m ranking.
    assert predictions[0]["latest_views"] == 50
    assert predictions[0]["latest_observed_at"] <= predictions[0]["prediction_at"]
    assert all(p["scored_at"] >= p["prediction_at"] for p in predictions)
    observation_ids = shortlist(registry, "42", DAY, 60)["predictions"][0]["observation_ids"]
    assert len(observation_ids) == 2 and all(type(i) is int for i in observation_ids)


def test_registry_is_append_only_and_rescoring_adds_a_new_run(source, tmp_path):
    registry = tmp_path / "predictions.sqlite3"
    first = rank_pool(source.path, registry, "42", DAY_START, 30, scored_at=NOW + 2 * 60 * MINUTE)
    second = rank_pool(source.path, registry, "42", DAY_START, 30, scored_at=NOW + 3 * 60 * MINUTE)

    assert first["run_id"] != second["run_id"]
    assert shortlist(registry, "42", DAY, 30, k=1)["run"]["run_id"] == second["run_id"]
    assert len(shortlist(registry, "42", DAY, 30, k=1)["predictions"]) == 1
    with closing(sqlite3.connect(registry)) as db:
        for statement in (
            "UPDATE predictions SET score = 1",
            "DELETE FROM predictions",
            "UPDATE ranking_runs SET pool_size = 9",
            "DELETE FROM ranking_runs",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="Append-only"):
                db.execute(statement)
        with pytest.raises(sqlite3.IntegrityError, match="sealed"):
            db.execute(
                "INSERT INTO predictions (run_id, clip_id, game_id, created_at, cutoff_minutes,"
                " prediction_at, scored_at, feature_status, observation_ids)"
                " VALUES (?, 'x', '42', 'c', 30, 'p', 's', 'eligible', '[]')",
                (first["run_id"],),
            )


def test_rank_rejects_unsafe_inputs(source, tmp_path):
    registry = tmp_path / "predictions.sqlite3"
    with pytest.raises(ValueError, match="separate"):
        rank_pool(source.path, source.path, "42", DAY_START, 60, scored_at=NOW + DAY_SPAN)
    with pytest.raises(ValueError, match="own score version"):
        rank_pool(source.path, registry, "42", DAY_START, 60, scorer=lambda row: 1)
    with pytest.raises(ValueError, match="Cutoff"):
        rank_pool(source.path, registry, "42", DAY_START, 45, scored_at=NOW + DAY_SPAN)
    with pytest.raises(ValueError, match="midnight"):
        rank_pool(source.path, registry, "42", NOW, 60, scored_at=NOW + DAY_SPAN)
    with pytest.raises(ValueError, match="precedes"):
        rank_pool(source.path, registry, "42", DAY_START, 60, scored_at=NOW)
    with pytest.raises(ValueError, match="observed by its cutoff"):
        rank_pool(
            source.path, registry, "42", DAY_START, 60,
            watermark=NOW + 30 * MINUTE, scored_at=NOW + DAY_SPAN,
        )  # fmt: skip
    other = tmp_path / "other.sqlite3"
    with closing(sqlite3.connect(other)) as db:
        db.execute("CREATE TABLE unrelated (x)")
    with pytest.raises(ValueError, match="another database"):
        rank_pool(source.path, other, "42", DAY_START, 60, scored_at=NOW + DAY_SPAN)


DAY_SPAN = timedelta(days=2)


def test_outcomes_link_once_after_maturity_without_changing_predictions(source, tmp_path):
    registry = tmp_path / "predictions.sqlite3"
    rank_pool(source.path, registry, "42", DAY_START, 60, scored_at=NOW + 2 * 60 * MINUTE)
    before = rows(registry, "SELECT * FROM predictions ORDER BY prediction_id")

    early = link_outcomes(source.path, registry, linked_at=NOW + 2 * 60 * MINUTE)
    assert early == {"linked": 0, "by_status": {"deferred": 2}}

    jobs = source.connection.execute(
        "SELECT job_id FROM jobs WHERE clip_id = 'a' AND target_age_seconds = 86400"
    ).fetchall()
    source.add_scheduled_snapshot(
        "a", NOW + timedelta(seconds=86460), 7000, 86400, [job for (job,) in jobs]
    )
    # A later unrelated observation moves the source watermark past the 24h+5m window.
    seen(source, "late", timedelta(hours=24, minutes=10), 6000)
    settled = link_outcomes(source.path, registry, linked_at=NOW + DAY_SPAN)
    # Clip b still has a pending 24h job, so its outcome waits instead of becoming missing.
    assert settled == {"linked": 1, "by_status": {"deferred": 1, "valid": 1}}
    outcome = rows(registry, "SELECT * FROM prediction_outcomes")[0]
    assert (outcome["outcome_status"], outcome["views_24h"]) == ("valid", 7000)
    assert link_outcomes(source.path, registry, linked_at=NOW + DAY_SPAN)["linked"] == 0
    assert rows(registry, "SELECT * FROM predictions ORDER BY prediction_id") == before
    with (
        closing(sqlite3.connect(registry)) as db,
        pytest.raises(sqlite3.IntegrityError, match="Append-only"),
    ):
        db.execute("UPDATE prediction_outcomes SET views_24h = 1")


def test_registry_cli_ranks_and_prints_the_shortlist(source, tmp_path, monkeypatch, capsys):
    registry = tmp_path / "predictions.sqlite3"
    monkeypatch.setattr(cli, "ignored_registry", lambda path: path)
    code = cli.main(
        ["--db", str(source.path), "rank", "--registry", str(registry), "--game-id", "42",
         "--day", DAY, "--cutoff", "60"]
    )  # fmt: skip
    assert code == 0
    assert "2/2 scored with baseline:latest_views:v1 (not_trained_yet)" in capsys.readouterr().out
    code = cli.main(
        ["shortlist", "--registry", str(registry), "--game-id", "42", "--day", DAY,
         "--cutoff", "60", "--k", "1"]
    )  # fmt: skip
    lines = capsys.readouterr().out.splitlines()
    assert code == 0 and len(lines) == 2 and lines[1].split() == ["1", "100", "a"]


def test_registry_must_be_git_ignored(tmp_path):
    with pytest.raises(ValueError, match="Git-ignored"):
        ignored_registry(tmp_path / "predictions.sqlite3")


def test_verify_offline_skips_tracked_files_missing_from_the_working_tree(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    sys.modules.pop("verify_offline", None)
    import verify_offline

    (tmp_path / "kept.md").write_text("# kept\n", encoding="utf-8")
    monkeypatch.setattr(verify_offline, "ROOT", tmp_path)
    monkeypatch.setattr(verify_offline, "git", lambda root, *args: b"kept.md\0deleted.md\0")
    assert verify_offline.source_paths("*.md") == ["kept.md"]
