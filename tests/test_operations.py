from __future__ import annotations

import configparser
import json
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_collector import NOW, clip

from viralclip import operations as ops
from viralclip.collector.service import Collector
from viralclip.deployment import snapshot_manifest, verify_snapshot
from viralclip.storage.backup import online_copy
from viralclip.storage.database import Database


@pytest.fixture
def live(tmp_path, monkeypatch):
    path = tmp_path / "synthetic.sqlite3"
    database = Database(path)
    database.upsert_game("42", "Fixture", NOW)
    database.record_clip(Collector._parse_clip(clip()), "42", NOW, None)
    monkeypatch.setattr(ops.shutil, "disk_usage", lambda _: (40 * ops.GIB, 0, 40 * ops.GIB))
    for key in ("VIRALCLIP_LOCAL_KEEP", "VIRALCLIP_REMOTE_DAILY", "VIRALCLIP_REMOTE_WEEKLY"):
        monkeypatch.delenv(key, raising=False)
    yield path
    database.close()


def test_verified_backup_and_retention_with_live_wal(live, tmp_path, monkeypatch):
    root = tmp_path / "backups"
    calls = []
    monkeypatch.setenv("VIRALCLIP_LOCAL_KEEP", "1")
    monkeypatch.setenv("VIRALCLIP_REMOTE_DAILY", "3")

    def restic(args, *, cwd=None):
        calls.append(args)
        if args[0] == "backup":
            verify_snapshot(cwd / ops.DB_NAME, cwd / ops.MANIFEST, expected_game_id="42")
            assert (live.parent / (live.name + "-wal")).is_file()

    ops.run_backup(live, root, NOW, expected_game_id="42", restic=restic)
    unrelated = root / "operator-data"
    unrelated.mkdir()
    ops.run_backup(live, root, NOW + timedelta(days=1), expected_game_id="42", restic=restic)
    bundles = [p for p in root.iterdir() if ops.STAMP.fullmatch(p.name)]
    assert len(bundles) == 1
    assert unrelated.is_dir()
    assert [args[0] for args in calls] == ["backup", "forget", "backup", "forget"]
    assert calls[-1][calls[-1].index("--keep-daily") + 1] == "3"
    assert json.loads((root / "latest-offsite.json").read_text())["bundle"] == bundles[0].name


def test_remote_failure_preserves_verified_local_backup_and_previous_marker(live, tmp_path):
    root = tmp_path / "backups"
    ops.run_backup(live, root, NOW, expected_game_id="42", restic=lambda *_args, **_kw: None)
    before = (root / "latest-offsite.json").read_bytes()

    def unavailable(args, **_kwargs):
        assert args[0] == "backup"
        raise RuntimeError("restic backup failed")

    with pytest.raises(RuntimeError, match="restic backup failed"):
        ops.run_backup(
            live, root, NOW + timedelta(days=1), expected_game_id="42", restic=unavailable
        )
    assert (root / "latest-offsite.json").read_bytes() == before
    assert len([p for p in root.iterdir() if ops.STAMP.fullmatch(p.name)]) == 2


def test_backup_aborts_before_creating_bundle_if_disk_reserve_not_met(live, tmp_path, monkeypatch):
    monkeypatch.setattr(ops.shutil, "disk_usage", lambda _: (40 * ops.GIB, 39 * ops.GIB, ops.GIB))
    root = tmp_path / "backups"
    with pytest.raises(RuntimeError, match="Insufficient free space"):
        ops.run_backup(
            live,
            root,
            NOW,
            expected_game_id="42",
            restic=lambda *_a, **_k: pytest.fail("remote contacted"),
        )
    assert not list(root.iterdir())
    assert ops.reserve_bytes(10 * ops.GIB, 40 * ops.GIB) == 21 * ops.GIB


