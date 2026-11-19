from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest
from test_collector import NOW, clip

from viralclip.cli import main
from viralclip.collector.service import Collector
from viralclip.storage.database import MIGRATIONS, Database
from viralclip.storage.health import CRITICAL, DEGRADED, HEALTHY, read_health


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "health # test.sqlite3")
    yield database
    database.close()


def discovery(db, game="42", *, age=60, truncated=False):
    end = NOW - timedelta(seconds=age)
    db.upsert_game(game, "Synthetic game", NOW)
    run = db.create_run(game, end - timedelta(minutes=30), end, end)
    db.finish_run(run, end, 1, 1, 0, 0, truncated=truncated)
    if not truncated:
        db.update_watermark(game, end)


def add_clip(db, clip_id, *, created_minutes, first_seen_minutes):
    created = NOW - timedelta(minutes=created_minutes)
    seen = created + timedelta(minutes=first_seen_minutes)
    db.record_clip(Collector._parse_clip(clip(clip_id, created_at=created)), "42", seen, None)
    return created


def job_id(db, clip_id, target=600):
    return db.connection.execute(
        "SELECT job_id FROM jobs WHERE clip_id = ? AND target_age_seconds = ?", (clip_id, target)
    ).fetchone()[0]


def report(db, interval=300):
    severity, lines = read_health(db.path, interval, now=NOW)
    return severity, "\n".join(lines)


def test_healthy_reports_real_lateness_and_strict_coverage(db):
    discovery(db)
    for clip_id, first_seen, delay in (("early", 5, 1), ("near-target", 9, 9)):
        created = add_clip(db, clip_id, created_minutes=12, first_seen_minutes=first_seen)
        observed = created + timedelta(seconds=600 + delay)
        db.add_scheduled_snapshot(clip_id, observed, 20, 600, [job_id(db, clip_id)])
    add_clip(db, "late", created_minutes=12, first_seen_minutes=11)
    add_clip(db, "omitted", created_minutes=12, first_seen_minutes=3)
    db.finish_jobs([job_id(db, "omitted")], "unavailable", NOW, "omitted")
    severity, output = report(db)
    assert severity == HEALTHY
    assert "Last successful discovery: 2026-11-16T11:59:00.000000Z (60.0s ago)" in output
    assert "Total clips: 4; total observations: 6" in output
    assert "10m: n=2, median=5.0s, P95=9.0s" in output
    assert "10m: 3/4 observed (75.0%), 1 missing" in output
    assert "Missed at discovery: 1; unavailable in refresh: 1; execution failures: 0" in output


def test_delayed_jobs_and_discovery(db):
    discovery(db, age=661)
    add_clip(db, "pending", created_minutes=16, first_seen_minutes=1)
    severity, output = report(db)
    assert severity == DEGRADED
    assert "Overdue jobs: 1" in output
    assert "maximum overdue age: 360.0s" in output
    assert "checkpoint is stale" in output
    add_clip(db, "very-late", created_minutes=26, first_seen_minutes=1)
    assert report(db)[0] == CRITICAL


def test_execution_failure_retry_and_exhaustion(db):
    discovery(db)
    add_clip(db, "failed", created_minutes=11, first_seen_minutes=1)
    job = job_id(db, "failed")
    db.start_jobs([job])
    db.finish_jobs([job], "failed", NOW, "synthetic failure")
    assert report(db)[0] == DEGRADED
    for _ in range(2):
        db.start_jobs([job])
        db.finish_jobs([job], "failed", NOW, "synthetic failure")
    severity, output = report(db)
    assert severity == CRITICAL
    assert "execution failures: 1 (1 exhausted)" in output


def test_discovery_reports_unresolved_truncation_and_per_category_staleness(db):
    discovery(db, age=120)
    discovery(db, age=60, truncated=True)
    severity, output = report(db)
    assert severity == DEGRADED
    assert "1 flagged truncated" in output
    assert "1 incomplete beyond checkpoint" in output
    discovery(db, age=30)
    assert report(db)[0] == HEALTHY
    discovery(db, game="43", age=1861)
    severity, output = report(db)
    assert severity == CRITICAL
    assert "Category '43' discovery or checkpoint is critically stale" in output
    assert report(db, interval=1200)[0] == HEALTHY


def test_recent_errors_are_reported_without_stored_message(db):
    discovery(db)
    db.record_error(NOW - timedelta(seconds=10), "Twitch OAuth: secret-token-fixture")
    db.record_error(NOW - timedelta(hours=2), "old error")
    severity, output = report(db)
    assert severity == DEGRADED
    assert "Operational errors recorded in the last hour: 1" in output
    assert "Error #1 at 2026-11-16T11:59:50.000000Z (authentication)" in output
    assert "secret-token-fixture" not in output


def test_empty_database_reports_no_history(db):
    severity, output = report(db)
    assert severity == DEGRADED
    assert "Last successful discovery: never" in output
    assert "Total clips: 0; total observations: 0" in output
    assert "10m: no due jobs" in output


def test_invalid_record_and_missing_completed_link(db):
    discovery(db)
    add_clip(db, "bad", created_minutes=11, first_seen_minutes=1)
    db.finish_jobs([job_id(db, "bad")], "completed", NOW)
    severity, output = report(db)
    assert severity == CRITICAL
    assert "malformed database records" in output
    with db.transaction() as conn:
        conn.execute("UPDATE jobs SET status = 'pending', due_at = 'invalid'")
    assert report(db)[0] == CRITICAL


def test_cli_reads_concurrent_wal_without_initializing(monkeypatch, db, capsys):
    discovery(db)
    sealed = db.path.read_bytes()
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO operational_errors(occurred_at, message) VALUES (?, ?)",
            ("2026-11-16T11:59:00.000000Z", "uncommitted error"),
        )
        monkeypatch.setattr("viralclip.storage.health.utc_now", lambda: NOW)
        monkeypatch.setattr("viralclip.cli.Database", lambda *_: pytest.fail("writer opened"))
        monkeypatch.setattr("viralclip.cli.TwitchClient", lambda *_: pytest.fail("Twitch opened"))
        monkeypatch.setenv("VIRALCLIP_DB_PATH", str(db.path))
        assert main(["health"]) == HEALTHY
        output = capsys.readouterr().out
        assert "Collector health: HEALTHY" in output
        assert "Operational errors recorded in the last hour: 0" in output
        assert db.path.read_bytes() == sealed


@pytest.mark.parametrize("kind", ["missing", "empty", "old", "invalid"])
def test_cli_handles_unavailable_database_without_mutation(tmp_path, capsys, kind):
    path = tmp_path / "health.sqlite3"
    if kind == "empty":
        path.touch()
    elif kind == "old":
        with sqlite3.connect(path) as connection:
            connection.executescript(MIGRATIONS[0])
        connection.close()
    elif kind == "invalid":
        path.write_text("not SQLite")
    before = path.read_bytes() if path.exists() else None
    assert main(["--db", str(path), "health"]) == CRITICAL
    assert "Collector health: CRITICAL" in capsys.readouterr().out
    assert (path.read_bytes() if path.exists() else None) == before


def test_late_observation_p95_can_degrade_without_backlog(db):
    discovery(db)
    created = add_clip(db, "recovered", created_minutes=17, first_seen_minutes=1)
    db.add_scheduled_snapshot(
        "recovered", created + timedelta(seconds=970), 25, 600, [job_id(db, "recovered")]
    )
    severity, output = report(db)
    assert severity == DEGRADED
    assert "Overdue jobs: 0" in output
    assert "median=370.0s, P95=370.0s" in output
