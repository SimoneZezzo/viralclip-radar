from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import pickle
import subprocess
from datetime import UTC, datetime, timedelta

import pytest

from viralclip.cli import main
from viralclip.dataset import Selection, extract
from viralclip.models import (
    EXPLORATORY,
    _validation_scores,
    add_activity,
    broadcaster_priors,
    discriminates,
    export_metadata,
    feature_vector,
    informative_k,
    load_models,
    run_c2,
    train_c2,
)
from viralclip.synthetic import generate

DAY = timedelta(days=1)
START = datetime(2026, 11, 1, tzinfo=UTC)
TRAIN = [START + i * DAY for i in range(4)]
VALIDATION = START + 6 * DAY
TEST = START + 10 * DAY
DAYS = [*TRAIN, VALIDATION, VALIDATION + DAY, TEST, TEST + DAY]
GAME = "42"


@pytest.fixture(scope="module")
def sealed(tmp_path_factory, request):
    root = tmp_path_factory.mktemp("c2")
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    (root / ".gitignore").write_text("data/\n", encoding="utf-8")
    previous = os.getcwd()
    os.chdir(root)  # Git-ignore checks run from the working directory
    request.addfinalizer(lambda: os.chdir(previous))
    collector = root / "data" / "collector.sqlite3"
    generate(collector, DAYS, game_id=GAME, clips_per_day=90)
    training = root / "data" / "training-export"
    extract(collector, Selection(DAYS[0], TEST, (GAME,)), training)
    full = root / "data" / "full-export"
    extract(collector, Selection(DAYS[0], DAYS[-1] + DAY, (GAME,)), full)
    metadata = root / "data" / "metadata.csv"
    assert export_metadata(collector, metadata) == 90 * len(DAYS) + 1
    model = root / "data" / "model"
    manifest = train_c2([training], model, VALIDATION, TEST, game_ids=(GAME,), metadata=metadata)
    return root, training, full, metadata, model, manifest


def test_training_compares_the_zoo_on_validation_and_seals_it(sealed):
    *_, model, manifest = sealed
    assert len(manifest["selection"]) == 8
    assert {item["features"] for item in manifest["selection"]} == {"safe", "exploratory"}
    assert manifest["selected"] in manifest["selection_ties"]
    assert manifest["selection_k"] == 50
    assert manifest["exploratory_assumption"] and manifest["metadata_sha256"]
    loaded, models = load_models(model)
    assert set(models["models"]) == {
        f"{s}:{m}" for s in ("safe", "exploratory") for m in ("ridge", "xgboost", "lightgbm", "mlp")
    }
    assert loaded == manifest


def test_training_refuses_an_export_that_reaches_the_test(sealed):
    root, _, full, *_ = sealed
    with pytest.raises(ValueError, match="end by the test start"):
        train_c2([full], root / "data" / "leaky", VALIDATION, TEST, game_ids=(GAME,))


def test_c2_evaluation_reports_every_model_against_baseline_and_c1(sealed):
    root, _, full, metadata, model, manifest = sealed
    output = root / "data" / "c2-report"
    arguments = ["evaluate", str(full), "--protocol", "c2-v1", "--game-id", GAME]
    arguments += ["--model", str(model), "--metadata", str(metadata), "--output", str(output)]
    arguments += ["--validation-start", VALIDATION.isoformat(), "--test-start", TEST.isoformat()]
    assert main(arguments) == 0
    report = json.loads((output / "evaluation.json").read_text(encoding="utf-8"))
    assert report["benchmark_protocol"] == "c2-v1"
    assert report["c2_model"]["selected"] == manifest["selected"]
    coverage = report["c2_model"]["metadata_coverage_at_cutoff"]
    assert coverage == {"train": 1, "validation": 1, "test": 1, "test_measured": 1}
    assert report["c2_model"]["evaluation_metadata_sha256"] == manifest["metadata_sha256"]
    block = report["by_cutoff_minutes"]["60"]
    methods = block["metrics"]["test"]["views_24h"]["50"]["overlap"]["methods"]
    assert {"latest_views", "c1", "c2", "c2:safe:ridge", "c2:exploratory:mlp"} <= set(methods)
    for reference in ("latest_views", "c1"):
        assert block[f"c2_vs_{reference}"]["50"]["days"] == 2
    assert "c2_vs_c1" not in report["by_cutoff_minutes"]["30"]
    for cutoff in ("30", "35", "65"):  # the 60-minute models rank no other cutoff
        test = report["by_cutoff_minutes"][cutoff]["metrics"]["test"]
        assert not any(m.startswith("c2") for m in test["views_24h"]["50"]["overlap"]["methods"])


