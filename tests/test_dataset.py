from __future__ import annotations

import csv
import json
import subprocess
from datetime import timedelta
from hashlib import sha256

import pytest
from test_collector import NOW, clip

from viralclip.cli import main
from viralclip.collector.service import Collector
from viralclip.dataset import CUTOFFS, FEATURES, Selection, candidate, outcome, read_source
from viralclip.storage.database import Database

DAY = timedelta(days=1)
MINUTE = timedelta(minutes=1)
TICK = timedelta(microseconds=1)


@pytest.fixture
def db(tmp_path):
    writer = Database(tmp_path / "source.sqlite3")
    writer.upsert_game("42", "Synthetic", NOW)
    yield writer
    writer.close()


def seen(db, name, offset, views=2):
    db.record_clip(Collector._parse_clip(clip(name, views=views)), "42", NOW + offset, None)


def job_ids(db, name, *targets):
    jobs = db.connection.execute(
        "SELECT job_id, target_age_seconds FROM jobs WHERE clip_id = ?", (name,)
    )
    return [job for job, age in jobs if age in targets]


def scheduled(db, name, offset, *targets, views=100):
    db.add_scheduled_snapshot(
        name,
        NOW + offset,
        views,
        targets[0] if len(targets) == 1 else None,
        job_ids(db, name, *targets),
    )


def selection(watermark=None, outages=()):
    return Selection(NOW, NOW + MINUTE, ("42",), watermark, outages)


def features(source, name, cutoff, outages=()):
    clip = next(c for c in source.clips if c.clip_id == name)
    return candidate(clip, source.observations[name], cutoff, source.watermark, outages)


@pytest.mark.parametrize("cutoff", CUTOFFS)
def test_prediction_boundary_is_inclusive_to_the_microsecond(db, cutoff):
    seen(db, "clip", MINUTE)
    seen(db, "clip", cutoff * MINUTE, views=20)
    seen(db, "clip", cutoff * MINUTE + TICK, views=999)
    source = read_source(db.path, selection())
    row = features(source, "clip", cutoff)
    assert row["latest_views"] == 20
    assert row["observation_count"] == 2
    assert row["staleness_seconds"] == 0
    assert row["observed_view_growth"] == 18
    assert row["growth_views_per_minute"] == pytest.approx(18 / (cutoff - 1))


def test_delayed_discovery_and_cutoff_maturity(db):
    seen(db, "late", 32 * MINUTE)
    seen(db, "later", 36 * MINUTE)
    source = read_source(db.path, selection(NOW + 35 * MINUTE))
    assert [c.clip_id for c in source.clips] == ["late"]
    late = features(source, "late", 30)
    assert late["feature_status"] == "late_discovery"
    assert late["discovery_delay_seconds"] is None
    assert late["latest_views"] is None
    eligible = features(source, "late", 35)
    assert eligible["discovery_delay_seconds"] == 32 * 60
    assert eligible["staleness_seconds"] == 3 * 60
    assert eligible["observed_view_growth"] is None
    assert features(source, "late", 60)["feature_status"] == "cutoff_immature"


def test_no_measurement_preserves_missing_features(db):
    seen(db, "clip", 5 * MINUTE)
    seen(db, "clip", 66 * MINUTE)
    source = read_source(db.path, selection())
    row = candidate(source.clips[0], [], 30, source.watermark, ())
    assert row["feature_status"] == "missing_observations"
    assert row["observation_count"] == 0
    assert row["discovery_delay_seconds"] == 300
    assert row["first_views"] is row["latest_views"] is row["growth_views_per_minute"] is None


def test_recovery_snapshot_uses_actual_time_and_is_deduplicated(db):
    seen(db, "clip", 2 * MINUTE)
    recovered = 61 * MINUTE
    scheduled(db, "clip", recovered, 1800, 3600, views=14)
    seen(db, "clip", recovered, views=999)  # Same instant, larger ID, different source.
    seen(db, "clip", 66 * MINUTE, views=1000)  # Advances the watermark past the 65m cutoff.
    source = read_source(db.path, selection())
    assert features(source, "clip", 30)["latest_views"] == 2
    assert features(source, "clip", 60)["latest_views"] == 2
    row = features(source, "clip", 65)
    assert row["latest_views"] == 14
    assert row["observation_count"] == 2
    assert row["growth_views_per_minute"] == pytest.approx(12 / 59)
    assert row["observation_ids"] == "1|2"


def test_outcome_requires_full_window_and_accepts_shared_recovery_link(db):
    seen(db, "clip", MINUTE)
    scheduled(db, "clip", DAY + 5 * MINUTE, 21600, 86400, views=0)
    before = read_source(db.path, selection(NOW + DAY + 5 * MINUTE - TICK))
    assert outcome(before.clips[0], before.jobs.get("clip"), before.watermark)[
        "outcome_status"
    ] == ("immature")
    at = read_source(db.path, selection(NOW + DAY + 5 * MINUTE))
    label = outcome(at.clips[0], at.jobs["clip"], at.watermark)
    assert label["outcome_status"] == "valid"
    assert label["label_age_seconds"] == 86700
    assert label["views_24h"] == 0


