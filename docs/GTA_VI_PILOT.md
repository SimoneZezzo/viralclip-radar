# GTA VI launch collector pilot

**Prepared for review.** Keep the existing GTA V service, unit, account, data
and credentials in place. Do not install or start this pilot before separate
authorization. The live authenticated name lookup and reverse ID lookup on
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
split windows at its 900-result safety threshold and uses at most 10 logical
pages per window and 20 per discovery cycle. Those are discovery page limits,
with snapshot and retry calls additional. At this cadence that is at most
four discovery pages/minute averaged across a normal cycle, sometimes bursty.
If the budget is exhausted, the persisted checkpoint can fall behind and
subsequent catch-up can grow the queried range. Twitch discovery is ranked by
views and capped, so absence from the database or a complete cycle does not
certify full coverage. [Helix Get Clips](https://dev.twitch.tv/docs/api/reference/clips)

Launch clips outside the initial window may be missed. Discovery delay,
indexing lag and saturation increase 10-minute misses. Review strict 10m,
30m and 60m coverage in `health` and report late/missed/unavailable jobs
separately. A later observation does not recreate an earlier one.

## Offline discovery recovery candidate

The offline Helix replay exhausted 20 logical discovery calls in two
successive cycles. Each cycle logged partial runs at 10, 10 and 0 pages
and left the checkpoint at 23:11 UTC. The original algorithm spent the
budget on the wide parent and its left child, then required both children
to finish before advancing. Each cycle's later end widened the same retry.

The candidate applies to category `1867279146`. It queries in UTC minute
intervals of at most five minutes, shortens a partial interval and retries
its first unresolved minute. Completed contiguous intervals advance the
checkpoint even if the next interval spends the rest of the budget or
returns an error. After a restart, existing run records supply the retry
interval, including a failed initial run or a provisional checkpoint from
the previous collector. A minute that reaches the truncation guard remains
open. When new coverage reaches the cycle's cutoff, remaining requests
revisit the existing lookback and overlap for delayed indexing.

The 20-call discovery budget, 900-result guard, 10-page guard, page size,
300-second cadence and configured 10-minute lookback stay in place. The
collector runs due snapshots before discovery and between pages. Bounded
Helix retries and observation requests are outside the discovery budget.
GTA V keeps its existing discovery path. The candidate uses the existing
SQLite schema and state. No live recovery evidence is available for it.

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

The verified source revision is
`c2e5c21300de1d6d98a89f8b7769fe69bdbd621e`.
The archive contains 53 files and its SHA-256 is
`d3e5bcc4506c44de43de737af023de452c3c3b57316a713ebcc9c60f697ff451`.
To reproduce the archive locally with a fresh output path, run:

```powershell
$revision = 'c2e5c21300de1d6d98a89f8b7769fe69bdbd621e'
$archive = "data/viralclip-gta-vi-$revision-rebuild.tar.gz"
uv run --offline --no-sync python -B scripts/package_release.py $revision --output $archive
if ($LASTEXITCODE -ne 0) { throw 'Source packaging failed' }
Get-FileHash -Algorithm SHA256 -LiteralPath $archive
```

The packager verifies archive members against the Git blobs. Compare the
full SHA-256 before staging. The archive includes source, tests and
deployment templates. Apply only the reviewed GTA VI runtime change.

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

Both units were active in the 13:59 UTC sample. GTA V was enabled at
boot and GTA VI disabled. Both use distinct Python 3.12.3 environments,
SQLite 3.45.1, project version 0.1.0, HTTPX 0.28.1 and python-dotenv 1.2.4.
The GTA VI discovery, launcher, database and HTTP modules match the
release parent. The installed `deployment.py` and `operations.py`
differ from that parent. The installed deployment helper still exposes
`_open_read_only(database: Path)` and `_check_schema(reader)`. Both
databases have migration versions 1 and 2. The candidate requires no
migration.

**NO-GO for a whole-package replacement.** Proceed to isolated staged
validation only after approval. The commands that transfer files,
write to staging and switch or stop/start the service all require
explicit rollout authorization. The following procedure preserves the
installed helper modules and dependency versions.

1. Use SCP with the existing identity to a new private staging directory
   under `/home/ubuntu`. Check the full SHA-256 there against the value
   above before extracting. Extract only
   `src/viralclip/collector/service.py` and `src/viralclip/gta_vi.py`.
   Confirm their SHA-256 values are
   `46cce79067d4fdfad4c43dc7a4bca2b777645192b3fb927b100d15c9e6aafb36`
   and `39abcede407ab334b94fa247ee94e076eb33d434c60e0b664b48e6224ea2a9a0`.
2. Build a root-owned sibling `/opt/viralclip-gta-vi.next` on the same
   filesystem by copying the current dedicated GTA VI runtime tree,
   omitting Python bytecode caches. Require the sibling path to be
   unused. In that copy replace the two corresponding files under
   `.venv/lib/python3.12/site-packages/viralclip/`. Refresh their two
   hash and size entries in the installed distribution's `RECORD`
   with SHA-256 encoded as unpadded URL-safe Base64. Verify all other
   installed sources and dependencies are unchanged. Confirm the two
   input hashes again. As `viralclip-gta-vi`, use the staged interpreter
   with `-IB` to import both modules and check their resolved paths and
   ID `1867279146`. Run the mocked discovery regression in a disposable
   test environment. Leave credentials and live DB paths out of testing.
3. Refresh the read-only baseline and verify disk reserve and access
   for the service user. Prove `renameat2` with `RENAME_EXCHANGE`
   works between two disposable directories on the same filesystem.
   The preflight observed ext4, the libc function, root-owned separate
   runtime directories and no conflicting systemd stop dependencies.
   Halt if the rehearsal, path, baseline or scope differs.
4. Stop with `sudo systemctl stop viralclip-gta-vi.service`. Confirm
   `MainPID=0`, an empty service cgroup and no process holding the GTA VI
   SQLite files that still exist. Use one `renameat2` exchange between
   `/opt/viralclip-gta-vi` and `/opt/viralclip-gta-vi.next`. On exchange
   failure, confirm the previous runtime remains at the live path and
   escalate immediately. On success, keep the previous runtime at
   `.next`, verify the new interpreter paths and module hashes at the
   live path, then run `sudo systemctl start viralclip-gta-vi.service`.
   Verify the new writer owns only the original GTA VI DB. Preserve the
   original systemd unit, environment, authorization and boot state.
5. Apply the three-cycle checks above with read-only probes of both
   games. Compare job P95 with the 5s GTA VI preflight baseline and judge
   it alongside overdue and failed jobs. Compare API error rates against
   zero observed API errors in the preflight hour. A persistent saturated
   minute must remain flagged as partial. Live catch-up capacity is
   unknown until measured.
6. For an authorized rollback, stop GTA VI, verify writer exit, exchange
   the same two directories back, validate the original source hashes,
   and start GTA VI. Verify database identity and continued observations,
   and compare GTA V with its preflight identity. The exchange leaves
   state paths alone. Normal SQLite close and restart can flush or
   recreate sidecars. Preserve the persisted checkpoint and run history.

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

## Windows preparation

From the repository root, the optional read-only exact check uses your
locally configured app credentials and prints only the ID. It neither
collects nor writes SQLite. A mismatch or failed lookup blocks approval.

```powershell
$py = '.\.venv\Scripts\python.exe'
$id = & $py -B -m viralclip.gta_vi resolve
if ($LASTEXITCODE -ne 0 -or $id -ne '1867279146') { throw 'Helix verification failed or changed' }
$env:PYTHON_DOTENV_DISABLED = '1'
& $py -B -m pytest tests/test_gta_vi.py tests/test_collector.py tests/test_operations.py
if ($LASTEXITCODE -ne 0) { throw 'Pilot tests failed' }
$release = "data/viralclip-gta-vi-$([guid]::NewGuid().ToString('N')).tar.gz"
tar.exe --exclude=__pycache__ --exclude='*.pyc' -czf $release pyproject.toml uv.lock .python-version README.md src tests deploy
if ($LASTEXITCODE -ne 0) { throw 'Archive creation failed' }
Get-FileHash -Algorithm SHA256 -LiteralPath $release
```

Review the source-only archive. After approval and checking the SSH host key,
upload it to a private staging directory. Use the actual OVH login.

```powershell
$Vps = 'ubuntu@REPLACE_WITH_VPS_ADDRESS'
ssh $Vps 'umask 077; mkdir -p ~/viralclip-stage; chmod 700 ~/viralclip-stage'
if ($LASTEXITCODE -ne 0) { throw 'Private VPS staging failed' }
scp $release "${Vps}:viralclip-stage/gta-vi.tar.gz"
if ($LASTEXITCODE -ne 0) { throw 'Pilot upload failed' }
```

## Ubuntu staging, after approval, with the marker absent

```bash
set -eu
expected='REPLACE_WITH_WINDOWS_SHA256'
printf '%s  %s\n' "${expected,,}" "$HOME/viralclip-stage/gta-vi.tar.gz" | sha256sum -c -
sudo test ! -e /opt/viralclip-gta-vi
sudo test ! -e /etc/viralclip/gta-vi-authorized
sudo test ! -e /etc/viralclip/gta-vi.env
sudo install -d -m 0755 -o "$(id -un)" -g "$(id -gn)" /opt/viralclip-gta-vi
tar -xzf "$HOME/viralclip-stage/gta-vi.tar.gz" -C /opt/viralclip-gta-vi
cd /opt/viralclip-gta-vi
export UV_LINK_MODE=copy
uv sync --locked --python /usr/bin/python3
uv run --no-sync pytest tests/test_gta_vi.py tests/test_collector.py tests/test_operations.py
uv sync --locked --no-editable --no-dev --python /usr/bin/python3
sudo chown -R root:root /opt/viralclip-gta-vi
sudo chmod -R a+rX,go-w /opt/viralclip-gta-vi
sudo useradd --system --user-group --home-dir /var/lib/viralclip-gta-vi --no-create-home --shell /usr/sbin/nologin viralclip-gta-vi
sudo install -d -o viralclip-gta-vi -g viralclip-gta-vi -m 0700 /var/lib/viralclip-gta-vi
sudo install -o root -g root -m 0600 deploy/gta-vi.env.example /etc/viralclip/gta-vi.env
sudoedit /etc/viralclip/gta-vi.env
pilot=/opt/viralclip-gta-vi/.venv/bin/python
db=/var/lib/viralclip-gta-vi/gta-vi.sqlite3
sudo test ! -e "$db"
sudo test ! -L "$db"
sudo -u viralclip-gta-vi env PYTHON_DOTENV_DISABLED=1 "$pilot" -B -m viralclip --db "$db" init-db
sudo install -m 0644 deploy/viralclip-gta-vi.service /etc/systemd/system/viralclip-gta-vi.service
sudo systemd-analyze verify /etc/systemd/system/viralclip-gta-vi.service
sudo systemctl daemon-reload
sudo systemctl show viralclip-gta-vi.service -p ActiveState -p UnitFileState -p MainPID
```

Enter the dedicated Twitch app credentials through the editor and keep the
verified ID and other defaults. For first-time staging, expect the new unit
to be inactive, disabled, `MainPID=0`. If the account, files or state already
exist, inspect them before proceeding. Check effective GTA V and GTA VI app
IDs privately. When both use the documented environment files and have no
overrides, the following verifies they differ without printing their values:

```bash
sudo "$pilot" -B - <<'PY'
from dotenv import dotenv_values
old = dotenv_values("/etc/viralclip/collector.env", interpolate=False).get("TWITCH_CLIENT_ID")
new = dotenv_values("/etc/viralclip/gta-vi.env", interpolate=False).get("TWITCH_CLIENT_ID")
if not old or not new or old == new:
    raise SystemExit("Require distinct nonempty app client IDs")
print("Dedicated Twitch app check passed")
PY
sudo systemd-run --wait --pipe --collect -p User=viralclip-gta-vi \
    -p EnvironmentFile=/etc/viralclip/gta-vi.env -p Environment=PYTHON_DOTENV_DISABLED=1 \
    "$pilot" -B -m viralclip.gta_vi preflight
```

If GTA V has effective credential overrides, stop staging and confirm
separation using those effective settings without displaying them. The
transient preflight checks disk paths and schema and issues no HTTP requests.

## Authorized pilot start, acceptance and stop

Immediately before any start, capture GTA V PID, discovery freshness, overdue
age, P95 by target, recent 429s and failures, plus `df -B1`, `free -m` and CPU
load. Review any existing cutover degradation and require advancing snapshots
without a growing backlog. Require free bytes of at least the larger of 20%
of the actual data filesystem and **2 × (both DB + WAL sizes) + 1 GiB**.
Plan to revisit disk growth after the first hour and day.

Only with explicit start approval:

```bash
sudo install -o root -g root -m 0600 /dev/null /etc/viralclip/gta-vi-authorized
sudo systemctl start viralclip-gta-vi.service
sudo systemctl show viralclip-collector.service viralclip-gta-vi.service -p MainPID -p ActiveState -p NRestarts
sudo -u viralclip env PYTHON_DOTENV_DISABLED=1 /opt/viralclip-radar/.venv/bin/python -B -m viralclip --db /var/lib/viralclip-radar/viralclip.sqlite3 health
sudo -u viralclip-gta-vi env PYTHON_DOTENV_DISABLED=1 "$pilot" -B -m viralclip --db "$db" health
sudo journalctl -u viralclip-gta-vi.service -n 35 --no-pager
sudo tail -n 30 "$db.http.jsonl"
df -h /var/lib/viralclip-gta-vi
free -m
```

Repeat after one discovery cycle, at 15, 30 and 60 minutes, then after the
6h and 24h targets mature. Confirm GTA V's unchanged PID and continuing
discovery/snapshots. GTA VI should have advancing discovery checkpoints,
new scheduled snapshots when due, no exhausted/failed jobs, no restarts
or OOM kills, and no overdue job older than five minutes. Inspect both
services' 429 and remaining-budget events. Review partial runs against the
checkpoint. One split or early discovery miss does not require a restart.
Pause GTA VI if repeated 429s, sustained low remaining budget under 10% of
the observed app bucket, a GTA V regression, three consecutive discovery cycles
without checkpoint advance, memory pressure (including swapping), or the disk
reserve breach is observed. Review the clipping sample and first hour growth
before widening the lookback or enabling startup. Verify the 6h/24h
outcomes prospectively. No initial completeness or growth-rate claim is made.

To stop only the pilot:

```bash
sudo rm -f /etc/viralclip/gta-vi-authorized
sudo systemctl disable --now viralclip-gta-vi.service
sudo systemctl show viralclip-gta-vi.service viralclip-collector.service -p MainPID -p ActiveState
```

Leave its SQLite files and lock in place. Once the pilot and backup plan are
accepted, enable only `viralclip-gta-vi.service` for startup if authorized.

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
