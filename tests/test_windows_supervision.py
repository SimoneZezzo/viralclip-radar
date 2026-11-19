from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from xml.etree.ElementTree import fromstring

import pytest

from viralclip.storage.database import Database
from viralclip.windows_supervision import (
    TASK_NAMESPACE,
    control_directory,
    main,
    preflight,
    supervise,
    task_xml,
)


def test_disabled_task_xml_configures_boot_restarts_and_single_instance(tmp_path):
    python = tmp_path / "With spaces" / "python.exe"
    database = tmp_path / "test & snapshots.sqlite3"
    xml = task_xml(python, tmp_path, database, "S-1-5-21-123-456-789-1001", "GTA & test", 300, 30)
    task = fromstring(xml)
    ns = {"t": TASK_NAMESPACE}
    expected = {
        "t:Settings/t:Enabled": "false",
        "t:Settings/t:MultipleInstancesPolicy": "IgnoreNew",
        "t:Settings/t:RestartOnFailure/t:Count": "3",
        "t:Settings/t:RestartOnFailure/t:Interval": "PT1M",
        "t:Settings/t:ExecutionTimeLimit": "PT0S",
        "t:Settings/t:AllowHardTerminate": "false",
        "t:Triggers/t:BootTrigger/t:Delay": "PT30S",
        "t:Triggers/t:BootTrigger/t:ExecutionTimeLimit": "PT0S",
        "t:Principals/t:Principal/t:LogonType": "Password",
        "t:Principals/t:Principal/t:RunLevel": "LeastPrivilege",
        "t:Actions/t:Exec/t:Command": str(python),
        "t:Actions/t:Exec/t:WorkingDirectory": str(tmp_path),
    }
    for path, value in expected.items():
        assert task.findtext(path, namespaces=ns) == value
    assert task.findtext("t:Actions/t:Exec/t:Arguments", namespaces=ns) == (
        f'-B -m viralclip.windows_supervision --db "{database}" run '
        '--game "GTA & test" --interval 300 --lookback 30'
    )