def test_c2_accepts_a_later_metadata_file_but_not_one_without_test_clips(sealed):
    root, _, full, metadata, model, manifest = sealed
    lines = metadata.read_text(encoding="utf-8").splitlines(keepends=True)
    test_ids = {
        line.split(",")[0]
        for line in (full / "candidates.csv").read_text(encoding="utf-8").splitlines()[1:]
        if ",2026-11-11" in line or ",2026-11-12" in line
    }
    assert test_ids
    early = root / "data" / "early-metadata.csv"
    early.write_text(
        "".join(line for line in lines if line.split(",")[0] not in test_ids), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="no scored test candidate"):
        run_c2(
            [full],
            root / "data" / "early-meta-report",
            VALIDATION,
            TEST,
            game_id=GAME,
            cohort="observed-at-cutoff",
            model_dir=model,
            metadata=early,
        )
    later = root / "data" / "later-metadata.csv"
    later.write_text("".join(lines) + "extra-clip,,,\n", encoding="utf-8")
    report = run_c2(
        [full],
        root / "data" / "later-meta-report",
        VALIDATION,
        TEST,
        game_id=GAME,
        cohort="observed-at-cutoff",
        model_dir=model,
        metadata=later,
    )
    assert report["c2_model"]["evaluation_metadata_sha256"] != manifest["metadata_sha256"]
    # Metadata only for a test day the benchmark drops for an outage: the report is refused.
    outage = (TEST + timedelta(hours=3), TEST + timedelta(hours=4))
    export = root / "data" / "test-outage-export"
    selection = Selection(DAYS[0], DAYS[-1] + DAY, (GAME,), outages=(outage,))
    extract(root / "data" / "collector.sqlite3", selection, export)
    dropped_day = {
        line.split(",")[0]
        for line in (full / "candidates.csv").read_text(encoding="utf-8").splitlines()[1:]
        if ",2026-11-11" in line
    }
    dropped = root / "data" / "dropped-day-metadata.csv"
    dropped.write_text(
        lines[0] + "".join(line for line in lines[1:] if line.split(",")[0] in dropped_day),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="no measured clip"):
        run_c2(
            [export],
            root / "data" / "dropped-day-report",
            VALIDATION,
            TEST,
            game_id=GAME,
            cohort="observed-at-cutoff",
            model_dir=model,
            metadata=dropped,
        )
    assert not (root / "data" / "dropped-day-report").exists()
    # Metadata only for scored test clips without a valid 24-hour label: also refused.
    with (full / "outcomes.csv").open(encoding="utf-8", newline="") as stream:
        invalid = {r["clip_id"] for r in csv.DictReader(stream) if r["outcome_status"] != "valid"}
    with (full / "candidates.csv").open(encoding="utf-8", newline="") as stream:
        unlabeled = {
            r["clip_id"]
            for r in csv.DictReader(stream)
            if r["clip_id"] in invalid
            and r["cutoff_minutes"] == "60"
            and r["feature_status"] == "eligible"
            and r["created_at"] >= TEST.isoformat()[:10]
        }
    assert unlabeled
    only_unlabeled = root / "data" / "unlabeled-metadata.csv"
    only_unlabeled.write_text(
        lines[0] + "".join(line for line in lines[1:] if line.split(",")[0] in unlabeled),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="no measured clip"):
        run_c2(
            [full],
            root / "data" / "unlabeled-report",
            VALIDATION,
            TEST,
            game_id=GAME,
            cohort="observed-at-cutoff",
            model_dir=model,
            metadata=only_unlabeled,
        )


def test_selection_skips_validation_days_the_benchmark_excludes(sealed):
    root, *_ = sealed
    outage = (VALIDATION + timedelta(hours=3), VALIDATION + timedelta(hours=4))
    export = root / "data" / "outage-export"
    selection = Selection(DAYS[0], TEST, (GAME,), outages=(outage,))
    extract(root / "data" / "collector.sqlite3", selection, export)
    manifest = train_c2(
        [export], root / "data" / "outage-model", VALIDATION, TEST, game_ids=(GAME,)
    )
    excluded = manifest["validation_days_excluded"]
    assert excluded == [{"game_id": GAME, "day_utc": VALIDATION.date().isoformat()}]
    train_outage = (TRAIN[1] + timedelta(hours=3), TRAIN[1] + timedelta(hours=4))
    export = root / "data" / "train-outage-export"
    extract(
        root / "data" / "collector.sqlite3",
        Selection(DAYS[0], TEST, (GAME,), outages=(train_outage,)),
        export,
    )
    manifest = train_c2(
        [export], root / "data" / "train-outage-model", VALIDATION, TEST, game_ids=(GAME,)
    )
    # The outage also hits the previous day's 24-hour label window, as in the benchmark.
    assert manifest["train_days_excluded"] == [
        {"game_id": GAME, "day_utc": day.date().isoformat()} for day in TRAIN[:2]
    ]
    assert manifest["validation_days_excluded"] == []


def test_top_k_overlap_needs_a_pool_that_can_discriminate():
    def pool(views, unscorable=0):
        return [(v, i >= unscorable) for i, v in enumerate(views)]

    assert not discriminates(pool([5] * 60), 50)  # every ordering scores 1
    assert not discriminates(pool(range(50)), 50)  # no clip outside the top 50
    assert discriminates(pool(range(51)), 50)
    # 51 varied labels but only 49 scorable clips: every model keeps all 49 in its top 50.
    assert not discriminates(pool(range(51), unscorable=2), 50)
    assert discriminates(pool(range(51), unscorable=2), 10)
    tied = [{"game_id": GAME, "day": START, "views_24h": 7, "eligible": True} for _ in range(60)]
    assert informative_k(tied) is None


