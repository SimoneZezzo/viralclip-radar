# Riferimento a firme e chiamate

[Indice delle schede](00-GUIDE.md) · [Spiegazione dei moduli](03-RESEARCH.md)

Indice statico ricavato con AST. I chiamanti e i test sono corrispondenze per simbolo, comprese quelle indirette nei callback definiti dentro un test. Le prove indirette e i percorsi effettivi sono nelle schede narrative. Per nomi condivisi come `main`, `_csv`, `preflight` e `close`, gli omonimi di altri moduli sono omessi dall'elenco per evitare attribuzioni ambigue. Importazioni dinamiche e callback passati senza invocarli possono sfuggire all'indice.

## src/viralclip/dataset.py

[Apri il file](../../../src/viralclip/dataset.py)

Import dichiarati. `import csv`, `import json`, `import sqlite3`, `import subprocess`, `from collections import Counter`, `from contextlib import closing`, `from dataclasses import dataclass`, `from datetime import datetime, timedelta`, `from hashlib import sha256`, `from math import isclose, log1p`, `from pathlib import Path`, `from viralclip.storage.database import parse_utc, to_utc_iso`.

Costanti. `VERSION`, `CUTOFFS`, `HORIZON`, `TOLERANCE`, `FEATURES`, `CANDIDATE_COLUMNS`, `OUTCOME_COLUMNS`.

### Classe Selection

