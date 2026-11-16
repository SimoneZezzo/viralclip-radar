# Independent Milestone 0 audit — 2026-11-16

Verdict: **NO-GO for unattended 24/7 collection yet.** The revised code passes
mocked verification on Windows, but credentials are absent, live collection and
a multi-hour soak are unverified, and Linux has not been executed. A supervised
live start is the next step. Milestone 0's live acceptance condition is not met.

## Scope and baseline

Read WORKFLOW.md and all tracked Python, tests, configuration, dependency manifest,
lockfile metadata and README. The repository is a small synchronous Python
package: argparse CLI, httpx, python-dotenv, sqlite3, pytest and Ruff; Python >=3.11,
local interpreter 3.12.13. No ML, dashboard, downloader, exporter, demo command,
or external publishing implementation exists. All test clip data is synthetic.
Tracked paths contain no .env or collected database. No existing real database
was opened or modified, no live API request was made, and nothing was pushed.

Before changes: 15 tests passed; Ruff passed. Those tests did not establish the
crash, pagination failure or malformed response guarantees described below.

## Milestone 0 checklist

Complete means implemented and exercised with mocks/local storage, not live Twitch.

| Requirement | Initial state | After audit |
| --- | --- | --- |
| Installable Python package, uv, CLI entry points | Complete | Complete; locked test run succeeds |
| init-db, collect once/loop, local credential-free status | Complete | Complete; CLI status and loop tick tested |
| Helpful missing credentials/configuration errors | Partial: invalid integer config escaped handler | Fixed; invalid numeric settings produce setup error |
| .env/env DB path, intervals, lookback, names and IDs | Complete | Complete; environment loading tested |
| Exact category resolution, no invented GTA VI ID, local cache | Partial: first search page only | Fixed; paginated search with finite safety cap |
| OAuth client credentials, expiry, bounded 401 renewal | Partial: malformed token response crashed | Fixed; expiry, malformed payloads and repeated 401 tested |
| Startup/hourly OAuth validation | Missing | Added and tested |
| Timeout, User-Agent, bounded network/5xx retries and jitter | Complete | Complete; network exhaustion tested |
| Rate headers, 429, Retry-After | Partial: zero delay/conflicting headers | Fixed; later header wins, HTTP-date supported, minimum backoff |
| Exactly one clip selector, first<=100, repeated IDs<=100 | Complete | Preserved; batch and selector separation exercised |
| UTC-aware internal/stored timestamps and actual ages | Partial: future-created values clamped to zero | Reject impossible negative ages; reject naive API boundaries |
| Overlap, minute boundaries and durable watermark | Incorrect: split children could skip incomplete siblings | Root advances only when all child windows complete |
| Restart retains first failed discovery interval | Partial: no checkpoint before first success | Initial checkpoint persisted before discovery |
| Pagination and finite work cap | Partial: saved pages only after all fetches | Ingest each page immediately; max 20 logical pages/cycle |
| Saturation flags and minute-aligned subdivision | Incorrect: full final pages without cursor treated complete | Split at >=900 fetched results; incomplete runs are partial |
| Run windows, counts, timestamps, errors, unique/new clips | Partial: unique count absent; interrupted runs stayed running | Added unique count and interrupted-run recovery |
| Clip upsert preserves first_seen_at | Complete | Preserved and tested |
| First count stored as actual discovery snapshot | Partial: later page failure discarded fetched measurements | Fixed; prior pages survive later request failure |
| Append-only observations and ingestion deduplication | Complete | Preserved SQL triggers and uniqueness; tested |
| Five persistent target jobs, unique clip/type/target | Complete | Preserved and tested |
| Late discovery marks targets missed; no backdating | Complete | Preserved and tested |
| Due ID batches and unordered response mapping | Complete | Preserved; 101 clips use two requests |
| Missing clips unavailable, never zero | Partial: malformed envelopes mistaken for omission | Fixed; only valid data arrays can establish unavailability |
| Failed jobs have bounded retries | Partial: could retry immediately on every poll | >=30-second delay, three job attempts; exhaustion tested |
| Restart recovers running jobs and real overdue observation | Partial: no target-to-measurement link for combined jobs | Jobs link to shared actual snapshot; full restart test passes |
| Snapshot insertion and job completion atomic | Incorrect: two separate commits | One transaction; injected failure rolls back both |
| Due snapshots prioritized | Partial: once per five-minute cycle | Five-second loop ticks and checks before discovery pages |
| WAL, foreign keys, useful indexes, migrations | Complete | Additive migration v2 verified against v1 fixture |
| Single logical writer / multiple collector protection | Partial: README warning only | Local OS lock; competing collector rejected, status usable |
| Multi-category failure handling | Incorrect: first failing category starved later ones | Continue other categories, then report failure |
| Windows/Linux path portability | Partial | pathlib preserved; Windows executed, Linux unverified |
| Credential/data exclusion and separation from demo | Partial: only sqlite3 suffix ignored | Added db suffixes, env variants, lock/cache ignores; fixtures synthetic |
| Official documentation and terms review | Partial | API checked; legal page body unavailable, terms clearance not asserted |
| Real clips plus repeated prospective observations | Unverified | Still unverified: no credentials configured |

