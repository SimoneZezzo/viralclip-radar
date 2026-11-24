# M1 reliability hardening

Audit of 2026-11-22 sampled working collectors. GTA V was healthy. GTA VI
was degraded with incomplete discovery. Its oldest overdue job was 3.6s at
sample B and neither collector had failed jobs. Both PIDs and database
identities stayed stable. Live status outside that sample is UNKNOWN.

A follow-up on November 22 at 23:44 UTC confirmed both reliability timers
active and enabled. The journal contained 103 GTA V HEALTHY samples and 101
GTA VI DEGRADED samples, with more than eight contiguous hours per timer.
The installed monitor module matched the local source. The installed GTA VI
discovery module matched commit `4ab8d05f1ca1`. The frontier correction, 48-hour
observation and reboot rehearsal remain open.

The November 23 integrity audit used a short SQLite online copy with a
source snapshot pinned in a private read-only mount. The successful copy
took 6.93s with no source WAL growth. The subsequent isolated read
passed the full SQLite integrity and foreign-key checks. On this
database, a capped live integrity read interrupted before a verdict.
Keep the live-read and isolated-verification budgets separate.
[Integrity evidence](PROJECT_HISTORY.md#2026-11-23-m1m2-discovery-and-data-quality-audit)

## GTA VI diagnosis and local correction

The [offline recovery replay](GTA_VI_DISCOVERY_REPLAY.md) compares the
current scan, a bounded overlap-page increase and narrower query windows.
The optional page increase is local. Use a separate gate for a limited
Helix comparison, a collector canary and the reboot rehearsal.

The November 22 22:52–23:52 UTC HTTP sample recorded 222 GTA VI category
requests and 766 ID refresh requests, all HTTP 200. It logged no retry,
429, or recorded network error. The minimum reported remaining budget
for both endpoints was 799. In the nearby A/B sample, the last hour
contained 12 budget stops and five known-ID omissions out of 24 recent
attempts. The budget stop in that lane is the seven-page overlap cap.
The ten-page current-bucket cap has its own `page_limit` status. Rate
limiting did not explain the incomplete runs in this sample.

Twitch documents minute-truncated request bounds, up to 100 clips per
page, view-ranked game results and approximately 1,000 paginated clips.
The November 21 live test returned rows outside requested minute bounds
and missed already-known clips even after cursor exhaustion. More pages
can help a cap-bound query, within the documented ceiling and the
collector's shared cost budget. They cannot establish that the same
ranked query exposes every clip.
[Twitch Get Clips](https://dev.twitch.tv/docs/api/reference/clips)
[Twitch rate limits and pagination](https://dev.twitch.tv/docs/api/guide/)

### Path and limits

GTA V uses the configured 30-minute lookback and five-minute checkpoint
overlap. It can subdivide capped windows at UTC minutes within a shared
20-page cycle budget. Every child must complete before the checkpoint
advances. GTA VI uses current and preceding ten-minute aligned queries
and a separate history/retry slot. It filters on the actual target UTC
interval, deduplicates each scan by clip ID and preserves partial evidence.
For both games SQLite holds one writer. First ingestion preserves
`first_seen_at`, creates five persistent refresh targets and adds the
actual discovery observation. ID refresh batches are capped at 100 and
due work runs before discovery pages. If ingestion occurs after a
target, the job is missed. Collector latency derives from clip creation
and first observed timestamps and includes upstream indexing and backfill.
The M2 extractor uses observations available by the prediction time and
24-hour job-linked labels in the inclusive 24h to 24h+5m window.

HTTP transport allows three retries plus a one-time 401 credential
refresh on the Helix request. The HTTP client uses 5s connect and 15s
other phase timeouts. Rate waits honor finite reset and Retry-After
headers, with exponential backoff for retryable failures. The 300s
schedule is a target cadence. Retries, auth, and due jobs do not share
a hard 300s wall-clock deadline; their calls are separate from the
20 logical discovery pages. Local regressions cover ignoring nonfinite
throttle headers and closing a GTA VI run on unexpected ordinary
exceptions with a sanitized error. The failed-run frontier fix
requires a usable page and a non-error outcome.

- Each cycle allows 10 logical pages for the current aligned bucket, 7 for
  the preceding bucket and 3 for history or retry. The first two are both
  recorded under `recent`. A remaining cursor at the 10-page cap is
  `page_limit`. A remaining cursor at the 7- or 3-page cap is `budget`.
  HTTP retry attempts are governed by the existing bounded transport policy.
  The observed budget stops are consistent with wider aligned searches
  returning more pages than these allowances. Their cause is separate from
  the Helix cap of roughly 1,000 paginated results. [Twitch Get Clips](https://dev.twitch.tv/docs/api/reference/clips#get-clips)
- On cursor exhaustion the collector compares unique IDs received inside the
  target window against already-known IDs in that SQLite window.
  A missing known ID is `known_incomplete`. Repeated cursors, a continuation
  page without new wire IDs and timestamps outside the aligned query produce
  `pagination_anomaly`. A clean cursor end cannot detect clips that Helix
  has never returned. The ledger persists outcome, target interval, raw,
  pertinent, repeated and unique counts. History progresses on usable
  attempts and preserves partial results.
- Retry starts only when history reaches the preceding aligned bucket.
  It takes the oldest incomplete history window that ended by that bucket
  and finished at least 30 minutes earlier, with at most one retry attempt
  per exact interval. It uses the shared 3-page history/retry allocation.
  The observed history lag explains the lack of retry. A retry outcome
  never grants completeness, and the original provenance remains visible.
- History can advance by an aligned bucket of up to 10 minutes per
  five-minute cycle. Actual catch-up depends on finishing cycles and usable
  responses. The recent scans retain priority. Transport failures in an
  earlier lane end a cycle before downstream lanes. Repeated such failures
  can starve history. Persistent failures of one history interval can also
  hold the sweep there. Separately evaluate isolated error handling and retry
  fairness against shared auth, throttling and total time budgets before
  changing them. Reusing the same capped query can repeatedly omit the same
  clips. Splitting or reducing windows needs a bounded Helix validation
  because the dated audit demonstrated discrepancies in returned ranges.
- The old frontier query accepted any run with a request, including a 503
  without a page or an error after a page. This could skip a history
  interval or advertise fresh recent discovery from an error. The fix
  requires a usable page and a non-error result. Empty successful pages
  still count. GTA V, the request budget, history/retry policy, schema
  and checkpoint writes are unchanged. A replay verifies that a failed
  interval is revisited. Existing holes before a later valid frontier stay
  visible in the ledger and need a separate recovery decision.
- Due observations are prioritized before each discovery page. A seconds-scale
  overdue age with zero failed and observations advancing fits normal queue
  ticks in this sample. Long transport waits and repeated backpressure can
  still cause persistent lateness. The monitor tests age and evidence of
  executed work before escalating. A delayed or absent observation is not
  reconstructed.

## Monitor behavior

The new `viralclip-reliability@.service` and `.timer` templates use one fixed
profile per collector and log to journald. Both timers run every five minutes
with short jitter. Each service runs under the existing collector account.
The monitor checks the read-only mount and existing DB/WAL/SHM before
opening SQLite, then uses `mode=ro`, `query_only` and one read transaction.
It reads systemd before and after the sample and checks disk and inode
capacity. The unit is restricted to local UNIX sockets. It performs no
corrective actions and requires no alert credential or backup components.

| Signal | Interpretation |
| --- | --- |
| Collector inactive or failed | UNHEALTHY. Startup or a process change during the sample is DEGRADED. PID, start time and automatic restart count provide continuity evidence. |
| Discovery stale | DEGRADED after 10m, UNHEALTHY after 30m for GTA V or GTA VI recent. A GTA VI history backlog with no usable run for 15m is DEGRADED. Incomplete attempts within the last hour also degrade coverage. The legacy GTA VI checkpoint remains diagnostic. |
| Overdue or failed jobs | DEGRADED at over 5m overdue or failure awaiting retry. UNHEALTHY at over 15m or retry exhaustion. A short overdue count alone is informational. |
| New observations and job completions | Shows a 15-minute observation window using the latest 16,384 rows. Counts from a capped tail are lower bounds. Job counts are limited to jobs due and completed within the last 15m. Zero fresh clips can be normal with advancing discovery and no overdue work. |
| Errors and resources | Two operational errors in 15m are DEGRADED. Free disk below 15% or inodes below 10% is DEGRADED. Disk below 10% or inodes below 5% is UNHEALTHY. |
| Inputs unavailable | UNKNOWN for missing process data, filesystem measurements or an unsafe, incompatible, busy or over-budget DB. A confirmed UNHEALTHY condition still takes precedence. |

The query allowance is 15 seconds and the service timeout is 45 seconds.
Each unit is capped at 25% of one CPU and 128 MiB, with low CPU and I/O
priority. An execution timeout or absent journal result indicates an
unavailable sample. Exit statuses are 0 HEALTHY, 1 DEGRADED, 2 UNHEALTHY and
3 UNKNOWN. systemd accepts 0 and 1 and records 2 and 3 as failed invocations.
The timer continues independently. Actual costs, mount flags and read-only
WAL behavior must be tested inside the target Ubuntu service namespace.

## VPS validation procedure

Every VPS step below requires separate operator authorization. Start with
the [read-only two-sample preflight](MILESTONE_1_ROLLOUT.md#0-linux-vps--read-only-inventory-and-baseline).
Save UTC timestamps, collector unit state, restart counts, database identities,
recent snapshots/jobs and disk/inodes. Treat UNKNOWN, wrong category or an
isolation failure as a stop for monitor activation.

Prepare a reviewed release and checksum with
[the existing packaging workflow](MILESTONE_1_ROLLOUT.md#package-a-reviewed-git-revision).
Use a dedicated root-owned runtime at `/opt/viralclip-reliability` with its
local venv and reviewed unit files under `deploy/`. Stage and verify the
release separately from both active collector trees. The monitor can be
piloted while the collectors still run their current revisions.

### Manual check and timer activation for a fresh installation

From the authorized Ubuntu shell, execute this with the reviewed runtime
already verified and both new unit names absent.

```bash
set -e
release=/opt/viralclip-reliability
for unit in 'viralclip-reliability@.service' 'viralclip-reliability@.timer'; do
    test ! -e "/etc/systemd/system/$unit"
    test ! -L "/etc/systemd/system/$unit"
done
for profile in viralclip viralclip-gta-vi; do
    for kind in service timer; do
        test "$(systemctl show "viralclip-reliability@$profile.$kind" -p LoadState --value)" = not-found
    done
done
test -x "$release/.venv/bin/python"
sudo -n systemd-analyze verify "$release/deploy/viralclip-reliability@.service" \
    "$release/deploy/viralclip-reliability@.timer"
sudo -n install -o root -g root -m 0644 "$release"/deploy/viralclip-reliability@.{service,timer} \
    /etc/systemd/system/
sudo -n systemctl daemon-reload
for profile in viralclip viralclip-gta-vi; do
    sudo -n systemctl start "viralclip-reliability@$profile.service"
    sudo -n journalctl -u "viralclip-reliability@$profile.service" -n 35 --no-pager
done
```

Require both manual results and valid SQLite evidence. A DEGRADED GTA VI
result can support the monitor pilot when it is explained by recorded incomplete
scan outcomes and the primary collection path remains timely. If either
manual run is UNKNOWN or UNHEALTHY, investigate in read-only mode and leave
the timers inactive until the condition is understood. After approval of the
manual evidence, activate only these timers.

```bash
sudo -n systemctl enable --now \
    viralclip-reliability@viralclip.timer viralclip-reliability@viralclip-gta-vi.timer
systemctl list-timers 'viralclip-reliability@*.timer' --all --no-pager
sudo -n journalctl -u viralclip-reliability@viralclip.service \
    -u viralclip-reliability@viralclip-gta-vi.service \
    --since '20 minutes ago' --no-pager
systemctl show viralclip-collector.service viralclip-gta-vi.service \
    -p MainPID -p NRestarts -p ActiveState -p UnitFileState
```

Verify at least two timer-driven runs per game, spaced about five minutes.
Compare collector PIDs, DB identities, queue ages, CPU and WAL growth before
and after activation. A WAL reader can delay WAL recycling and the two
timers can overlap despite jitter. Roll back the monitor if latency, resource
use or WAL growth regress materially. Observe both timers for at least
48 hours before proposing M1 closure.

### Collector correction, reboot and rollback

Deploy the frontier correction only under separate approval using the GTA VI
controlled release, smoke and rollback steps in
[the GTA VI pilot](GTA_VI_PILOT.md). Keep the GTA V runtime and both data
directories in place. Capture the current runtime identity and preserve the
rollback runtime. During smoke verify recent and history advance, the job
queue completes and partial/failed intervals remain recorded. Recheck after
at least three cycles, then observe stability without supervision. Compare
with the preflight rather than interpreting natural DB or WAL growth as
a monitor write.

For the separately authorized reboot rehearsal, record the boot ID and the
two collectors' boot enablement before reboot. Capture fresh baseline samples
using the read-only runbook. Use `sudo -n systemctl reboot` only within the
approved maintenance window with operator recovery access. On reconnect check
`cat /proc/sys/kernel/random/boot_id` and both service states. Confirm a new
boot ID, both processes started automatically with the same database
identities, both monitor timers came up and collection resumed. Capture a
second sample at least six minutes later. If either service fails to resume,
record the evidence and use the approved incident procedure.

Keep the reboot rehearsal on the current verified runtime and environment.
Validate both timer instances and their schedules before the maintenance
window. Require separate approval for reboot and keep console recovery
available. Record the outage boundaries in UTC and preserve the measured
observation gap for M2. Run two timer-driven results per game after boot
and compare their budgets, disk and job queues to the fresh preflight.
Keep the pending discovery canary out of the reboot window.

Monitor rollback touches only the dedicated units introduced above. Diff the
installed units against the verified release before removal.

```bash
set -e
sudo -n cmp /opt/viralclip-reliability/deploy/viralclip-reliability@.service \
    /etc/systemd/system/viralclip-reliability@.service
sudo -n cmp /opt/viralclip-reliability/deploy/viralclip-reliability@.timer \
    /etc/systemd/system/viralclip-reliability@.timer
sudo -n systemctl disable --now \
    viralclip-reliability@viralclip.timer viralclip-reliability@viralclip-gta-vi.timer
sudo -n systemctl stop \
    viralclip-reliability@viralclip.service viralclip-reliability@viralclip-gta-vi.service
sudo -n rm -- /etc/systemd/system/viralclip-reliability@.service \
    /etc/systemd/system/viralclip-reliability@.timer
sudo -n systemctl daemon-reload
systemctl show viralclip-collector.service viralclip-gta-vi.service \
    -p MainPID -p NRestarts -p ActiveState -p UnitFileState
```

Leave runtime and journals available for diagnosis. Repeat the read-only
samples after rollback. Collector code rollback uses its separately reviewed
rollback runtime and incident steps.

### Proposed M1 closure gate

Require 48h of journal evidence for both timers, including samples at no more
than six-minute start intervals, or an explained maintenance gap followed by
a recovery sample. No unexplained collector restarts or stuck jobs beyond 5m.
Discovery recent stays within 10m and history lag trends downward or stays
bounded by an explicitly reviewed target. For GTA VI verify that partial
outcomes remain visible and judge operational continuity independently from
Helix completeness. Disk and inode reserves remain above warning levels,
read-only samples stay within their allowance and the authorized reboot
demonstrates automatic recovery. M2 cohort coverage and scoring are separate
gates. Existing backup waiver remains in effect.

### Short closeout procedure

Both collectors and timers were active and enabled at the November 23
07:47 UTC verification. The usable continuous journal intervals were
16.50h and 16.33h. Read the last 49 hours of the existing journals after
both streams have naturally reached 48 hours. Confirm the six-minute
cadence and review any interruption before accepting continuity.

For the separately approved reboot, preflight both services, both DB
identities, the boot ID, and disk and queue headroom. Keep the current
runtime and config for this exercise. On reconnect, check a different
boot ID, both automatically started collectors and timers, unchanged
DB identities, and new discovery and scheduled observations. Require two
timer samples after boot. Record the UTC gap for M2. Use the authorized
incident procedure if recovery fails. Keep the canary in a separate
maintenance window.