[`Selection`](../../../src/viralclip/dataset.py#L61) (righe 61–66).

Campi dichiarati. `start: datetime`, `end: datetime`, `games: tuple[str, ...]`, `watermark: datetime | None`, `outages: tuple[tuple[datetime, datetime], ...]`.

### Classe Clip

[`Clip`](../../../src/viralclip/dataset.py#L70) (righe 70–75).

Campi dichiarati. `clip_id: str`, `game_id: str`, `created: datetime`, `first_seen: datetime`, `broadcaster_id: str | None`.

### Classe Observation

[`Observation`](../../../src/viralclip/dataset.py#L79) (righe 79–82).

Campi dichiarati. `snapshot_id: int`, `observed: datetime`, `views: int`.

### Classe Source

[`Source`](../../../src/viralclip/dataset.py#L86) (righe 86–93).

Campi dichiarati. `watermark: datetime`, `latest_observed_at: datetime`, `max_snapshot_id: int`, `schema: int`, `clips: list[Clip]`, `observations: dict[str, list[Observation]]`, `jobs: dict[str, sqlite3.Row]`.

### read_source

`read_source(path: Path, selection: Selection) -> Source`

[`Sorgente`](../../../src/viralclip/dataset.py#L96) (righe 96–165).

Chiamate nel corpo. `any`, `ValueError`, `path.resolve().as_uri`, `path.resolve`, `closing`, `sqlite3.connect`, `db.execute`, `db.execute('SELECT MAX(version) FROM schema_migrations').fetchone`, `db.execute('SELECT MAX(observed_at), MAX(snapshot_id) FROM clip_snapshots').fetchone`, `parse_utc`, `to_utc_iso`, `', '.join`, `parameters.extend`, `Clip`, `Observation`, `max`, `min`, `timedelta`, `db.execute("\n                    SELECT j.job_id, j.status, j.due_at, j.completed_at,\n                           s.snapshot_id, s.clip_id AS snapshot_clip_id, s.source,\n                           s.observed_at, s.age_seconds, s.view_count, s.target_age_seconds\n                    FROM jobs j LEFT JOIN clip_snapshots s USING (snapshot_id)\n                    WHERE j.clip_id = ? AND j.job_type = 'view_snapshot'\n                      AND j.target_age_seconds = 86400\n                    ", (clip.clip_id,)).fetchone`, `Source`.

Chiamanti per nome. [`extract`](../../../src/viralclip/dataset.py#L361).

Test che richiamano il simbolo. [`test_prediction_boundary_is_inclusive_to_the_microsecond`](../../../tests/test_dataset.py#L61), [`test_delayed_discovery_and_cutoff_maturity`](../../../tests/test_dataset.py#L74), [`test_no_measurement_preserves_missing_features`](../../../tests/test_dataset.py#L90), [`test_recovery_snapshot_uses_actual_time_and_is_deduplicated`](../../../tests/test_dataset.py#L101), [`test_outcome_requires_full_window_and_accepts_shared_recovery_link`](../../../tests/test_dataset.py#L117), [`test_future_jobs_and_mutable_metadata_cannot_change_candidate_features`](../../../tests/test_dataset.py#L164).

### candidate

`candidate(clip: Clip, observations: list[Observation], cutoff: int, watermark: datetime, outages: tuple[tuple[datetime, datetime], ...]) -> dict`

[`Sorgente`](../../../src/viralclip/dataset.py#L168) (righe 168–225).

Chiamate nel corpo. `timedelta`, `dict.fromkeys`, `row.update`, `to_utc_iso`, `any`, `max`, `type`, `ValueError`, `eligible.get`, `(clip.first_seen - clip.created).total_seconds`, `'|'.join`, `log1p`, `(first.observed - clip.created).total_seconds`, `(latest.observed - clip.created).total_seconds`, `(prediction - latest.observed).total_seconds`, `(latest.observed - first.observed).total_seconds`.

Chiamanti per nome. [`extract`](../../../src/viralclip/dataset.py#L361).

Test che richiamano il simbolo. [`test_no_measurement_preserves_missing_features`](../../../tests/test_dataset.py#L90).

### outcome

`outcome(clip: Clip, job: sqlite3.Row | None, watermark: datetime) -> dict`

[`Sorgente`](../../../src/viralclip/dataset.py#L228) (righe 228–272).

Chiamate nel corpo. `dict.fromkeys`, `parse_utc`, `(observed - clip.created).total_seconds`, `HORIZON.total_seconds`, `isclose`, `type`, `row.update`, `to_utc_iso`.

Chiamanti per nome. [`extract`](../../../src/viralclip/dataset.py#L361).

Test che richiamano il simbolo. [`test_outcome_requires_full_window_and_accepts_shared_recovery_link`](../../../tests/test_dataset.py#L117).

### _coverage

`_coverage(candidates: list[dict], outcomes: dict[str, dict], clips: dict[str, Clip]) -> dict`

[`Sorgente`](../../../src/viralclip/dataset.py#L275) (righe 275–302).

Chiamate nel corpo. `Counter`, `broadcasters.pop`, `broadcasters.most_common`.

Chiamanti per nome. [`extract`](../../../src/viralclip/dataset.py#L361).

### _outage_coverage

`_outage_coverage(source: Source, selection: Selection, outcomes: dict[str, dict]) -> list[dict]`

[`Sorgente`](../../../src/viralclip/dataset.py#L305) (righe 305–331).

Chiamate nel corpo. `Counter`, `any`, `timedelta`, `to_utc_iso`, `groups.items`.

Chiamanti per nome. [`extract`](../../../src/viralclip/dataset.py#L361).

### _csv

`_csv(path: Path, columns: tuple[str, ...], rows: list[dict]) -> None`

[`Sorgente`](../../../src/viralclip/dataset.py#L334) (righe 334–338).

Chiamate nel corpo. `path.open`, `csv.DictWriter`, `writer.writeheader`, `writer.writerows`.

Chiamanti per nome. [`extract`](../../../src/viralclip/dataset.py#L361).

### write_json

`write_json(path: Path, payload: dict) -> None`

[`Sorgente`](../../../src/viralclip/dataset.py#L341) (righe 341–344).

Chiamate nel corpo. `path.open`, `json.dump`, `stream.write`.

Chiamanti per nome. [`extract`](../../../src/viralclip/dataset.py#L361), [`run_evaluation`](../../../src/viralclip/evaluation.py#L527).

### ignored_output

`ignored_output(output: Path) -> Path`

[`Sorgente`](../../../src/viralclip/dataset.py#L347) (righe 347–358).

Chiamate nel corpo. `output.resolve`, `output.exists`, `ValueError`, `subprocess.run`, `output.as_posix`.

Chiamanti per nome. [`extract`](../../../src/viralclip/dataset.py#L361), [`run_evaluation`](../../../src/viralclip/evaluation.py#L527), [`main`](../../../src/viralclip/windows_supervision.py#L216).

### extract

`extract(path: Path, selection: Selection, output: Path) -> dict`

[`Sorgente`](../../../src/viralclip/dataset.py#L361) (righe 361–449).

Chiamate nel corpo. `ignored_output`, `read_source`, `candidate`, `outcome`, `source.jobs.get`, `outcomes[r['clip_id']].items`, `Counter`, `outcomes.values`, `_outage_coverage`, `_coverage`, `to_utc_iso`, `output.mkdir`, `_csv`, `sha256(f'viralclip:broadcaster:{c.broadcaster_id}'.encode()).hexdigest`, `sha256`, `f'viralclip:broadcaster:{c.broadcaster_id}'.encode`, `write_json`, `sha256((output / name).read_bytes()).hexdigest`, `(output / name).read_bytes`.

Chiamanti per nome. [`main`](../../../src/viralclip/cli.py#L79).

## src/viralclip/evaluation.py

[Apri il file](../../../src/viralclip/evaluation.py)

Import dichiarati. `import csv`, `import io`, `import json`, `from collections import Counter, defaultdict`, `from dataclasses import dataclass`, `from datetime import datetime, timedelta`, `from hashlib import sha256`, `from math import isfinite, log1p, log2`, `from pathlib import Path`, `from statistics import mean`, `from viralclip.dataset import CUTOFFS, FEATURES, HORIZON, TOLERANCE, ignored_output, write_json`, `from viralclip.storage.database import parse_utc, to_utc_iso`.

Costanti. `VERSION`, `MATURITY`, `DAY`, `MIN_DAYS`, `MIN_POOL`, `BASELINES`.

### Classe Candidate

[`Candidate`](../../../src/viralclip/evaluation.py#L28) (righe 28–39).

Campi dichiarati. `clip_id: str`, `game_id: str`, `created: datetime`, `cutoff: int`, `status: str`, `observation_ids: str`, `scores: tuple[float | None, ...]`.

### Candidate.day

`Candidate.day(self) -> datetime`

[`Sorgente`](../../../src/viralclip/evaluation.py#L38) (righe 38–39).

Chiamate nel corpo. `self.created.replace`.

### Classe Outcome

[`Outcome`](../../../src/viralclip/evaluation.py#L43) (righe 43–47).

Campi dichiarati. `status: str`, `views: int | None`, `observed: datetime | None`, `provenance: tuple[int, int] | None`.

### Classe SourceWindow

[`SourceWindow`](../../../src/viralclip/evaluation.py#L51) (righe 51–55).

Campi dichiarati. `start: datetime`, `end: datetime`, `watermark: datetime`, `games: tuple[str, ...]`.

### Classe Inputs

[`Inputs`](../../../src/viralclip/evaluation.py#L59) (righe 59–67).

Campi dichiarati. `candidates: dict[tuple[str, int], Candidate]`, `outcomes: dict[str, Outcome]`, `broadcasters: dict[str, str | None]`, `windows: list[SourceWindow]`, `outages: set[tuple[datetime, datetime]]`, `fingerprints: list[dict]`, `input_candidates: int`, `input_outcomes: int`.

### _csv

`_csv(data: bytes) -> list[dict[str, str]]`

[`Sorgente`](../../../src/viralclip/evaluation.py#L70) (righe 70–71).

Chiamate nel corpo. `csv.DictReader`, `io.StringIO`, `data.decode`.

Chiamanti per nome. [`read_inputs`](../../../src/viralclip/evaluation.py#L148).

### _candidate

`_candidate(row: dict[str, str], window: SourceWindow) -> Candidate`

[`Sorgente`](../../../src/viralclip/evaluation.py#L74) (righe 74–113).

Chiamate nel corpo. `parse_utc`, `timedelta`, `ValueError`, `isfinite`, `(parse_utc(row['latest_observed_at']) - created).total_seconds`, `any`, `max`, `Candidate`.

Chiamanti per nome. [`read_inputs`](../../../src/viralclip/evaluation.py#L148).

Test che richiamano il simbolo. [`test_future_feature_timestamp_is_rejected`](../../../tests/test_evaluation.py#L131).

### _outcome

`_outcome(row: dict[str, str], clip: Candidate, watermark: datetime) -> Outcome`

[`Sorgente`](../../../src/viralclip/evaluation.py#L116) (righe 116–145).

Chiamate nel corpo. `ValueError`, `Outcome`, `parse_utc`, `(observed - clip.created).total_seconds`.

Chiamanti per nome. [`read_inputs`](../../../src/viralclip/evaluation.py#L148).

### read_inputs

`read_inputs(directories: list[Path]) -> Inputs`

[`Sorgente`](../../../src/viralclip/evaluation.py#L148) (righe 148–274).

Chiamate nel corpo. `Inputs`, `(directory / 'manifest.json').read_bytes`, `json.loads`, `ValueError`, `names.add`, `(directory / name).read_bytes`, `sha256(data).hexdigest`, `sha256`, `SourceWindow`, `parse_utc`, `sha256(raw_manifest).hexdigest`, `to_utc_iso`, `inputs.outages.add`, `_csv`, `_candidate`, `clip_identity.setdefault`, `inputs.candidates.get`, `_outcome`, `inputs.outcomes.get`, `broadcaster_times.get`.

Chiamanti per nome. [`run_evaluation`](../../../src/viralclip/evaluation.py#L527).

Test che richiamano il simbolo. [`test_hash_mismatch_is_rejected`](../../../tests/test_evaluation.py#L197), [`test_conflicting_labels_fail_even_if_hash_is_internally_consistent`](../../../tests/test_evaluation.py#L205), [`test_valid_label_with_an_unelapsed_window_is_rejected`](../../../tests/test_evaluation.py#L217).

### ranking_metrics

`ranking_metrics(order: list[str], views: dict[str, int], k: int) -> dict`

[`Sorgente`](../../../src/viralclip/evaluation.py#L277) (righe 277–291).

Chiamate nel corpo. `views.values`, `views.items`, `relevant.intersection`, `_dcg`.

Chiamanti per nome. [`_scores`](../../../src/viralclip/evaluation.py#L414).

Test che richiamano il simbolo. [`test_ranking_metrics_use_true_outcomes_and_include_boundary_ties`](../../../tests/test_evaluation.py#L32).

### _dcg

`_dcg(values: list[int]) -> float`

[`Sorgente`](../../../src/viralclip/evaluation.py#L294) (righe 294–295).

Chiamate nel corpo. `log1p`, `log2`, `enumerate`.

Chiamanti per nome. [`ranking_metrics`](../../../src/viralclip/evaluation.py#L277).

### _day_is_covered

`_day_is_covered(day: datetime, game: str, windows: list[SourceWindow], deadline: datetime | None) -> bool`

[`Sorgente`](../../../src/viralclip/evaluation.py#L298) (righe 298–311).

Chiamate nel corpo. `min`, `max`.

Chiamanti per nome. [`_period`](../../../src/viralclip/evaluation.py#L314).

### _period

`_period(rows: list[Candidate], inputs: Inputs, label_deadline: datetime | None) -> tuple[dict, dict[int, dict[str, Candidate]], set[str], set[tuple[str, datetime]]]`

[`Sorgente`](../../../src/viralclip/evaluation.py#L314) (righe 314–383).

Chiamate nel corpo. `_day_is_covered`, `Counter`, `enumerate`, `_outage_exposed`, `_population`, `eligible[cutoff].values`, `set.intersection`, `eligible.values`, `defaultdict`, `grouped.items`, `day.date().isoformat`, `day.date`.

Chiamanti per nome. [`evaluate`](../../../src/viralclip/evaluation.py#L459).

### _outage_exposed

`_outage_exposed(row: Candidate, inputs: Inputs) -> bool`

[`Sorgente`](../../../src/viralclip/evaluation.py#L386) (righe 386–390).

Chiamate nel corpo. `any`, `timedelta`.

Chiamanti per nome. [`_period`](../../../src/viralclip/evaluation.py#L314), [`_population`](../../../src/viralclip/evaluation.py#L393).

### _population

`_population(rows, inputs: Inputs) -> dict`

[`Sorgente`](../../../src/viralclip/evaluation.py#L393) (righe 393–411).

Chiamate nel corpo. `Counter`, `inputs.broadcasters.get`, `tokens.pop`, `tokens.most_common`, `_outage_exposed`, `enumerate`.

Chiamanti per nome. [`_period`](../../../src/viralclip/evaluation.py#L314).

### _scores

`_scores(period, inputs: Inputs, k: int) -> dict`

[`Sorgente`](../../../src/viralclip/evaluation.py#L414) (righe 414–456).

Chiamate nel corpo. `eligible.items`, `defaultdict`, `candidates.values`, `pools.items`, `enumerate`, `ranking_metrics`, `day.date().isoformat`, `day.date`, `mean`.

Chiamanti per nome. [`evaluate`](../../../src/viralclip/evaluation.py#L459).

### evaluate

`evaluate(inputs: Inputs, validation_start: datetime | None, test_start: datetime | None, k: int) -> dict`

[`Sorgente`](../../../src/viralclip/evaluation.py#L459) (righe 459–524).

Chiamate nel corpo. `ValueError`, `any`, `t.replace`, `inputs.candidates.values`, `_period`, `periods.items`, `_scores`, `to_utc_iso`.

Chiamanti per nome. [`run_evaluation`](../../../src/viralclip/evaluation.py#L527).

Test che richiamano il simbolo. [`test_chronological_evaluation_scores_cutoff_and_matched_pools`](../../../tests/test_evaluation.py#L67), [`test_embargo_requires_full_label_window_even_for_already_observed_labels`](../../../tests/test_evaluation.py#L105), [`test_several_partial_intervals_on_one_day_do_not_create_independent_days`](../../../tests/test_evaluation.py#L119).

### run_evaluation

`run_evaluation(directories: list[Path], output: Path, validation_start: datetime | None, test_start: datetime | None, k: int) -> dict`

[`Sorgente`](../../../src/viralclip/evaluation.py#L527) (righe 527–587).

Chiamate nel corpo. `ignored_output`, `read_inputs`, `evaluate`, `to_utc_iso`, `MATURITY.total_seconds`, `zip`, `period['by_cutoff_minutes'].items`, `{'overall': report['overall'], **report['periods']}.items`, `output.mkdir`, `write_json`, `sha256((output / 'evaluation.json').read_bytes()).hexdigest`, `sha256`, `(output / 'evaluation.json').read_bytes`.

Chiamanti per nome. [`main`](../../../src/viralclip/cli.py#L79).
