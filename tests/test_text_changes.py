"""Point-in-time preservation of clip text metadata (TEXT_METADATA_PRESERVATION.md, option C)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from viralclip import deployment
from viralclip.collector.service import Collector
from viralclip.storage import database
from viralclip.storage.database import Database, to_utc_iso
from viralclip.twitch.client import TwitchAPIError, TwitchClient

CREATED = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
CUTOFFS = (30, 35, 60, 65)


def raw(title="A clip", name="Streamer", language="en", views=10, clip_id="clip-1") -> dict:
    return {
        "id": clip_id,
        "broadcaster_id": "b-1",
        "broadcaster_name": name,
        "creator_id": "c-1",
        "title": title,
        "url": f"https://clips.twitch.tv/{clip_id}",
        "created_at": to_utc_iso(CREATED),
        "view_count": views,
        "language": language,
        "duration": 30.0,
    }


def at(minutes: float) -> datetime:
    return CREATED + timedelta(minutes=minutes)


@pytest.fixture
def db(tmp_path: Path):
    database = Database(tmp_path / "db.sqlite3")
    database.upsert_game("42", "GTA", CREATED)
    yield database
    database.close()


def discover(db: Database, minutes: float, **fields) -> None:
    db.record_clip(Collector._parse_clip(raw(**fields)), "42", at(minutes), None)


def refresh(db: Database, minutes: float, **fields) -> None:
    db.add_scheduled_snapshot(
        "clip-1", at(minutes), 10, None, text=Collector._parse_clip(raw(**fields))
    )


def changes(db: Database) -> list[tuple]:
    return [
        tuple(row)
        for row in db.connection.execute(
            "SELECT observed_at, source, title, broadcaster_name, language "
            "FROM clip_text_changes ORDER BY observed_at, change_id"
        )
    ]


def title_at(db: Database, minutes: float):
    known = db.text_known_at("clip-1", at(minutes))
    return known and known["title"]


def test_first_observation_uses_the_snapshot_acquisition_time(db):
    discover(db, 4.5)
    snapshot = db.connection.execute("SELECT observed_at FROM clip_snapshots").fetchone()[0]
    assert changes(db) == [(snapshot, "discovery", "A clip", "Streamer", "en")]
    assert snapshot == to_utc_iso(at(4.5))


def test_unchanged_rediscovery_and_refresh_append_nothing(db):
    discover(db, 1)
    discover(db, 6)
    refresh(db, 10)
    refresh(db, 30)
    assert len(changes(db)) == 1
    assert db.connection.execute("SELECT COUNT(*) FROM clip_snapshots").fetchone()[0] == 4


def test_value_known_at_each_cutoff_is_reconstructed(db):
    discover(db, 2, title="first")
    discover(db, 20, title="first")
    refresh(db, 30.5, title="edited")
    discover(db, 34, title="edited")
    refresh(db, 60.2, title="final", name="Renamed")
    refresh(db, 66, title="final", name="Renamed")
    expected = {30: "first", 35: "edited", 60: "edited", 65: "final"}
    assert {cutoff: title_at(db, cutoff) for cutoff in CUTOFFS} == expected
    assert db.text_known_at("clip-1", at(65))["broadcaster_name"] == "Renamed"
    assert db.text_known_at("clip-1", at(1)) is None
    # The clips row is unchanged by this work: it keeps the last discovered value only.
    assert db.connection.execute("SELECT title FROM clips").fetchone()[0] == "edited"
    assert len(changes(db)) == 3


def test_null_transitions_are_changes_and_empty_differs_from_null(db):
    discover(db, 1, title=None, language=None)
    discover(db, 2, title=None, language=None)
    discover(db, 3, title="named", language=None)
    discover(db, 4, title=None, language=None)
    discover(db, 5, title="", language=None)
    discover(db, 6, title="", language="en")
    assert [(row[2], row[4]) for row in changes(db)] == [
        (None, None),
        ("named", None),
        (None, None),
        ("", None),
        ("", "en"),
    ]
    assert title_at(db, 3.5) == "named"
    assert title_at(db, 4.5) is None


def test_replays_are_idempotent_and_first_write_wins(db):
    discover(db, 1, title="kept")
    discover(db, 1, title="kept")
    refresh(db, 11, title="kept")
    refresh(db, 11, title="kept")
    discover(db, 1, title="contradictory replay")
    assert [row[2] for row in changes(db)] == ["kept"]


def test_out_of_order_observation_keeps_later_values_exact(db):
    discover(db, 1, title="A")
    refresh(db, 3, title="A")  # skipped as unchanged
    discover(db, 2, title="B")  # arrives late, e.g. after a clock step
    assert [title_at(db, m) for m in (1, 2, 2.5, 3, 4)] == ["A", "B", "B", "A", "A"]
    assert [(row[1], row[2]) for row in changes(db)] == [
        ("discovery", "A"),
        ("discovery", "B"),
        ("scheduled", "A"),
    ]


def test_out_of_order_equal_value_and_before_first_observation(db):
    discover(db, 5, title="A")
    discover(db, 7, title="C")
    discover(db, 6, title="A")  # equal to the value known at 6: nothing to add
    discover(db, 2, title="Z")  # earlier than every row: no value to restore
    assert [title_at(db, m) for m in (1, 2, 5, 6, 7)] == [None, "Z", "A", "A", "C"]
    assert [row[2] for row in changes(db)] == ["Z", "A", "C"]


def test_ledger_is_append_only(db):
    discover(db, 1)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.connection.execute("UPDATE clip_text_changes SET title = 'x'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.connection.execute("DELETE FROM clip_text_changes")


def test_text_failure_rolls_back_the_whole_observation(db):
    discover(db, 1)
    db.connection.execute(
        "CREATE TRIGGER fail_text BEFORE INSERT ON clip_text_changes "
        "BEGIN SELECT RAISE(ABORT, 'forced'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="forced"):
        discover(db, 6, title="changed", clip_id="clip-1")
    with pytest.raises(sqlite3.IntegrityError, match="forced"):
        discover(db, 6, clip_id="clip-2")
    job = db.connection.execute(
        "SELECT job_id FROM jobs WHERE clip_id = 'clip-1' AND target_age_seconds = 600"
    ).fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError, match="forced"):
        db.add_scheduled_snapshot(
            "clip-1",
            at(10),
            10,
            600,
            [job],
            text=Collector._parse_clip(raw(title="changed")),
        )
    conn = db.connection
    assert conn.execute("SELECT COUNT(*) FROM clip_snapshots").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0] == 1
    assert conn.execute("SELECT title FROM clips").fetchone()[0] == "A clip"
    assert conn.execute("SELECT status FROM jobs WHERE job_id = ?", (job,)).fetchone()[0] == (
        "pending"
    )


def test_scheduled_snapshot_without_text_records_no_text(db):
    discover(db, 1)
    db.add_scheduled_snapshot("clip-1", at(10), 10, None)
    assert len(changes(db)) == 1


def test_schema_stays_v2_and_existing_databases_gain_the_ledger(tmp_path):
    path = tmp_path / "db.sqlite3"
    Database(path).close()
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE clip_text_changes")  # a database created before this change
    reopened = Database(path)
    names = {
        row[0]
        for row in reopened.connection.execute(
            "SELECT name FROM sqlite_schema WHERE name LIKE 'clip_text_changes%'"
        )
    }
    assert names >= {
        "clip_text_changes",
        "clip_text_changes_no_update",
        "clip_text_changes_no_delete",
    }
    versions = reopened.connection.execute("SELECT version FROM schema_migrations").fetchall()
    assert [row[0] for row in versions] == [1, 2]
    reopened.close()
    reader = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    deployment._check_schema(reader)
    reader.close()


def test_lookups_use_indexes_without_sorting(db):
    discover(db, 1)
    for sql in (database.TEXT_KNOWN_AT_SQL, database.NEXT_TEXT_SQL, database.NEXT_SNAPSHOT_SQL):
        plan = " ".join(
            row[3] for row in db.connection.execute("EXPLAIN QUERY PLAN " + sql, ("clip-1", ""))
        )
        assert "INDEX" in plan and "SCAN" not in plan and "TEMP B-TREE" not in plan, plan


def test_replay_after_a_skipped_observation_keeps_the_first_text(db):
    discover(db, 1, title="A")
    discover(db, 5, title="A")  # unchanged: no text row, but the snapshot exists
    discover(db, 5, title="B")  # replay of the same observation key
    refresh(db, 10, title="A")
    refresh(db, 10, title="B")
    assert [row[2] for row in changes(db)] == ["A"]
    assert title_at(db, 5) == "A" and title_at(db, 10) == "A"


def test_missing_trigger_is_recreated(tmp_path):
    path = tmp_path / "db.sqlite3"
    Database(path).close()
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TRIGGER clip_text_changes_no_delete")
    reopened = Database(path)
    assert reopened.connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type = 'trigger' AND name = ?",
        ("clip_text_changes_no_delete",),
    ).fetchone()
    reopened.close()


@pytest.mark.parametrize("field", ["title", "broadcaster_name", "language"])
def test_non_text_metadata_is_rejected_at_parse(field):
    clip = raw()
    clip[field] = ["not", "text"]
    with pytest.raises(TwitchAPIError):
        Collector._parse_clip(clip)
    clip[field] = None
    assert Collector._parse_clip(clip)[field] is None


def test_collector_refresh_preserves_text_changes(db):
    discover(db, 1, title="before")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/validate"):
            return httpx.Response(200, json={"client_id": "id", "expires_in": 3600})
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        return httpx.Response(200, json={"data": [raw(title="after", views=50)]})

    twitch = TwitchClient(
        "id",
        "secret",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _delay: None,
        jitter=lambda _low, _high: 0,
    )
    collector = Collector(db, twitch, clock=lambda: at(10.5))
    assert collector.collect_due_snapshots() == 1
    twitch.http.close()
    assert [(row[1], row[2]) for row in changes(db)] == [
        ("discovery", "before"),
        ("scheduled", "after"),
    ]
    scheduled = db.connection.execute(
        "SELECT observed_at FROM clip_snapshots WHERE source = 'scheduled'"
    ).fetchone()[0]
    assert changes(db)[1][0] == scheduled
    assert title_at(db, 10) == "before"
    assert title_at(db, 30) == "after"
