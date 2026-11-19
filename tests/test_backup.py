import sqlite3
from contextlib import closing

import pytest
from test_collector import NOW, clip

from viralclip.collector.service import Collector
from viralclip.storage.backup import backup_and_verify, online_copy, validate
from viralclip.storage.database import Database


def test_online_backup_and_restore_see_committed_wal_only(tmp_path):
    source = tmp_path / "live.sqlite3"
    backup = tmp_path / "backups" / "snapshot.sqlite3"
    writer = Database(source)
    try:
        writer.upsert_game("42", "fixture", NOW)
        writer.record_clip(Collector._parse_clip(clip()), "42", NOW, None)
        writer.connection.execute(
            "INSERT INTO operational_errors (occurred_at, message) VALUES ('fixture', 'uncommitted')"
        )
        assert source.with_suffix(".sqlite3-wal").stat().st_size > 0
        metrics = backup_and_verify(source, backup)
        assert metrics["clips"] == metrics["clip_snapshots"] == 1
        assert metrics["jobs"] == 5
        assert metrics["operational_errors"] == 0
        assert writer.connection.in_transaction
        assert list(backup.parent.iterdir()) == [backup]
    finally:
        writer.close()


def test_copy_refuses_existing_destination_or_source_alias(tmp_path):
    source = tmp_path / "live.sqlite3"
    destination = tmp_path / "existing.sqlite3"
    Database(source).close()
    destination.write_bytes(b"keep")
    for protected in (destination, source):
        original = protected.read_bytes()
        with pytest.raises(FileExistsError):
            online_copy(source, protected)
        assert protected.read_bytes() == original


def test_validation_rejects_incorrect_completed_job_link(tmp_path):
    source = tmp_path / "invalid.sqlite3"
    writer = Database(source)
    try:
        writer.upsert_game("42", "fixture", NOW)
        writer.record_clip(Collector._parse_clip(clip()), "42", NOW, None)
    finally:
        writer.close()
    with closing(sqlite3.connect(source)) as connection, connection:
        connection.execute("UPDATE jobs SET status = 'completed' WHERE target_age_seconds = 600")
    with pytest.raises(ValueError, match="Invalid job links: 1"):
        validate(source)