def test_missing_unavailable_invalid_and_out_of_window_are_never_zero(db):
    for name in ("missing", "unavailable", "future", "invalid", "late", "early"):
        seen(db, name, MINUTE)
    db.finish_jobs(job_ids(db, "unavailable", 86400), "unavailable", NOW + DAY)
    db.finish_jobs(job_ids(db, "future", 86400), "unavailable", NOW + DAY + 6 * MINUTE)
    other = db.connection.execute(
        "SELECT snapshot_id FROM clip_snapshots WHERE clip_id='missing'"
    ).fetchone()[0]
    with db.transaction() as connection:
        connection.execute(
            "UPDATE jobs SET status='completed', completed_at=?, snapshot_id=? "
            "WHERE clip_id='invalid' AND target_age_seconds=86400",
            ((NOW + DAY).isoformat(), other),
        )
    scheduled(db, "late", DAY + 5 * MINUTE + TICK, 86400)
    scheduled(db, "early", DAY - TICK, 86400)
    assert outcome_statuses(db) == {
        "missing": "missing",
        "unavailable": "unavailable",
        "future": "missing",
        "invalid": "invalid_link",
        "late": "outside_window",
        "early": "outside_window",
    }


def outcome_statuses(db):
    source = read_source(db.path, selection())
    rows = [outcome(c, source.jobs.get(c.clip_id), source.watermark) for c in source.clips]
    assert all(r["views_24h"] is None for r in rows)
    return {r["clip_id"]: r["outcome_status"] for r in rows}


def test_future_jobs_and_mutable_metadata_cannot_change_candidate_features(db):
    seen(db, "clip", 3 * MINUTE)
    seen(db, "clip", 65 * MINUTE, views=10)
    frozen = selection(NOW + 65 * MINUTE)
    before = read_source(db.path, frozen)
    scheduled(db, "clip", DAY, 86400, views=9999)
    with db.transaction() as conn:
        conn.execute(
            "UPDATE clips SET title='future title', language='future', broadcaster_id='future', "
            "duration_seconds=999 WHERE clip_id='clip'"
        )
    after = read_source(db.path, frozen)
    for cutoff in CUTOFFS:
        assert features(before, "clip", cutoff) == features(after, "clip", cutoff)
    assert after.jobs == {}


def test_cli_exports_separate_audit_files_and_blackout_coverage(db, tmp_path, monkeypatch, capsys):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("data/\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("viralclip.cli.Database", lambda *_: pytest.fail("SQLite writer opened"))
    monkeypatch.setattr("viralclip.cli.TwitchClient", lambda *_: pytest.fail("Twitch opened"))
    seen(db, "known", 5 * MINUTE)
    seen(db, "late", 40 * MINUTE)
    scheduled(db, "known", DAY, 86400)
    scheduled(db, "late", DAY + 5 * MINUTE, 86400)
    args = [
        "--db",
        str(db.path),
        "dataset",
        "--start",
        NOW.isoformat(),
        "--end",
        (NOW + MINUTE).isoformat(),
        "--game-id",
        "42",
        "--outage",
        (NOW + 7 * MINUTE).isoformat(),
        (NOW + 39 * MINUTE).isoformat(),
    ]
    assert main([*args, "--output", "public-output"]) == 1
    assert not (tmp_path / "public-output").exists()
    capsys.readouterr()
    output = tmp_path / "data" / "run"
    assert main([*args, "--output", str(output)]) == 0
    assert "30m: 2 candidates, 1 eligible, 1 labeled" in capsys.readouterr().out
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    coverage = json.loads((output / "coverage.json").read_text(encoding="utf-8"))
    assert manifest["model_feature_columns"] == list(FEATURES)
    for name, checksum in manifest["sha256"].items():
        assert sha256((output / name).read_bytes()).hexdigest() == checksum
    with (output / "candidates.csv").open(encoding="utf-8", newline="") as stream:
        candidates = list(csv.DictReader(stream))
    assert len(candidates) == 8
    assert not {"title", "broadcaster_id", "views_24h", "outcome_status"} & candidates[0].keys()
    assert coverage["outages"][0]["early_target_overlap_outcomes"] == {
        "known_before_gap": {"valid": 1},
        "discovered_after_gap": {"valid": 1},
        "discovered_during_gap": {},
    }
    assert coverage["by_cutoff_minutes"]["30"]["labeled"] == 1
    assert coverage["by_cutoff_minutes"]["60"]["labeled"] == 2
    assert main([*args, "--output", str(output)]) == 1
