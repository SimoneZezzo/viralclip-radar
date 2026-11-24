from __future__ import annotations

import os
import sqlite3
import subprocess
from contextlib import closing
from datetime import timedelta
from types import SimpleNamespace

import pytest
from test_collector import NOW, clip

from viralclip import reliability as monitor
from viralclip.collector.service import Collector
from viralclip.storage.database import Database
from viralclip.storage.discovery import BUCKET, bucket_start, ensure_scan_ledger, history_start
from viralclip.storage.health import CRITICAL, DEGRADED, HEALTHY, read_health

V = "32982"
VI = "1867279146"


@pytest.fixture
def db(tmp_path):
    with closing(Database(tmp_path / "monitor.sqlite3")) as database:
        yield database


def seed(db, game=V, age=60):
    end = NOW - timedelta(seconds=age)
    db.upsert_game(game, "Synthetic", NOW)
    run = db.create_run(game, end - BUCKET, end, end)
    db.finish_run(run, end, 1, 1, 0, 0)
    db.update_watermark(game, end)


def sample(db, game=V):
    lines, alerts = [], []
    monitor.sample_database(db.connection, game, NOW, lines, alerts)
    return max((level for level, _ in alerts), default=0), "\n".join(lines)


def test_idle_discovery_is_healthy_without_new_clips(db):
    seed(db)
    level, lines = sample(db)
    assert level == HEALTHY
    assert "Observations in last 15m: 0" in lines


@pytest.mark.parametrize("overdue,level", [(4, HEALTHY), (301, DEGRADED), (901, CRITICAL)])
def test_job_duration_distinguishes_tick_from_backlog(db, overdue, level):
    seed(db)
    created = NOW - timedelta(seconds=600 + overdue)
    db.record_clip(Collector._parse_clip(clip("synthetic", created_at=created)), V, created, None)
    actual, lines = sample(db)
    assert actual == level
    assert f"oldest {overdue:.1f}s" in lines


def test_executed_jobs_and_scheduled_observations(db):
    seed(db)
    created = NOW - timedelta(minutes=11)
    db.record_clip(Collector._parse_clip(clip("synthetic", created_at=created)), V, created, None)
    job = db.connection.execute("SELECT job_id FROM jobs WHERE target_age_seconds=600").fetchone()[
        0
    ]
    db.add_scheduled_snapshot("synthetic", NOW, 10, 600, [job])
    level, lines = sample(db)
    assert level == HEALTHY
    assert "1 completed of jobs due" in lines
    assert "(1 scheduled in tail)" in lines


def test_stale_discovery_and_transient_error(db):
    seed(db)
    db.record_error(NOW - timedelta(minutes=1), "fixture")
    assert sample(db)[0] == HEALTHY
    db.record_error(NOW - timedelta(minutes=2), "fixture")
    assert sample(db)[0] == DEGRADED
    seed(db, age=1801)
    # A separate stale checkpoint demonstrates critical even with older successful runs.
    db.connection.execute("DELETE FROM discovery_checkpoints")
    db.update_watermark(V, NOW - timedelta(minutes=31))
    assert sample(db)[0] == CRITICAL


def finish(db, start, end, lane, outcome, pages):
    run = db.create_run(VI, start, end, NOW)
    db.finish_run(
        run,
        NOW,
        1,
        pages,
        0,
        0,
        truncated=outcome not in ("cursor_exhausted", "error"),
        error="synthetic" if outcome == "error" else None,
        scan=(lane, outcome, 0, 0),
    )


def test_errors_do_not_move_history_or_keep_recent_fresh(db):
    seed(db, VI, age=3600)
    ensure_scan_ledger(db.connection)
    current = bucket_start(NOW)
    prior = current - BUCKET
    start = prior - BUCKET
    finish(db, start - BUCKET, start, "history", "budget", 1)
    finish(db, start, prior, "history", "error", 0)
    finish(
        db,
        current - timedelta(hours=1) - BUCKET,
        current - timedelta(hours=1),
        "recent",
        "cursor_exhausted",
        1,
    )
    finish(db, prior, current, "recent", "error", 1)
    assert history_start(db.connection, VI, prior) == start
    assert sample(db, VI)[0] == CRITICAL
    # A later usable page resumes the sweep. It leaves an explicit partial result.
    finish(db, start, prior, "history", "budget", 1)
    finish(db, prior, current, "recent", "known_incomplete", 1)
    assert history_start(db.connection, VI, prior) == prior
    assert read_health(db.path, 300, now=NOW)[0] == DEGRADED
    level, lines = sample(db, VI)
    assert level == DEGRADED
    assert "known_incomplete" in lines
    assert "History sweep lag: 0s" in lines
    finish(db, start, prior, "retry", "cursor_exhausted", 1)
    assert history_start(db.connection, VI, prior) == prior
    assert "1 with retry" in sample(db, VI)[1]