## Confirmed defects by severity

No confirmed Critical defect (secret disclosure, destructive migration or fabricated
historical counts) was found. High defects affecting trustworthy collection were:

1. Discovery buffered all pages before persistence: any later request failure or
   interruption discarded earlier real measurements. Fixed by immediate ingestion.
2. Recursive subdivision advanced the watermark independently per child, allowing
   a successful later sibling to hide an earlier incomplete interval. Fixed by
   advancing only the complete root interval; persist an initial checkpoint too.
3. Saturation without a continuation cursor was reported complete. Fixed with
   conservative near-ceiling detection and partial status.
4. Missing/invalid response envelopes could become false unavailability, or raise
   uncaught type errors and strand running jobs. Fixed with explicit shape checks.
5. Snapshot write and job completion were independent transactions. Fixed atomic
   write and per-job snapshot linkage; old records remain unchanged.
6. Two collectors could recover each other's running jobs and duplicate work.
   Added a process-lifetime OS lock before recovery. Local filesystems only;
   network-share locking and hard-link aliases are not certified.
7. Snapshot deadlines were checked only once per discovery interval. Added short
   snapshot polling independent of discovery, plus checks between discovery pages.
8. Malformed OAuth responses could terminate the collector; token validation was
   absent. Added safe parsing and startup/hourly validation with bounded retries.
9. One category failure skipped all later categories. Fixed category isolation.

Medium findings addressed: retry headers could induce zero-delay retries or ignore
the later reset; failed jobs retried immediately; category lookup ignored later
pages; negative ages were silently clamped; malformed counts were coerced;
interrupted runs remained running; unique discovery counts were not persisted;
invalid configuration escaped the CLI error handler; data ignores were incomplete.

Medium limitations retained: request_count counts logical discovery calls, not
all HTTP retries/OAuth requests; budget excludes retries and scheduled requests.
The approximate API ceiling and popularity sorting still bias discovery. A
chronically saturated interval may never catch up within the bounded budget.
Status is a local summary, not a coverage/health certification; its last_error
can include missed-target/recovery reasons. Failed jobs exhausted at three attempts
need inspection. There is no per-job claim/fetch-start timestamp; actual successful
observation time and target/due/completion are retained. No uptime guarantee exists.

Low: README's original green-suite statement described only 15 tests; updated
with this audit and current evidence. Formatting touched changed Python files only.

## Execution trace after fixes

CLI loads environment and creates/migrates SQLite. Status needs no token.
Collect acquires the OS lock, recovers running jobs and interrupted discovery runs.
Due jobs run first. Game names use cached exact IDs or paginated category search.
The client requests an app token by form POST, validates it and uses Client-Id and
Bearer headers for Helix. Expiry renews proactively; 401 renews once per request.

Discovery floors UTC bounds to whole minutes, overlaps the lookback/checkpoint,
and records a run. Each page receives a real response-time timestamp and is
ingested immediately: metadata upsert, append-only snapshot, five unique jobs.
Late targets are marked missed. Saturation subdivides within a finite budget;
incomplete/error runs do not advance the root watermark. Existing checkpoints
from earlier buggy runs cannot prove past completeness; lost measurements cannot
be repaired and must not be treated as historical ground truth.

