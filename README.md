# ViralClip Radar

ViralClip Radar prospectively collects public Twitch clip metadata and actual
view-count observations. The collector stores metadata and observations at
their real timestamps. Model validation requires mature chronological cohorts.

## Local portfolio demo

The demo is a React + TypeScript app (`web/`, built with Vite and Tailwind CSS)
served by a FastAPI backend. Build the front end once, then start the server
from the checkout:

```powershell
npm --prefix web ci
npm --prefix web run build
uv run --offline --no-sync viralclip demo
```

Open `http://127.0.0.1:8765` and stop the server with Ctrl+C. For front-end
work, keep the demo running and use `npm --prefix web run dev`, which proxies
`/api` to it. `npm ci` needs network access once; builds and tests then run
offline. FastAPI and Uvicorn are in the uv `dev` group, so collector installs
do not need them.

The demo builds a collector database holding only synthetic clips, labeled
`SYNTHETIC / NOT REAL TWITCH DATA`, ranks it through the live ranking
registry and stores the runs in `data/demo/registry-v3.sqlite3`. GTA VI
shows simulated model scores and GTA V shows `latest_views` baseline scores.
The score runs from 1 to 100 relative to the selected game and pool.
Estimated views are an internal input to the simulated model.

The service only selects clips. Each clip card offers the clip link with
**Copy clip link** and **Open on Twitch**, plus links to external editors
the user chooses and pays for. The site never downloads, uploads or edits
video. Synthetic clips have no Twitch page, so their link uses the reserved
`example.invalid` domain and **Open on Twitch** stays disabled with a reason.
The demo needs no account or credentials.

## Quick start (Windows PowerShell)

