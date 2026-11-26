# Text metadata preservation

Proposal of 2026-11-26. **Status: option C APPROVED by the owner on
2026-11-26, limited to `title`, `broadcaster_name` and `language`, and
IMPLEMENTED LOCALLY the same day (`storage/database.py`,
`tests/test_text_changes.py`); not deployed.** See
[implementation](#implementation-2026-11-26). Deployment and any production step need
separate owner authorization and a review (persistence and collectors are
sensitive areas). This is a
preventive infrastructure change during V1. It does not start V2, it adds no
model feature, and it leaves every V1 protocol, export and evaluator
unchanged. It revisits the observed-metadata capture cancelled on 2026-11-25
([decision](PROJECT_HISTORY.md#2026-11-25-feature-and-generalization-plan-approved)),
which the owner re-approved in this minimal form. The separate table
compatible with schema v2 is an explicitly temporary solution; folding it
into the versioned migrations is re-evaluated after V1.

## Why: audit of 2026-11-26

Read-only code audit; no database was opened.

- `clips.title`, `broadcaster_name` and `language` live in one mutable row
  (`storage/database.py`, migration v1). `record_clip` writes them with
  `INSERT ... ON CONFLICT(clip_id) DO UPDATE SET title = excluded.title, ...`,
  so every rediscovery overwrites them; only `first_seen_at` and `created_at`
  are kept.
- `clip_snapshots` is append-only but stores only `view_count`.
- Scheduled refreshes (10m, 30m, 60m, 6h, 24h) receive the title from Helix
  and discard it: `add_scheduled_snapshot` stores only the view count
  (`collector/service.py`, `collect_due_snapshots`).
- Rediscovery timing: legacy discovery rescans the last 30 minutes every
  cycle and catches up from checkpoint − 5 minutes after an outage; GTA VI
  `recent` lanes cover the current and previous 10-minute buckets, while
  `retry` (after at least 30 minutes) and `history` (after outages) can
  rediscover a clip hours later.
- `last_seen_at` is written by the same statement as the title, so it is the
  observation time of the stored value.

### What existing data can and cannot support

For a clip and cutoff instant `T = created_at + cutoff`:

| Case | Title known at `T` |
| --- | --- |
| `first_seen_at > T` | None; the clip was unknown at `T`. |
| `last_seen_at <= T` | The stored title, observed at `last_seen_at <= T`, was the latest value known at `T`. Candidate subset only. |
| `first_seen_at <= T < last_seen_at` | **Not recoverable.** The stored value was observed after `T`; an earlier value, if different, is lost. |

Titles of the third case must never be presented as recoverable. The second
case is selection-biased (clips rediscovered late are excluded, and late
rediscovery depends on view rank) and its share is UNKNOWN until a read-only
query runs on a sealed copy with authorization. Whether V2 may use it is a
V2 protocol decision. How often Twitch titles change in the first hour is
UNKNOWN.

## Options compared

All three options write in the transactions that already exist in
`record_clip` (discovery) and `add_scheduled_snapshot` (scheduled refresh),
leave the `clips` UPSERT and every reader untouched, and store `title`,
`broadcaster_name` and `language` with the actual UTC observation time.

| Criterion | A. First value, immutable | B. Full append-only history | C. Append-only changes, first observation included |
| --- | --- | --- | --- |
| Rows | One per clip | One per observation (about one per snapshot) | One per clip plus one per change |
| Value known at `T` | First value if observed `<= T`; edits before `T` invisible (stale but leak-free) | Exact | Exact: latest row with `observed_at <= T` |
| Detects edits | No | Yes | Yes |
| Re-confirmation times | No | Yes | Implied by `clip_snapshots`, written in the same transaction |
| Write per observation | `INSERT OR IGNORE` on the clip key; only the first succeeds | One insert | One indexed read of the latest row plus a conditional insert |
| Idempotence | Primary key | `UNIQUE (clip_id, observed_at, source)` | Same key plus the change predicate; replays insert nothing |
| Disk, four games (below) | 44–57 MB/day | 371–412 MB/day | 54–77 MB/day |
| Main risk | Misses the edits a text model needs to see | Disk: brings the VPS exhaustion date forward by about two weeks | Slightly more code; the change test must be NULL-safe |

**Recommendation: C.** It reconstructs the exact value at every cutoff, like
B, at about one fifth of B's disk cost and close to A's. With
`clip_snapshots` it loses no information about when values were observed.

### Disk estimate

Documented volumes: GTA VI 143–191k new clips and 0.97–1.01 M snapshots per
day; GTA V about 5.6k clips and 58k snapshots per day (read-only check of
2026-11-25); Fortnite about 12.2k and VALORANT about 9.5k clips per day
(volume probe of 2026-11-25, estimates). Current growth 0.63–0.66 GB/day for
GTA V and VI, 29 GB free on 2026-11-25.

Assumptions, unverified: clip ID 45 B, timestamp 27 B, source 9 B, average
title 45 B, broadcaster name 12 B, language 2 B; about 240 B per row with the
unique index and about 320 B with B-tree slack; option A about 260 B per clip;
catalog games 6–10 observations per clip; at most 10% of clips change once
(0–10%) for option C. 30-day months.

| Game | A per day | B per day | C per day |
| --- | --- | --- | --- |
| GTA VI | 37–50 MB | 310–323 MB | 46–67 MB |
| GTA V | 1.5 MB | 19 MB | 1.8–2.0 MB |
| Fortnite + VALORANT | 5.6 MB | 42–70 MB | 6.9–7.6 MB |
| **Total per day** | **44–57 MB** | **371–412 MB** | **54–77 MB** |
| **Total per month** | **1.3–1.7 GB** | **11.1–12.4 GB** | **1.6–2.3 GB** |

Option C adds about 7–11% to the current GTA V and VI growth and moves the
disk-full forecast earlier by roughly 3–5 days. Option B adds about 50% and
would move it from early January to about late December, inside the formal
calendar (replication matures December 25). The estimate must be replaced by
a measured size (`dbstat`) on a synthetic database before rollout.

Write overhead: C adds one indexed lookup and at most one row per discovered
or refreshed clip, inside a transaction the collector already commits, so no
extra commit or fsync; about 1 M operations per day for GTA VI, about 12
per second on average. Helix request counts do not change.

## Schema: why outside the versioned migrations

The table would be created idempotently (`CREATE TABLE IF NOT EXISTS`, with
append-only triggers) when the writer opens, like `gta_vi_scan_attempts`
([manual](PROJECT_MANUAL.md)), and the schema version stays 2. Technical
reason: four gates require exactly v2 and would reject a v3 database:

- `m2_audit.py` raises `unsupported_schema` (frozen V1 audit tooling);
- `reliability.py` `sample_database` raises in the production monitor;
- `deployment.py` `_check_schema` refuses collector preflight unless the
  history is `[1, 2]`;
- `windows_supervision.py` refuses a schema other than `SCHEMA_VERSION`.

A v3 migration during V1 would change frozen evaluation and operational
gates and require coordinated code and database rollouts on live collectors
for a table no V1 component reads. No reader enumerates tables, so an extra
table is invisible to existing tools. After the V1 formal results the table
can be folded into a versioned migration with `IF NOT EXISTS` (open
question below).

## Draft table (option C)

```sql
CREATE TABLE IF NOT EXISTS clip_text_changes (
    change_id INTEGER PRIMARY KEY,
    clip_id TEXT NOT NULL REFERENCES clips(clip_id),
    observed_at TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('discovery', 'scheduled')),
    title TEXT,
    broadcaster_name TEXT,
    language TEXT,
    UNIQUE (clip_id, observed_at, source)
);
-- BEFORE UPDATE and BEFORE DELETE triggers raising 'append-only', as on clip_snapshots.
```

Insert when no row exists for the clip, or when the latest row (by
`observed_at`, then `change_id`) differs on any field compared with `IS NOT`
(NULL-safe). A NULL observed value is stored as observed, never filled from a
later observation.

## Implementation (2026-11-26)

- `Database.ensure_text_ledger()` runs after `migrate()` when the writer
  opens. It does nothing when the table and both triggers exist; otherwise it
  creates the missing objects with `IF NOT EXISTS` in one `BEGIN IMMEDIATE`
  transaction. `schema_migrations` stays `[1, 2]`.
- `record_clip` and `add_scheduled_snapshot(..., text=...)` call
  `_record_text` inside their existing transaction, after the snapshot, with
  the snapshot's own `observed_at` (the actual acquisition time). The
  collector passes the parsed Helix clip on scheduled refreshes; callers that
  pass no text record none. The `clips` UPSERT is unchanged.
- Change test: the row for the latest `observed_at <= t` compared field by
  field with Python equality, so NULL to value, value to NULL and NULL versus
  empty string are changes. Two rows at the same instant (discovery and
  scheduled) resolve by `source`, so the unique index serves the whole
  `ORDER BY` with no temporary sort. Text is recorded only when the
  observation's snapshot is actually inserted: a replay at the same
  `(clip_id, observed_at, source)` keeps its first text, like its views.
- `_parse_clip` rejects a non-string `title`, `broadcaster_name` or
  `language` (NULL allowed) as invalid Helix data; on a scheduled refresh
  this fails that clip's jobs instead of aborting the batch.
- Out-of-order observations (for example after a clock step): if a change
  is inserted before the clip's next snapshot and no text row lies between,
  that next observation had been skipped as equal to the previous value, so
  the previous value is appended at that snapshot's time and source. Then
  "latest row `<= T`" stays exact for every `T`. Known limit: this assumes
  that next observation carried text. It holds for the collector, which
  always passes text; it fails only if a clock step goes back before a
  snapshot recorded without text (before deployment, or by a test or
  synthetic caller that omits `text`), where the restored value may not be
  the one actually observed.
- `Database.text_known_at(clip_id, at)` returns the preserved value known at
  `at`. Nothing in V1 reads the table: exports, evaluators and the registry
  are unchanged.
- No backfill: clips seen before deployment have no rows until their next
  observation, which is recorded at its own time.

Evidence on synthetic data only:

- 18 new tests (first observation time, unchanged observations, cutoffs
  30/35/60/65, NULL and empty transitions, replays including a replay after
  a skipped observation, out-of-order cases, append-only triggers, rollback
  of the whole observation, no text without text, schema still v2 with the
  `deployment` schema check passing, missing ledger and missing trigger
  recreated, query plans of the code's own queries using indexes with no
  scan or temporary sort, non-text metadata rejected, collector refresh end
  to end).
- Independent review (reviewer sub-review; reviewer at its usage limit until
  November 29): 20,000 random out-of-order sequences found no value at any
  `T` other than the latest observed at or before `T`. Its findings (replay
  after a skipped observation, index tie-break sort, non-text fields on
  scheduled refresh, test gaps) are fixed; the restoration limit above is
  documented. A reviewer review remains advisable before any deployment.
- `viralclip synthetic-dry-run` at `dfc0ebd` and with the change: dataset,
  benchmark and registry outputs byte-identical (only the absolute path in
  the benchmark manifest and the collector database differ); `health`
  output identical.
- Measured size (`dbstat`, 20,000 clips, 8 observations each, titles of
  15–75 characters, about 10% of clips changing once): 22,261 rows, 5.86 MB
  for table and index, **263 bytes per row, 293 bytes per clip** (265 and
  296 on a 5,000-clip rerun after the review fixes). Scaled to
  the documented volumes: GTA VI 42–56 MB/day, GTA V 1.6 MB/day, Fortnite
  and VALORANT 6.4 MB/day; **50–64 MB/day, 1.5–1.9 GB/month** for four
  games, inside the estimate above.
- Overhead: an unchanged scheduled refresh costs about 5 µs more in memory
  (34.4 versus 29.4 µs per call, after the review fixes); on disk a committed observation costs about
  1.7 ms, so the added cost is under 1% and adds no commit. Helix requests
  are unchanged.

## Minimal plan, subject to separate authorization

1. **Implement** (owner GO): the ensure function, two calls inside the
   existing transactions, no change to the `clips` UPSERT, exports,
   evaluators or version gates.
2. **Test offline, synthetic only:** first observation recorded; unchanged
   rediscovery and scheduled refresh insert nothing; a change inserts one row;
   NULL to value and value to NULL are changes; a replay at the same
   `observed_at` is ignored; the append-only triggers abort update and
   delete; a failure in the text insert rolls back the snapshot of the same
   transaction; value at `T` equals the latest row `<= T`; existing v2
   databases open with the version still 2; `m2_audit`, `reliability`,
   `deployment preflight`, `health` and `dataset` outputs unchanged on a
   fixture; measured bytes per row with `dbstat`. Then strict
   `verify_offline.py` and a reviewer review.
3. **Roll out** (separate authorization, approved runbook): one collector at
   a time outside formal cutoff windows, after a fresh preflight; record the
   start time per database. Data before that time stays as described above.
4. **Rollback:** redeploy the previous release. The table stays and is
   ignored by every reader; dropping it would be a production database change
   needing its own authorization. Rollback loses only the text observations
   that would have been recorded meanwhile; views, jobs and V1 data are
   unaffected.

## Risks and open questions

- Owner decision: re-approve a capture cancelled on 2026-11-25.
- Average title length and change rate are assumptions; measure before
  rollout.
- Disk: even option C brings VPS-3 slightly closer.
- Rollout timing relative to formal windows (V1 gaps under ten minutes do not
  exclude days, but a deploy is still a collector restart).
- Whether to also preserve `game_id` and `duration_seconds` (overwritten,
  not textual) or Helix fields not stored today (`creator_name`,
  `thumbnail_url`, `vod_offset`, `is_featured`). Out of scope here;
  `is_featured` is decided after the cutoff and would be leakage as a
  current-value feature.
- Folding the table into a versioned migration after V1.
- Twitch terms: text metadata follows the same private-data rules as the
  rest of the Helix data.