def test_restore_drill_calls_real_sqlite_verifier(live, tmp_path):
    root = tmp_path / "backups"
    ops.run_backup(live, root, NOW, expected_game_id="42", restic=lambda *_a, **_k: None)
    bundle = next(path for path in root.iterdir() if ops.STAMP.fullmatch(path.name))
    manifest = json.loads((bundle / ops.MANIFEST).read_text(encoding="utf-8"))
    assert (manifest["manifest_version"], manifest["game_id"]) == (2, "42")
    output = tmp_path / "restored"

    def restic(args):
        assert args[:2] == ["restore", "latest"]
        shutil.copytree(bundle, output / "bundle")

    before = live.read_bytes()
    ops.restore_latest(output, expected_game_id="42", restic=restic)
    assert (output / "rehearsal.sqlite3").is_file()
    assert live.read_bytes() == before
    with pytest.raises(FileExistsError):
        ops.restore_latest(output, expected_game_id="42", restic=restic)


def test_backup_rejects_wrong_game_before_publish(live, tmp_path):
    root = tmp_path / "backups"
    with pytest.raises(ValueError, match="expected game ID"):
        ops.run_backup(
            live,
            root,
            NOW,
            expected_game_id="32982",
            restic=lambda *_a, **_k: pytest.fail("remote contacted"),
        )
    assert not list(root.iterdir())


def _legacy_bundle(tmp_path, game_ids, *, record_discovery=True):
    bundle = tmp_path / "bundle"
    donor = Database(tmp_path / "donor.sqlite3")
    try:
        for game_id in game_ids:
            donor.upsert_game(game_id, game_id, NOW)
        if game_ids and record_discovery:
            run = donor.create_run(game_ids[0], NOW - timedelta(minutes=10), NOW, NOW)
            donor.finish_run(run, NOW, 1, 1, 0, 0)
        database = bundle / ops.DB_NAME
        online_copy(donor.path, database)
    finally:
        donor.close()
    manifest = snapshot_manifest(database)
    (bundle / ops.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    return bundle, manifest


def _fake_restore(bundle, output):
    def restic(args):
        assert args[:2] == ["restore", "latest"]
        shutil.copytree(bundle, output / "bundle")

    return restic


@pytest.mark.parametrize(
    ("game_ids", "expected_id", "record_discovery", "message"),
    [
        pytest.param(("32982",), "1867279146", True, "expected game ID", id="gta-v-as-gta-vi"),
        pytest.param(("1867279146",), "32982", True, "expected game ID", id="gta-vi-as-gta-v"),
        pytest.param((), "32982", False, "exactly one game ID", id="empty"),
        pytest.param(("32982", "1867279146"), "32982", True, "exactly one game ID", id="mixed"),
        pytest.param(
            ("32982",), "32982", False, "no clips or successful discovery", id="seed-only"
        ),
    ],
)
def test_restore_rejects_untrusted_database_identity(
    tmp_path, game_ids, expected_id, record_discovery, message
):
    bundle, _manifest = _legacy_bundle(tmp_path, game_ids, record_discovery=record_discovery)
    output = tmp_path / "rejected"
    with pytest.raises(ValueError, match=message):
        ops.restore_latest(
            output, expected_game_id=expected_id, restic=_fake_restore(bundle, output)
        )
    assert not (output / "rehearsal.sqlite3").exists()


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        pytest.param({"manifest_version": 2}, "manifest game ID", id="missing-id"),
        pytest.param(
            {"manifest_version": 2, "game_id": "1867279146"},
            "manifest game ID",
            id="contradictory-id",
        ),
        pytest.param({"sha256": "0" * 64}, "differ from the source manifest", id="wrong-digest"),
        pytest.param({"manifest_version": 3}, "manifest version", id="unknown-version"),
        pytest.param(None, "duplicate keys", id="duplicate-identity"),
    ],
)
def test_restore_rejects_bad_metadata(tmp_path, changes, message):
    bundle, manifest = _legacy_bundle(tmp_path, ("32982",))
    if changes is None:
        manifest["manifest_version"] = 2
        manifest["game_id"] = "32982"
        serialized = json.dumps(manifest)[:-1] + ', "game_id": "1867279146"}'
    else:
        serialized = json.dumps(manifest | changes)
    (bundle / ops.MANIFEST).write_text(serialized, encoding="utf-8")
    output = tmp_path / "rejected"
    with pytest.raises(ValueError, match=message):
        ops.restore_latest(output, expected_game_id="32982", restic=_fake_restore(bundle, output))
    assert not (output / "rehearsal.sqlite3").exists()


