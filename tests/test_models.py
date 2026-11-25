from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta

import pytest

from viralclip.cli import main
from viralclip.dataset import Selection, extract
from viralclip.models import (
    EXPLORATORY,
    add_activity,
    broadcaster_priors,
    export_metadata,
    feature_vector,
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
    assert report["c2_model"]["metadata_coverage_at_cutoff"] == 1
    block = report["by_cutoff_minutes"]["60"]
    methods = block["metrics"]["test"]["views_24h"]["50"]["overlap"]["methods"]
    assert {"latest_views", "c1", "c2", "c2:safe:ridge", "c2:exploratory:mlp"} <= set(methods)
    for reference in ("latest_views", "c1"):
        assert block[f"c2_vs_{reference}"]["50"]["days"] == 2
    assert "c2_vs_c1" not in report["by_cutoff_minutes"]["30"]


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
    with pytest.raises(ValueError, match="exact --metadata"):
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


def test_metadata_export_refuses_a_tracked_path(sealed):
    root, *_ = sealed
    with pytest.raises(ValueError, match="Git-ignored"):
        export_metadata(root / "data" / "collector.sqlite3", root / "metadata.csv")


def test_leave_one_out_prior_ignores_the_rows_own_label():
    meta = {"solo": {"broadcaster": "b1"}, "peer": {"broadcaster": "b2"}}
    base = {"clip_id": "solo", "latest_views": 5, "first_views": 1}
    base |= {"growth_views_per_minute": 1.0, "staleness_seconds": 60.0}
    base |= {"latest_observation_age_seconds": 3540.0, "observation_count": 2}
    base |= {"discovery_delay_seconds": 60.0, "created": START, "category_activity": 0}
    peer = base | {"clip_id": "peer", "views_24h": 50}
    values = []
    for label in (0, 999):
        row = base | {"views_24h": label}
        priors = broadcaster_priors([row, peer], meta)
        vector = feature_vector(row, EXPLORATORY, meta, priors, own=True)
        values.append(vector[EXPLORATORY.index("broadcaster_prior")])
    assert values[0] == pytest.approx(values[1])


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