Install [uv](https://docs.astral.sh/uv/), then from the repository directory:

```powershell
uv sync
Copy-Item .env.example .env
# Edit .env and set TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET.
uv run viralclip init-db
uv run viralclip collect --game "Grand Theft Auto V" --once
uv run viralclip status
uv run pytest
```

Create a Twitch application in the [Twitch Developer Console](https://dev.twitch.tv/console/apps).
Put its Client ID and Client Secret in `.env`; do not commit that file. The
collector uses an OAuth app access token and the official Helix API. No
credentials are needed for `init-db` or `status`.

The collector resolves a game name to its actual Twitch category ID. If Twitch
does not return an exact category match, collection stops with an error; it
never substitutes another GTA category. You can instead provide category IDs
using `VIRALCLIP_GAME_IDS` or repeated `--game-id ID` options.

## Offline verification

From a Git checkout, install the locked development dependencies once, then
run the same verifier used by CI on Windows and Ubuntu.

```text
uv sync --locked
uv run --offline --no-sync python -B scripts/verify_offline.py --strict
```

The verifier uses synthetic fixtures and disables dotenv. It reports pytest
counts, Ruff, Git whitespace, Bash syntax, PowerShell parsing and a verified
source archive of the committed `HEAD`. Each check reports `PASS`, `FAIL`,
`SKIP` or `UNKNOWN`. Exit `1` means a failed check. Exit `2` means an unknown
result or a skip in strict mode. Omit `--strict` to allow reported skips when
an optional interpreter is unavailable. On Windows, Git for Windows supplies
Bash. On Ubuntu, install PowerShell to run its parser locally.

The release command and its inventory checks are documented in the
[operations runbook](docs/MILESTONE_1_ROLLOUT.md#package-a-reviewed-git-revision).

## Continuous collection

Set `VIRALCLIP_GAMES` and optionally `VIRALCLIP_GAME_IDS` in `.env`, then run:

```powershell
uv run viralclip collect --loop
```

Leave that terminal and computer running; Ctrl+C stops cleanly. The default
discovery interval is 300 seconds with a 30-minute overlapping lookback. Tune
`DISCOVERY_INTERVAL_SECONDS` and `DISCOVERY_LOOKBACK_MINUTES` as needed. A
sleeping, shut down, or disconnected computer creates collection gaps that
cannot be recovered from historical Twitch clip view counts.
Run only one collector process against a given database at a time.
The collector enforces this with a local OS file lock; status remains available.
Snapshot jobs are checked every five seconds between discovery cycles and before
each discovery page. Slow HTTP calls and rate-limit waits can still delay them.

The SQLite database defaults to `data/viralclip.sqlite3`; override it with
`VIRALCLIP_DB_PATH` or the global `--db` option. SQLite uses WAL, foreign keys,
versioned migrations, append-only snapshots, and persistent per-clip jobs.

## Collector health

From a second terminal, run:

```powershell
uv run viralclip health
uv run viralclip --db "path/to/collector.sqlite3" health
```

Health uses a consistent read-only SQLite transaction, sees committed WAL data,
and requires no Twitch credentials. It creates no database and runs no migrations.
The report uses UTC and evaluates all categories stored in the database, so a
stale category can affect the result even when another category is current.

| Status | Exit code | Rule |
| --- | --- | --- |
| HEALTHY | 0 | No investigation thresholds triggered |
| DEGRADED | 1 | A category has no successful discovery or checkpoint yet, discovery or a checkpoint is older than the larger of 10 minutes or two discovery intervals, a job is overdue by more than 5 minutes, a failure awaits retry, a target's recent P95 lateness exceeds 5 minutes, or recent discovery/operational errors or incomplete windows beyond the checkpoint are present |
| CRITICAL | 2 | Discovery or a checkpoint is older than the larger of 30 minutes or six intervals, a job is overdue by more than 15 minutes, a job has exhausted its three attempts, or the database or required records cannot be read |

Counts and strict early coverage are cumulative. Overdue jobs are due
pending, running, or failed jobs. Missed-at-discovery and unavailable outcomes
remain separate and do not independently trigger alerts. A clip has early coverage
when it has any actual observation at or before its 10m, 30m, or 60m deadline,
among clips with that target already due. For example, a scheduled 60m
measurement that arrives one second late contributes to lateness and cannot
count for strict 60m coverage.

Discovery run counts, operational errors, and scheduled lateness use the last
hour. Lateness compares each completed job's linked observation time with its
due time and uses nearest-rank P95. A truncated parent window still appears in
the report when subdivision advances the checkpoint past it. Completed windows
describe recorded API searches. Actual coverage across Twitch is unknown.
The latest five recent error entries include timestamps, row IDs, and coarse
categories. Raw error messages are omitted.

## Twitch HTTP telemetry

An updated `collect` process writes UTF-8 JSON Lines next to its database.
The default path is `data/viralclip.sqlite3.http.jsonl`. The name follows the
database filename, including when using `--db`. Set `VIRALCLIP_HTTP_LOG_DIR`
in the environment or `.env` to choose another directory, or set it to
`off` to disable file logging. Use separate output paths for collectors with
the same database filename. Each log has one writer.

The file opens on the first event. It rotates at approximately 5 MiB and
retains three backups (`.1` newest through `.3` oldest), for roughly 20 MiB
per collector. Write and rotation errors are ignored so collection can proceed.
Use local storage because writes are synchronous. Existing collector processes
keep their current behavior. Live telemetry begins when an updated collector
starts collecting in a separately planned deployment.

- `http_request` records each attempt's coarse endpoint, status, monotonic
  duration in milliseconds, and outcome, including timeouts, network errors and
  HTTP 429. When present and valid, numeric rate-limit remaining and reset
  epoch fields are included. Malformed values are omitted and identified by
  field name.
- `http_retry` records the next attempt and its reason. `rate_limit_wait`
  records the planned sleep for a 429 retry or an exhausted bucket. Sum
  `delay_seconds` from wait events alone to avoid double-counting retry delays.
- `oauth_refresh` records attempts, successes and failures for initial token
  acquisition, expiry-based renewal and renewal after a 401. The HTTP token
  validation endpoint is recorded separately.

Inspect the latest rate-limit pressure in PowerShell:

```powershell
Get-Content data/viralclip.sqlite3.http.jsonl -Tail 1000 |
    ConvertFrom-Json |
    Where-Object { $_.event -eq 'rate_limit_wait' -or $_.status -eq 429 -or $_.rate_limit_remaining -eq 0 }
```

Logs omit credentials, headers other than the two parsed numeric rate-limit
fields, URLs, query parameters, request and response bodies, and exception text.
The SQLite health command continues to report stored collector health independently.

For a repeatable online backup, temporary restore drill, boot startup, crash
recovery and operator controls on Windows, see the
[Windows supervision runbook](docs/WINDOWS_SUPERVISION.md).
For staged Oracle ARM64 or generic x86-64 setup and the single-writer
handoff, see the [Linux deployment runbook](docs/LINUX_DEPLOYMENT.md).
For the active no-backup policy, collector health and disk monitoring, see the
[collection and monitoring plan](docs/MILESTONE_1_ROLLOUT.md#current-collection-and-monitoring-plan).

## What the observations mean

Discovery records the clip's current view count with its actual fetch time.
The collector schedules prospective observations at 10 minutes, 30 minutes,
60 minutes, 6 hours, and 24 hours after clip creation. If a clip is first
discovered after a target age, that target is marked missed; no historical
value is fabricated. A clip absent from a refresh response is recorded as
unavailable, never as zero views. Overlapping discovery can capture multiple
real observations, while duplicate observations from the same ingestion
timestamp are ignored. Twitch discovery is popularity-ordered and limited, so
the database records windows that may be truncated and does not claim
exhaustive coverage.

Jobs retain their target ages separately from actual measurement ages. After a
restart, multiple overdue targets may share one current snapshot, linked through
`jobs.snapshot_id`; that observation is not an on-time historical measurement.
Failed jobs retry after at least 30 seconds, up to three job attempts (each HTTP
request also has bounded retries). Exhausted jobs remain failed for inspection.
GTA V legacy discovery uses at most 20 logical page requests per cycle, splitting
windows near 900 results. GTA VI uses fixed structural lanes instead: 10 recent
pages, 7 overlap pages plus up to 3 time-bounded extra pages
(`VIRALCLIP_GTA_VI_OVERLAP_PAGES`, 8 in production) and 3 history or retry pages. Incomplete windows are marked partial and do not advance
the category checkpoint. Severe saturation can prevent catch-up; inspect coverage
before using these observations for research.

The API and application access remain subject to Twitch rate limits and terms.
This project stores operational clip metadata locally; review applicable Twitch
terms before redistributing collected data or derived datasets.

## Point-in-time dataset

Use `uv run viralclip dataset --help` to build local, read-only extracts at
30, 35, 60 and 65 minutes with linked 24-hour outcomes. See the
[dataset guide](docs/POINT_IN_TIME_DATASET.md) for the audit files, selection
rules, and reproducible PowerShell examples.

Use `uv run viralclip evaluate --help` to compare chronological ranking
baselines from local dataset artifacts. See the
[evaluation guide](docs/CHRONOLOGICAL_EVALUATION.md) for split maturity,
matched cohorts, metrics and the insufficient-data behavior.

## Live ranking registry

`uv run viralclip rank` scores one game, UTC creation day and cutoff with the
declared `latest_views` baseline and seals the run in a separate, append-only
SQLite registry under a Git-ignored path. The run records
`model_status=not_trained_yet` until a validated model exists. Only clips
observed by their cutoff enter the pool, and only observations at or before
the cutoff are used. `viralclip link-outcomes` later attaches settled 24-hour
outcomes in their own table without changing any prediction, and
`viralclip shortlist` prints the top K of the latest run for a pool. Both
writing commands read the collector database read-only.

## Synthetic dry run

`uv run --offline --no-sync viralclip synthetic-dry-run --output data/dry-run`
builds a collector database of `SYNTHETIC / NOT REAL TWITCH DATA` clips on the
preliminary 2/2/2 calendar, then runs the point-in-time export, benchmark
protocol v1, the live ranking registry at the 60-minute cutoff and 24-hour
outcome linking. It writes `summary.json` in a new Git-ignored directory and
needs no credentials or real data. The numbers describe the generator, not
Twitch.

## License

The code is released under the [MIT License](LICENSE). The license covers this
repository's code only. Collected Twitch data, derived datasets and models stay
private under the Twitch terms and are not part of the repository. Third-party
dependencies and the bundled agent skills keep their own licenses. Confirm the
provenance of `web/public/gameplay.jpg` before any public release, or replace
it with original artwork.

## Milestone and project progress

See [PROJECT_STATUS.md](PROJECT_STATUS.md) for the maintained milestone checklist,
saved session context, verification evidence, blockers and next steps.

- [x] **Milestone 0 — Collector MVP:** CLI, Twitch OAuth/Helix client, SQLite
  migrations, discovery, persistent snapshot jobs, retry/rate-limit handling,
  and mocked tests are implemented and passed an independent audit;
  see [the acceptance evidence](docs/PROJECT_HISTORY.md#2026-11-18-final-milestone-0-acceptance-go).
- [x] **Milestone 0 — Live acceptance:** passed, including the prospective
  post-restart cohort through 24 hours.
- [ ] **Milestone 1 — 24/7 operations:** health, backup and restore, and live
  telemetry verified. GTA V and GTA VI run as separate systemd services on
  a Linux VPS and start at boot. The 48-hour monitoring gate and a reboot
  rehearsal remain open. Windows supervision is prepared offline.
- [ ] **Milestone 2 — Features and baselines:** point-in-time builder and
  chronological evaluation harness verified. More mature days are needed
  for real out-of-time scores.
- [ ] **Milestone 3 — Machine learning:** not started.
- [ ] **Milestone 4 — Demo and presentation:** not started.