def test_restore_checks_database_even_when_manifest_claims_expected_game(tmp_path):
    bundle, manifest = _legacy_bundle(tmp_path, ("32982",))
    manifest.update(manifest_version=2, game_id="1867279146")
    (bundle / ops.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / "rejected"
    with pytest.raises(ValueError, match="Backup database does not contain the expected game ID"):
        ops.restore_latest(
            output, expected_game_id="1867279146", restic=_fake_restore(bundle, output)
        )
    assert not (output / "rehearsal.sqlite3").exists()


def test_restore_requires_independent_expected_game_id(tmp_path):
    output = tmp_path / "rejected"
    with pytest.raises(SystemExit) as exit_info:
        ops.main(["restore-latest", str(output)])
    assert exit_info.value.code == 2
    with pytest.raises(ValueError, match="expected game ID is required"):
        ops.restore_latest(
            output, expected_game_id="", restic=lambda _: pytest.fail("remote contacted")
        )
    assert not output.exists()


@pytest.mark.parametrize("game_id", ["32982", "1867279146"])
def test_restore_accepts_legacy_empty_discovery_for_expected_game(tmp_path, game_id):
    bundle, _manifest = _legacy_bundle(tmp_path, (game_id,))
    output = tmp_path / "verified"
    ops.restore_latest(output, expected_game_id=game_id, restic=_fake_restore(bundle, output))
    assert (output / "rehearsal.sqlite3").is_file()


def test_monitor_combines_state_disk_and_backup_freshness(live, tmp_path, monkeypatch):
    root = tmp_path / "backups"
    ops.run_backup(live, root, NOW, expected_game_id="42", restic=lambda *_a, **_k: None)
    monkeypatch.setattr(ops, "read_health", lambda *_: (0, ["Collector health passed."]))

    def active(_unit):
        return {
            "ActiveState": "active",
            "SubState": "running",
            "MainPID": "42",
            "Result": "success",
        }

    assert ops.monitor(live, root, NOW, service=active)[0] == 0
    queried = []
    assert (
        ops.monitor(
            live,
            root,
            NOW,
            collector_unit="other.service",
            backup_unit="other-backup.service",
            service=lambda unit: queried.append(unit) or active(unit),
        )[0]
        == 0
    )
    assert queried == ["other.service", "other-backup.service"]
    assert ops.monitor(live, root, NOW + timedelta(hours=31), service=active)[0] == 1
    assert ops.monitor(live, root, NOW + timedelta(hours=49), service=active)[0] == 2
    assert ops.monitor(live, root, NOW, service=lambda _: {"ActiveState": "failed"})[0] == 2
    monkeypatch.setattr(
        ops.shutil, "disk_usage", lambda _: (40 * ops.GIB, 37 * ops.GIB, 3 * ops.GIB)
    )
    assert ops.monitor(live, root, NOW, service=active)[0] == 2
    severity, lines = ops.monitor(live.with_name("missing.sqlite3"), root, NOW, service=active)
    assert severity == 2
    assert "Could not measure collector database storage." in lines


def test_restic_passes_isolated_credentials_without_logging_remote_output(tmp_path, monkeypatch):
    credentials = {
        "s3-access-key": "fixture-access",
        "s3-secret-key": "fixture-secret",
        "restic-password": "fixture-password",
    }
    for name, value in credentials.items():
        (tmp_path / name).write_text(value, encoding="utf-8")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
    monkeypatch.setenv("RESTIC_REPOSITORY", "s3:https://fixture.test/bucket/private")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "must-not-reach-child")

    def command(argv, *, env, **_options):
        assert argv == ["/usr/bin/restic", "--no-cache", "check"]
        assert env["AWS_SECRET_ACCESS_KEY"] == "fixture-secret"
        assert "TWITCH_CLIENT_SECRET" not in env
        return subprocess.CompletedProcess(argv, 10, b"", b"fixture-secret")

    monkeypatch.setattr(ops.subprocess, "run", command)
    with pytest.raises(RuntimeError, match="^restic check failed with exit code 10$"):
        ops._restic(["check"])


