from __future__ import annotations

import json
import subprocess
from datetime import timedelta
from hashlib import sha256
from math import log1p, log2

import pytest
from test_collector import NOW, clip

from viralclip.cli import main
from viralclip.collector.service import Collector
from viralclip.dataset import CUTOFFS, Selection, extract
from viralclip.evaluation import (
    MATURITY,
    Candidate,
    Inputs,
    Outcome,
    SourceWindow,
    _candidate,
    evaluate,
    ranking_metrics,
    read_inputs,
)
from viralclip.storage.database import Database, to_utc_iso

DAY = timedelta(days=1)
START = NOW.replace(hour=0)


def test_ranking_metrics_use_true_outcomes_and_include_boundary_ties():
    views = {"a": 100, "b": 100, **{str(i): i for i in range(8)}}
    result = ranking_metrics(["7", "a", "b", *(str(i) for i in range(7))], views, 2)
    assert result["precision_at_k"] == 0.5
    assert result["recall_at_k"] == 0.5
    assert result["relevant"] == 2
    assert result["ndcg_at_k"] == pytest.approx(
        (log1p(7) + log1p(100) / log2(3)) / (log1p(100) + log1p(100) / log2(3))
    )
    assert ranking_metrics(["only"], {"only": 0}, 10)["ndcg_at_k"] is None


def examples(start=START, end=START + 10 * DAY):
    return Inputs({}, {}, {}, [SourceWindow(start, end, end + MATURITY, ("42",))], set(), [], 0, 0)


def add_clip(inputs, clip_id, created, views, *, late=False, sparse=False):
    inputs.outcomes[clip_id] = Outcome("valid", views, created + DAY)
    inputs.broadcasters[clip_id] = str(int(views) % 2)
    inputs.input_outcomes += 1
    for cutoff in CUTOFFS:
        eligible = not (late and cutoff == 30)
        scores = (views, None if sparse else views, None if sparse else views, views / 5)
        inputs.candidates[clip_id, cutoff] = Candidate(
            clip_id,
            "42",
            created,
            cutoff,
            "eligible" if eligible else "late_discovery",
            "1" if eligible else "",
            scores if eligible else (None,) * 4,
        )
        inputs.input_candidates += 1


def test_chronological_evaluation_scores_cutoff_and_matched_pools():
    inputs = examples()
    for offset in range(10):
        for i in range(11):
            add_clip(
                inputs,
                f"{offset}-{i}",
                START + offset * DAY + timedelta(minutes=i),
                i,
                late=i == 10,
                sparse=i == 9,
            )
    inputs.outages.add((START + 4 * DAY, START + 4 * DAY + timedelta(minutes=3)))
    report = evaluate(inputs, START + 4 * DAY, START + 8 * DAY, 1)
    assert report["status"] == "EVALUATED"
    assert [p["unique_clips"] for p in report["periods"].values()] == [44, 44, 22]
    valid = report["periods"]["validation"]
    assert len(valid["rankable_creation_days"]) == 2
    assert valid["by_cutoff_minutes"][30]["embargoed_valid_outcomes"] == 10
    assert valid["by_cutoff_minutes"][30]["outage_exposed_candidates"] == 3
    assert valid["by_cutoff_minutes"][30]["missing_scores_among_eligible"]["growth_rate"] == 4
    assert (
        valid["by_cutoff_minutes"][30]["matched_population"]["broadcaster_concentration"][
            "distinct_known"
        ]
        == 2
    )
    assert set(report["metrics"]) == {"validation", "test"}
    scores = report["metrics"]["test"]
    for cutoff in CUTOFFS:
        assert [p["clips"] for p in scores[cutoff]["matched"]["pools"]] == [10, 10]
        assert [p["clips"] for p in scores[cutoff]["cutoff_eligible"]["pools"]] == (
            [10, 10] if cutoff == 30 else [11, 11]
        )
        assert scores[cutoff]["matched"]["macro_average"]["latest_views"]["ndcg_at_k"] == 1
        assert scores[cutoff]["matched"]["macro_average"]["growth_rate"]["precision_at_k"] == 0


def test_embargo_requires_full_label_window_even_for_already_observed_labels():
    inputs = examples()
    boundary = START + 4 * DAY
    add_clip(inputs, "edge", boundary - MATURITY, 12)
    add_clip(inputs, "too-late", boundary - MATURITY + timedelta(microseconds=1), 15)
    add_clip(inputs, "test", START + 8 * DAY, 22)
    report = evaluate(inputs, boundary, START + 8 * DAY, 10)
    train = report["periods"]["train"]["by_cutoff_minutes"][30]
    assert report["status"] == "INSUFFICIENT DATA"
    assert train["label_status_among_eligible"] == {"valid": 1, "embargoed_at_period_boundary": 1}
    assert train["eligible_with_label"] == 1
    assert not report["metrics"]