def test_prepare_generates_local_xml_without_opening_database(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("data/\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "missing.sqlite3"
    args = ["--db", str(db_path), "prepare", "--sid", "S-1-5-21-1000"]
    assert main([*args, "--output", "visible"]) == 2
    assert not (tmp_path / "visible").exists()
    assert main([*args, "--output", "data/task"]) == 0
    assert (tmp_path / "data/task/collector.xml").is_file()
    assert not db_path.exists()


def test_preflight_keeps_existing_wal_and_rejects_drift_or_missing_file(tmp_path, monkeypatch):
    db_path = tmp_path / "fixture.sqlite3"
    monkeypatch.setenv("VIRALCLIP_DB_PATH", str(db_path))
    monkeypatch.setenv("TWITCH_CLIENT_ID", "synthetic-id")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "synthetic-secret")
    monkeypatch.setenv("VIRALCLIP_GAME_IDS", "")
    monkeypatch.setenv("DISCOVERY_INTERVAL_SECONDS", "300")
    monkeypatch.setenv("DISCOVERY_LOOKBACK_MINUTES", "30")
    with pytest.raises(ValueError, match="existing database is missing"):
        preflight(db_path, 300, 30)
    assert not db_path.exists()
    db = Database(db_path)
    try:
        db.acquire_collector_lock()  # Read-only preflight can run alongside an owner.
        db_bytes = db_path.read_bytes()
        wal = Path(str(db_path) + "-wal")
        wal_bytes = wal.read_bytes()
        preflight(db_path, 300, 30)
        assert db_path.read_bytes() == db_bytes
        assert wal.read_bytes() == wal_bytes
        with pytest.raises(ValueError, match="lookback differs"):
            preflight(db_path, 300, 45)
        monkeypatch.setenv("VIRALCLIP_GAME_IDS", "other")
        with pytest.raises(ValueError, match="Additional category"):
            preflight(db_path, 300, 30)
        monkeypatch.setenv("VIRALCLIP_GAME_IDS", "")
        with db.transaction() as connection:
            connection.execute("DELETE FROM schema_migrations WHERE version = 2")
        with pytest.raises(ValueError, match="schema differs"):
            preflight(db_path, 300, 30)
    finally:
        db.close()


def test_pause_survives_attempts_resume_never_launches(tmp_path):
    db_path = tmp_path / "missing.sqlite3"
    args = ["--db", str(db_path)]
    marker = control_directory(db_path) / "pause"
    assert main([*args, "pause"]) == 0
    assert marker.is_file()
    events = []
    for _ in range(2):
        assert (
            supervise(
                marker,
                lambda: pytest.fail("paused attempt launched"),
                lambda event, **kw: events.append(event),
            )
            == 0
        )
    assert events == ["paused", "paused"]
    assert main([*args, "resume"]) == 0
    assert not marker.exists()
    assert not db_path.exists()


@pytest.mark.parametrize(
    ("collector_exit", "event", "code"),
    [(0, "unexpected_clean_exit", 1), (2, "collector_failed", 2)],
)
def test_unexpected_exits_preserve_scheduler_failure(tmp_path, collector_exit, event, code):
    events = []
    assert (
        supervise(
            tmp_path / "pause",
            lambda: collector_exit,
            lambda name, **fields: events.append((name, fields)),
        )
        == code
    )
    assert events == [("starting", {}), (event, {"exit_code": code})]


def test_crash_is_reported_without_exception_message(tmp_path):
    def fail():
        raise RuntimeError("synthetic secret")

    events = []
    assert (
        supervise(tmp_path / "pause", fail, lambda name, **fields: events.append((name, fields)))
        == 1
    )
    assert events[-1] == ("collector_exception", {"error_type": "RuntimeError", "exit_code": 1})


def test_pause_interrupts_and_runs_synthetic_cleanup(tmp_path):
    script = """
import json, sys, time
from pathlib import Path
from viralclip.windows_supervision import supervise

marker = Path(sys.argv[1])
def collector():
    marker.touch()
    try:
        while True:
            time.sleep(0.02)
    finally:
        print("collector cleanup")

def record(name, **fields):
    print(json.dumps({"event": name, **fields}))

raise SystemExit(supervise(marker, collector, record, poll_seconds=0.05))
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", script, str(tmp_path / "pause")],
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    started, cleanup, stopped = result.stdout.splitlines()
    assert json.loads(started) == {"event": "starting"}
    assert cleanup == "collector cleanup"
    assert json.loads(stopped) == {"event": "paused", "exit_code": 0}


def test_runner_checks_before_dispatch_and_records_failure(tmp_path, monkeypatch):
    db_path = tmp_path / "synthetic.sqlite3"
    calls = []
    preflights = []

    def check(path, interval, lookback):
        preflights.append((path, interval, lookback))
        if len(preflights) == 1:
            raise ValueError("private string")

    def collector(argv):
        calls.append(argv)
        return 1

    monkeypatch.setattr("viralclip.windows_supervision.sys.platform", "win32")
    monkeypatch.setattr("viralclip.windows_supervision.preflight", check)
    monkeypatch.setattr("viralclip.cli.main", collector)
    args = ["--db", str(db_path), "run"]
    assert main(args) == 2
    assert not calls
    assert main(args) == 1
    assert preflights == [(db_path, 300, 30)] * 2
    assert calls == [["--db", str(db_path), "collect", "--game", "Grand Theft Auto V", "--loop"]]
    log = (control_directory(db_path) / "lifecycle.jsonl").read_text(encoding="utf-8")
    assert "private string" not in log
    assert [json.loads(line)["event"] for line in log.splitlines()] == [
        "starting",
        "preflight_failed",
        "collector_failed",
        "starting",
        "collector_failed",
    ]


def test_real_cross_process_database_lock_rejects_second_owner(tmp_path):
    db = Database(tmp_path / "synthetic.sqlite3")
    script = """
import sys
from viralclip.storage.database import Database
db = Database(sys.argv[1])
try:
    db.acquire_collector_lock()
except ValueError:
    raise SystemExit(7)
finally:
    db.close()
"""
    try:
        db.acquire_collector_lock()
        command = [sys.executable, "-B", "-c", script, str(db.path)]
        blocked = subprocess.run(command, capture_output=True, timeout=5, check=False)
        assert blocked.returncode == 7
        db.close()
        released = subprocess.run(command, capture_output=True, timeout=5, check=False)
        assert released.returncode == 0
    finally:
        db.close()
