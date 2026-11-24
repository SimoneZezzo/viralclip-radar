from __future__ import annotations

import json
import sqlite3
import subprocess
from contextlib import closing
from datetime import UTC, datetime

import pytest

from viralclip.cli import main
from viralclip.synthetic import LABEL, dry_run, generate, views_at

DAY = datetime(2026, 11, 24, tzinfo=UTC)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("data/\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_view_curve_is_monotone_and_reaches_the_24h_total():
    ages = [0, 60, 600, 3600, 21600, 86400]
    views = [views_at(1000, 7200, age) for age in ages]
    assert views == sorted(views)
    assert views[0] == 0 and views[-1] == 1000


def test_generator_is_seeded_labeled_and_keeps_missing_states_distinct(tmp_path):
    first = generate(tmp_path / "a.sqlite3", [DAY], clips_per_day=60)
    second = generate(tmp_path / "b.sqlite3", [DAY], clips_per_day=60)
    assert first == second
    dumps = []
    for name in ("a.sqlite3", "b.sqlite3"):
        with closing(sqlite3.connect(tmp_path / name)) as db:
            dumps.append(
                db.execute(
                    "SELECT clip_id, observed_at, view_count FROM clip_snapshots ORDER BY 1, 2"
                ).fetchall()
            )
            names = [row[0] for row in db.execute("SELECT name FROM games")]
            statuses = dict(db.execute("SELECT status, count(*) FROM jobs GROUP BY status"))
            negative = db.execute(
                "SELECT count(*) FROM clip_snapshots WHERE view_count < 0"
            ).fetchone()[0]
    assert dumps[0] == dumps[1]
    assert names and all(LABEL in name for name in names)
    assert statuses["completed"] > 0 and negative == 0
    with pytest.raises(ValueError, match="must be new"):
        generate(tmp_path / "a.sqlite3", [DAY])


def test_dry_run_exercises_benchmark_registry_and_outcomes(workspace):
    summary = dry_run(workspace / "data" / "run", clips_per_day=30)

    assert summary["label"] == LABEL
    assert summary["benchmark_status"] == "MECHANISM ONLY"
    assert set(summary["test_top50_overlap_macro_mean"]) >= {"latest_views", "growth_rate"}
    runs = summary["registry_runs"]
    assert len(runs) == 2 and all(run["model_status"] == "not_trained_yet" for run in runs)
    # A daily replay scores after the last cutoff, so early clips may already be mature.
    assert summary["registry_mode"] == "daily replay"
    assert all(
        0 <= run["ranked_with_24h_outcome_already_observed"] <= run["pool_size"] for run in runs
    )
    outcomes = summary["outcomes"]
    assert outcomes["by_status"]["valid"] > 0
    assert outcomes["linked"] == sum(
        count for status, count in outcomes["by_status"].items() if status != "deferred"
    )
    written = json.loads((workspace / "data" / "run" / "summary.json").read_text("utf-8"))
    assert written["benchmark_status"] == "MECHANISM ONLY"
    assert (workspace / "data" / "run" / "benchmark" / "manifest.json").is_file()
    with pytest.raises(ValueError, match="new directory"):
        dry_run(workspace / "data" / "run", clips_per_day=30)


def test_dry_run_reports_insufficient_data_instead_of_crashing(workspace, capsys):
    code = main(["synthetic-dry-run", "--output", "data/tiny", "--clips-per-day", "1"])
    output = capsys.readouterr().out
    assert code == 0
    assert "Benchmark: INSUFFICIENT DATA" in output
    assert "Test top-50 overlap (views_24h, 60m): not scored" in output


def test_dry_run_requires_a_git_ignored_output(workspace):
    with pytest.raises(ValueError, match="Git-ignored"):
        dry_run(workspace / "visible", clips_per_day=30)


def test_dry_run_cli_needs_no_collector_settings(workspace, monkeypatch, capsys):
    monkeypatch.setattr(
        "viralclip.cli.load_settings", lambda: pytest.fail("dry run read collector settings")
    )
    code = main(["synthetic-dry-run", "--output", "data/cli", "--clips-per-day", "30"])
    output = capsys.readouterr().out
    assert code == 0
    assert output.startswith(LABEL) and "Benchmark: MECHANISM ONLY" in output
    assert main(["synthetic-dry-run", "--output", "data/zero", "--clips-per-day", "0"]) == 1
