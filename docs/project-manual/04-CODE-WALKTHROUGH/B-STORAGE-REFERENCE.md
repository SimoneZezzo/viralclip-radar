# Riferimento a firme e chiamate

[Indice delle schede](00-GUIDE.md) · [Spiegazione dei moduli](02-STORAGE.md)

Indice statico ricavato con AST. I chiamanti e i test sono corrispondenze per simbolo, comprese quelle indirette nei callback definiti dentro un test. Le prove indirette e i percorsi effettivi sono nelle schede narrative. Per nomi condivisi come `main`, `_csv`, `preflight` e `close`, gli omonimi di altri moduli sono omessi dall'elenco per evitare attribuzioni ambigue. Importazioni dinamiche e callback passati senza invocarli possono sfuggire all'indice.

## src/viralclip/storage/__init__.py

[Apri il file](../../../src/viralclip/storage/__init__.py)

Import dichiarati. nessuno.

Il modulo non dichiara funzioni o classi.

## src/viralclip/storage/backup.py

[Apri il file](../../../src/viralclip/storage/backup.py)

Import dichiarati. `import argparse`, `import json`, `import sqlite3`, `import time`, `from contextlib import closing`, `from pathlib import Path`, `from tempfile import TemporaryDirectory`, `from viralclip.config import load_settings`.

### _reader

`_reader(path: Path) -> sqlite3.Connection`

