from __future__ import annotations

import configparser
import json
import shlex
from datetime import timedelta
from pathlib import Path
from shutil import copyfile

import pytest
from test_collector import NOW, clip

from viralclip.collector.service import Collector
from viralclip.deployment import main, preflight, snapshot_manifest, verify_snapshot
from viralclip.storage.backup import backup_and_verify, online_copy
from viralclip.storage.database import Database, to_utc_iso

ROOT = Path(__file__).resolve().parents[1]


def test_service_uses_fixed_non_root_paths_and_graceful_shutdown():
    unit = configparser.ConfigParser(interpolation=None)
    unit.read(ROOT / "deploy/viralclip-collector.service", encoding="utf-8")
    service = unit["Service"]
    environment = dict(
        line.split("=", 1)
        for line in (ROOT / "deploy/collector.env.example").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )
    start = shlex.split(service["ExecStart"])
    guard = shlex.split(service["ExecStartPre"])
    assert service["User"] == service["Group"] == "viralclip"
    assert service["StateDirectory"] == "viralclip-radar"
    assert service["StateDirectoryMode"] == "0700"
    assert service["UMask"] == "0077"
    assert service["ProtectSystem"] == "strict"
    assert service["Environment"] == "PYTHON_DOTENV_DISABLED=1"
    assert service["EnvironmentFile"] == "/etc/viralclip/collector.env"
    assert service["KillSignal"] == "SIGINT"
    assert service["Restart"] == "on-failure"
    assert unit["Unit"]["StartLimitBurst"] == "5"
    assert unit["Unit"]["ConditionPathExists"] == "/etc/viralclip/production-authorized"
    assert unit["Install"]["WantedBy"] == "multi-user.target"
    assert start[-4:] == ["collect", "--game", "Grand Theft Auto V", "--loop"]
    assert guard[0] == start[0] == "/opt/viralclip-radar/.venv/bin/python"
    assert start[start.index("--db") + 1] == guard[-1] == environment["VIRALCLIP_DB_PATH"]
    assert environment["VIRALCLIP_GAME_IDS"] == ""
    assert environment["TWITCH_CLIENT_ID"] == environment["TWITCH_CLIENT_SECRET"] == ""


def test_synthetic_transfer_preserves_links_pending_jobs_and_real_times(tmp_path):
    source = tmp_path / "collector.sqlite3"
    donor = Database(source)
    try:
        donor.upsert_game("42", "Synthetic", NOW)
        donor.record_clip(Collector._parse_clip(clip()), "42", NOW, None)
        jobs = list(donor.connection.execute("SELECT job_id, target_age_seconds FROM jobs"))
        job_ids = {age: job for job, age in jobs}
        observed = NOW + timedelta(minutes=10, seconds=17)
        donor.add_scheduled_snapshot("clip-1", observed, 28, 600, [job_ids[600]])
        donor.start_jobs([job_ids[1800]])
    finally:
        donor.close()  # The final transfer snapshot is taken with the donor stopped.
    backup = tmp_path / "backup.sqlite3"
    metrics = backup_and_verify(source, backup)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(snapshot_manifest(backup)), encoding="utf-8")
    received = tmp_path / "received.sqlite3"
    copyfile(backup, received)  # Simulate the transfer of a closed, standalone artifact.
    verify_snapshot(received, manifest_path)
    assert metrics["schema_version"] == 2
    assert metrics["latest_observation_utc"] == to_utc_iso(observed)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert [(row["status"], row["target_age_seconds"]) for row in payload["outstanding_jobs"]] == [
        ("pending", 3600),
        ("pending", 21600),
        ("pending", 86400),
        ("running", 1800),
    ]
    restored = tmp_path / "restored.sqlite3"
    online_copy(received, restored)
    assert snapshot_manifest(restored)["metrics"] == metrics
    receiver = Database(restored)
    try:
        receiver.acquire_collector_lock()
        receiver.recover_running_jobs()
        assert (
            receiver.connection.execute(
                "SELECT status FROM jobs WHERE target_age_seconds=1800"
            ).fetchone()[0]
            == "pending"
        )
        assert receiver.connection.execute(
            "SELECT observed_at FROM clip_snapshots WHERE source='scheduled'"
        ).fetchone()[0] == to_utc_iso(observed)
    finally:
        receiver.close()


def test_manifest_rejects_wal_and_verify_rejects_wrong_transfer(tmp_path, capsys):
    source = tmp_path / "source.sqlite3"
    writer = Database(source)
    try:
        with pytest.raises(ValueError, match="no sidecars"):
            snapshot_manifest(source)
        staged = tmp_path / "stage.sqlite3"
        online_copy(source, staged)
    finally:
        writer.close()
    assert main(["manifest", str(staged)]) == 0
    expected = tmp_path / "manifest.json"
    manifest = json.loads(capsys.readouterr().out)
    manifest["sha256"] = "0" * 64
    expected.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="differ from the source manifest"):
        verify_snapshot(staged, expected)


def test_service_preflight_declines_missing_schema_or_changed_configuration(tmp_path, monkeypatch):
    path = tmp_path / "state.sqlite3"
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setenv("VIRALCLIP_DB_PATH", str(path))
    monkeypatch.setenv("TWITCH_CLIENT_ID", "synthetic-id")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "synthetic-secret")
    monkeypatch.setenv("DISCOVERY_INTERVAL_SECONDS", "300")
    monkeypatch.setenv("DISCOVERY_LOOKBACK_MINUTES", "30")
    monkeypatch.setenv("VIRALCLIP_GAME_IDS", "")
    with pytest.raises(ValueError, match="database is missing"):
        preflight(path)
    assert not path.exists()
    donor = tmp_path / "donor.sqlite3"
    Database(donor).close()
    online_copy(donor, path)
    before = path.read_bytes()
    preflight(path)
    assert path.read_bytes() == before
    monkeypatch.setenv("DISCOVERY_INTERVAL_SECONDS", "60")
    with pytest.raises(ValueError, match="cadence"):
        preflight(path)
    monkeypatch.setenv("DISCOVERY_INTERVAL_SECONDS", "300")
    db = Database(path)
    try:
        with db.transaction() as writer:
            writer.execute("DELETE FROM schema_migrations WHERE version=2")
        with pytest.raises(ValueError, match="schema v2"):
            preflight(path)
    finally:
        db.close()