def test_heartbeat_only_sends_severity(tmp_path, monkeypatch):
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
    (tmp_path / "alert-url").write_text("https://fixture.test/token", encoding="utf-8")
    requests = []

    class Fake:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def open(self, request, *, timeout):
            requests.append((request.full_url, request.data, timeout))
            return self

    monkeypatch.setattr(ops, "build_opener", lambda *_: Fake())
    ops._heartbeat(0)
    ops._heartbeat(1)
    assert requests == [
        ("https://fixture.test/token", b"HEALTHY", 10),
        ("https://fixture.test/token/fail", b"DEGRADED", 10),
    ]


def test_operations_units_do_not_own_or_restart_collector():
    deploy = Path(__file__).resolve().parents[1] / "deploy"
    for name in ("backup", "monitor"):
        service = configparser.ConfigParser(interpolation=None, strict=False)
        service.read(deploy / f"viralclip-{name}.service", encoding="utf-8")
        settings = service["Service"]
        assert settings["User"] == "viralclip"
        assert settings["Type"] == "oneshot"
        assert settings["ProtectSystem"] == "strict"
        assert f"viralclip.operations {name}" in settings["ExecStart"]
        if name == "backup":
            assert settings["ExecStart"].endswith("--expected-game-id 32982")
        assert "collector.env" not in (deploy / f"viralclip-{name}.service").read_text()
        timer = configparser.ConfigParser(interpolation=None)
        timer.read(deploy / f"viralclip-{name}.timer", encoding="utf-8")
        assert timer["Install"]["WantedBy"] == "timers.target"
        assert (
            timer["Timer"]["OnCalendar"]
            == {
                "backup": "*-*-* 03:30:00 UTC",
                "monitor": "*:0/5",
            }[name]
        )
        if name == "backup":
            assert timer["Timer"].getboolean("Persistent")


def test_live_wal_mount_probe_and_http_rates(live, tmp_path, monkeypatch):
    root = tmp_path / "backups"
    root.mkdir()
    monkeypatch.setattr(ops.os, "ST_RDONLY", 1, raising=False)
    monkeypatch.setattr(
        ops.os,
        "statvfs",
        lambda path: SimpleNamespace(f_flag=int(path != root)),
        raising=False,
    )
    ops.verify_mounts(live, root, writable_backup=True)
    assert not list(root.iterdir())
    with pytest.raises(RuntimeError, match="unexpected write"):
        ops.verify_mounts(live, root, writable_backup=False)
    log = live.with_name(live.name + ".http.jsonl")
    log.write_text(
        "\n".join(
            json.dumps({"event": "http_request", "timestamp": NOW.isoformat(), "status": code})
            for code in (200, 429, None)
        ),
        encoding="utf-8",
    )
    assert "3 attempts, 2 failures (66.7%), 1 HTTP 429" in ops._http_rates(live, NOW)


def test_gta_vi_operations_isolate_paths_and_schedule():
    deploy = Path(__file__).resolve().parents[1] / "deploy"
    for mode in ("backup", "monitor"):
        prefix = deploy / f"viralclip-gta-vi-{mode}"
        text = prefix.with_suffix(".service").read_text()
        assert "User=viralclip-gta-vi\nGroup=viralclip-gta-vi" in text
        assert "/var/lib/viralclip-gta-vi/gta-vi.sqlite3" in text
        assert "--backup-dir /var/lib/viralclip-gta-vi/backups" in text
        assert "operations probe " in text
        assert "/etc/viralclip/gta-vi-ops/" in text
        assert "/var/lib/viralclip-radar" not in text
        assert ("ReadWritePaths=" in text) == (mode == "backup")
        assert ("--writable-backup" in text) == (mode == "backup")
        if mode == "backup":
            assert "--expected-game-id 1867279146" in text
    assert "04:15:00 UTC" in (deploy / "viralclip-gta-vi-backup.timer").read_text()
