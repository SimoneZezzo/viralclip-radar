from __future__ import annotations

import csv
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


def add_clip(inputs, clip_id, created, views, *, late=False, sparse=False, game="42"):
    inputs.primary_clips.add(clip_id)
    inputs.outcomes[clip_id] = Outcome("valid", views, created + DAY)
    inputs.broadcasters[clip_id] = str(int(views) % 2)
    inputs.input_outcomes += 1
    for cutoff in CUTOFFS:
        eligible = not (late and cutoff == 30)
        scores = (views, None if sparse else views, None if sparse else views, views / 5)
        inputs.candidates[clip_id, cutoff] = Candidate(
            clip_id,
            game,
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
    report = evaluate(inputs, START + 4 * DAY, START + 8 * DAY, 1)
    assert report["status"] == "EVALUATED"
    assert [p["unique_clips"] for p in report["periods"].values()] == [44, 44, 22]
    valid = report["periods"]["validation"]
    assert len(valid["rankable_creation_days"]) == 2
    assert valid["by_cutoff_minutes"][30]["embargoed_valid_outcomes"] == 10
    assert valid["by_cutoff_minutes"][30]["outage_exposed_candidates"] == 0
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


def test_sparse_game_cannot_borrow_rankable_days_from_other_game():
    inputs = examples()
    inputs.windows.append(
        SourceWindow(START, START + 10 * DAY, START + 10 * DAY + MATURITY, ("43",))
    )
    for offset in range(10):
        for number in range(10):
            created = START + offset * DAY + timedelta(minutes=number)
            add_clip(inputs, f"42-{offset}-{number}", created, number)
            if offset in (0, 4, 8):
                add_clip(inputs, f"43-{offset}-{number}", created, number, game="43")
    report = evaluate(inputs, START + 4 * DAY, START + 8 * DAY, 1)
    assert report["status"] == "INSUFFICIENT DATA"
    assert not report["metrics"]
    assert len(report["reasons"]) == 3 and all("game 43" in reason for reason in report["reasons"])


def test_outage_during_outcome_excludes_only_affected_game_day():
    inputs = examples()
    outage = START + DAY, START + DAY + timedelta(minutes=1)
    inputs.windows.append(
        SourceWindow(START, START + 10 * DAY, START + 10 * DAY + MATURITY, ("43",), (outage,))
    )
    for number in range(10):
        add_clip(inputs, f"42-{number}", START, number)
        add_clip(inputs, f"43-{number}", START, number, game="43")
    overall = evaluate(inputs, None, None, 1)["overall"]
    assert overall["rankable_creation_days_by_game"] == {"42": [START.date().isoformat()], "43": []}
    assert overall["matched_labeled_clips"] == 20


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


def test_self_consistent_csv_hash_cannot_authorize_fabricated_growth(replays):
    left, _ = replays
    path = left / "candidates.csv"
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        rows = list(reader)
    rows[0]["observed_view_growth"] = "42"
    rows[0]["growth_views_per_minute"] = "42"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(rows)
    manifest_path = left / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sha256"][path.name] = sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="Baseline growth disagrees"):
        read_inputs([left])


def test_primary_discovery_evidence_is_bound_to_the_export_that_supplied_rows(
    tmp_path, monkeypatch
):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("data/\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    selection = Selection(START, START + DAY, ("42",), START + DAY + MATURITY)
    for name, covered in (("attested", True), ("diagnostic", False)):
        db = Database(tmp_path / f"{name}.sqlite3")
        try:
            db.upsert_game("42", "Synthetic", START)
            parsed = Collector._parse_clip(clip(name, created_at=START))
            db.record_clip(parsed, "42", START, None)
            if covered:
                run = db.create_run("42", START, START + DAY, START + DAY)
                db.record_clip(parsed, "42", START + DAY, run)
                db.finish_run(run, START + DAY, 1, 1, 1, 0)
            job = db.connection.execute(
                "SELECT job_id FROM jobs WHERE clip_id=? AND target_age_seconds=86400", (name,)
            ).fetchone()[0]
            db.add_scheduled_snapshot(name, START + DAY, 100, 86400, [job])
            db.record_clip(
                Collector._parse_clip(clip("stamp", created_at=selection.watermark)),
                "42",
                selection.watermark,
                None,
            )
        finally:
            db.close()
        export = tmp_path / "data" / name
        coverage = extract(db.path, selection, export)
        assert bool(coverage["primary_discovery"]["game_days"]) is covered
    primary, diagnostic = (tmp_path / "data" / name for name in ("attested", "diagnostic"))
    inputs = read_inputs([primary, diagnostic])
    assert inputs.primary_clips == {"attested"}
    assert evaluate(inputs, None, None, 10)["overall"]["matched_labeled_clips"] == 2

    coverage_path = primary / "coverage.json"
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    coverage["primary_discovery"]["policy"] = "legacy-search-day-v1"
    coverage_path.write_text(json.dumps(coverage), encoding="utf-8")
    manifest_path = primary / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sha256"][coverage_path.name] = sha256(coverage_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    prior = read_inputs([primary, diagnostic])
    assert prior.primary_clips == set()
    assert evaluate(prior, None, None, 10)["overall"]["matched_labeled_clips"] == 2

    coverage_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Dataset hash mismatch for coverage.json"):
        read_inputs([primary])


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
    explicit = left.parent / "explicit-primary"
    assert (
        main(["evaluate", str(left), str(right), "--cohort", "primary", "--output", str(explicit)])
        == 0
    )
    for name in ("evaluation.json", "manifest.json"):
        assert (output / name).read_bytes() == (explicit / name).read_bytes()


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
