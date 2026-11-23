from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest

from viralclip import dataset, evaluation, m2_audit
from viralclip.m2_audit import GAMES, split_options
from viralclip.storage.database import MIGRATIONS, to_utc_iso

START = datetime(2025, 11, 1, tzinfo=UTC)
DAY = timedelta(days=1)
MINUTE = timedelta(minutes=1)


class Fixture:
    def __init__(self, directory, game):
        self.path = directory / (game + ".sqlite3")
        self.game = GAMES[game]
        self.db = sqlite3.connect(self.path)
        for version, migration in enumerate(MIGRATIONS, 1):
            self.db.executescript(migration)
            self.db.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER)")
            self.db.execute("INSERT INTO schema_migrations VALUES(?)", (version,))
        self.db.execute(
            "INSERT INTO games VALUES(?,?,?)", (self.game, "fixture", to_utc_iso(START))
        )

    def snapshot(self, cid, created, offset, views, source="discovery", target=None):
        return self.db.execute(
            """
            INSERT INTO clip_snapshots(clip_id,observed_at,age_seconds,view_count,source,target_age_seconds)
            VALUES (?,?,?,?,?,?)
            """,
            (cid, to_utc_iso(created + offset), offset.total_seconds(), views, source, target),
        ).lastrowid

    def clip(self, cid, created, *, seen=2, early=(2,), result="valid", views=1):
        first = to_utc_iso(created + seen * MINUTE)
        self.db.execute(
            """
            INSERT INTO clips(clip_id,game_id,created_at,first_seen_at,last_seen_at,title)
            VALUES(?,?,?,?,?,'PRIVATE_SYNTHETIC_TITLE')
            """,
            (cid, self.game, to_utc_iso(created), first, first),
        )
        for minute in early:
            self.snapshot(cid, created, minute * MINUTE, 0)
        if result == "missing":
            return
        due = to_utc_iso(created + DAY)
        at = DAY + 6 * MINUTE if result == "outside_window" else DAY
        snapshot = None
        state = "completed"
        if result == "unavailable":
            state = "unavailable"
        elif result == "invalid_link":
            snapshot = self.db.execute(
                "SELECT snapshot_id FROM clip_snapshots WHERE clip_id<>? LIMIT 1", (cid,)
            ).fetchone()[0]
        else:
            snapshot = self.snapshot(cid, created, at, views, "scheduled", 86400)
        self.db.execute(
            """
            INSERT INTO jobs(clip_id,target_age_seconds,due_at,completed_at,status,snapshot_id)
            VALUES(?,86400,?,?,?,?)
            """,
            (cid, due, to_utc_iso(created + at), state, snapshot),
        )

    def stamp(self, at):
        self.clip("PRIVATE_WATERMARK_CLIP", at, seen=0, early=(0,), result="missing")

    def run(self, start, end, kind="completed", lane=None, outcome=None, finished=None):
        cursor = self.db.execute(
            """
            INSERT INTO collection_runs(game_id,window_start,window_end,started_at,finished_at,
                request_count,status,potentially_truncated,error_summary)
            VALUES(?,?,?,?,?,1,?,?,?)
            """,
            (
                self.game,
                to_utc_iso(start),
                to_utc_iso(end),
                to_utc_iso(end),
                to_utc_iso(finished or end),
                kind,
                int(kind == "partial"),
                "PRIVATE_SYNTHETIC_ERROR" if kind == "error" else None,
            ),
        )
        if lane:
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS gta_vi_scan_attempts(
                    run_id INTEGER PRIMARY KEY, lane TEXT, outcome TEXT
                )
                """
            )
            self.db.execute(
                "INSERT INTO gta_vi_scan_attempts VALUES(?,?,?)", (cursor.lastrowid, lane, outcome)
            )

    def pool(self, offset, count=10):
        day = START + offset * DAY
        for number in range(count):
            self.clip(f"PRIVATE_TEST_CLIP_{offset}_{number}", day + number * MINUTE, views=number)
        self.run(day, day + DAY)

    def close(self):
        self.db.commit()
        self.db.close()


@pytest.fixture(scope="session")
def linux_guard():
    if sys.platform == "linux":
        probe = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                "from viralclip.m2_audit import deny_fs_writes; deny_fs_writes()",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if "viralclip.m2_audit.AuditError: landlock_" in probe.stderr:
            pytest.skip("Linux audit requires Landlock ABI >= 3")
        assert probe.returncode == 0, probe.stderr


@pytest.fixture
def pair(tmp_path, linux_guard):
    return Fixture(tmp_path, "gta-v"), Fixture(tmp_path, "gta-vi")


def cli(v, vi, *args):
    process = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-m",
            "viralclip.m2_audit",
            "--gta-v",
            str(v),
            "--gta-vi",
            str(vi),
            *args,
        ],
        capture_output=True,
        text=True,
        timeout=16,
        check=False,
    )
    assert "PRIVATE_" not in process.stdout + process.stderr
    return process, json.loads(process.stdout)


def one_day_report(pair, *args):
    v, vi = pair
    for db in pair:
        db.close()
    process, report = cli(v.path, vi.path, "--start", "2025-11-01", "--end", "2025-11-02", *args)
    return process, report, report["games"]["gta-v"]["days"][0]


def test_independent_games_use_common_watermark_and_keep_empty_days(pair):
    v, vi = pair
    for game, offset, stamp in ((v, 0, 4), (vi, 1, 5)):
        game.pool(offset)
        game.stamp(START + stamp * DAY)
        game.close()
    process, report = cli(v.path, vi.path)
    assert process.returncode == 0
    assert report["common_watermark"] == to_utc_iso(START + 4 * DAY)
    for game, offset, stamp in (("gta-v", 0, 4), ("gta-vi", 1, 5)):
        result = report["games"][game]
        assert result["individual_watermark"] == to_utc_iso(START + stamp * DAY)
        assert result["admissible_days"] == 1
        assert result["days"][offset]["admissible"]
        assert result["days"][offset]["observations"] == 20
        assert result["decision"] == "PARTIAL"
        assert result["splits"]["software"]["feasible_boundary_pairs"] == 0
        assert result["days"][2]["clips"] == 0
        assert result["days"][2]["observations"] == 0
        assert "no_clips" in result["days"][2]["exclusion_reasons"]
    assert report["games"]["gta-vi"]["totals"]["clips_first_seen_after_watermark"] == 1


def test_readiness_requests_audit_only_for_possible_mature_legacy_splits(pair):
    v, vi = pair
    v.pool(0)
    for offset in (0, 1, 4, 5, 8, 9):
        day = START + offset * DAY
        if offset:
            v.run(day, day + DAY)
        vi.run(day, day + DAY, "scanned", "recent", "cursor_exhausted")
    for fixture in pair:
        fixture.stamp(START + 12 * DAY)
        fixture.close()
    args = ("--readiness", "--start", "2025-11-01", "--end", "2025-11-11")
    process, report = cli(v.path, vi.path, *args, "--quality-day", "2025-11-01")
    assert process.returncode == 0
    assert report["mode"] == "readiness"
    assert report["common_watermark"] == to_utc_iso(START + 12 * DAY)
    left, right = (report["games"][name] for name in ("gta-v", "gta-vi"))
    assert left["calendar_candidates"] == 6
    assert left["potential_split_pairs"] >= 1
    assert left["next_action"] == "AUDIT_SEALED_SOURCES"
    assert left["decision"] == "PARTIAL"
    assert left["matched_and_validated_days"] is None
    assert left["quality_day"]["matched_all_cutoffs"] == 10
    assert right["calendar_candidates"] == right["potential_split_pairs"] == 0
    assert right["next_action"] == "WAIT_FOR_COVERED_MATURE_DAYS"
    assert right["days"][0]["exclusion_reasons"] == ["insufficient_discovery_coverage_evidence"]

    _, report = cli(
        v.path,
        vi.path,
        *args,
        "--outage",
        "gta-v",
        to_utc_iso(START + 2 * DAY),
        to_utc_iso(START + 2 * DAY + MINUTE),
    )
    assert report["games"]["gta-v"]["potential_split_pairs"] == 0
    assert report["games"]["gta-v"]["next_action"] == "WAIT_FOR_COVERED_MATURE_DAYS"


def test_feature_and_label_attrition_duplicates_and_link_errors(pair):
    v, vi = pair
    v.clip("PRIVATE_ZERO", START, views=0)
    v.snapshot("PRIVATE_ZERO", START, 2 * MINUTE, 99, "scheduled")
    v.clip("PRIVATE_65", START, seen=62, early=(62,))
    v.clip("PRIVATE_30", START, seen=34, early=(34,))
    v.clip("PRIVATE_NO_EARLY", START, early=())
    v.clip("PRIVATE_MISSING", START, result="missing")
    v.clip("PRIVATE_LATE_OUTCOME", START, result="outside_window")
    v.clip("PRIVATE_UNAVAILABLE", START, result="unavailable")
    v.clip("PRIVATE_WRONG_LINK", START, result="invalid_link")
    v.run(START, START + DAY)
    v.stamp(START + 3 * DAY)
    vi.stamp(START + 3 * DAY)
    process, report, day = one_day_report(pair)
    assert process.returncode == 2
    assert report["games"]["gta-v"]["decision"] == "NO-GO"
    assert day["outcome_status"] == {
        "valid": 4,
        "immature": 0,
        "missing": 1,
        "unavailable": 1,
        "invalid_link": 1,
        "outside_window": 1,
    }
    assert day["matched_all_cutoffs"] == 1
    assert day["cutoffs"]["60"]["matched_at_cutoff"] == 2
    assert day["cutoffs"]["65"]["matched_at_cutoff"] == 3
    assert day["cutoffs"]["60"]["feature_status"]["late_discovery"] == 1
    assert day["cutoffs"]["30"]["feature_status"]["late_discovery"] == 2
    assert day["cutoffs"]["65"]["feature_status"]["missing_observations"] == 1
    assert day["cutoffs"]["65"]["eligible_two_observations"] == 0
    assert "insufficient_matched_labels" in day["exclusion_reasons"]


def test_immature_outcome_even_when_job_already_completed(pair):
    v, vi = pair
    v.clip("PRIVATE_MEASURED", START)
    v.stamp(START + DAY + 4 * MINUTE)
    vi.stamp(START + DAY + 4 * MINUTE)
    _, _, day = one_day_report(pair)
    assert day["outcome_status"]["immature"] == 1
    assert day["valid_labels"] == 0
    assert day["valid_label_fraction_of_mature"] is None


def test_first_discovery_day_delay_bins_and_linked_schedule_are_distinct(pair):
    v, vi = pair
    v.clip("PRIVATE_FROM_YESTERDAY", START - 10 * MINUTE, seen=20, early=(20,))
    v.clip("PRIVATE_LATE_TODAY", START, seen=30, early=(30,))
    v.clip("PRIVATE_ON_TIME", START, seen=2, early=(2,))
    v.db.execute(
        "INSERT INTO jobs(clip_id,target_age_seconds,due_at,completed_at,status) "
        "VALUES(?,600,?,?,'missed')",
        (
            "PRIVATE_LATE_TODAY",
            to_utc_iso(START + 10 * MINUTE),
            to_utc_iso(START + 30 * MINUTE),
        ),
    )
    v.stamp(START + 3 * DAY)
    vi.stamp(START + 3 * DAY)
    process, _, day = one_day_report(pair)
    assert process.returncode == 0
    assert day["clips"] == 2
    assert day["first_seen_this_utc_day"] == 3
    bins = {item["upper_inclusive_seconds"]: item["clips"] for item in day["discovery_delay_bins"]}
    assert bins[600] == bins[1800] == 1
    assert day["scheduled_jobs_due_by_target_seconds"]["600"] == {
        "expected_due": 2,
        "job_rows_due": 1,
        "without_due_job_row": 1,
        "missed_before_discovery": 1,
    }
    assert day["scheduled_jobs_due_by_target_seconds"]["86400"]["recorded"] == 2


def test_coverage_union_outages_and_structural_lanes(pair):
    v, vi = pair
    v.pool(0)
    v.run(START, START + 30 * MINUTE, "partial")
    v.run(START + DAY, START + 2 * DAY - 10 * MINUTE)
    v.run(START + DAY, START + DAY + 20 * MINUTE)
    v.run(START + 2 * DAY - 10 * MINUTE, START + 2 * DAY, "error")
    vi.pool(0)
    vi.run(START, START + 5 * MINUTE, "partial", "retry", "known_incomplete")
    vi.run(START + DAY, START + 2 * DAY, "scanned", "recent", "cursor_exhausted")
    vi.run(START + DAY, START + 2 * DAY, "partial", "history", "budget")
    vi.run(
        START + DAY,
        START + 2 * DAY,
        "scanned",
        "retry",
        "cursor_exhausted",
        finished=START + 5 * DAY,
    )
    for game in pair:
        game.stamp(START + 4 * DAY)
        game.close()
    _, report = cli(
        v.path,
        vi.path,
        "--outage",
        "gta-v",
        to_utc_iso(START + DAY + MINUTE),
        to_utc_iso(START + DAY + 2 * MINUTE),
    )
    v_result, vi_result = (report["games"][key] for key in GAMES)
    v_day, v_gap = v_result["days"][:2]
    assert v_day["discovery"]["legacy_success_seconds"] == 86400
    assert v_day["discovery"]["unresolved_problem_seconds"] == 0
    assert "declared_outage_in_creation_or_observation_period" in v_day["exclusion_reasons"]
    assert v_gap["discovery"]["legacy_success_seconds"] == 85800
    assert v_gap["discovery"]["unresolved_problem_seconds"] == 600
    assert "insufficient_discovery_coverage_evidence" in v_gap["exclusion_reasons"]
    vi_day, vi_scan = vi_result["days"][:2]
    assert vi_day["discovery"]["known_incomplete_seconds"] == 300
    assert "unresolved_discovery_problem" in vi_day["exclusion_reasons"]
    assert vi_scan["discovery"]["attempted_seconds"] == 86400
    assert vi_scan["discovery"]["legacy_success_seconds"] == 0
    assert vi_result["discovery"]["lane_run_outcomes_in_audit"] == {
        "recent": {"cursor_exhausted": 1},
        "history": {"budget": 1},
        "retry": {"known_incomplete": 1},
    }
    assert vi_result["discovery"]["twitch_population_completeness"] == "UNKNOWN"


def test_full_workflow_go_is_per_game_and_uses_whole_day_embargo(pair):
    v, vi = pair
    for offset in (0, 1, 4, 5, 8, 9):
        v.pool(offset)
    vi.pool(0, count=9)
    for db in pair:
        db.stamp(START + 11 * DAY + 5 * MINUTE)
        db.close()
    _, report = cli(v.path, vi.path)
    v_report, vi_report = (report["games"][game] for game in GAMES)
    assert v_report["decision"] == "GO"
    assert v_report["splits"]["software"]["feasible_boundary_pairs"] == 1
    assert v_report["splits"]["software"]["example"] == {
        "validation_start": to_utc_iso(START + 4 * DAY),
        "test_start": to_utc_iso(START + 8 * DAY),
        "days": {"train": 2, "validation": 2, "test": 2},
        "matched": {"train": 20, "validation": 20, "test": 20},
    }
    assert v_report["splits"]["experiment"]["feasible_boundary_pairs"] == 0
    assert vi_report["decision"] == "PARTIAL"
    assert vi_report["admissible_days"] == 0
    assert v_report["days"][9]["fully_mature"]


def test_experiment_requires_500_matched_labels_and_disjoint_days():
    offsets = (*range(7), 9, 10, 11, *range(14, 21))
    days = [START + d * DAY for d in offsets]
    matches = [10] * 10 + [71] * 6 + [73]
    below = split_options(days, matches, time.monotonic() + 1)
    assert below["experiment"]["feasible_boundary_pairs"] == 0
    assert below["software"]["feasible_boundary_pairs"] > 0
    matches[-1] += 1
    exact = split_options(days, matches, time.monotonic() + 1)
    assert exact["experiment"]["feasible_boundary_pairs"] == 1
    assert exact["experiment"]["example"]["matched"]["test"] == 500


def test_empty_and_unreadable_are_explicit_and_do_not_create_files(pair, tmp_path):
    v, vi = pair
    v.close()
    vi.close()
    missing = tmp_path / "PRIVATE_NONEXISTENT.sqlite3"
    process, report = cli(v.path, missing)
    assert process.returncode == 2
    assert report["watermark_status"] == "UNKNOWN"
    v_result, vi_result = (report["games"][game] for game in GAMES)
    assert v_result["status"] == "UNKNOWN" and v_result["decision"] == "PARTIAL"
    assert v_result["totals"]["clips_at_snapshot"] == 0
    assert v_result["totals"]["clips_at_watermark"] is None
    assert v_result["days"] is None
    assert vi_result["decision_reason"] == "database_or_required_sidecar_missing"
    assert "totals" not in vi_result
    assert not missing.exists()


def test_wrong_category_is_rejected_and_other_game_uses_own_watermark(pair):
    v, vi = pair
    v.db.execute("INSERT INTO games VALUES('111','wrong',?)", (to_utc_iso(START),))
    vi.pool(0)
    vi.stamp(START + 3 * DAY)
    for db in pair:
        db.close()
    process, report = cli(v.path, vi.path)
    assert process.returncode == 2
    assert report["games"]["gta-v"]["decision_reason"] == "unexpected_game_id"
    assert report["games"]["gta-vi"]["watermark_basis"] == "individual_only"


def test_deadline_and_active_rollback_journal_fail_closed(pair):
    v, vi = pair
    v.close()
    vi.close()
    with closing(sqlite3.connect(v.path)) as writer:
        writer.execute("BEGIN EXCLUSIVE")
        process, report = cli(v.path, vi.path, "--timeout", "1")
    assert process.returncode == 2
    assert report["games"]["gta-v"]["decision_reason"] == "deadline_exceeded"
    assert report["games"]["gta-v"]["status"] == "UNKNOWN"
    journal = Path(str(v.path) + "-journal")
    journal.write_bytes(b"PRIVATE_JOURNAL")
    process, report = cli(v.path, vi.path)
    assert process.returncode == 2
    assert (
        report["games"]["gta-v"]["decision_reason"]
        == "live_or_unsealed_source_requires_linux_landlock"
    )
    assert journal.read_bytes() == b"PRIVATE_JOURNAL"


def test_sealed_databases_have_identical_bytes_and_no_new_sidecars(pair):
    for db in pair:
        db.pool(0)
        db.stamp(START + 3 * DAY)
        db.close()
    before = {f: (f.read_bytes(), f.stat().st_mtime_ns) for f in pair[0].path.parent.iterdir()}
    process, _ = cli(*(f.path for f in pair))
    assert process.returncode == 0
    after = {f: (f.read_bytes(), f.stat().st_mtime_ns) for f in pair[0].path.parent.iterdir()}
    assert before == after


def test_wal_and_shm_are_preserved_or_read_refuses_without_guard(pair):
    v, vi = pair
    try:
        for fixture in pair:
            fixture.db.commit()
            assert fixture.db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
            fixture.pool(0)
            fixture.stamp(START + 3 * DAY)
            fixture.db.commit()
        before = {f: f.read_bytes() for f in v.path.parent.iterdir()}
        assert len(before) == 6
        process, report = cli(v.path, vi.path)
        if sys.platform == "linux":
            assert process.returncode == 0
            assert report["games"]["gta-v"]["admissible_days"] == 1
        else:
            assert process.returncode == 2
            assert report["games"]["gta-v"]["decision_reason"] == (
                "live_or_unsealed_source_requires_linux_landlock"
            )
        assert before == {f: f.read_bytes() for f in v.path.parent.iterdir()}
    finally:
        for fixture in pair:
            fixture.close()


def test_guard_failure_never_opens_database(monkeypatch, capsys):
    def no_landlock():
        raise m2_audit.AuditError("landlock_abi_3_unavailable")

    def unexpected_open(*args):
        pytest.fail("SQLite opened before Landlock")

    monkeypatch.setattr(m2_audit.sys, "platform", "linux")
    monkeypatch.setattr(m2_audit, "deny_fs_writes", no_landlock)
    monkeypatch.setattr(m2_audit, "open_snapshot", unexpected_open)
    assert m2_audit.main(["--gta-v", "x", "--gta-vi", "y"]) == 2
    assert "landlock_abi_3_unavailable" in capsys.readouterr().out


def test_streamed_source_checks_support_hashes(pair):
    v, vi = pair
    for fixture in pair:
        fixture.pool(0)
        fixture.stamp(START + 3 * DAY)
        fixture.close()
    source = Path(m2_audit.__file__).read_text(encoding="utf-8")
    hashes = [
        sha256(Path(module.__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for module in (dataset, evaluation)
    ]
    command = [
        sys.executable,
        "-I",
        "-B",
        "-",
        "--gta-v",
        str(v.path),
        "--gta-vi",
        str(vi.path),
        "--verify-support",
    ]
    result = subprocess.run(
        command + hashes,
        input=source,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["games"]["gta-v"]["admissible_days"] == 1
    result = subprocess.run(
        command + ["0" * 64, hashes[1]],
        input=source,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["games"]["gta-v"]["decision_reason"] == (
        "support_module_hash_mismatch"
    )
