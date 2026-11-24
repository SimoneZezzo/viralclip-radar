# Riferimento a firme e chiamate

[Indice delle schede](00-GUIDE.md) · [Spiegazione dei moduli](01-COLLECTION.md)

Indice statico ricavato con AST. I chiamanti e i test sono corrispondenze per simbolo, comprese quelle indirette nei callback definiti dentro un test. Le prove indirette e i percorsi effettivi sono nelle schede narrative. Per nomi condivisi come `main`, `_csv`, `preflight` e `close`, gli omonimi di altri moduli sono omessi dall'elenco per evitare attribuzioni ambigue. Importazioni dinamiche e callback passati senza invocarli possono sfuggire all'indice.

## src/viralclip/__init__.py

[Apri il file](../../../src/viralclip/__init__.py)

Import dichiarati. nessuno.

Il modulo non dichiara funzioni o classi.

## src/viralclip/__main__.py

[Apri il file](../../../src/viralclip/__main__.py)

Import dichiarati. `from viralclip.cli import main`.

Il modulo non dichiara funzioni o classi.

## src/viralclip/cli.py

[Apri il file](../../../src/viralclip/cli.py)

Import dichiarati. `import argparse`, `import sqlite3`, `import sys`, `import time`, `from pathlib import Path`, `from viralclip.collector.service import Collector`, `from viralclip.config import load_settings`, `from viralclip.dataset import CUTOFFS, Selection, extract`, `from viralclip.evaluation import run_evaluation`, `from viralclip.storage.database import Database, parse_utc, utc_now`, `from viralclip.storage.health import LEVELS, read_health`, `from viralclip.twitch.client import TwitchAPIError, TwitchClient`, `from viralclip.twitch.telemetry import HttpEventLog`.

### _parser

`_parser() -> argparse.ArgumentParser`