def test_several_partial_intervals_on_one_day_do_not_create_independent_days():
    inputs = examples(START, START + timedelta(hours=3))
    inputs.windows *= 3
    for i in range(20):
        add_clip(inputs, str(i), START + timedelta(minutes=i), i)
    report = evaluate(inputs, None, None, 10)
    assert report["status"] == "INSUFFICIENT DATA"
    assert report["overall"]["matched_labeled_clips"] == 20
    assert not report["overall"]["covered_mature_creation_days"]
    assert report["periods"] == report["metrics"] == {}


def test_future_feature_timestamp_is_rejected():
    prediction = START + timedelta(minutes=30)
    row = {
        "created_at": to_utc_iso(START),
        "cutoff_minutes": "30",
        "game_id": "42",
        "prediction_at": to_utc_iso(prediction),
        "feature_status": "eligible",
        "first_observed_at": to_utc_iso(START),
        "latest_observed_at": to_utc_iso(prediction + timedelta(microseconds=1)),
    }
    with pytest.raises(ValueError, match="outside its prediction window"):
        _candidate(row, examples().windows[0])


@pytest.fixture
def replays(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("data/\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    db = Database(tmp_path / "synthetic.sqlite3")
    try:
        db.upsert_game("42", "Synthetic", NOW)
        for name in ("early", "late"):
            db.record_clip(
                Collector._parse_clip(clip(name)), "42", NOW + timedelta(minutes=5), None
            )
            job = db.connection.execute(
                "SELECT job_id FROM jobs WHERE clip_id=? AND target_age_seconds=86400", (name,)
            ).fetchone()[0]
            db.add_scheduled_snapshot(name, NOW + DAY + timedelta(minutes=5), 100, 86400, [job])
    finally:
        db.close()
    selection = Selection(START, START + DAY, ("42",))
    left, right = tmp_path / "data/left", tmp_path / "data/right"
    extract(db.path, selection, left)
    extract(db.path, selection, right)
    return left, right


def test_overlap_deduplicates_and_report_manifest_is_reproducible(replays, monkeypatch, capsys):
    monkeypatch.setattr("viralclip.cli.load_settings", lambda: pytest.fail("configuration opened"))
    left, right = replays
    output = left.parent / "evaluation"
    assert main(["evaluate", str(left), str(right), "--output", str(output)]) == 0
    assert "INSUFFICIENT DATA" in capsys.readouterr().out
    report = json.loads((output / "evaluation.json").read_text(encoding="utf-8"))
    assert report["deduplication"] == {
        "input_candidate_rows": 16,
        "unique_candidate_rows": 8,
        "duplicate_candidate_rows_removed": 8,
        "duplicate_clip_occurrences_removed": 2,
    }
    assert report["overall"]["matched_labeled_clips"] == 2
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert (
        manifest["evaluation_sha256"]
        == sha256((output / "evaluation.json").read_bytes()).hexdigest()
    )
    assert (
        manifest["datasets"][0]["manifest_sha256"]
        == sha256((left / "manifest.json").read_bytes()).hexdigest()
    )
    assert "broadcaster-1" not in (left / "broadcasters.csv").read_text(encoding="utf-8")


def test_hash_mismatch_is_rejected(replays):
    left, _ = replays
    with (left / "candidates.csv").open("ab") as stream:
        stream.write(b"tampered\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        read_inputs([left])


def test_conflicting_labels_fail_even_if_hash_is_internally_consistent(replays):
    left, right = replays
    labels = right / "outcomes.csv"
    labels.write_bytes(labels.read_bytes().replace(b",100\n", b",101\n"))
    source_manifest = right / "manifest.json"
    manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
    manifest["sha256"]["outcomes.csv"] = sha256(labels.read_bytes()).hexdigest()
    source_manifest.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="disagree on a valid label"):
        read_inputs([left, right])


def test_valid_label_with_an_unelapsed_window_is_rejected(replays):
    _, right = replays
    path = right / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["source_watermark"] = to_utc_iso(NOW + MATURITY - timedelta(microseconds=1))
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="maturity disagrees"):
        read_inputs([right])
