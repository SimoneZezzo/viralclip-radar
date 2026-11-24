from __future__ import annotations

import csv
import json
import subprocess
import sys
from contextlib import closing
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from viralclip.collector.service import GTA_VI_GAME_ID
from viralclip.dataset import Selection, extract
from viralclip.evaluation import DAY, MATURITY
from viralclip.storage.database import Database, to_utc_iso

START = datetime(2026, 11, 1, tzinfo=UTC)
VALIDATION = START + 4 * DAY
TEST = START + 8 * DAY
END = START + 10 * DAY
MINUTE = timedelta(minutes=1)
TICK = timedelta(microseconds=1)


def make_export(
    root, name, *, top_label=100, outages=(), game=GTA_VI_GAME_ID, primary=False, id_prefix=""
):
    path = root / "data" / (name + ".sqlite3")
    path.parent.mkdir(exist_ok=True)
    labels = {}
    with closing(Database(path)) as db:
        db.upsert_game(game, "Synthetic game", START)
        for offset in (0, 1, 2, 4, 5, 8, 9):
            created = START + offset * DAY
            records = []
            for index in range(1 if offset == 2 else 13):
                cid = f"{id_prefix}{offset}-{index:02d}"
                seen = created + (15 if index < 9 else (60, 36, 45, 60)[index - 9]) * MINUTE
                if index == 12:
                    seen += TICK
                views = 100 if index == 0 else 70 if index in (1, 2) else index
                record = {"id": cid, "created_at": created, "view_count": views}
                records.append(record)
                if index == 11:
                    # A known identity without a stored early view measurement.
                    with db.transaction() as conn:
                        conn.execute(
                            """INSERT INTO clips(clip_id,game_id,created_at,first_seen_at,last_seen_at)
                               VALUES(?,?,?,?,?)""",
                            (
                                cid,
                                game,
                                to_utc_iso(created),
                                to_utc_iso(seen),
                                to_utc_iso(seen),
                            ),
                        )
                        Database._create_jobs(conn, cid, created, seen)
                else:
                    db.record_clip(record, game, seen, None)
                if index == 7:
                    db.record_clip(
                        record | {"view_count": 9000},
                        game,
                        created + 60 * MINUTE + TICK,
                        None,
                    )
                labels[cid] = (created, top_label if (offset, index) == (8, 0) else 100 + index)
            if primary:
                end = created + DAY
                run = db.create_run(game, created, end, end)
                for record in records:
                    db.record_clip(record, game, end, run)
                db.finish_run(run, end, 1, len(records), len(records), 0)
        # The optional label goes last so removing it preserves other snapshot IDs.
        sorted_labels = sorted(labels.items(), key=lambda item: item[0] == f"{id_prefix}8-00")
        for cid, (created, label) in sorted_labels:
            if label is not None:
                job = db.connection.execute(
                    "SELECT job_id FROM jobs WHERE clip_id=? AND target_age_seconds=86400", (cid,)
                ).fetchone()[0]
                db.add_scheduled_snapshot(cid, created + DAY, label, 86400, [job])
        now = END + MATURITY
        db.record_clip({"id": "stamp", "created_at": now, "view_count": 0}, game, now, None)
    artifact = root / "data" / name
    extract(path, Selection(START, END, (game,), outages=outages), artifact)
    return artifact


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("data/\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def cli(artifact, output, *extra, splits=True, additional=(), cohort="observed-at-cutoff"):
    arguments = [
        sys.executable,
        "-I",
        "-B",
        "-m",
        "viralclip",
        "evaluate",
        str(artifact),
        *map(str, additional),
        "--cohort",
        cohort,
        "--output",
        str(output),
        *extra,
    ]
    if splits:
        arguments.extend(
            ("--validation-start", to_utc_iso(VALIDATION), "--test-start", to_utc_iso(TEST))
        )
    return subprocess.run(arguments, capture_output=True, text=True, timeout=15, check=False)


@pytest.mark.parametrize("cohort", ["observed-at-cutoff", "primary"])
def test_benchmark_cli_freezes_both_cohorts_and_reports_sensitivity(workspace, cohort):
    reports = []
    frozen = []
    for name, label in (("missing", None), ("present", 500)):
        source = make_export(
            workspace, name, top_label=label, game="42", primary=cohort == "primary"
        )
        output = workspace / "data" / f"benchmark-{name}"
        result = cli(source, output, "--protocol", "benchmark-v1", "--game-id", "42", cohort=cohort)
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines()[0] == "MECHANISM ONLY"
        reports.append(load_report(output))
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        orders = (output / "frozen_orders.json").read_bytes()
        assert manifest["sha256"]["frozen_orders.json"] == sha256(orders).hexdigest()
        frozen.append(((output / "recommendations.csv").read_bytes(), orders))
    assert frozen[0] == frozen[1]
    report = reports[0]
    assert report["game_id"] == "42"
    assert report["primary_endpoint"] is None
    cutoff = report["by_cutoff_minutes"]["60"]
    assert cutoff["rankable_days_by_split"] == {"train": 2, "validation": 2, "test": 2}
    assert cutoff["valid_test_labels"] == 23
    assert "embargo_at_split_boundary" in cutoff["days"][2]["exclusions"]
    day = cutoff["days"][8]["metrics"]
    total = day["views_24h"]["50"]
    latest = total["methods"]["latest_views"]
    assert total["effective_k"] == 11
    assert total["ideal_overlap"] == total["random_expected_overlap"] == latest["overlap"] == 1
    assert latest["frozen_overlap"] == pytest.approx(11 / 12)
    assert latest["frozen_valid_labels"] == 11
    assert day["post_cutoff_log_growth"]["50"]["target_count"] == 10
    paired = cutoff["metrics"]["test"]["views_24h"]["50"]["overlap"]["methods"]["latest_views"]
    assert paired["paired_ci95"] == [0, 0]
    assert paired["beats_latest_views"] is None


def test_benchmark_primary_cannot_borrow_label_from_unattested_export(workspace):
    attested = make_export(workspace, "attested", top_label=None, game="42", primary=True)
    diagnostic = make_export(workspace, "diagnostic", top_label=500, game="42", primary=True)
    coverage_path = diagnostic / "coverage.json"
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    coverage["primary_discovery"]["policy"] = "legacy-search-day-v1"
    coverage_path.write_text(json.dumps(coverage), encoding="utf-8")
    manifest_path = diagnostic / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sha256"]["coverage.json"] = sha256(coverage_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    output = workspace / "data" / "primary-report"
    result = cli(
        attested,
        output,
        "--protocol",
        "benchmark-v1",
        "--game-id",
        "42",
        additional=(diagnostic,),
        cohort="primary",
    )
    assert result.returncode == 0, result.stderr
    day = load_report(output)["by_cutoff_minutes"]["60"]["days"][8]
    assert day["cohort_size"] == 12
    assert day["valid_labels"] == 11


def test_benchmark_selects_one_exact_game_from_multiple_exports(workspace):
    source = make_export(workspace, "selected", game="42")
    unrelated = make_export(workspace, "unrelated", game="43", id_prefix="other-")
    output = workspace / "data" / "one-game"
    result = cli(
        source, output, "--protocol", "benchmark-v1", "--game-id", "42", additional=(unrelated,)
    )
    assert result.returncode == 0, result.stderr
    report = load_report(output)
    assert report["game_id"] == "42"
    assert report["by_cutoff_minutes"]["60"]["valid_test_labels"] == 24
    assert "other-" not in (output / "recommendations.csv").read_text(encoding="utf-8")


def load_report(directory):
    return json.loads((directory / "evaluation.json").read_text(encoding="utf-8"))


def load_ranking(directory, day, cutoff, method):
    with (directory / "recommendations.csv").open(encoding="utf-8", newline="") as stream:
        return [
            row
            for row in csv.DictReader(stream)
            if (row["day_utc"], row["cutoff_minutes"], row["baseline"])
            == (day.date().isoformat(), str(cutoff), method)
        ]


def test_observed_cli_freezes_every_cutoff_before_labels(workspace):
    source = make_export(workspace, "missing-label", top_label=None)
    output = workspace / "data" / "evaluation"
    result = cli(source, output)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "EVALUATED"
    report = load_report(output)
    assert report["game_id"] == GTA_VI_GAME_ID
    assert report["main_cutoff_minutes"] == 60
    assert report["never_discovered_clips"] == "UNKNOWN"
    cutoffs = report["by_cutoff_minutes"]
    assert cutoffs["60"]["rankable_days_by_split"] == {"train": 2, "validation": 2, "test": 2}
    assert cutoffs["60"]["valid_test_labels"] == 23
    assert not cutoffs["60"]["target_met"]
    assert cutoffs["65"]["valid_test_labels"] == 25
    for cutoff in ("30", "35"):
        assert cutoffs[cutoff]["status"] == "INSUFFICIENT DATA"
        assert cutoffs[cutoff]["metrics"] == {}
    assert set(cutoffs["60"]["metrics"]) == {"validation", "test"}
    day = cutoffs["60"]["days"][8]
    assert day["cohort_size"] == 12
    assert day["features_valid"] == 11
    assert day["features_missing"] == day["late_discoveries_at_watermark"] == 1
    assert day["latest_measurement_age_seconds"] == {"min": 900, "median": 900, "max": 3600}
    assert day["latest_measurement_staleness_seconds"] == {"min": 0, "median": 2700, "max": 2700}
    assert day["label_status"]["valid"] == 11
    assert day["label_status"]["missing"] == 1
    assert day["top10"]["latest_views"] == {
        "positions": 10,
        "valid_scores": 10,
        "valid_labels": 9,
        "valid_score_and_label": 9,
    }
    assert cutoffs["60"]["days"][2]["top10_trivial"]
    assert "embargo_at_split_boundary" in cutoffs["60"]["days"][2]["exclusion_reasons"]
    assert not cutoffs["60"]["days"][2].get("metrics")
    assert day["metrics"]["full_cohort"] is None
    assert cutoffs["60"]["days"][9]["metrics"]["full_cohort"]["label_denominator"] == 12
    latest = load_ranking(output, TEST, 60, "latest_views")
    assert [row["clip_id"] for row in latest[:3]] == ["8-00", "8-01", "8-02"]
    assert next(row["score"] for row in latest if row["clip_id"] == "8-07") == "7"
    assert "8-12" not in {row["clip_id"] for row in latest}
    assert load_ranking(output, TEST, 65, "latest_views")[0]["score"] == "9000"
    growth = load_ranking(output, TEST, 60, "observed_growth")
    assert [row["clip_id"] for row in growth] == [f"8-{i:02d}" for i in range(10)]
    assert all(row["score"] == "" for row in growth)
    assert growth[-1]["clip_id"] == "8-09"  # Exact first_seen cutoff, even with missing score.
    labeled = day["metrics"]["labeled_subset"]
    assert labeled["label_denominator"] == 11
    assert "8-00" not in labeled["baselines"]["latest_views"]["top10_clip_ids"]
    assert latest[0]["position"] == "1"
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["datasets"][0]["watermark"] == to_utc_iso(END + MATURITY)
    assert (
        manifest["datasets"][0]["manifest_sha256"]
        == sha256((source / "manifest.json").read_bytes()).hexdigest()
    )
    expected = (output / "recommendations.csv").read_bytes()
    for label in (5, 500):
        changed_source = make_export(workspace, f"value-{label}", top_label=label)
        assert (changed_source / "candidates.csv").read_bytes() == (
            source / "candidates.csv"
        ).read_bytes()
        changed = workspace / "data" / f"changed-{label}"
        result = cli(changed_source, changed)
        assert result.returncode == 0, result.stderr
        assert (changed / "recommendations.csv").read_bytes() == expected
        other_manifest = json.loads((changed / "manifest.json").read_text(encoding="utf-8"))
        assert (
            other_manifest["sha256"]["recommendations.csv"]
            == manifest["sha256"]["recommendations.csv"]
        )


def test_observed_cli_reports_outages_and_uses_no_implicit_boundaries(workspace):
    source = make_export(
        workspace, "outage", outages=((TEST + DAY + MINUTE, TEST + DAY + 2 * MINUTE),)
    )
    output = workspace / "data" / "blocked"
    result = cli(source, output)
    assert result.returncode == 0, result.stderr
    cutoff = load_report(output)["by_cutoff_minutes"]["60"]
    assert cutoff["status"] == "INSUFFICIENT DATA"
    assert cutoff["rankable_days_by_split"]["test"] == 0
    assert cutoff["metrics"] == {}
    assert len(load_ranking(output, TEST, 60, "latest_views")) == 10
    assert "declared_outage_in_creation_or_label_window" in cutoff["days"][8]["exclusion_reasons"]
    ready = make_export(workspace, "no-split")
    explicit = workspace / "data" / "without-boundaries"
    result = cli(ready, explicit, splits=False)
    assert result.returncode == 0, result.stderr
    report = load_report(explicit)
    assert report["status"] == "SPLIT BOUNDARIES REQUIRED"
    assert report["by_cutoff_minutes"]["60"]["metrics"] == {}


def test_observed_cli_counts_overlapping_exports_once(workspace):
    source = make_export(workspace, "overlap")
    output = workspace / "data" / "overlap-report"
    result = cli(source, output, additional=(source,))
    assert result.returncode == 0, result.stderr
    cutoff = load_report(output)["by_cutoff_minutes"]["60"]
    assert cutoff["valid_test_labels"] == 24
    assert cutoff["rankable_days_by_split"]["test"] == 2
    assert cutoff["days"][8]["cohort_size"] == 12
    assert len(load_ranking(output, TEST, 60, "latest_views")) == 10


def test_observed_cli_rejects_rehashed_timestamp_leak_and_missing_outcome_row(workspace):
    source = make_export(workspace, "invalid")
    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    path = source / "candidates.csv"
    original = path.read_bytes()
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        rows = list(reader)
    row = next(r for r in rows if r["clip_id"] == "8-09" and r["cutoff_minutes"] == "60")
    row["latest_observed_at"] = to_utc_iso(TEST + 60 * MINUTE + TICK)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    manifest["sha256"]["candidates.csv"] = sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    output = workspace / "data" / "rejected"
    result = cli(source, output)
    assert result.returncode == 1
    assert "outside its prediction window" in result.stderr
    assert not output.exists()

    path.write_bytes(original)
    manifest["sha256"]["candidates.csv"] = sha256(original).hexdigest()
    outcomes = source / "outcomes.csv"
    outcomes.write_bytes(b"\n".join(outcomes.read_bytes().splitlines()[:-1]) + b"\n")
    manifest["sha256"]["outcomes.csv"] = sha256(outcomes.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    result = cli(source, output)
    assert result.returncode == 1
    assert "Incomplete clip, cutoff or outcome keys" in result.stderr
    assert not output.exists()