[`Sorgente`](../../../src/viralclip/cli.py#L24) (righe 24–63).

Chiamate nel corpo. `argparse.ArgumentParser`, `parser.add_argument`, `parser.add_subparsers`, `commands.add_parser`, `collect.add_argument`, `collect.add_mutually_exclusive_group`, `mode.add_argument`, `dataset.add_argument`, `evaluation.add_argument`.

Chiamanti per nome. [`main`](../../../src/viralclip/cli.py#L79).

### _print_status

`_print_status(database: Database) -> None`

[`Sorgente`](../../../src/viralclip/cli.py#L66) (righe 66–75).

Chiamate nel corpo. `database.status`, `utc_now`, `status['jobs'].get`.

Chiamanti per nome. [`main`](../../../src/viralclip/cli.py#L79).

### main

`main(argv: list[str] | None=None) -> int`

[`Sorgente`](../../../src/viralclip/cli.py#L79) (righe 79–204).

Chiamate nel corpo. `_parser().parse_args`, `_parser`, `run_evaluation`, `parse_utc`, `load_settings`, `settings.__class__`, `settings.db_path.__class__(args.db).expanduser`, `settings.db_path.__class__`, `read_health`, `'\n'.join`, `Selection`, `extract`, `Database`, `_print_status`, `HttpEventLog`, `TwitchClient`, `Collector`, `collector.collect_cycle`, `time.monotonic`, `collector.collect_due_snapshots`, `database.record_error`, `utc_now`, `time.sleep`, `min`, `twitch.close`, `http_log.close`, `isinstance`, `database.close`.

## src/viralclip/collector/__init__.py

[Apri il file](../../../src/viralclip/collector/__init__.py)

Import dichiarati. nessuno.

Il modulo non dichiara funzioni o classi.

## src/viralclip/collector/service.py

[Apri il file](../../../src/viralclip/collector/service.py)

Import dichiarati. `from collections.abc import Callable`, `from datetime import UTC, datetime, timedelta`, `from viralclip.storage.database import Database, utc_now`, `from viralclip.twitch.client import TwitchAPIError, TwitchClient`.

### Classe Collector

[`Collector`](../../../src/viralclip/collector/service.py#L10) (righe 10–229).

### Collector.__init__

`Collector.__init__(self, database: Database, twitch: TwitchClient, *, lookback_minutes: int=30, clock: Callable[[], datetime]=utc_now)`

[`Sorgente`](../../../src/viralclip/collector/service.py#L11) (righe 11–24).

Chiamate nel corpo. `self.database.acquire_collector_lock`, `self.database.recover_running_jobs`.

### Collector.resolve_game

`Collector.resolve_game(self, name: str) -> str`

[`Sorgente`](../../../src/viralclip/collector/service.py#L26) (righe 26–40).

Chiamate nel corpo. `self.clock`, `self.database.cached_game`, `self.twitch.search_categories`, `next`, `item.get('name', '').casefold`, `item.get`, `name.casefold`, `TwitchAPIError`, `self.database.upsert_game`.

Chiamanti per nome. [`Collector.collect_cycle`](../../../src/viralclip/collector/service.py#L209).

Test che richiamano il simbolo. [`test_search_exact_category_on_second_page`](../../../tests/test_audit.py#L259), [`test_game_lookup_exact_match_and_missing_category`](../../../tests/test_collector.py#L48).

### Collector._whole_minute_window

`Collector._whole_minute_window(self, game_id: str, now: datetime) -> tuple[datetime, datetime]`

[`Sorgente`](../../../src/viralclip/collector/service.py#L42) (righe 42–51).

Chiamate nel corpo. `now.astimezone(UTC).replace`, `now.astimezone`, `timedelta`, `self.database.connection.execute('SELECT watermark FROM discovery_checkpoints WHERE game_id = ?', (game_id,)).fetchone`, `self.database.connection.execute`, `datetime.fromisoformat`, `min`.

Chiamanti per nome. [`Collector.discover`](../../../src/viralclip/collector/service.py#L53).

### Collector.discover

`Collector.discover(self, game_id: str) -> int`

[`Sorgente`](../../../src/viralclip/collector/service.py#L53) (righe 53–62).

Chiamate nel corpo. `self._whole_minute_window`, `self.clock`, `self.database.connection.execute('SELECT 1 FROM discovery_checkpoints WHERE game_id = ?', (game_id,)).fetchone`, `self.database.connection.execute`, `self.database.update_watermark`, `timedelta`, `self._discover_window`.

Chiamanti per nome. [`Collector.collect_cycle`](../../../src/viralclip/collector/service.py#L209).

Test che richiamano il simbolo. [`test_page_survives_later_failure_and_checkpoint_does_not_advance`](../../../tests/test_audit.py#L32), [`test_saturation_without_cursor_is_flagged_and_children_cannot_skip_gap`](../../../tests/test_audit.py#L51), [`test_successful_clip_pagination_uses_cursor_and_actual_page_times`](../../../tests/test_audit.py#L338), [`test_overlapping_discovery_preserves_first_seen_and_appends_snapshots`](../../../tests/test_collector.py#L103), [`test_discovery_uses_persisted_watermark_after_a_long_gap`](../../../tests/test_collector.py#L329).

### Collector._discover_window

`Collector._discover_window(self, game_id: str, start: datetime, end: datetime, budget: list[int]) -> tuple[int, bool]`

[`Sorgente`](../../../src/viralclip/collector/service.py#L64) (righe 64–136).

Chiamate nel corpo. `self.database.create_run`, `self.clock`, `self.collect_due_snapshots`, `self.twitch.get_clips`, `self.twitch.parse_data`, `self._parse_clip`, `unique_ids.add`, `self.database.record_clip`, `self.twitch.parse_cursor`, `self.database.finish_run`, `(end - start).total_seconds`, `midpoint.replace`, `self._discover_window`.

Chiamanti per nome. [`Collector.discover`](../../../src/viralclip/collector/service.py#L53).

### Collector._parse_clip

`Collector._parse_clip(raw: dict) -> dict`

[`Sorgente`](../../../src/viralclip/collector/service.py#L139) (righe 139–161).

Chiamate nel corpo. `isinstance`, `raw.get`, `ValueError`, `type`, `datetime.fromisoformat`, `created_at.utcoffset`, `created_at.astimezone`, `TwitchAPIError`.

Chiamanti per nome. [`Collector._discover_window`](../../../src/viralclip/collector/service.py#L64), [`Collector.collect_due_snapshots`](../../../src/viralclip/collector/service.py#L163).

Test che richiamano il simbolo. [`test_malformed_refresh_is_failed_not_unavailable`](../../../tests/test_audit.py#L71), [`test_snapshot_and_completion_roll_back_together`](../../../tests/test_audit.py#L82), [`test_invalid_counts_are_not_measurements`](../../../tests/test_audit.py#L233), [`test_failed_jobs_have_delay_and_bounded_attempts`](../../../tests/test_audit.py#L238), [`test_impossible_age_rejected_without_any_rows`](../../../tests/test_audit.py#L363), [`test_online_backup_and_restore_see_committed_wal_only`](../../../tests/test_backup.py#L12), [`test_validation_rejects_incorrect_completed_job_link`](../../../tests/test_backup.py#L45), [`test_late_discovery_marks_old_targets_missed_without_backdating`](../../../tests/test_collector.py#L141), [`test_due_snapshot_batches_under_one_hundred_and_handles_unordered_results`](../../../tests/test_collector.py#L164), [`test_unavailable_clip_is_not_recorded_as_zero`](../../../tests/test_collector.py#L300), [`test_restart_recovers_running_jobs_without_duplicates`](../../../tests/test_collector.py#L348), [`test_snapshots_cannot_be_updated_or_deleted`](../../../tests/test_collector.py#L369), [`test_synthetic_transfer_preserves_links_pending_jobs_and_real_times`](../../../tests/test_deployment.py#L51).

### Collector.collect_due_snapshots

`Collector.collect_due_snapshots(self) -> int`

[`Sorgente`](../../../src/viralclip/collector/service.py#L163) (righe 163–207).

Chiamate nel corpo. `self.database.due_jobs`, `self.clock`, `grouped.setdefault`, `range`, `self.database.start_jobs`, `self.twitch.get_clips`, `self.twitch.parse_data`, `any`, `isinstance`, `item.get`, `TwitchAPIError`, `self.database.finish_jobs`, `results.get`, `self._parse_clip`, `self.database.add_scheduled_snapshot`.

Chiamanti per nome. [`main`](../../../src/viralclip/cli.py#L79), [`Collector._discover_window`](../../../src/viralclip/collector/service.py#L64), [`Collector.collect_cycle`](../../../src/viralclip/collector/service.py#L209).

Test che richiamano il simbolo. [`test_malformed_refresh_is_failed_not_unavailable`](../../../tests/test_audit.py#L71), [`test_full_http_flow_restart_and_delayed_snapshot`](../../../tests/test_audit.py#L100), [`test_failed_jobs_have_delay_and_bounded_attempts`](../../../tests/test_audit.py#L238), [`test_due_snapshot_batches_under_one_hundred_and_handles_unordered_results`](../../../tests/test_collector.py#L164), [`test_unavailable_clip_is_not_recorded_as_zero`](../../../tests/test_collector.py#L300).

### Collector.collect_cycle

`Collector.collect_cycle(self, games: tuple[str, ...], game_ids: tuple[str, ...]=()) -> None`

[`Sorgente`](../../../src/viralclip/collector/service.py#L209) (righe 209–229).

Chiamate nel corpo. `self.collect_due_snapshots`, `self.discover`, `self.resolve_game`, `self.database.record_error`, `self.clock`, `self.database.connection.execute('SELECT 1 FROM games WHERE game_id = ?', (game_id,)).fetchone`, `self.database.connection.execute`, `self.database.upsert_game`, `TwitchAPIError`.

Chiamanti per nome. [`main`](../../../src/viralclip/cli.py#L79).

Test che richiamano il simbolo. [`test_full_http_flow_restart_and_delayed_snapshot`](../../../tests/test_audit.py#L100), [`test_bad_category_does_not_starve_other_categories`](../../../tests/test_audit.py#L329).

## src/viralclip/config.py

[Apri il file](../../../src/viralclip/config.py)

Import dichiarati. `import os`, `from dataclasses import dataclass`, `from pathlib import Path`, `from dotenv import load_dotenv`.

### Classe Settings

[`Settings`](../../../src/viralclip/config.py#L11) (righe 11–23).

Campi dichiarati. `client_id: str | None`, `client_secret: str | None`, `db_path: Path`, `discovery_interval_seconds: int`, `discovery_lookback_minutes: int`, `games: tuple[str, ...]`, `game_ids: tuple[str, ...]`, `http_log_directory: str | None`.

### Settings.has_twitch_credentials

`Settings.has_twitch_credentials(self) -> bool`

[`Sorgente`](../../../src/viralclip/config.py#L22) (righe 22–23).

### _positive_int

`_positive_int(name: str, default: int) -> int`

[`Sorgente`](../../../src/viralclip/config.py#L26) (righe 26–36).

Chiamate nel corpo. `os.getenv`, `raw.strip`, `ValueError`.

Chiamanti per nome. [`load_settings`](../../../src/viralclip/config.py#L43).

### _csv_values

`_csv_values(name: str) -> tuple[str, ...]`

[`Sorgente`](../../../src/viralclip/config.py#L39) (righe 39–40).

Chiamate nel corpo. `value.strip`, `os.getenv(name, '').split`, `os.getenv`.

Chiamanti per nome. [`load_settings`](../../../src/viralclip/config.py#L43).

### load_settings

`load_settings() -> Settings`

[`Sorgente`](../../../src/viralclip/config.py#L43) (righe 43–54).

Chiamate nel corpo. `load_dotenv`, `Settings`, `os.getenv`, `Path(os.getenv('VIRALCLIP_DB_PATH', 'data/viralclip.sqlite3')).expanduser`, `Path`, `_positive_int`, `_csv_values`.

Chiamanti per nome. [`main`](../../../src/viralclip/cli.py#L79), [`preflight`](../../../src/viralclip/deployment.py#L33), [`_preflight`](../../../src/viralclip/gta_vi.py#L45), [`main`](../../../src/viralclip/gta_vi.py#L90), [`main`](../../../src/viralclip/storage/backup.py#L125), [`preflight`](../../../src/viralclip/windows_supervision.py#L92).

Test che richiamano il simbolo. [`test_credentials_loaded_from_environment`](../../../tests/test_collector.py#L68).

## src/viralclip/twitch/__init__.py

[Apri il file](../../../src/viralclip/twitch/__init__.py)

Import dichiarati. nessuno.

Il modulo non dichiara funzioni o classi.

## src/viralclip/twitch/client.py

[Apri il file](../../../src/viralclip/twitch/client.py)

Import dichiarati. `import random`, `import time`, `from collections.abc import Callable`, `from datetime import UTC, datetime`, `from email.utils import parsedate_to_datetime`, `from math import isfinite`, `import httpx`.

### Classe TwitchAPIError

[`TwitchAPIError`](../../../src/viralclip/twitch/client.py#L13) (righe 13–14).

### Classe TwitchClient

[`TwitchClient`](../../../src/viralclip/twitch/client.py#L17) (righe 17–401).

### TwitchClient.__init__

`TwitchClient.__init__(self, client_id: str, client_secret: str, *, http: httpx.Client | None=None, sleep: Callable[[float], None]=time.sleep, jitter: Callable[[float, float], float]=random.uniform, wall_clock: Callable[[], float]=time.time, max_retries: int=3, events: Callable[[dict[str, object]], None] | None=None)`

[`Sorgente`](../../../src/viralclip/twitch/client.py#L21) (righe 21–48).

Chiamate nel corpo. `httpx.Client`, `httpx.Timeout`.

### TwitchClient.close

`TwitchClient.close(self) -> None`

[`Sorgente`](../../../src/viralclip/twitch/client.py#L50) (righe 50–52).

Chiamate nel corpo. `self.http.close`.

### TwitchClient._event

`TwitchClient._event(self, event: str, endpoint: str, **fields: object) -> None`

[`Sorgente`](../../../src/viralclip/twitch/client.py#L54) (righe 54–60).

Chiamate nel corpo. `self._events`.

Chiamanti per nome. [`TwitchClient._request`](../../../src/viralclip/twitch/client.py#L66), [`TwitchClient._wait_for_retry`](../../../src/viralclip/twitch/client.py#L117), [`TwitchClient._get_token`](../../../src/viralclip/twitch/client.py#L132), [`TwitchClient._get`](../../../src/viralclip/twitch/client.py#L254).

### TwitchClient._network_reason

`TwitchClient._network_reason(error: httpx.RequestError) -> str`

[`Sorgente`](../../../src/viralclip/twitch/client.py#L63) (righe 63–64).

Chiamate nel corpo. `isinstance`.

Chiamanti per nome. [`TwitchClient._request`](../../../src/viralclip/twitch/client.py#L66), [`TwitchClient._request_token`](../../../src/viralclip/twitch/client.py#L145), [`TwitchClient._validate_token`](../../../src/viralclip/twitch/client.py#L195), [`TwitchClient._get`](../../../src/viralclip/twitch/client.py#L254).

### TwitchClient._request

`TwitchClient._request(self, endpoint: str, attempt: int, send: Callable[..., httpx.Response], url: str, **kwargs: object) -> httpx.Response`

[`Sorgente`](../../../src/viralclip/twitch/client.py#L66) (righe 66–115).

Chiamate nel corpo. `send`, `time.perf_counter`, `self._event`, `round`, `self._network_reason`, `response.headers.get`, `value.isascii`, `value.isdecimal`.

Chiamanti per nome. [`TwitchClient._request_token`](../../../src/viralclip/twitch/client.py#L145), [`TwitchClient._validate_token`](../../../src/viralclip/twitch/client.py#L195), [`TwitchClient._get`](../../../src/viralclip/twitch/client.py#L254).

### TwitchClient._wait_for_retry

`TwitchClient._wait_for_retry(self, endpoint: str, next_attempt: int, backoff_attempt: int, reason: str, response: httpx.Response | None=None) -> None`

[`Sorgente`](../../../src/viralclip/twitch/client.py#L117) (righe 117–130).

Chiamate nel corpo. `self._retry_delay`, `isfinite`, `self._event`, `self.sleep`.

Chiamanti per nome. [`TwitchClient._request_token`](../../../src/viralclip/twitch/client.py#L145), [`TwitchClient._validate_token`](../../../src/viralclip/twitch/client.py#L195), [`TwitchClient._get`](../../../src/viralclip/twitch/client.py#L254).

### TwitchClient._get_token

`TwitchClient._get_token(self, force: bool=False) -> str`

[`Sorgente`](../../../src/viralclip/twitch/client.py#L132) (righe 132–143).

Chiamate nel corpo. `self.wall_clock`, `self._event`, `self._request_token`.

Chiamanti per nome. [`TwitchClient._get`](../../../src/viralclip/twitch/client.py#L254).

### TwitchClient._request_token

`TwitchClient._request_token(self) -> str`

[`Sorgente`](../../../src/viralclip/twitch/client.py#L145) (righe 145–193).

Chiamate nel corpo. `range`, `self._request`, `TwitchAPIError`, `self._wait_for_retry`, `self._network_reason`, `response.json`, `isinstance`, `type`, `self.wall_clock`.

Chiamanti per nome. [`TwitchClient._get_token`](../../../src/viralclip/twitch/client.py#L132).

### TwitchClient._validate_token

`TwitchClient._validate_token(self, token: str) -> None`

[`Sorgente`](../../../src/viralclip/twitch/client.py#L195) (righe 195–229).

Chiamate nel corpo. `self.wall_clock`, `range`, `self._request`, `TwitchAPIError`, `self._wait_for_retry`, `self._network_reason`, `response.json`.

Chiamanti per nome. [`TwitchClient._get`](../../../src/viralclip/twitch/client.py#L254).

### TwitchClient._retry_delay

`TwitchClient._retry_delay(self, response: httpx.Response | None, attempt: int) -> float`

[`Sorgente`](../../../src/viralclip/twitch/client.py#L231) (righe 231–252).

Chiamate nel corpo. `response.headers.get`, `min`, `self.jitter`, `parsedate_to_datetime(retry_after).timestamp`, `parsedate_to_datetime`, `self.wall_clock`, `max`.

Chiamanti per nome. [`TwitchClient._wait_for_retry`](../../../src/viralclip/twitch/client.py#L117).

Test che richiamano il simbolo. [`test_rate_limit_respects_later_header_and_never_zero_delay`](../../../tests/test_audit.py#L214).

### TwitchClient._get

`TwitchClient._get(self, path: str, params: dict | list[tuple[str, str]], *, endpoint: str) -> dict`

[`Sorgente`](../../../src/viralclip/twitch/client.py#L254) (righe 254–313).

Chiamate nel corpo. `self._get_token`, `self._validate_token`, `max`, `self.wall_clock`, `isfinite`, `self._event`, `self.sleep`, `self._request`, `TwitchAPIError`, `self._wait_for_retry`, `self._network_reason`, `response.headers.get`, `response.json`, `isinstance`.

Chiamanti per nome. [`TwitchClient.get_games`](../../../src/viralclip/twitch/client.py#L315), [`TwitchClient.search_categories`](../../../src/viralclip/twitch/client.py#L321), [`TwitchClient.get_clips`](../../../src/viralclip/twitch/client.py#L362).

### TwitchClient.get_games

`TwitchClient.get_games(self, *, name: str | None=None, game_id: str | None=None) -> list[dict]`

[`Sorgente`](../../../src/viralclip/twitch/client.py#L315) (righe 315–319).

Chiamate nel corpo. `ValueError`, `self.parse_data`, `self._get`.

Chiamanti per nome. [`resolve`](../../../src/viralclip/gta_vi.py#L38).

### TwitchClient.search_categories

`TwitchClient.search_categories(self, name: str) -> list[dict]`

[`Sorgente`](../../../src/viralclip/twitch/client.py#L321) (righe 321–343).

Chiamate nel corpo. `range`, `self._get`, `self.parse_data`, `any`, `isinstance`, `item.get`, `TwitchAPIError`, `categories.extend`, `item['name'].casefold`, `name.casefold`, `self.parse_cursor`.

Chiamanti per nome. [`Collector.resolve_game`](../../../src/viralclip/collector/service.py#L26).

### TwitchClient.parse_data

`TwitchClient.parse_data(payload: dict) -> list[dict]`

[`Sorgente`](../../../src/viralclip/twitch/client.py#L346) (righe 346–350).

Chiamate nel corpo. `payload.get`, `isinstance`, `any`, `TwitchAPIError`.

Chiamanti per nome. [`Collector._discover_window`](../../../src/viralclip/collector/service.py#L64), [`Collector.collect_due_snapshots`](../../../src/viralclip/collector/service.py#L163), [`TwitchClient.get_games`](../../../src/viralclip/twitch/client.py#L315), [`TwitchClient.search_categories`](../../../src/viralclip/twitch/client.py#L321).

### TwitchClient.parse_cursor

`TwitchClient.parse_cursor(payload: dict) -> str | None`

[`Sorgente`](../../../src/viralclip/twitch/client.py#L353) (righe 353–360).

Chiamate nel corpo. `payload.get`, `isinstance`, `TwitchAPIError`, `pagination.get`.

Chiamanti per nome. [`Collector._discover_window`](../../../src/viralclip/collector/service.py#L64), [`TwitchClient.search_categories`](../../../src/viralclip/twitch/client.py#L321).

### TwitchClient.get_clips

`TwitchClient.get_clips(self, *, game_id: str | None=None, clip_ids: list[str] | None=None, started_at: datetime | None=None, ended_at: datetime | None=None, after: str | None=None) -> dict`

[`Sorgente`](../../../src/viralclip/twitch/client.py#L362) (righe 362–401).

Chiamate nel corpo. `ValueError`, `params.extend`, `started_at.utcoffset`, `started_at.astimezone(UTC).isoformat().replace`, `started_at.astimezone(UTC).isoformat`, `started_at.astimezone`, `ended_at.utcoffset`, `ended_at.astimezone(UTC).isoformat().replace`, `ended_at.astimezone(UTC).isoformat`, `ended_at.astimezone`, `self._get`.

Chiamanti per nome. [`Collector._discover_window`](../../../src/viralclip/collector/service.py#L64), [`Collector.collect_due_snapshots`](../../../src/viralclip/collector/service.py#L163).

Test che richiamano il simbolo. [`test_invalid_oauth_response_is_safe`](../../../tests/test_audit.py#L183), [`test_token_validation_hourly_and_token_expiry`](../../../tests/test_audit.py#L190), [`test_repeated_401_is_bounded`](../../../tests/test_audit.py#L272), [`test_network_retry_is_bounded`](../../../tests/test_audit.py#L281), [`test_invalid_selectors_rejected_without_http`](../../../tests/test_audit.py#L375), [`test_401_refreshes_token_once_and_retries_request`](../../../tests/test_collector.py#L80), [`test_429_waits_for_retry_after_and_retries`](../../../tests/test_collector.py#L206), [`test_5xx_retries_with_bounded_backoff`](../../../tests/test_collector.py#L226), [`test_oauth_5xx_retries_without_exposing_credentials`](../../../tests/test_collector.py#L246), [`test_rate_limit_remaining_defers_next_request_until_reset`](../../../tests/test_collector.py#L266), [`test_http_retry_sequence_rate_pressure_and_secret_exclusion`](../../../tests/test_http_telemetry.py#L14), [`test_oauth_refresh_after_401_and_invalid_response`](../../../tests/test_http_telemetry.py#L113), [`test_logging_failures_preserve_requests_and_retries`](../../../tests/test_http_telemetry.py#L150).

## src/viralclip/twitch/telemetry.py

[Apri il file](../../../src/viralclip/twitch/telemetry.py)

Import dichiarati. `import json`, `import logging`, `from datetime import UTC, datetime`, `from logging.handlers import RotatingFileHandler`, `from pathlib import Path`.

### Classe _QuietRotatingHandler

[`_QuietRotatingHandler`](../../../src/viralclip/twitch/telemetry.py#L12) (righe 12–15).

### _QuietRotatingHandler.handleError

`_QuietRotatingHandler.handleError(self, record: logging.LogRecord) -> None`

[`Sorgente`](../../../src/viralclip/twitch/telemetry.py#L13) (righe 13–15).

### Classe HttpEventLog

[`HttpEventLog`](../../../src/viralclip/twitch/telemetry.py#L18) (righe 18–56).

### HttpEventLog.__init__

`HttpEventLog.__init__(self, db_path: Path, directory: str | None)`

[`Sorgente`](../../../src/viralclip/twitch/telemetry.py#L19) (righe 19–22).

### HttpEventLog.__call__

`HttpEventLog.__call__(self, event: dict[str, object]) -> None`

[`Sorgente`](../../../src/viralclip/twitch/telemetry.py#L24) (righe 24–48).

Chiamate nel corpo. `Path(self._directory).expanduser`, `Path`, `directory.mkdir`, `_QuietRotatingHandler`, `datetime.now(UTC).isoformat`, `datetime.now`, `json.dumps`, `self._handler.handle`, `logging.LogRecord`.

### HttpEventLog.close

`HttpEventLog.close(self) -> None`

[`Sorgente`](../../../src/viralclip/twitch/telemetry.py#L50) (righe 50–56).

Chiamate nel corpo. `self._handler.close`.
