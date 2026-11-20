# Riferimento a firme e chiamate

[Indice delle schede](00-GUIDE.md) · [Spiegazione dei moduli](04-OPERATIONS.md)

Indice statico ricavato con AST. I chiamanti e i test sono corrispondenze per simbolo, comprese quelle indirette nei callback definiti dentro un test. Le prove indirette e i percorsi effettivi sono nelle schede narrative. Per nomi condivisi come `main`, `_csv`, `preflight` e `close`, gli omonimi di altri moduli sono omessi dall'elenco per evitare attribuzioni ambigue. Importazioni dinamiche e callback passati senza invocarli possono sfuggire all'indice.

## src/viralclip/deployment.py

[Apri il file](../../../src/viralclip/deployment.py)

Import dichiarati. `import argparse`, `import json`, `import sqlite3`, `from contextlib import closing`, `from hashlib import file_digest`, `from pathlib import Path`, `from viralclip.config import load_settings`, `from viralclip.storage.backup import validate`, `from viralclip.storage.database import MIGRATIONS`.

Costanti. `SCHEMA_VERSION`.

### Classe BackupIdentityError

[`BackupIdentityError`](../../../src/viralclip/deployment.py#L19) (righe 19–20).

### _open_read_only

`_open_read_only(database: Path) -> sqlite3.Connection`

[`Sorgente`](../../../src/viralclip/deployment.py#L23) (righe 23–24).

Chiamate nel corpo. `sqlite3.connect`, `database.resolve().as_uri`, `database.resolve`.

Chiamanti per nome. [`preflight`](../../../src/viralclip/deployment.py#L33), [`snapshot_manifest`](../../../src/viralclip/deployment.py#L83), [`_preflight`](../../../src/viralclip/gta_vi.py#L45).

### _check_schema

`_check_schema(reader: sqlite3.Connection) -> None`

[`Sorgente`](../../../src/viralclip/deployment.py#L27) (righe 27–30).

Chiamate nel corpo. `reader.execute('SELECT version FROM schema_migrations ORDER BY version').fetchall`, `reader.execute`, `ValueError`.

Chiamanti per nome. [`preflight`](../../../src/viralclip/deployment.py#L33), [`snapshot_manifest`](../../../src/viralclip/deployment.py#L83), [`_preflight`](../../../src/viralclip/gta_vi.py#L45).

### preflight

`preflight(database: Path) -> None`

[`Sorgente`](../../../src/viralclip/deployment.py#L33) (righe 33–51).

Chiamate nel corpo. `load_settings`, `database.is_file`, `database.resolve`, `settings.db_path.resolve`, `ValueError`, `closing`, `_open_read_only`, `reader.execute`, `_check_schema`, `reader.execute('PRAGMA journal_mode').fetchone`, `reader.execute('SELECT snapshot_id FROM jobs LIMIT 1').fetchone`.

Chiamanti per nome. [`main`](../../../src/viralclip/deployment.py#L161).

### _check_game_identity

`_check_game_identity(reader: sqlite3.Connection, expected_game_id: str) -> None`

[`Sorgente`](../../../src/viralclip/deployment.py#L54) (righe 54–80).

Chiamate nel corpo. `expected_game_id.strip`, `BackupIdentityError`, `reader.execute('SELECT game_id FROM games LIMIT 2').fetchall`, `reader.execute`, `reader.execute(f'SELECT 1 FROM {table} WHERE game_id IS NOT ? LIMIT 1', (expected_game_id,)).fetchone`, `reader.execute("\n        SELECT EXISTS (SELECT 1 FROM clips) OR EXISTS (\n            SELECT 1 FROM collection_runs WHERE status = 'completed' AND finished_at IS NOT NULL\n            AND potentially_truncated = 0 AND error_summary IS NULL AND pages_seen > 0\n        )\n        ").fetchone`.

Chiamanti per nome. [`snapshot_manifest`](../../../src/viralclip/deployment.py#L83).

### snapshot_manifest

`snapshot_manifest(database: Path, *, expected_game_id: str | None=None) -> dict[str, object]`

[`Sorgente`](../../../src/viralclip/deployment.py#L83) (righe 83–126).

Chiamate nel corpo. `database.resolve`, `any`, `database.with_name(database.name + suffix).exists`, `database.with_name`, `ValueError`, `closing`, `_open_read_only`, `reader.execute`, `reader.execute('PRAGMA journal_mode').fetchone`, `_check_schema`, `_check_game_identity`, `reader.execute("\n            SELECT status, target_age_seconds, COUNT(*), MIN(due_at), MAX(due_at)\n            FROM jobs WHERE status IN ('pending', 'running', 'failed')\n            GROUP BY status, target_age_seconds ORDER BY status, target_age_seconds\n            ").fetchall`, `validate`, `database.open`, `file_digest(stream, 'sha256').hexdigest`, `file_digest`, `database.stat`, `manifest.update`.

Chiamanti per nome. [`verify_snapshot`](../../../src/viralclip/deployment.py#L136), [`main`](../../../src/viralclip/deployment.py#L161), [`run_backup`](../../../src/viralclip/operations.py#L202).

Test che richiamano il simbolo. [`test_synthetic_transfer_preserves_links_pending_jobs_and_real_times`](../../../tests/test_deployment.py#L51), [`test_manifest_rejects_wal_and_verify_rejects_wrong_transfer`](../../../tests/test_deployment.py#L100).

### _unique_manifest_fields

`_unique_manifest_fields(pairs: list[tuple[str, object]]) -> dict[str, object]`

[`Sorgente`](../../../src/viralclip/deployment.py#L129) (righe 129–133).

Chiamate nel corpo. `ValueError`.

### verify_snapshot

`verify_snapshot(database: Path, manifest_path: Path, *, expected_game_id: str | None=None) -> None`

[`Sorgente`](../../../src/viralclip/deployment.py#L136) (righe 136–158).

Chiamate nel corpo. `json.loads`, `manifest_path.read_text`, `isinstance`, `expected.get`, `type`, `ValueError`, `BackupIdentityError`, `snapshot_manifest`, `json.dumps`.

Chiamanti per nome. [`main`](../../../src/viralclip/deployment.py#L161), [`restore_latest`](../../../src/viralclip/operations.py#L254).

Test che richiamano il simbolo. [`test_synthetic_transfer_preserves_links_pending_jobs_and_real_times`](../../../tests/test_deployment.py#L51), [`test_manifest_rejects_wal_and_verify_rejects_wrong_transfer`](../../../tests/test_deployment.py#L100), [`test_verified_backup_and_retention_with_live_wal`](../../../tests/test_operations.py#L34).

### main

`main(argv: list[str] | None=None) -> int`

[`Sorgente`](../../../src/viralclip/deployment.py#L161) (righe 161–188).

Chiamate nel corpo. `argparse.ArgumentParser`, `parser.add_subparsers`, `commands.add_parser`, `command.add_argument`, `parser.parse_args`, `preflight`, `snapshot_manifest`, `json.dumps`, `verify_snapshot`, `parser.exit`.

## src/viralclip/gta_vi.py

[Apri il file](../../../src/viralclip/gta_vi.py)

Import dichiarati. `import argparse`, `import os`, `import sqlite3`, `from contextlib import closing`, `from pathlib import Path`, `from viralclip.cli import main as collector`, `from viralclip.config import load_settings`, `from viralclip.deployment import _check_schema, _open_read_only`, `from viralclip.twitch.client import TwitchAPIError, TwitchClient`.

Costanti. `NAME`, `APPROVED_GAME_ID`, `DB_NAME`.

### _exact_match

`_exact_match(records: list[dict]) -> str`

[`Sorgente`](../../../src/viralclip/gta_vi.py#L23) (righe 23–35).

Chiamate nel corpo. `ValueError`, `record.get`, `isinstance`, `game_id.strip`.

Chiamanti per nome. [`resolve`](../../../src/viralclip/gta_vi.py#L38).

Test che richiamano il simbolo. [`test_resolver_rejects_missing_and_wrong_categories`](../../../tests/test_gta_vi.py#L45).

### resolve

`resolve(client: TwitchClient) -> str`

[`Sorgente`](../../../src/viralclip/gta_vi.py#L38) (righe 38–42).

Chiamate nel corpo. `_exact_match`, `client.get_games`, `ValueError`.

Chiamanti per nome. [`read_source`](../../../src/viralclip/dataset.py#L96), [`ignored_output`](../../../src/viralclip/dataset.py#L347), [`_open_read_only`](../../../src/viralclip/deployment.py#L23), [`preflight`](../../../src/viralclip/deployment.py#L33), [`snapshot_manifest`](../../../src/viralclip/deployment.py#L83), [`_preflight`](../../../src/viralclip/gta_vi.py#L45), [`main`](../../../src/viralclip/gta_vi.py#L90), [`verify_mounts`](../../../src/viralclip/operations.py#L67), [`restore_latest`](../../../src/viralclip/operations.py#L254), [`_reader`](../../../src/viralclip/storage/backup.py#L16), [`Database.acquire_collector_lock`](../../../src/viralclip/storage/database.py#L144), [`read_health`](../../../src/viralclip/storage/health.py#L209), [`preflight`](../../../src/viralclip/windows_supervision.py#L92), [`main`](../../../src/viralclip/windows_supervision.py#L216).

Test che richiamano il simbolo. [`test_health_preflight_reports_both_results_under_errexit`](../../../tests/test_dual_collector_runbook.py#L35), [`test_helix_verifies_exact_name_then_returned_id`](../../../tests/test_gta_vi.py#L17), [`test_unit_has_separate_paths_and_activation_marker`](../../../tests/test_gta_vi.py#L104), [`test_operations_units_do_not_own_or_restart_collector`](../../../tests/test_operations.py#L321), [`test_gta_vi_operations_isolate_paths_and_schedule`](../../../tests/test_operations.py#L373).

### _preflight

`_preflight(state: Path, game_id: str) -> Path`

[`Sorgente`](../../../src/viralclip/gta_vi.py#L45) (righe 45–87).

Chiamate nel corpo. `ValueError`, `load_settings`, `state.absolute`, `state.resolve`, `database.is_symlink`, `database.is_file`, `database.stat`, `sibling.is_symlink`, `sibling.exists`, `sibling.is_file`, `sibling.stat`, `closing`, `_open_read_only`, `reader.execute`, `_check_schema`, `reader.execute('PRAGMA journal_mode').fetchone`, `reader.execute('SELECT 1 FROM games WHERE game_id <> ?', (game_id,)).fetchone`.

Chiamanti per nome. [`main`](../../../src/viralclip/gta_vi.py#L90).

Test che richiamano il simbolo. [`test_pilot_dispatches_only_pinned_game_with_existing_database`](../../../tests/test_gta_vi.py#L71), [`test_preflight_rejects_id_drift_and_donor_alias`](../../../tests/test_gta_vi.py#L85).

### main

`main(argv: list[str] | None=None) -> int`

[`Sorgente`](../../../src/viralclip/gta_vi.py#L90) (righe 90–120).

Chiamate nel corpo. `argparse.ArgumentParser`, `parser.add_subparsers`, `commands.add_parser`, `command.add_argument`, `Path`, `parser.parse_args`, `load_settings`, `ValueError`, `TwitchClient`, `resolve`, `client.close`, `os.environ.get`, `_preflight`, `collector`, `parser.exit`.

## src/viralclip/operations.py

[Apri il file](../../../src/viralclip/operations.py)

Import dichiarati. `import argparse`, `import json`, `import os`, `import re`, `import shutil`, `import sqlite3`, `import subprocess`, `import sys`, `from collections.abc import Callable`, `from contextlib import closing`, `from datetime import UTC, datetime, timedelta`, `from pathlib import Path`, `from tempfile import NamedTemporaryFile, TemporaryDirectory`, `from urllib.parse import urlsplit`, `from urllib.request import HTTPRedirectHandler, Request, build_opener`, `from viralclip.deployment import BackupIdentityError, snapshot_manifest, verify_snapshot`, `from viralclip.storage.backup import backup_and_verify`, `from viralclip.storage.database import parse_utc`, `from viralclip.storage.health import CRITICAL, DEGRADED, LEVELS, read_health`.

Costanti. `DB_NAME`, `MANIFEST`, `COLLECTOR`, `BACKUP`, `TAG`, `HOST`, `STAMP`, `GIB`.

### _atomic_json

`_atomic_json(path: Path, contents: dict) -> None`

[`Sorgente`](../../../src/viralclip/operations.py#L36) (righe 36–48).

Chiamate nel corpo. `NamedTemporaryFile`, `Path`, `json.dump`, `stream.close`, `temp.unlink`, `temp.replace`.

Chiamanti per nome. [`run_backup`](../../../src/viralclip/operations.py#L202).

### reserve_bytes

`reserve_bytes(database_bytes: int, capacity: int) -> int`

[`Sorgente`](../../../src/viralclip/operations.py#L51) (righe 51–53).

Chiamate nel corpo. `max`.

Chiamanti per nome. [`run_backup`](../../../src/viralclip/operations.py#L202), [`monitor`](../../../src/viralclip/operations.py#L295).

Test che richiamano il simbolo. [`test_backup_aborts_before_creating_bundle_if_disk_reserve_not_met`](../../../tests/test_operations.py#L75).

### _file_bytes

`_file_bytes(path: Path) -> int`

[`Sorgente`](../../../src/viralclip/operations.py#L56) (righe 56–60).

Chiamate nel corpo. `path.stat`.

Chiamanti per nome. [`_source_bytes`](../../../src/viralclip/operations.py#L63).

### _source_bytes

`_source_bytes(database: Path) -> int`

[`Sorgente`](../../../src/viralclip/operations.py#L63) (righe 63–64).

Chiamate nel corpo. `database.stat`, `_file_bytes`, `database.with_name`.

Chiamanti per nome. [`run_backup`](../../../src/viralclip/operations.py#L202), [`monitor`](../../../src/viralclip/operations.py#L295).

### verify_mounts

`verify_mounts(database: Path, root: Path, *, writable_backup: bool) -> None`

[`Sorgente`](../../../src/viralclip/operations.py#L67) (righe 67–86).

Chiamate nel corpo. `database.with_name`, `path.exists`, `os.statvfs`, `RuntimeError`, `closing`, `sqlite3.connect`, `database.resolve().as_uri`, `database.resolve`, `db.execute`, `db.execute('PRAGMA journal_mode').fetchone`, `db.execute('SELECT MAX(snapshot_id) FROM clip_snapshots').fetchone`, `NamedTemporaryFile`, `probe.write`, `probe.flush`.

Chiamanti per nome. [`main`](../../../src/viralclip/operations.py#L383).

Test che richiamano il simbolo. [`test_live_wal_mount_probe_and_http_rates`](../../../tests/test_operations.py#L348).

### _http_rates

`_http_rates(database: Path, now: datetime) -> str`

[`Sorgente`](../../../src/viralclip/operations.py#L89) (righe 89–116).

Chiamate nel corpo. `database.with_name`, `timedelta`, `log.with_name(log.name + suffix).open`, `log.with_name`, `json.loads`, `event.get`, `parse_utc`, `isinstance`.

Chiamanti per nome. [`monitor`](../../../src/viralclip/operations.py#L295).

Test che richiamano il simbolo. [`test_live_wal_mount_probe_and_http_rates`](../../../tests/test_operations.py#L348).

### _retention

`_retention(name: str, default: int) -> int`

[`Sorgente`](../../../src/viralclip/operations.py#L119) (righe 119–123).

Chiamate nel corpo. `os.environ.get`, `ValueError`.

Chiamanti per nome. [`run_backup`](../../../src/viralclip/operations.py#L202).

### _https_url

`_https_url(value: str) -> bool`

[`Sorgente`](../../../src/viralclip/operations.py#L126) (righe 126–132).

Chiamate nel corpo. `urlsplit`.

Chiamanti per nome. [`_restic_environment`](../../../src/viralclip/operations.py#L142), [`_heartbeat`](../../../src/viralclip/operations.py#L371).

### _credentials_dir

`_credentials_dir() -> Path`

[`Sorgente`](../../../src/viralclip/operations.py#L135) (righe 135–139).

Chiamate nel corpo. `os.environ.get`, `ValueError`, `Path`.

Chiamanti per nome. [`_restic_environment`](../../../src/viralclip/operations.py#L142), [`_heartbeat`](../../../src/viralclip/operations.py#L371).

### _restic_environment

`_restic_environment() -> dict[str, str]`

[`Sorgente`](../../../src/viralclip/operations.py#L142) (righe 142–166).

Chiamate nel corpo. `os.environ.get`, `repo.startswith`, `_https_url`, `urlsplit(repo[3:]).path.strip`, `urlsplit`, `ValueError`, `_credentials_dir`, `(credentials / filename).read_text(encoding='utf-8').strip`, `(credentials / filename).read_text`, `all`, `values.values`, `password.read_bytes().strip`, `password.read_bytes`.

Chiamanti per nome. [`_restic`](../../../src/viralclip/operations.py#L169).

### _restic

`_restic(args: list[str], *, cwd: Path | None=None) -> None`

[`Sorgente`](../../../src/viralclip/operations.py#L169) (righe 169–180).

Chiamate nel corpo. `subprocess.run`, `_restic_environment`, `RuntimeError`.

Chiamanti per nome. [`main`](../../../src/viralclip/operations.py#L383).

Test che richiamano il simbolo. [`test_restic_passes_isolated_credentials_without_logging_remote_output`](../../../tests/test_operations.py#L273).

### _local_retention

`_local_retention(root: Path, keep: int) -> None`

[`Sorgente`](../../../src/viralclip/operations.py#L183) (righe 183–199).

Chiamate nel corpo. `root.iterdir`, `STAMP.fullmatch`, `item.is_dir`, `item.is_symlink`, `bundle.iterdir`, `all`, `p.is_file`, `p.is_symlink`, `path.unlink`, `bundle.rmdir`.

Chiamanti per nome. [`run_backup`](../../../src/viralclip/operations.py#L202).

### run_backup

`run_backup(database: Path, root: Path, now: datetime, *, expected_game_id: str, restic: Callable[..., None]=_restic) -> None`

[`Sorgente`](../../../src/viralclip/operations.py#L202) (righe 202–251).

Chiamate nel corpo. `expected_game_id.strip`, `BackupIdentityError`, `_retention`, `root.mkdir`, `shutil.disk_usage`, `reserve_bytes`, `_source_bytes`, `RuntimeError`, `now.astimezone(UTC).strftime`, `now.astimezone`, `bundle.exists`, `ValueError`, `TemporaryDirectory`, `Path`, `staged.mkdir`, `backup_and_verify`, `snapshot_manifest`, `_atomic_json`, `staged.rename`, `now.astimezone(UTC).isoformat`, `restic`, `_local_retention`.

Chiamanti per nome. [`main`](../../../src/viralclip/operations.py#L383).

Test che richiamano il simbolo. [`test_verified_backup_and_retention_with_live_wal`](../../../tests/test_operations.py#L34), [`test_remote_failure_preserves_verified_local_backup_and_previous_marker`](../../../tests/test_operations.py#L58), [`test_backup_aborts_before_creating_bundle_if_disk_reserve_not_met`](../../../tests/test_operations.py#L75), [`test_restore_drill_calls_real_sqlite_verifier`](../../../tests/test_operations.py#L90), [`test_backup_rejects_wrong_game_before_publish`](../../../tests/test_operations.py#L110), [`test_monitor_combines_state_disk_and_backup_freshness`](../../../tests/test_operations.py#L234).

### restore_latest

`restore_latest(output: Path, *, expected_game_id: str, restic: Callable[..., None]=_restic) -> None`

[`Sorgente`](../../../src/viralclip/operations.py#L254) (righe 254–269).

Chiamate nel corpo. `expected_game_id.strip`, `BackupIdentityError`, `output.mkdir`, `restic`, `output.resolve`, `output.rglob`, `ValueError`, `manifests[0].with_name`, `verify_snapshot`, `backup_and_verify`.

Chiamanti per nome. [`main`](../../../src/viralclip/operations.py#L383).

Test che richiamano il simbolo. [`test_restore_drill_calls_real_sqlite_verifier`](../../../tests/test_operations.py#L90), [`test_restore_rejects_untrusted_database_identity`](../../../tests/test_operations.py#L161), [`test_restore_rejects_bad_metadata`](../../../tests/test_operations.py#L187), [`test_restore_checks_database_even_when_manifest_claims_expected_game`](../../../tests/test_operations.py#L202), [`test_restore_requires_independent_expected_game_id`](../../../tests/test_operations.py#L214), [`test_restore_accepts_legacy_empty_discovery_for_expected_game`](../../../tests/test_operations.py#L227).

### _service_state

`_service_state(name: str) -> dict[str, str]`

[`Sorgente`](../../../src/viralclip/operations.py#L272) (righe 272–292).

Chiamate nel corpo. `subprocess.run`, `line.split`, `result.stdout.splitlines`.

### monitor

`monitor(database: Path, root: Path, now: datetime, *, collector_unit: str=COLLECTOR, backup_unit: str=BACKUP, service: Callable[[str], dict[str, str]]=_service_state) -> tuple[int, list[str]]`

[`Sorgente`](../../../src/viralclip/operations.py#L295) (righe 295–363).

Chiamate nel corpo. `read_health`, `_http_rates`, `service`, `collector.get`, `backup.get`, `max`, `shutil.disk_usage`, `_source_bytes`, `reserve_bytes`, `json.loads`, `(root / f'latest-{kind}.json').read_text`, `parse_utc`, `timedelta`, `STAMP.fullmatch`, `ValueError`, `all`, `(root / name / filename).is_file`.

Chiamanti per nome. [`main`](../../../src/viralclip/operations.py#L383).

### Classe _NoRedirect

[`_NoRedirect`](../../../src/viralclip/operations.py#L366) (righe 366–368).

### _NoRedirect.redirect_request

`_NoRedirect.redirect_request(self, req, fp, code, msg, headers, newurl)`

[`Sorgente`](../../../src/viralclip/operations.py#L367) (righe 367–368).

### _heartbeat

`_heartbeat(severity: int) -> None`

[`Sorgente`](../../../src/viralclip/operations.py#L371) (righe 371–380).

Chiamate nel corpo. `(_credentials_dir() / 'alert-url').read_text(encoding='utf-8').strip`, `(_credentials_dir() / 'alert-url').read_text`, `_credentials_dir`, `_https_url`, `ValueError`, `url.rstrip`, `Request`, `LEVELS[severity].encode`, `build_opener(_NoRedirect()).open`, `build_opener`, `_NoRedirect`.

Chiamanti per nome. [`main`](../../../src/viralclip/operations.py#L383).

Test che richiamano il simbolo. [`test_heartbeat_only_sends_severity`](../../../tests/test_operations.py#L296).

### main

`main(argv: list[str] | None=None) -> int`

[`Sorgente`](../../../src/viralclip/operations.py#L383) (righe 383–444).

Chiamate nel corpo. `argparse.ArgumentParser`, `parser.add_subparsers`, `commands.add_parser`, `options.add_argument`, `restore.add_argument`, `parser.parse_args`, `run_backup`, `datetime.now`, `verify_mounts`, `monitor`, `'\n'.join`, `_heartbeat`, `_restic`, `restore_latest`, `type`.

## src/viralclip/windows_supervision.py

[Apri il file](../../../src/viralclip/windows_supervision.py)

Import dichiarati. `import argparse`, `import json`, `import logging`, `import re`, `import sqlite3`, `import subprocess`, `import sys`, `from _thread import interrupt_main`, `from collections.abc import Callable`, `from contextlib import closing`, `from datetime import UTC, datetime`, `from logging.handlers import RotatingFileHandler`, `from pathlib import Path`, `from threading import Event, Thread`, `from xml.etree.ElementTree import Element, SubElement, indent, tostring`, `from viralclip.config import load_settings`, `from viralclip.dataset import ignored_output`, `from viralclip.storage.database import MIGRATIONS`, `from viralclip.cli import main as collector_main`.

Costanti. `SCHEMA_VERSION`, `TASK_NAMESPACE`, `DEFAULT_GAME`.

### control_directory

`control_directory(db_path: Path) -> Path`

[`Sorgente`](../../../src/viralclip/windows_supervision.py#L30) (righe 30–31).

Chiamate nel corpo. `db_path.with_name`.

Chiamanti per nome. [`_run`](../../../src/viralclip/windows_supervision.py#L181), [`main`](../../../src/viralclip/windows_supervision.py#L216).

Test che richiamano il simbolo. [`test_pause_survives_attempts_resume_never_launches`](../../../tests/test_windows_supervision.py#L97), [`test_runner_checks_before_dispatch_and_records_failure`](../../../tests/test_windows_supervision.py#L182).

### task_xml

`task_xml(python: Path, root: Path, db_path: Path, sid: str, game: str, interval: int, lookback: int) -> bytes`

[`Sorgente`](../../../src/viralclip/windows_supervision.py#L34) (righe 34–89).

Chiamate nel corpo. `re.fullmatch`, `ValueError`, `game.strip`, `min`, `Element`, `SubElement`, `subprocess.list2cmdline`, `indent`, `tostring`.

Chiamanti per nome. [`main`](../../../src/viralclip/windows_supervision.py#L216).

Test che richiamano il simbolo. [`test_disabled_task_xml_configures_boot_restarts_and_single_instance`](../../../tests/test_windows_supervision.py#L22).

### preflight

`preflight(db_path: Path, interval: int, lookback: int) -> None`

[`Sorgente`](../../../src/viralclip/windows_supervision.py#L92) (righe 92–113).

Chiamate nel corpo. `load_settings`, `settings.db_path.resolve`, `ValueError`, `db_path.is_file`, `closing`, `sqlite3.connect`, `db_path.as_uri`, `db.execute`, `db.execute('SELECT version FROM schema_migrations ORDER BY version').fetchall`, `range`, `db.execute('PRAGMA journal_mode').fetchone`.

Chiamanti per nome. [`_run.start`](../../../src/viralclip/windows_supervision.py#L205), [`main`](../../../src/viralclip/windows_supervision.py#L216).

### is_paused

`is_paused(marker: Path) -> bool`

[`Sorgente`](../../../src/viralclip/windows_supervision.py#L116) (righe 116–121).

Chiamate nel corpo. `marker.stat`.

Chiamanti per nome. [`supervise`](../../../src/viralclip/windows_supervision.py#L124), [`supervise.monitor`](../../../src/viralclip/windows_supervision.py#L140), [`main`](../../../src/viralclip/windows_supervision.py#L216).

### supervise

`supervise(marker: Path, start: Callable[[], int], record: Callable[..., None], *, poll_seconds: float=1) -> int`

[`Sorgente`](../../../src/viralclip/windows_supervision.py#L124) (righe 124–178).

Chiamate nel corpo. `is_paused`, `record`, `Event`, `Thread`, `watcher.start`, `start`, `finished.set`, `watcher.join`, `type`, `monitor_failed.is_set`, `pause_seen.is_set`.

Chiamanti per nome. [`_run`](../../../src/viralclip/windows_supervision.py#L181).

Test che richiamano il simbolo. [`test_pause_survives_attempts_resume_never_launches`](../../../tests/test_windows_supervision.py#L97), [`test_unexpected_exits_preserve_scheduler_failure`](../../../tests/test_windows_supervision.py#L123), [`test_crash_is_reported_without_exception_message`](../../../tests/test_windows_supervision.py#L136).

### supervise.monitor

`supervise.monitor() -> None`

[`Sorgente`](../../../src/viralclip/windows_supervision.py#L140) (righe 140–151).

Chiamate nel corpo. `finished.wait`, `is_paused`, `monitor_failed.set`, `interrupt_main`, `pause_seen.set`.

### _run

`_run(db_path: Path, game: str, interval: int, lookback: int) -> int`

[`Sorgente`](../../../src/viralclip/windows_supervision.py#L181) (righe 181–213).

Chiamate nel corpo. `ValueError`, `control_directory`, `directory.mkdir`, `closing`, `RotatingFileHandler`, `supervise`.

Chiamanti per nome. [`main`](../../../src/viralclip/windows_supervision.py#L216).

### _run.record

`_run.record(event: str, **fields: object) -> None`

[`Sorgente`](../../../src/viralclip/windows_supervision.py#L197) (righe 197–203).

Chiamate nel corpo. `json.dumps`, `datetime.now(UTC).isoformat`, `datetime.now`, `handler.handle`, `logging.LogRecord`.

Chiamanti per nome. [`supervise`](../../../src/viralclip/windows_supervision.py#L124), [`_run.start`](../../../src/viralclip/windows_supervision.py#L205).

### _run.start

`_run.start() -> int`

[`Sorgente`](../../../src/viralclip/windows_supervision.py#L205) (righe 205–211).

Chiamate nel corpo. `preflight`, `record`, `collector_main`.

Chiamanti per nome. [`supervise`](../../../src/viralclip/windows_supervision.py#L124).

### main

`main(argv: list[str] | None=None) -> int`

[`Sorgente`](../../../src/viralclip/windows_supervision.py#L216) (righe 216–271).

Chiamate nel corpo. `argparse.ArgumentParser`, `parser.add_argument`, `parser.add_subparsers`, `commands.add_parser`, `options.add_argument`, `parser.parse_args`, `args.db.resolve`, `str(db_path).startswith`, `ValueError`, `control_directory`, `task_xml`, `Path`, `Path.cwd`, `ignored_output`, `output.mkdir`, `(output / 'collector.xml').open`, `stream.write`, `preflight`, `_run`, `directory.mkdir`, `marker.touch`, `marker.unlink`, `is_paused`.

Chiamanti per nome. [`_run.start`](../../../src/viralclip/windows_supervision.py#L205).
