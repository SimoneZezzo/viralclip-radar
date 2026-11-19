# Point-in-time dataset, version 2a.2

Use the dataset command from the repository root with Git and the project's
Python environment available. The command opens the configured database in
SQLite read-only mode, sets `query_only`, and takes a single consistent read.
It uses no collector writer or Twitch connection. The creation range is
required, has an inclusive start and exclusive end, and can span multiple
categories by repeating `--game-id`. Timestamps must include a UTC offset.
With no `--watermark`, the latest measurement in the read is the source watermark.
Explicit watermarks may be earlier than that measurement.

```powershell
uv run viralclip dataset --start 2026-11-17T18:49:26.389030Z --end 2026-11-17T20:03:00Z --game-id 32982 --watermark 2026-11-18T20:07:07.891063Z --output data/datasets/post-restart-example
```

The output directory must be new and ignored by Git. Use the local
`data/datasets/` tree. Keep these files and all source databases local.

| Artifact | Contents |
| --- | --- |
| `candidates.csv` | One row per clip known by the source watermark and per cutoff. Includes feature eligibility, features, and the contributing snapshot IDs ordered by time. |
| `outcomes.csv` | One row per clip. Separates valid, immature, unavailable, missing, invalid-link and outside-window outcomes. Valid outcomes include the linked job and snapshot IDs, observation time, actual age and view count. |
| `dataset.csv` | Join of eligible features to valid outcomes, keyed by clip and cutoff. |
| `coverage.json` | Counts, attrition, freshness, growth missingness, outage exposure and broadcaster concentration. |
| `broadcasters.csv` | Local audit-only grouping tokens, introduced in 2a.2 for concentration checks after splitting or deduplication. These are pseudonyms, not anonymous identifiers or model inputs. |
| `manifest.json` | Version, schema, watermark, source high-water markers, selection rules, model-feature allowlist, provenance pointers and output SHA-256 digests. Written last. |

## Selection contract

- The 30, 35, 60 and 65 minute predictions are distinct experiments.
  Features use actual measurement times up to and including `prediction_at`.
  A cutoff must have elapsed and the clip must already have been discovered for
  features to be eligible. At least one eligible measurement is required.
  At duplicate instants the smallest snapshot ID wins. Growth and rate need
  two distinct times and use actual elapsed minutes. CSV blanks represent
  missing values. A real zero is preserved.
- Candidate features are computed without reading outcomes in the feature
  function. Labels require a completed `view_snapshot` job at target 86,400
  seconds, with a linked same-clip scheduled observation measured in
  `[24h, 24h + 5m]`. Job completion time and observation time must agree.
  This full label window must have elapsed at the source watermark. Missing
  or unavailable outcomes keep blank labels.
- Only the manifest's `model_feature_columns` are intended as numerical model
  inputs. Identifiers, cutoff and label timestamps, outage flags and other
  audit columns are for selection or analysis. Mutable clip titles, status,
  language and other current metadata are excluded. Broadcaster concentration
  uses current stored broadcaster IDs in aggregate and never emits the IDs.
  The current stored game ID selects the cohort and is outside the feature list.
- Pass `--outage START END` for each known interval to annotate prediction
  windows and report clips with a nominal 10m, 30m or 60m deadline inside the
  measurement gap, grouped by discovery timing. Coverage flags do not
  impute missing observations or filter the modeled rows.

The extractor replays **measurement time**. Schema v2 has no independent
snapshot commit timestamp or metadata history. For exact reruns, retain a
verified local source backup, the selection, and the extraction version.
The source high-water markers identify the read used for each run. Discovery
counts describe the observed population. Late discovery, unreturned clips and
unavailable outcomes can affect selection. Choose a single cutoff per experiment
and keep all rows from the same clip together in any chronological split.
See the [chronological evaluation guide](CHRONOLOGICAL_EVALUATION.md) for the
baseline harness and scoring gates.

## November 18 verification commands

The three read-only runs used the earlier audit watermarks. To reproduce them
from the current checkout, choose fresh output directories (the original
outputs use `m2a-exploratory`, `m2a-blackout` and `m2a-post-restart`).

```powershell
function Invoke-DatasetReplay($start, $end, $watermark, $name) {
    .\.venv\Scripts\python.exe -B -m viralclip --db data/viralclip.sqlite3 dataset `
        --start $start --end $end --game-id 32982 --watermark $watermark `
        --outage 2026-11-17T18:26:14.379860Z 2026-11-17T18:49:26.389030Z `
        --output "data/datasets/m2a-replay-$name"
}
Invoke-DatasetReplay 2026-11-17T12:30:00Z 2026-11-17T14:51:00Z 2026-11-18T14:55:08.794420Z exploratory
Invoke-DatasetReplay 2026-11-17T17:26:14.379860Z 2026-11-17T18:49:26.389030Z 2026-11-18T20:07:07.891063Z blackout
Invoke-DatasetReplay 2026-11-17T18:49:26.389030Z 2026-11-17T20:03:00Z 2026-11-18T20:07:07.891063Z post-restart
```