def status(**kwargs):
    return {
        "LoadState": "loaded",
        "ActiveState": "active",
        "SubState": "running",
        "MainPID": "100",
        "NRestarts": "0",
        "ExecMainStartTimestampMonotonic": "1",
        "UnitFileState": "enabled",
    } | kwargs


@pytest.fixture
def system(monkeypatch):
    monkeypatch.setattr(monitor, "_read", lambda *args: None)
    monkeypatch.setattr(
        os,
        "statvfs",
        lambda _: SimpleNamespace(f_blocks=100, f_bavail=30, f_files=100, f_favail=30),
        raising=False,
    )


def test_stopped_service_with_unknown_disk_is_unhealthy(monkeypatch, system, tmp_path):
    monkeypatch.setattr(
        monitor, "_service_state", lambda _: status(ActiveState="inactive", SubState="dead")
    )

    def unavailable(_):
        raise OSError

    monkeypatch.setattr(os, "statvfs", unavailable)
    assert monitor.monitor("fixture", V, tmp_path / "db")[0] == CRITICAL


def test_simulated_restart_is_reported(monkeypatch, system, tmp_path):
    states = iter([status(), status(MainPID="101", ExecMainStartTimestampMonotonic="2")])
    monkeypatch.setattr(monitor, "_service_state", lambda _: next(states))
    level, lines = monitor.monitor("fixture", V, tmp_path / "db")
    assert level == DEGRADED
    assert any("changed" in line for line in lines)


@pytest.mark.parametrize("error", [sqlite3.OperationalError("busy"), OSError("unavailable")])
def test_unavailable_read_is_unknown_without_leaking_details(monkeypatch, system, tmp_path, error):
    monkeypatch.setattr(monitor, "_service_state", lambda _: status())

    def fail(*_):
        raise error

    monkeypatch.setattr(monitor, "_read", fail)
    level, lines = monitor.monitor("fixture", V, tmp_path / "db")
    assert level == monitor.UNKNOWN
    assert "SQLite snapshot, mount isolation or deadline unavailable." in "\n".join(lines)
    assert str(error) not in lines


def test_missing_systemd_and_low_inodes(monkeypatch, system, tmp_path):
    def unavailable(_):
        raise subprocess.TimeoutExpired("fixture", 10)

    monkeypatch.setattr(monitor, "_service_state", unavailable)
    assert monitor.monitor("fixture", V, tmp_path / "db")[0] == monitor.UNKNOWN
    monkeypatch.setattr(
        os,
        "statvfs",
        lambda _: SimpleNamespace(f_blocks=100, f_bavail=30, f_files=100, f_favail=4),
    )
    assert monitor.monitor("fixture", V, tmp_path / "db")[0] == CRITICAL


@pytest.mark.parametrize("free,level", [(9, CRITICAL), (12, DEGRADED), (31, HEALTHY)])
def test_free_disk_thresholds(monkeypatch, system, tmp_path, free, level):
    monkeypatch.setattr(monitor, "_service_state", lambda _: status())
    monkeypatch.setattr(
        os,
        "statvfs",
        lambda _: SimpleNamespace(f_blocks=100, f_bavail=free, f_files=100, f_favail=30),
    )
    assert monitor.monitor("fixture", V, tmp_path / "db")[0] == level


def test_reader_refuses_writable_mount_before_sqlite_open(monkeypatch, db):
    def unexpected_open(*args, **kwargs):
        pytest.fail("opened the database before checking its mount")

    monkeypatch.setattr(os, "statvfs", lambda _: SimpleNamespace(f_flag=0), raising=False)
    monkeypatch.setattr(os, "ST_RDONLY", 1, raising=False)
    monkeypatch.setattr(sqlite3, "connect", unexpected_open)
    with pytest.raises((ValueError, OSError)):
        monitor._read(db.path, V, [], [])