Snapshot jobs are grouped by clip and fetched in <=100 repeated ID parameters,
without game_id. Valid results are mapped by ID. Actual observed_at and age are
stored once per clip/fetch, with target ages retained on jobs; insertion, links
and completion commit together. Valid omitted IDs become unavailable, never zero.
Malformed data fails/retries, not unavailable. A crash before commit leaves work
recoverable; a crash after commit leaves a completed job and its snapshot.

The loop checks jobs between discovery cycles and pages; network retries may
still delay deadlines. API failures are retained in SQLite; loop failures print
to stderr. SQLite/storage failures intentionally stop the process rather than
pretend persistence succeeded. Ctrl+C closes HTTP, SQLite and the OS lock.

## Verification evidence

Commands actually executed on Windows / Python 3.12.13:

```text
uv run pytest                         baseline: 15 passed
uv run ruff check .                   baseline: passed
uv run --locked pytest                final: 48 passed in 1.75 seconds
uv run ruff check .                   final: all checks passed
uv run ruff format --check .          final: 15 files already formatted
```

An intermediate format check found formatting differences; changed files were
formatted and the final check passed. Initial sandboxed uv commands could not
read uv's external cache; reruns with approved access succeeded.

New tests exercise partial pagination failure; saturation and bounded splitting;
malformed refresh/OAuth payloads; atomic rollback; additive v1-to-v2 migration;
competing collector rejection; full mocked HTTP category/discovery flow followed
by database close/reopen and a 65-minute delayed snapshot; hourly validation and
token expiry; rate-limit headers; retry exhaustion; category pagination/isolation;
loop timing and Ctrl+C cleanup; credential-free CLI status; invalid counts;
successful cursor pagination with distinct per-page observation times; invalid
selector rejection; negative-age rejection. Unordered batch results use distinct
view counts per clip, verifying ID-to-value mapping rather than just row counts.

Credential presence was checked as a boolean only: **false**. No secret values
were printed. Live OAuth/category/clips calls, real multi-observation collection,
production volume, long-duration operation and Linux execution are unverified.
The existing environment was used; a fresh uv sync on a clean machine was not run.

## Official documentation checked

- [Get Clips](https://dev.twitch.tv/docs/api/reference/clips): exclusive selector,
  repeated IDs <=100, unordered ID results, descending popularity, minute truncation,
  approximate 1,000 result ceiling. Request construction matches these rules.
- [Search Categories](https://dev.twitch.tv/docs/api/reference/search/): fuzzy
  results and cursor pagination; resolver deliberately requires an exact name.
- [OAuth](https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/): app
  client-credentials POST and expiry; no refresh token is assumed.
- [Validation](https://dev.twitch.tv/docs/authentication/validate-tokens/): startup
  and hourly validation, now implemented.
- [API concepts](https://dev.twitch.tv/docs/api/guide/): dynamic rate headers and
  cursor behavior, handled without a fixed requests-per-minute assumption.
- [Developer Agreement](https://legal.twitch.com/en/legal/developer-agreement/):
  page opened, but the retrieved body lacked substantive agreement text. This
  audit cannot certify legal retention, research use or redistribution rights.
  Do not distribute real databases, derived datasets or weights without review.

## Modified files and next action

Runtime: cli.py, collector/service.py, storage/database.py, twitch/client.py.
Verification: tests/test_collector.py, new tests/test_audit.py.
Documentation/exclusions: README.md, .gitignore, this report. No dependency change.
Migration v2 only adds columns; it neither rewrites nor deletes existing snapshots.

Next: add credentials to .env, run a supervised discovery and repeated observation,
inspect status plus actual timestamps in SQLite, then conduct a multi-hour trial.
Use the README commands; monitor another terminal with `uv run viralclip status`.
Keep the Windows machine awake and connected through 24 hours to assess 24-hour
jobs. Do not infer coverage or readiness from clip counts alone. No system settings
were changed, service provisioned or Milestone 1 feature implemented.