def test_validation_ranks_labeled_clips_without_features_last():
    class Model:
        def predict(self, vectors):
            return [1.0 for _ in vectors]

    rows = [
        {"clip_id": "a", "eligible": False},
        {"clip_id": "b", "eligible": True, "latest_views": 3, "first_views": 1},
    ]
    rows[1] |= {"growth_views_per_minute": 1.0, "staleness_seconds": 60.0}
    rows[1] |= {"latest_observation_age_seconds": 60.0, "observation_count": 2}
    rows[1] |= {"discovery_delay_seconds": 60.0, "created": START, "prediction": START}
    rows[1] |= {"category_activity": 0}
    scores = _validation_scores(Model(), rows, ("log1p_latest_views",), {}, {})
    assert scores == [-math.inf, 1.0]


def test_c2_rejects_other_boundaries_tampering_and_missing_metadata(sealed, tmp_path):
    root, _, full, metadata, model, _ = sealed
    with pytest.raises(ValueError, match="boundaries"):
        run_c2(
            [full],
            root / "data" / "early",
            VALIDATION,
            TEST - DAY,
            game_id=GAME,
            cohort="observed-at-cutoff",
            model_dir=model,
            metadata=metadata,
        )
    with pytest.raises(ValueError, match="need a --metadata"):
        run_c2(
            [full],
            root / "data" / "no-metadata",
            VALIDATION,
            TEST,
            game_id=GAME,
            cohort="observed-at-cutoff",
            model_dir=model,
        )
    copy = tmp_path / "model"
    copy.mkdir()
    (copy / "manifest.json").write_bytes((model / "manifest.json").read_bytes())
    (copy / "models.pkl").write_bytes((model / "models.pkl").read_bytes() + b"x")
    with pytest.raises(ValueError, match="do not match"):
        load_models(copy)
    sealed_payload = pickle.loads((model / "models.pkl").read_bytes())
    del sealed_payload["decision"]["artifact_schema"]  # an artifact from before the schema
    old = pickle.dumps(sealed_payload)
    manifest = json.loads((model / "manifest.json").read_text(encoding="utf-8"))
    manifest.pop("artifact_schema")
    manifest["models_sha256"] = hashlib.sha256(old).hexdigest()
    (copy / "models.pkl").write_bytes(old)
    (copy / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="retrain"):
        load_models(copy)


def test_metadata_export_refuses_a_tracked_path(sealed):
    root, *_ = sealed
    with pytest.raises(ValueError, match="Git-ignored"):
        export_metadata(root / "data" / "collector.sqlite3", root / "metadata.csv")


def test_prior_uses_only_labels_matured_by_the_prediction():
    meta = {name: {"broadcaster": "b1"} for name in ("focal", "later", "older")}
    base = {"clip_id": "focal", "latest_views": 5, "first_views": 1}
    base |= {"growth_views_per_minute": 1.0, "staleness_seconds": 60.0}
    base |= {"latest_observation_age_seconds": 3540.0, "observation_count": 2}
    base |= {"discovery_delay_seconds": 60.0, "category_activity": 0}
    t = START + 2 * DAY
    focal = base | {"created": t, "prediction": t + timedelta(hours=1), "views_24h": 10}
    older = base | {"clip_id": "older", "created": t - 2 * DAY, "views_24h": 50}
    values = []
    for later_label, own_label in ((0, 10), (999, 10), (0, 999)):
        later = base | {"clip_id": "later", "created": t + DAY, "views_24h": later_label}
        row = focal | {"views_24h": own_label}
        priors = broadcaster_priors([row, later, older], meta)
        vector = feature_vector(row, EXPLORATORY, meta, priors)
        values.append(vector[EXPLORATORY.index("broadcaster_prior")])
        assert vector[EXPLORATORY.index("broadcaster_clips")] == pytest.approx(0.6931471805599453)
    assert values[0] == pytest.approx(values[1]) == pytest.approx(values[2])


def test_category_activity_counts_only_peers_discovered_by_the_cutoff():
    t = START + timedelta(hours=2)
    minute = timedelta(minutes=1)
    rows = [
        {"clip_id": "focal", "game_id": GAME, "prediction": t, "first_seen": t - 50 * minute},
        {"clip_id": "early", "game_id": GAME, "prediction": t, "first_seen": t - 10 * minute},
        {"clip_id": "late", "game_id": GAME, "prediction": t + DAY, "first_seen": t + minute},
        {"clip_id": "old", "game_id": GAME, "prediction": t + DAY, "first_seen": t - 120 * minute},
        {"clip_id": "other", "game_id": "7", "prediction": t, "first_seen": t - 5 * minute},
    ]
    add_activity(rows)
    assert rows[0]["category_activity"] == 1  # "early" only: not itself, "late", "old" or "other"
