# GTA VI launch collector pilot

**Running since November 21, 2026** as a separate service next to GTA V,
which keeps its own unit, account, data and credentials. The live authenticated name lookup and reverse ID lookup on
November 19, 2026 returned **Grand Theft Auto VI, 1867279146**. [Helix Get Games](https://dev.twitch.tv/docs/api/reference/games)

For changes to the existing GTA VI service, see the
[offline recovery candidate and rollout gates](#offline-discovery-recovery-candidate).

## Scope and capacity

The pilot uses a new service account, executable tree, state directory,
database, SQLite lock file, HTTP JSONL and journal unit. It collects just
the verified GTA VI ID, at a **300-second cadence** with a **10-minute initial
lookback** and the existing overlapping checkpoint. The startup guard refuses
the GTA V path or ID, alias files, extra games, altered pilot settings and
unexpected schema. This reuses the existing collector's 10m/30m/60m/6h/24h job
schedule and actual observation timestamps. It adds no history replay.

The VPS has 2 vCores, 4 GB RAM and 40 GB disk. The pilot starts with nice 10,
relative I/O weight 20, a 35%-of-one-core CPU quota and 256/512 MiB memory
high/max settings. These are containment controls. Shared disk, network and
CPU contention remain possible. Low resource use on GTA V does not establish
GTA VI launch load. Load the existing rate-limit and 429 logs on both services
before increasing volume.

Use a separately authorized Twitch app for this independent collector. The
normal Helix app-access bucket is keyed by client ID; separate tokens on the
same client ID still share that bucket. The clients coordinate neither budget
nor cooldown across processes. Do not begin the pilot with the GTA V app or
assume that a separate app prevents endpoint-level 429s. Keep request scheduling
at the pilot defaults. [Twitch rate limits](https://dev.twitch.tv/docs/api/guide/#twitch-rate-limits)

A two-request launch-day sample at **15:27–15:37 Europe/Rome** returned
89 clips plus a cursor on the first page of the ten-minute window. The final
closed minute sampled within that window returned zero and no cursor.
The ten-minute page was incomplete. The sample did not measure how many pages
remain, full launch volume or the VPS app's rate limit. The collector can
now uses fixed structural lanes per cycle (see
[scan progress](#separate-scan-progress-and-coverage)). Those are discovery
page limits, with snapshot and retry calls additional. If the budget is exhausted, the persisted checkpoint can fall behind and
subsequent catch-up can grow the queried range. Twitch discovery is ranked by
views and capped, so absence from the database or a complete cycle does not
certify full coverage. [Helix Get Clips](https://dev.twitch.tv/docs/api/reference/clips)

Launch clips outside the initial window may be missed. Discovery delay,
indexing lag and saturation increase 10-minute misses. Review strict 10m,
30m and 60m coverage in `health` and report late/missed/unavailable jobs
separately. A later observation does not recreate an earlier one.

## Offline discovery recovery candidate

The minute-interval candidate described here was superseded on November 21
by the structural discovery release `4ab8d05f1ca1`, described under
[scan progress and coverage](#separate-scan-progress-and-coverage). Its full
text is preserved in Git (`git show b10cf94:docs/GTA_VI_PILOT.md`).
[Release evidence](PROJECT_HISTORY.md#2026-11-21-gta-vi-structural-discovery-release)

### GTA VI data impact

The latest read-only audit recorded the 2026-11-20 23:11 UTC checkpoint
still stalled at the 2026-11-21 13:35 UTC follow-up, at least 14 hours
and 24 minutes behind. November 20 had 83,760 seconds of completed search
windows, leaving 44 minutes outside recorded complete coverage. The
November 21 audit recorded zero complete-window seconds so far. Partial
runs still returned clips and existing jobs continued recording views.
These are audited search intervals. The percentage of Twitch clips
discovered and the current endpoint of the gap are unknown.

Catch-up can recover metadata and current counters for clips that Helix
still returns. Get Clips orders by views, truncates bounds to whole
minutes and caps the number of results per search. Recovery depends on
clip availability, minute density and capacity within the same budget.
Historical views absent from SQLite cannot be reconstructed from current
counts. A late first observation cannot supply a missing 10m/30m/60m
feature or a missed 24h outcome window. Retain actual timestamps.
[Helix Get Clips](https://dev.twitch.tv/docs/api/reference/clips)

Keep November 20 and 21 GTA VI UTC creation dates out of the primary M2
day-level evaluation while coverage or label maturity remains incomplete.
Recompute the actual coverage union and censoring after any approved
catch-up. Report late discovery, missing early observations and immature
or unavailable outcomes separately. Any evaluation of these partial days
belongs in a separate sensitivity analysis. Keep the existing 24h+5m
label-maturity embargo and the chronological gates.
[M2 readiness gates](CHRONOLOGICAL_EVALUATION.md#research-readiness-and-gta-v-retirement)

### Future rollout decision

These steps apply to any GTA VI-only runtime change. Build the reviewed
revision with `scripts/package_release.py`, which verifies archive members
against the Git blobs, and compare the full SHA-256 before staging. Apply
only the reviewed GTA VI runtime change.

1. Obtain specific authorization for a GTA VI-only release and service
   handoff. Inspect the live unit, effective interpreter path, Python
   version, installed module locations and hashes for both games. Compare
   the GTA VI runtime with the reviewed baseline. Identify and verify the
   previous runtime for rollback. Keep credentials out of the evidence.
2. Before the handoff, capture a read-only baseline for both games. Record
   service identity and boot policy, PID and start time, distinct DB
   device/inode/link count, checkpoint and flagged intervals, latest
   observations, overdue and failed jobs, disk reserve and recent 429s.
   Correlate complete UTC minutes per cycle, logical requests and retry
   load with the incoming five minutes per cycle. Verify the GTA VI ID,
   path, writer isolation, cadence and existing resource settings.
3. After approval, verify the SHA-256 again in private staging. Check
   available bytes and inodes on both staging and runtime filesystems
   against the disk reserve and the space for two releases. Verify
   runtime ownership, directory traversal and executable access for the
   GTA VI service user. Test the isolated runtime with synthetic data and
   verify it resolves reviewed modules from the final service path.
   Keep the unit, environment, authorization marker and state paths in
   place. Stop only GTA VI, confirm its writer has exited, switch its
   dedicated runtime at the existing path, then start only GTA VI.
   Record the new GTA VI PID and release. Verify that GTA V's PID, start
   time, executable and database identity stay stable.
4. Sample at least three successive GTA VI discovery cycles and continue
   through backlog reduction and one normal overlap cycle. Confirm
   contiguous completed windows against the starting watermark and each
   successive watermark, shrinking lag while backlogged, active
   observations and stable job lateness, rate limits and disk reserve.
   Check the completed-window union for gaps and confirm that persistently
   saturated minutes remain partial and visible.
   Compare job P95 and the oldest overdue job with the baseline and the
   [operations thresholds](MILESTONE_1_ROLLOUT.md#current-collection-and-monitoring-plan).

**GO for rollout** requires the reviewed artifact and its digest, explicit
authorization, an acceptable baseline, service and DB isolation, and a
verified executable rollback path. **GO to continue** requires contiguous
progress and backlog reduction (or a caught-up checkpoint), working
overlap, healthy jobs, and an unchanged GTA V service. **NO-GO** applies
to a persistent saturated minute, a missing interval under the checkpoint,
lag that fails to shrink under sustained load, more 429s or worsening
snapshot health, a storage alert, or a change to GTA V's process or DB
identity. For an authorized rollback, stop only GTA VI, confirm no writer
remains, restore the verified previous runtime at the existing service
path and start GTA VI. Recheck its code hash, database identity, checkpoint
and observation jobs, and confirm GTA V still matches the baseline.
Preserve the DB, WAL, valid checkpoint and run evidence throughout.
Rollback restores the prior discovery behavior and may bring back the
stall. If capacity is insufficient, quantify the gap and seek approval
for any configuration change.

### 2026-11-21 VPS preflight

The targeted two-file runtime exchange for the minute-interval candidate
was prepared and executed on November 21. Its full procedure, hashes and
checks are preserved in Git (`git show b10cf94:docs/GTA_VI_PILOT.md`).
[Preflight evidence](PROJECT_HISTORY.md#2026-11-21-gta-vi-rollout-preflight)

### Coverage gate after the live Helix diagnostic

The [recovery replay and validation gate](GTA_VI_DISCOVERY_REPLAY.md)
records the paired-page candidate and the rejection of five-minute
narrowing for the rounded-boundary case.

On November 21, an aligned Helix query for November 20 23:10–23:20 UTC
ended without a cursor but missed at least 60 clips from 23:19–23:20
that Helix returned by ID in the same diagnostic. Separate featured and
non-featured sequences also omitted IDs previously seen in the
unfiltered sequence. Timestamp filtering and deduplication can improve
result relevance. They provide no evidence that an exhausted query
covered the requested window.

Keep the GTA VI checkpoint behind the unresolved interval. A candidate
that advances it must demonstrate coverage through an independently
verifiable retrieval method. Known-ID checks can falsify a coverage
claim. They cannot enumerate clips whose IDs are unknown. The active
runtime and the preserved rollback runtime remain available.
[Diagnostic evidence](PROJECT_HISTORY.md#2026-11-21-gta-vi-helix-coverage-blocker)

### Separate scan progress and coverage

The GTA VI scan ledger is an optional additive extension to the existing
SQLite v2 core. It joins to `collection_runs` by run ID and is written
with the final run counters in one transaction. The former GTA VI
checkpoint and historical records remain intact. The prior runtime
can still open the database without a downgrade. GTA V continues on
the existing code path and does not create the ledger.

| Signal | Meaning |
| --- | --- |
| Recent scan watermark | Greatest end of a recent window where a discovery request was attempted. It is independent of historical holes. |
| Historical scan watermark | End of the contiguous historical attempt sweep, starting at the preserved legacy checkpoint when available. |
| `cursor_exhausted` / `scanned` | Helix ended pagination and no omission of a known ID was detected. Coverage is uncertified. |
| `known_incomplete` | Pagination ended, but at least one already-known clip in the target interval was absent. |
| `budget`, `page_limit`, `error`, `pagination_anomaly` | The scan stopped before it demonstrated a clean pagination end. The run preserves the reason and counters. |
| No recorded attempt | An interval is unscanned under the new policy. Old `completed` runs record legacy pagination only. |

Each cycle gives scheduled observations priority before discovery and
before each page. Up to ten logical pages go to the current ten-minute
UTC bucket, seven to the preceding bucket for delayed indexing, and
three to a historical interval. The request uses bucket-aligned bounds
and the persistence filter applies the original `created_at` to the
actual target, excluding the part of the open bucket after the cycle
cutoff. Raw rows, pertinent rows, unique persisted candidates and
repeated IDs are counted separately. A repeated cursor, a cursor
with no new IDs, or timestamps outside the API request bounds stop
the scan. The legacy raw 900-row heuristic is retained on the GTA V path.

The historical pass records each attempted bucket and proceeds with
the next. Once the sweep catches up, an incomplete historical interval
can be revisited once after a 30-minute delay. Its original attempt
and status stay visible. The current and previous buckets are revisited
each cycle. An API error uses the existing bounded client retries and
remains visible in the run ledger. Logical budgets exclude those retries
and scheduled refresh calls.

The scan watermark measures progress only. Coverage and the number of
undiscovered clips remain unknown. View-ranked capped responses can
favor popular clips, so future datasets must treat the observed clips
as a selected population. Existing feature and label rules use actual
observation times and retain missing observations and late discovery.
The dataset and evaluation code does not derive candidate completeness
from the scan watermark. A full UTC-day cohort still requires
independent coverage evidence.

### Persistent boot enablement

The installed GTA VI unit is enabled persistently under
`multi-user.target`, pulled in by the host's default
`graphical.target`. The configuration requires its existing runtime,
service account, writable state directory, environment file and
authorization marker. Network ordering uses `network-online.target`
and the configured networkd wait-online service.

Verify with `systemctl is-enabled viralclip-gta-vi.service` and inspect
the symlink under `/etc/systemd/system/multi-user.target.wants/`.
The enablement used `systemctl enable` with both collectors running.
Actual reboot recovery has yet to be tested.
[Enablement evidence](PROJECT_HISTORY.md#2026-11-21-gta-vi-persistent-boot-enablement)

## Initial installation

The first installation, staging and authorized start were completed on
November 21, 2026. Those one-time commands are preserved in Git
(`git show b10cf94:docs/GTA_VI_PILOT.md`). Current health checks use the
[dual-collector runbook](DUAL_COLLECTOR_OPERATIONS.md).
[Activation evidence](PROJECT_HISTORY.md#2026-11-21-gta-vi-controlled-activation)

## Backup and monitoring integration

The operations CLI accepts `--collector-unit viralclip-gta-vi.service`
and `--backup-unit viralclip-gta-vi-backup.service` for a distinct monitor.
Keep the original GTA V operations files and values. When deploying GTA VI
operations, stage copies of the backup and monitor service/timer pairs with
`viralclip-gta-vi-{backup,monitor}` names. Run them as `viralclip-gta-vi`
with the DB above and `--backup-dir /var/lib/viralclip-gta-vi/backups`, and set
`ReadWritePaths` on the backup unit to that directory. Use separately scoped
backup config/credentials, a **different restic repository prefix** and a
separate heartbeat. Stagger the timers, for example at 04:15 UTC for GTA VI
and 03:30 UTC for GTA V. Verify each archive and restore independently before
enablement. These follow-up operations units are not activated by the pilot.
[Backup and monitoring runbook](BACKUP_AND_MONITORING.md)