[`Sorgente`](../../../src/viralclip/storage/backup.py#L16) (righe 16–17).

Chiamate nel corpo. `sqlite3.connect`, `path.resolve().as_uri`, `path.resolve`.

Chiamanti per nome. [`online_copy`](../../../src/viralclip/storage/backup.py#L20), [`validate`](../../../src/viralclip/storage/backup.py#L42).

### online_copy

`online_copy(source: Path, destination: Path) -> None`

[`Sorgente`](../../../src/viralclip/storage/backup.py#L20) (righe 20–39).

Chiamate nel corpo. `closing`, `_reader`, `reader.execute`, `destination.parent.mkdir`, `destination.touch`, `time.monotonic`, `sqlite3.connect`, `reader.backup`, `writer.execute('PRAGMA journal_mode = DELETE').fetchone`, `writer.execute`, `ValueError`, `destination.unlink`.

Chiamanti per nome. [`backup_and_verify`](../../../src/viralclip/storage/backup.py#L114).

Test che richiamano il simbolo. [`test_copy_refuses_existing_destination_or_source_alias`](../../../tests/test_backup.py#L33), [`test_synthetic_transfer_preserves_links_pending_jobs_and_real_times`](../../../tests/test_deployment.py#L51), [`test_manifest_rejects_wal_and_verify_rejects_wrong_transfer`](../../../tests/test_deployment.py#L100), [`test_service_preflight_declines_missing_schema_or_changed_configuration`](../../../tests/test_deployment.py#L119).

### online_copy.check_deadline

`online_copy.check_deadline(status: int, _remaining: int, _total: int) -> None`

[`Sorgente`](../../../src/viralclip/storage/backup.py#L28) (righe 28–30).

Chiamate nel corpo. `time.monotonic`, `TimeoutError`.

### validate

`validate(path: Path) -> dict[str, object]`

[`Sorgente`](../../../src/viralclip/storage/backup.py#L42) (righe 42–111).

Chiamate nel corpo. `closing`, `_reader`, `reader.execute`, `reader.execute('PRAGMA integrity_check').fetchall`, `ValueError`, `reader.execute('PRAGMA foreign_key_check').fetchone`, `reader.execute(f'SELECT COUNT(*) FROM {table}').fetchone`, `reader.execute("\n            SELECT COUNT(*) FROM jobs j LEFT JOIN clip_snapshots s USING (snapshot_id)\n            WHERE (j.status = 'completed' AND (\n                s.snapshot_id IS NULL OR s.clip_id <> j.clip_id OR s.source <> 'scheduled'\n                OR j.completed_at IS NOT s.observed_at OR s.observed_at < j.due_at\n            )) OR (j.status <> 'completed' AND j.snapshot_id IS NOT NULL)\n            ").fetchone`, `reader.execute("\n            SELECT COUNT(*) FROM clip_snapshots\n            WHERE source = 'scheduled' AND snapshot_id NOT IN (\n                SELECT snapshot_id FROM jobs WHERE snapshot_id IS NOT NULL\n            )\n            ").fetchone`, `reader.execute("\n            SELECT COUNT(*) FROM clips c WHERE (\n                SELECT COUNT(DISTINCT target_age_seconds) FROM jobs j\n                WHERE j.clip_id = c.clip_id AND j.job_type = 'view_snapshot'\n                  AND j.target_age_seconds IN (600, 1800, 3600, 21600, 86400)\n            ) <> 5\n            ").fetchone`, `reader.execute('SELECT MAX(version) FROM schema_migrations').fetchone`, `reader.execute("SELECT COUNT(*) FROM jobs WHERE target_age_seconds = 86400 AND status = 'completed'").fetchone`, `reader.execute('SELECT MAX(observed_at) FROM clip_snapshots').fetchone`, `reader.execute("\n            SELECT MAX(finished_at) FROM collection_runs\n            WHERE status = 'completed' AND error_summary IS NULL AND potentially_truncated = 0\n            ").fetchone`.

Chiamanti per nome. [`snapshot_manifest`](../../../src/viralclip/deployment.py#L83), [`backup_and_verify`](../../../src/viralclip/storage/backup.py#L114).

Test che richiamano il simbolo. [`test_validation_rejects_incorrect_completed_job_link`](../../../tests/test_backup.py#L45).

### backup_and_verify

`backup_and_verify(source: Path, destination: Path) -> dict[str, object]`

[`Sorgente`](../../../src/viralclip/storage/backup.py#L114) (righe 114–122).

Chiamate nel corpo. `online_copy`, `validate`, `TemporaryDirectory`, `Path`, `ValueError`.

Chiamanti per nome. [`run_backup`](../../../src/viralclip/operations.py#L202), [`restore_latest`](../../../src/viralclip/operations.py#L254), [`main`](../../../src/viralclip/storage/backup.py#L125).

Test che richiamano il simbolo. [`test_online_backup_and_restore_see_committed_wal_only`](../../../tests/test_backup.py#L12), [`test_synthetic_transfer_preserves_links_pending_jobs_and_real_times`](../../../tests/test_deployment.py#L51).

### main

`main() -> int`

[`Sorgente`](../../../src/viralclip/storage/backup.py#L125) (righe 125–137).

Chiamate nel corpo. `argparse.ArgumentParser`, `parser.add_argument`, `parser.parse_args`, `load_settings`, `backup_and_verify`, `parser.exit`, `json.dumps`.

## src/viralclip/storage/database.py

[Apri il file](../../../src/viralclip/storage/database.py)

Import dichiarati. `import sqlite3`, `from collections.abc import Iterator`, `from contextlib import contextmanager`, `from datetime import UTC, datetime, timedelta`, `from pathlib import Path`, `import os`, `import msvcrt`, `import fcntl`.

Costanti. `TARGET_AGES_SECONDS`, `MIGRATIONS`.

### utc_now

`utc_now() -> datetime`

[`Sorgente`](../../../src/viralclip/storage/database.py#L111) (righe 111–112).

Chiamate nel corpo. `datetime.now`.

Chiamanti per nome. [`_print_status`](../../../src/viralclip/cli.py#L58), [`main`](../../../src/viralclip/cli.py#L70), [`Database.migrate`](../../../src/viralclip/storage/database.py#L181), [`read_health`](../../../src/viralclip/storage/health.py#L209).

### to_utc_iso

`to_utc_iso(value: datetime) -> str`

[`Sorgente`](../../../src/viralclip/storage/database.py#L115) (righe 115–118).

Chiamate nel corpo. `value.utcoffset`, `ValueError`, `value.astimezone(UTC).isoformat(timespec='microseconds').replace`, `value.astimezone(UTC).isoformat`, `value.astimezone`.

Chiamanti per nome. [`read_source`](../../../src/viralclip/dataset.py#L96), [`candidate`](../../../src/viralclip/dataset.py#L168), [`outcome`](../../../src/viralclip/dataset.py#L228), [`_outage_coverage`](../../../src/viralclip/dataset.py#L305), [`extract`](../../../src/viralclip/dataset.py#L361), [`read_inputs`](../../../src/viralclip/evaluation.py#L148), [`evaluate`](../../../src/viralclip/evaluation.py#L459), [`run_evaluation`](../../../src/viralclip/evaluation.py#L527), [`Database.migrate`](../../../src/viralclip/storage/database.py#L181), [`Database.upsert_game`](../../../src/viralclip/storage/database.py#L206), [`Database.record_clip`](../../../src/viralclip/storage/database.py#L225), [`Database._create_jobs`](../../../src/viralclip/storage/database.py#L292), [`Database.create_run`](../../../src/viralclip/storage/database.py#L314), [`Database.finish_run`](../../../src/viralclip/storage/database.py#L326), [`Database.update_watermark`](../../../src/viralclip/storage/database.py#L360), [`Database.record_error`](../../../src/viralclip/storage/database.py#L370), [`Database.due_jobs`](../../../src/viralclip/storage/database.py#L377), [`Database.finish_jobs`](../../../src/viralclip/storage/database.py#L402), [`Database.add_scheduled_snapshot`](../../../src/viralclip/storage/database.py#L420), [`Database.status`](../../../src/viralclip/storage/database.py#L471), [`read_health`](../../../src/viralclip/storage/health.py#L209).

Test che richiamano il simbolo. [`test_page_survives_later_failure_and_checkpoint_does_not_advance`](../../../tests/test_audit.py#L32), [`test_saturation_without_cursor_is_flagged_and_children_cannot_skip_gap`](../../../tests/test_audit.py#L51), [`test_full_http_flow_restart_and_delayed_snapshot`](../../../tests/test_audit.py#L100), [`test_additive_migration_preserves_existing_measurements`](../../../tests/test_audit.py#L154), [`test_status_is_local_and_timestamps_require_timezone`](../../../tests/test_collector.py#L388), [`test_synthetic_transfer_preserves_links_pending_jobs_and_real_times`](../../../tests/test_deployment.py#L51), [`test_future_feature_timestamp_is_rejected`](../../../tests/test_evaluation.py#L131), [`test_valid_label_with_an_unelapsed_window_is_rejected`](../../../tests/test_evaluation.py#L217).

### parse_utc

`parse_utc(value: str) -> datetime`

[`Sorgente`](../../../src/viralclip/storage/database.py#L121) (righe 121–125).

Chiamate nel corpo. `datetime.fromisoformat`, `parsed.utcoffset`, `ValueError`, `parsed.astimezone`.

Chiamanti per nome. [`main`](../../../src/viralclip/cli.py#L70), [`read_source`](../../../src/viralclip/dataset.py#L96), [`outcome`](../../../src/viralclip/dataset.py#L228), [`_candidate`](../../../src/viralclip/evaluation.py#L74), [`_outcome`](../../../src/viralclip/evaluation.py#L116), [`read_inputs`](../../../src/viralclip/evaluation.py#L148), [`_http_rates`](../../../src/viralclip/operations.py#L89), [`monitor`](../../../src/viralclip/operations.py#L295), [`Database.cached_game`](../../../src/viralclip/storage/database.py#L217), [`Database.add_scheduled_snapshot`](../../../src/viralclip/storage/database.py#L420), [`_age`](../../../src/viralclip/storage/health.py#L21), [`_observations`](../../../src/viralclip/storage/health.py#L139), [`read_health`](../../../src/viralclip/storage/health.py#L209).

### Classe Database

[`Database`](../../../src/viralclip/storage/database.py#L128) (righe 128–517).

### Database.__init__

`Database.__init__(self, path: str | Path)`

[`Sorgente`](../../../src/viralclip/storage/database.py#L129) (righe 129–142).

Chiamate nel corpo. `Path`, `self.path.parent.mkdir`, `sqlite3.connect`, `self.connection.execute`, `self.migrate`.

### Database.acquire_collector_lock

`Database.acquire_collector_lock(self) -> None`

[`Sorgente`](../../../src/viralclip/storage/database.py#L144) (righe 144–168).

Chiamate nel corpo. `open`, `self.path.resolve`, `lock.seek`, `lock.read`, `lock.write`, `lock.flush`, `msvcrt.locking`, `lock.fileno`, `fcntl.flock`, `lock.close`, `ValueError`.

Chiamanti per nome. [`Collector.__init__`](../../../src/viralclip/collector/service.py#L11).

Test che richiamano il simbolo. [`test_second_collector_rejected_but_status_available`](../../../tests/test_audit.py#L143), [`test_synthetic_transfer_preserves_links_pending_jobs_and_real_times`](../../../tests/test_deployment.py#L51), [`test_preflight_keeps_existing_wal_and_rejects_drift_or_missing_file`](../../../tests/test_windows_supervision.py#L63), [`test_real_cross_process_database_lock_rejects_second_owner`](../../../tests/test_windows_supervision.py#L216).

### Database.close

`Database.close(self) -> None`

[`Sorgente`](../../../src/viralclip/storage/database.py#L170) (righe 170–174).

Chiamate nel corpo. `self.connection.close`, `self._collector_lock.close`.

Chiamanti per nome. [`Database.acquire_collector_lock`](../../../src/viralclip/storage/database.py#L144).

### Database.transaction

`Database.transaction(self) -> Iterator[sqlite3.Connection]`

[`Sorgente`](../../../src/viralclip/storage/database.py#L177) (righe 177–179).

Chiamanti per nome. [`Database.upsert_game`](../../../src/viralclip/storage/database.py#L206), [`Database.record_clip`](../../../src/viralclip/storage/database.py#L225), [`Database.create_run`](../../../src/viralclip/storage/database.py#L314), [`Database.finish_run`](../../../src/viralclip/storage/database.py#L326), [`Database.update_watermark`](../../../src/viralclip/storage/database.py#L360), [`Database.record_error`](../../../src/viralclip/storage/database.py#L370), [`Database.start_jobs`](../../../src/viralclip/storage/database.py#L391), [`Database.finish_jobs`](../../../src/viralclip/storage/database.py#L402), [`Database.add_scheduled_snapshot`](../../../src/viralclip/storage/database.py#L420), [`Database.recover_running_jobs`](../../../src/viralclip/storage/database.py#L457).

Test che richiamano il simbolo. [`test_missing_unavailable_invalid_and_out_of_window_are_never_zero`](../../../tests/test_dataset.py#L131), [`test_future_jobs_and_mutable_metadata_cannot_change_candidate_features`](../../../tests/test_dataset.py#L164), [`test_service_preflight_declines_missing_schema_or_changed_configuration`](../../../tests/test_deployment.py#L119), [`test_invalid_record_and_missing_completed_link`](../../../tests/test_health.py#L129), [`test_cli_reads_concurrent_wal_without_initializing`](../../../tests/test_health.py#L141), [`test_preflight_keeps_existing_wal_and_rejects_drift_or_missing_file`](../../../tests/test_windows_supervision.py#L63).

### Database.migrate

`Database.migrate(self) -> None`

[`Sorgente`](../../../src/viralclip/storage/database.py#L181) (righe 181–204).

Chiamate nel corpo. `self.connection.execute`, `self.connection.execute('SELECT COALESCE(MAX(version), 0) FROM schema_migrations').fetchone`, `enumerate`, `to_utc_iso`, `utc_now`, `applied_at.replace`, `self.connection.executescript`, `self.connection.rollback`.

Chiamanti per nome. [`Database.__init__`](../../../src/viralclip/storage/database.py#L129).

### Database.upsert_game

`Database.upsert_game(self, game_id: str, name: str, resolved_at: datetime) -> None`

[`Sorgente`](../../../src/viralclip/storage/database.py#L206) (righe 206–215).

Chiamate nel corpo. `self.transaction`, `conn.execute`, `to_utc_iso`.

Chiamanti per nome. [`Collector.resolve_game`](../../../src/viralclip/collector/service.py#L26), [`Collector.collect_cycle`](../../../src/viralclip/collector/service.py#L209).

Test che richiamano il simbolo. [`test_online_backup_and_restore_see_committed_wal_only`](../../../tests/test_backup.py#L12), [`test_validation_rejects_incorrect_completed_job_link`](../../../tests/test_backup.py#L45), [`test_overlapping_discovery_preserves_first_seen_and_appends_snapshots`](../../../tests/test_collector.py#L103), [`test_late_discovery_marks_old_targets_missed_without_backdating`](../../../tests/test_collector.py#L141), [`test_due_snapshot_batches_under_one_hundred_and_handles_unordered_results`](../../../tests/test_collector.py#L164), [`test_unavailable_clip_is_not_recorded_as_zero`](../../../tests/test_collector.py#L300), [`test_discovery_uses_persisted_watermark_after_a_long_gap`](../../../tests/test_collector.py#L329), [`test_restart_recovers_running_jobs_without_duplicates`](../../../tests/test_collector.py#L348), [`test_snapshots_cannot_be_updated_or_deleted`](../../../tests/test_collector.py#L369), [`test_synthetic_transfer_preserves_links_pending_jobs_and_real_times`](../../../tests/test_deployment.py#L51), [`test_preflight_rejects_id_drift_and_donor_alias`](../../../tests/test_gta_vi.py#L85).

### Database.cached_game

`Database.cached_game(self, name: str, max_age_seconds: int, now: datetime) -> sqlite3.Row | None`

[`Sorgente`](../../../src/viralclip/storage/database.py#L217) (righe 217–223).

Chiamate nel corpo. `self.connection.execute('SELECT * FROM games WHERE name = ? COLLATE NOCASE', (name,)).fetchone`, `self.connection.execute`, `(now - parse_utc(row['last_resolved_at'])).total_seconds`, `parse_utc`.

Chiamanti per nome. [`Collector.resolve_game`](../../../src/viralclip/collector/service.py#L26).

### Database.record_clip

`Database.record_clip(self, clip: dict, game_id: str, observed_at: datetime, run_id: int | None) -> bool`

[`Sorgente`](../../../src/viralclip/storage/database.py#L225) (righe 225–289).

Chiamate nel corpo. `ValueError`, `to_utc_iso`, `self.transaction`, `conn.execute('SELECT clip_id FROM clips WHERE clip_id = ?', (clip_id,)).fetchone`, `conn.execute`, `clip.get`, `(observed_at - clip['created_at']).total_seconds`, `self._create_jobs`.

Chiamanti per nome. [`Collector._discover_window`](../../../src/viralclip/collector/service.py#L64).

Test che richiamano il simbolo. [`test_malformed_refresh_is_failed_not_unavailable`](../../../tests/test_audit.py#L71), [`test_snapshot_and_completion_roll_back_together`](../../../tests/test_audit.py#L82), [`test_failed_jobs_have_delay_and_bounded_attempts`](../../../tests/test_audit.py#L238), [`test_impossible_age_rejected_without_any_rows`](../../../tests/test_audit.py#L363), [`test_online_backup_and_restore_see_committed_wal_only`](../../../tests/test_backup.py#L12), [`test_validation_rejects_incorrect_completed_job_link`](../../../tests/test_backup.py#L45), [`test_late_discovery_marks_old_targets_missed_without_backdating`](../../../tests/test_collector.py#L141), [`test_due_snapshot_batches_under_one_hundred_and_handles_unordered_results`](../../../tests/test_collector.py#L164), [`test_unavailable_clip_is_not_recorded_as_zero`](../../../tests/test_collector.py#L300), [`test_restart_recovers_running_jobs_without_duplicates`](../../../tests/test_collector.py#L348), [`test_snapshots_cannot_be_updated_or_deleted`](../../../tests/test_collector.py#L369), [`test_synthetic_transfer_preserves_links_pending_jobs_and_real_times`](../../../tests/test_deployment.py#L51).

### Database._create_jobs

`Database._create_jobs(conn: sqlite3.Connection, clip_id: str, created_at: datetime, first_seen_at: datetime) -> None`

[`Sorgente`](../../../src/viralclip/storage/database.py#L292) (righe 292–312).

Chiamate nel corpo. `timedelta`, `conn.execute`, `to_utc_iso`.

Chiamanti per nome. [`Database.record_clip`](../../../src/viralclip/storage/database.py#L225).

### Database.create_run

`Database.create_run(self, game_id: str, start: datetime, end: datetime, started: datetime) -> int`

[`Sorgente`](../../../src/viralclip/storage/database.py#L314) (righe 314–324).

Chiamate nel corpo. `self.transaction`, `conn.execute`, `to_utc_iso`.

Chiamanti per nome. [`Collector._discover_window`](../../../src/viralclip/collector/service.py#L64).

### Database.finish_run

`Database.finish_run(self, run_id: int, finished: datetime, requests: int, pages: int, seen: int, new: int, truncated: bool=False, error: str | None=None, unique: int=0) -> None`

[`Sorgente`](../../../src/viralclip/storage/database.py#L326) (righe 326–358).

Chiamate nel corpo. `self.transaction`, `conn.execute`, `to_utc_iso`.

Chiamanti per nome. [`Collector._discover_window`](../../../src/viralclip/collector/service.py#L64).

### Database.update_watermark

`Database.update_watermark(self, game_id: str, watermark: datetime) -> None`

[`Sorgente`](../../../src/viralclip/storage/database.py#L360) (righe 360–368).

Chiamate nel corpo. `self.transaction`, `conn.execute`, `to_utc_iso`.

Chiamanti per nome. [`Collector.discover`](../../../src/viralclip/collector/service.py#L53).

Test che richiamano il simbolo. [`test_discovery_uses_persisted_watermark_after_a_long_gap`](../../../tests/test_collector.py#L329).

### Database.record_error

`Database.record_error(self, occurred_at: datetime, message: str) -> None`

[`Sorgente`](../../../src/viralclip/storage/database.py#L370) (righe 370–375).

Chiamate nel corpo. `self.transaction`, `conn.execute`, `to_utc_iso`.

Chiamanti per nome. [`main`](../../../src/viralclip/cli.py#L70), [`Collector.collect_cycle`](../../../src/viralclip/collector/service.py#L209).

Test che richiamano il simbolo. [`test_recent_errors_are_reported_without_stored_message`](../../../tests/test_health.py#L110).

### Database.due_jobs

`Database.due_jobs(self, now: datetime, limit: int=1000) -> list[sqlite3.Row]`

[`Sorgente`](../../../src/viralclip/storage/database.py#L377) (righe 377–389).

Chiamate nel corpo. `self.connection.execute`, `to_utc_iso`.

Chiamanti per nome. [`Collector.collect_due_snapshots`](../../../src/viralclip/collector/service.py#L163).

Test che richiamano il simbolo. [`test_failed_jobs_have_delay_and_bounded_attempts`](../../../tests/test_audit.py#L238).

### Database.start_jobs

`Database.start_jobs(self, job_ids: list[int]) -> None`

[`Sorgente`](../../../src/viralclip/storage/database.py#L391) (righe 391–400).

Chiamate nel corpo. `','.join`, `self.transaction`, `conn.execute`.

Chiamanti per nome. [`Collector.collect_due_snapshots`](../../../src/viralclip/collector/service.py#L163).

Test che richiamano il simbolo. [`test_full_http_flow_restart_and_delayed_snapshot`](../../../tests/test_audit.py#L100), [`test_restart_recovers_running_jobs_without_duplicates`](../../../tests/test_collector.py#L348), [`test_synthetic_transfer_preserves_links_pending_jobs_and_real_times`](../../../tests/test_deployment.py#L51), [`test_execution_failure_retry_and_exhaustion`](../../../tests/test_health.py#L79).

### Database.finish_jobs

`Database.finish_jobs(self, job_ids: list[int], status: str, completed_at: datetime, error: str | None=None) -> None`

[`Sorgente`](../../../src/viralclip/storage/database.py#L402) (righe 402–418).

Chiamate nel corpo. `','.join`, `self.transaction`, `conn.execute`, `to_utc_iso`, `timedelta`.

Chiamanti per nome. [`Collector.collect_due_snapshots`](../../../src/viralclip/collector/service.py#L163).

Test che richiamano il simbolo. [`test_missing_unavailable_invalid_and_out_of_window_are_never_zero`](../../../tests/test_dataset.py#L131), [`test_healthy_reports_real_lateness_and_strict_coverage`](../../../tests/test_health.py#L49), [`test_execution_failure_retry_and_exhaustion`](../../../tests/test_health.py#L79), [`test_invalid_record_and_missing_completed_link`](../../../tests/test_health.py#L129).

### Database.add_scheduled_snapshot

`Database.add_scheduled_snapshot(self, clip_id: str, observed_at: datetime, view_count: int, target_age: int | None, job_ids: list[int] | None=None) -> None`

[`Sorgente`](../../../src/viralclip/storage/database.py#L420) (righe 420–455).

Chiamate nel corpo. `self.connection.execute('SELECT created_at FROM clips WHERE clip_id = ?', (clip_id,)).fetchone`, `self.connection.execute`, `ValueError`, `(observed_at - parse_utc(row['created_at'])).total_seconds`, `parse_utc`, `self.transaction`, `conn.execute`, `to_utc_iso`, `conn.execute("SELECT snapshot_id FROM clip_snapshots WHERE clip_id = ? AND observed_at = ? AND source = 'scheduled'", (clip_id, to_utc_iso(observed_at))).fetchone`.

Chiamanti per nome. [`Collector.collect_due_snapshots`](../../../src/viralclip/collector/service.py#L163).

Test che richiamano il simbolo. [`test_snapshot_and_completion_roll_back_together`](../../../tests/test_audit.py#L82), [`test_synthetic_transfer_preserves_links_pending_jobs_and_real_times`](../../../tests/test_deployment.py#L51), [`test_healthy_reports_real_lateness_and_strict_coverage`](../../../tests/test_health.py#L49), [`test_late_observation_p95_can_degrade_without_backlog`](../../../tests/test_health.py#L177).

### Database.recover_running_jobs

`Database.recover_running_jobs(self) -> None`

[`Sorgente`](../../../src/viralclip/storage/database.py#L457) (righe 457–469).

Chiamate nel corpo. `self.transaction`, `conn.execute`.

Chiamanti per nome. [`Collector.__init__`](../../../src/viralclip/collector/service.py#L11).

Test che richiamano il simbolo. [`test_synthetic_transfer_preserves_links_pending_jobs_and_real_times`](../../../tests/test_deployment.py#L51).

### Database.status

`Database.status(self, now: datetime) -> dict`

[`Sorgente`](../../../src/viralclip/storage/database.py#L471) (righe 471–517).

Chiamate nel corpo. `self.connection.execute("\n            SELECT finished_at FROM collection_runs\n            WHERE status = 'completed' AND error_summary IS NULL AND potentially_truncated = 0\n            ORDER BY finished_at DESC LIMIT 1\n            ").fetchone`, `self.connection.execute`, `self.connection.execute('\n            SELECT message FROM (\n                SELECT error_summary AS message, COALESCE(finished_at, started_at) AS occurred_at\n                FROM collection_runs WHERE error_summary IS NOT NULL\n                UNION ALL\n                SELECT last_error, COALESCE(completed_at, due_at)\n                FROM jobs WHERE last_error IS NOT NULL\n                UNION ALL\n                SELECT message, occurred_at FROM operational_errors\n            )\n            ORDER BY occurred_at DESC LIMIT 1\n            ').fetchone`, `self.connection.execute("\n            SELECT COUNT(*) FROM jobs\n            WHERE status IN ('pending', 'failed') AND due_at <= ? AND attempts < 3\n            ", (to_utc_iso(now),)).fetchone`, `to_utc_iso`, `table_count`.

Chiamanti per nome. [`_print_status`](../../../src/viralclip/cli.py#L58).

Test che richiamano il simbolo. [`test_page_survives_later_failure_and_checkpoint_does_not_advance`](../../../tests/test_audit.py#L32), [`test_malformed_refresh_is_failed_not_unavailable`](../../../tests/test_audit.py#L71), [`test_snapshot_and_completion_roll_back_together`](../../../tests/test_audit.py#L82), [`test_full_http_flow_restart_and_delayed_snapshot`](../../../tests/test_audit.py#L100), [`test_second_collector_rejected_but_status_available`](../../../tests/test_audit.py#L143), [`test_impossible_age_rejected_without_any_rows`](../../../tests/test_audit.py#L363), [`test_status_is_local_and_timestamps_require_timezone`](../../../tests/test_collector.py#L388).

### Database.status.table_count

`Database.status.table_count(table: str) -> int`

[`Sorgente`](../../../src/viralclip/storage/database.py#L472) (righe 472–473).

Chiamate nel corpo. `self.connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone`, `self.connection.execute`.

Chiamanti per nome. [`Database.status`](../../../src/viralclip/storage/database.py#L471).

## src/viralclip/storage/health.py

[Apri il file](../../../src/viralclip/storage/health.py)

Import dichiarati. `import sqlite3`, `from collections import defaultdict`, `from contextlib import closing`, `from datetime import datetime, timedelta`, `from math import ceil`, `from pathlib import Path`, `from statistics import median`, `from viralclip.storage.database import TARGET_AGES_SECONDS, parse_utc, to_utc_iso, utc_now`.

Costanti. `LEVELS`, `RECENT`, `EARLY_TARGETS`.

### _age

`_age(now: datetime, timestamp: str) -> float`

[`Sorgente`](../../../src/viralclip/storage/health.py#L21) (righe 21–25).

Chiamate nel corpo. `(now - parse_utc(timestamp)).total_seconds`, `parse_utc`, `ValueError`.

Chiamanti per nome. [`_discovery`](../../../src/viralclip/storage/health.py#L28), [`_jobs`](../../../src/viralclip/storage/health.py#L94), [`_observations`](../../../src/viralclip/storage/health.py#L139).

### _discovery

`_discovery(db: sqlite3.Connection, now: datetime, since: str, interval_seconds: int, lines: list[str], alerts: list[tuple[int, str]]) -> None`

[`Sorgente`](../../../src/viralclip/storage/health.py#L28) (righe 28–91).

Chiamate nel corpo. `db.execute("\n        SELECT MAX(finished_at) FROM collection_runs\n        WHERE status = 'completed' AND potentially_truncated = 0 AND error_summary IS NULL\n        ").fetchone`, `db.execute`, `_age`, `db.execute("\n        SELECT g.game_id, c.watermark,\n               MAX(CASE WHEN r.status = 'completed' AND r.potentially_truncated = 0\n                         AND r.error_summary IS NULL THEN r.finished_at END) AS last_success,\n               COUNT(*) FILTER (WHERE r.finished_at >= ? AND r.status = 'completed'\n                         AND r.potentially_truncated = 0 AND r.error_summary IS NULL) AS complete,\n               COUNT(*) FILTER (WHERE r.finished_at >= ? AND r.status = 'partial') AS partial,\n               COUNT(*) FILTER (WHERE r.finished_at >= ? AND r.status = 'error') AS errors,\n               COUNT(*) FILTER (WHERE r.status = 'running') AS running,\n               COUNT(*) FILTER (WHERE r.finished_at >= ? AND r.potentially_truncated = 1)\n                   AS truncated,\n               COUNT(*) FILTER (WHERE r.finished_at >= ?\n                         AND (r.status IN ('partial', 'error') OR r.potentially_truncated = 1)\n                         AND (c.watermark IS NULL OR r.window_end > c.watermark)) AS unresolved\n        FROM games g\n        LEFT JOIN discovery_checkpoints c USING (game_id)\n        LEFT JOIN collection_runs r USING (game_id)\n        GROUP BY g.game_id\n        ORDER BY g.game_id\n        ", (since,) * 5).fetchall`, `max`.

Chiamanti per nome. [`read_health`](../../../src/viralclip/storage/health.py#L209).

### _jobs

`_jobs(db: sqlite3.Connection, now: datetime, cutoff: str, lines: list[str], alerts: list[tuple[int, str]]) -> None`

[`Sorgente`](../../../src/viralclip/storage/health.py#L94) (righe 94–136).

Chiamate nel corpo. `db.execute("\n        SELECT status, COUNT(*) AS total,\n               COUNT(*) FILTER (WHERE due_at <= ? AND status IN ('pending','running','failed'))\n                   AS overdue,\n               MIN(CASE WHEN due_at <= ? AND status IN ('pending','running','failed')\n                   THEN due_at END) AS oldest_due,\n               COUNT(*) FILTER (WHERE status = 'failed' AND attempts >= 3) AS exhausted,\n               COUNT(*) FILTER (WHERE julianday(due_at) IS NULL) AS invalid_due\n        FROM jobs GROUP BY status\n        ", (cutoff, cutoff)).fetchall`, `db.execute`, `max`, `_age`, `totals.get`, `any`, `ValueError`.

Chiamanti per nome. [`read_health`](../../../src/viralclip/storage/health.py#L209).

### _observations

`_observations(db: sqlite3.Connection, now: datetime, since: str, cutoff: str, lines: list[str], alerts: list[tuple[int, str]]) -> None`

[`Sorgente`](../../../src/viralclip/storage/health.py#L139) (righe 139–206).

Chiamate nel corpo. `defaultdict`, `db.execute`, `ValueError`, `(parse_utc(observed) - parse_utc(row['due_at'])).total_seconds`, `parse_utc`, `_age`, `RECENT.total_seconds`, `ceil`, `median`, `by_target.get`.

Chiamanti per nome. [`read_health`](../../../src/viralclip/storage/health.py#L209).

### read_health

`read_health(path: Path, interval_seconds: int, *, now: datetime | None=None) -> tuple[int, list[str]]`

[`Sorgente`](../../../src/viralclip/storage/health.py#L209) (righe 209–276).

Chiamate nel corpo. `path.resolve().as_uri`, `path.resolve`, `sqlite3.connect`, `closing`, `db.execute`, `db.execute('SELECT (SELECT COUNT(*) FROM clips), (SELECT COUNT(*) FROM clip_snapshots)').fetchone`, `utc_now`, `to_utc_iso`, `_discovery`, `_jobs`, `_observations`, `db.execute('SELECT COUNT(*) FROM operational_errors WHERE occurred_at >= ?', (since,)).fetchone`, `parse_utc`, `max`, `lines.extend`.

Chiamanti per nome. [`main`](../../../src/viralclip/cli.py#L70), [`monitor`](../../../src/viralclip/operations.py#L295).
