# Milestone 1 operations runbook for GTA V and GTA VI

**Current status.** Both collectors run as separate systemd services on the
OVH VPS and are enabled at boot. The reliability timers are active. M1-02 is
cancelled. The operator waived the off-VPS requirement of M1-01, which
remains **PARTIAL**, and accepted permanent dataset loss if the VPS and its
copies are lost. The original backup, Restic and alert rollout phases were
removed on 2026-11-24 and can be recovered from `fe53f94`. The remaining M1
gates are in the [M1 closure gate](M1_RELIABILITY_HARDENING.md#proposed-m1-closure-gate).

## Current collection and monitoring plan

Keep one collector process and one SQLite writer per game, each with its
own systemd account, database and WAL. The repository health CLI reads
discovery, job and observation counters. The `viralclip-reliability@`
timers sample both collectors read-only and record severity in the journal
([reliability hardening](M1_RELIABILITY_HARDENING.md)). The older operations
monitor units expect backup markers and would raise backup incidents under
the current policy, so they stay uninstalled. Use lightweight SQL for
frequent checks and reserve full coverage scans for occasional audits. The
journal is unavailable if the entire VPS is lost.

| Signal | Warning | Critical |
| --- | --- | --- |
| Service and identity | Unplanned restart with service recovered | Inactive service, PID/DB alias, unreadable DB or wrong category |
| Complete discovery or checkpoint | More than 10 minutes old, or unresolved flagged windows | More than 30 minutes old or a stalled checkpoint |
| Latest observation | More than 10 minutes old while work is due | More than 30 minutes old while work is due |
| Scheduled jobs | Oldest overdue above 5 minutes, failures awaiting retry, or P95 lateness above 5 minutes | Oldest overdue above 15 minutes or exhausted retries |
| Disk and SQLite reserve | Under 20% free or projected below the critical reserve within 14 days | Below the larger of 10% of capacity or 1 GiB plus twice the seven-day peak of combined WAL usage, or projected to reach it within 3 days |

For the structural GTA VI runtime, evaluate live discovery freshness
using the recent scan watermark, persisted cycle outcomes and actual
new clips. Evaluate historical work with its own contiguous attempt
watermark and unresolved intervals. The frozen legacy checkpoint and
an exhausted API cursor cannot establish current failure or complete
coverage on their own. GTA V continues to use its legacy checkpoint
and overlapping search windows.

Track both DBs and their WAL/SHM files, free bytes and inodes, and daily UTC
growth. Use daily samples rather than a single checkpoint jump for the
forecast. Count late, unavailable and missed observations separately.
Correlate discovery flags, errors and HTTP 429s when aggregate telemetry
is available. Escalate a critical finding to the operator. Remediation,
restart and deletion are separate choices.

## 0. LINUX VPS — read-only inventory and baseline

Use [phase0-inspect.sh](phase0-inspect.sh) for this phase. Transfer and execution
require operator authorization. The script reports `PASS`, `FAIL` and `UNKNOWN`
per check. Both collectors are inspected independently. It inventories timer and
cron candidates by name, reports systemd and host capacity, and samples only
aggregate SQLite data. SQLite probes require regular existing WAL sidecars and a
per-process kernel write restriction. An unavailable restriction yields
`UNKNOWN` and leaves the database unopened. The script uses `sudo -n` for
privileged reads and applies no alternative escalation.

### Stage and verify the script

In the existing authorized **Ubuntu Bash** terminal, make a private temporary
directory and copy the printed path.

```bash
phase0_dir=$(umask 077; mktemp -d /tmp/viralclip-phase0.XXXXXXXX) &&
printf '%s\n' "$phase0_dir"
```

From the repository root in **local PowerShell**, use the already trusted SSH
destination or alias. Enter the printed temporary path and retain the printed
SHA-256. The copy performs no remote script execution.

```powershell
$phase0Source = (Resolve-Path -LiteralPath '.\docs\phase0-inspect.sh').Path
$phase0Target = Read-Host 'Approved SSH alias or user@host'
$phase0Dir = Read-Host 'Temporary directory printed by Ubuntu'
if ($phase0Target -cnotmatch '^(?:[A-Za-z_][A-Za-z0-9_.-]*@)?[A-Za-z0-9][A-Za-z0-9.-]*$' -or
    $phase0Dir -cnotmatch '^/tmp/viralclip-phase0\.[A-Za-z0-9]{8}$') {
    throw 'Invalid target or temporary directory'
}
$phase0Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $phase0Source).Hash
scp.exe -o StrictHostKeyChecking=yes -o UpdateHostKeys=no $phase0Source "${phase0Target}:${phase0Dir}/phase0-inspect.sh"
if ($LASTEXITCODE -ne 0) { throw 'Transfer failed' }
$phase0Hash
```

Back in the **same Ubuntu Bash** terminal, paste the local digest when
prompted. This block validates the hash and syntax only.

```bash
phase0_script="$phase0_dir/phase0-inspect.sh"
if read -r -p 'Local SHA-256: ' phase0_hash &&
   [[ "$phase0_hash" =~ ^[A-Fa-f0-9]{64}$ ]] &&
   printf '%s  %s\n' "${phase0_hash,,}" "$phase0_script" | sha256sum --check --strict &&
   env -u BASH_ENV bash -n -- "$phase0_script"; then
  printf 'PASS transfer and Bash syntax\n'
else
  printf 'STOP: hash or syntax verification failed\n' >&2
fi
```

### Collect and compare the samples

Only after the preceding `PASS` and explicit execution authorization, run in
**Ubuntu Bash**. A recent inventory from the same inspection window can be
retained. Otherwise run `inventory` first and check capacity before opening
the databases.

```bash
env -u BASH_ENV bash -- "$phase0_script" inventory
```

```bash
env -u BASH_ENV bash -- "$phase0_script" sample-a
```

Save the result for both games and the `A_ANCHOR` value. B requires at least
six minutes after A finished. After reviewing A, enter the value after the
equals sign without the label. A premature B exits without sampling.

```bash
read -r -p 'A_ANCHOR value: ' phase0_anchor &&
env -u BASH_ENV bash -- "$phase0_script" sample-b "$phase0_anchor"
```

- **Inventory.** Report expected unit states, operations paths and unresolved
  alternate schedules. A missing unit can be a verified inventory result.
  Confirm with the operator whether either database already feeds another
  backup or prune job. Existing operations files or unexplained automation
  require an upgrade review before any rollout.
- **Isolation and integrity.** Compare stable PID, process start timestamp and
  DB device/inode across A/B. Require distinct PIDs and DB identities between
  GTA V (`32982`) and GTA VI (`1867279146`), correct PID–DB links, expected
  categories and zero wrong rows. A must show SQLite integrity and zero FK,
  job-link and schedule violations.
- **Progress.** For each game, require a later checkpoint and a new complete
  discovery run. Empty discovery can pass that check. Compare snapshot counts
  and last observation time, scheduled observations, completed jobs and oldest
  overdue age. For a refresh pass, require new scheduled observations and
  completions with a healthy queue. If no job was due, or it became due just
  before B, refresh can remain `UNKNOWN`. HTTP-level verification remains
  `UNKNOWN` without separately authorized aggregate telemetry.
- **Revision.** `UNKNOWN RELEASE` is expected without a trusted deployment
  receipt that connects a commit and digest to the running process. Report
  those identifiers only if that link can be established.
- **Stop.** Stop on hash or syntax mismatch, wrong category, alias, unexpected
  PID change, integrity failure, stalled collector or resource pressure.
  Keep denied, incomplete or timed-out checks as `UNKNOWN`. Do not loosen
  privileges or SQLite protections. A `PASS READINGS` only means the queries
  returned. No rollout follows from these samples without separate approval.

Share UTC timestamps, aggregate verdicts and counters, expected unit names,
resource headroom and a summary of alternate schedules. Keep full system
output private. The script does not inspect credential files or process
environment, invoke Restic or change collector state.

The inventory also reports these operations units by name. They are not
installed under the current policy; an unexpected unit or schedule requires
review before any change.

| Game | Backup service and timer | Monitor service and timer | Expected game ID |
| --- | --- | --- | --- |
| GTA V | `viralclip-backup.service` and `viralclip-backup.timer`, 03:30 UTC | `viralclip-monitor.service` and `viralclip-monitor.timer`, every 5 minutes | `32982` |
| GTA VI | `viralclip-gta-vi-backup.service` and `viralclip-gta-vi-backup.timer`, 04:15 UTC | `viralclip-gta-vi-monitor.service` and `viralclip-gta-vi-monitor.timer`, every 5 minutes | `1867279146` |

## M1-01 interim VPS retention and Windows retirement

Two closed online recovery anchors, created on 2026-11-20 and verified by
hash, category, manifest and SQLite checks, are retained on the VPS at
`/home/ubuntu/viralclip-recovery-anchors/anchor-20261120T223940Z.kprYXW/`.
The staging originals remain under `~/viralclip-stage/`. The Windows VHDX
was removed on 2026-11-21. VPS retention shares the live databases'
exposure to complete host loss, which the operator accepted.
[Retention evidence](PROJECT_HISTORY.md#2026-11-21-m1-01-stable-vps-anchor-retention)
· [Removal evidence](PROJECT_HISTORY.md#2026-11-21-m1-01-windows-vhdx-removed)

To re-verify the anchors in an authorized SSH session, check that each DB and
`manifest.json` is a regular file on a canonical path without SQLite sidecars,
with `0700` directories and `0600` files. Compare each database SHA-256 with
the table below. Run the installed per-game `viralclip.deployment verify`
with `-B` and `PYTHON_DOTENV_DISABLED=1`, supplying `32982` for
`gta-v/viralclip.sqlite3` and `1867279146` for `gta-vi/gta-vi.sqlite3`. If
the installed CLI lacks `--expected-game-id`, check the category with SQLite
`mode=ro` and `query_only`. Verify the games serially and keep each verdict.

| Anchor | Category | Expected SHA-256 supplied by the operator |
| --- | --- | --- |
| GTA V | `32982` | `c1f37dfa0c83de5b28ca85ad838f5463c90f48242981fc4c893acfee84a50ba0` |
| GTA VI | `1867279146` | `48268202a5e330073399228fe5d1274240d9f2c571f4dff1b10dca7e8adfb7bd` |

## Package a reviewed Git revision

From the repository root in Windows PowerShell, enter the full commit hash
that was reviewed and tested. The packager reads the raw Git blobs under the
release allowlist and checks the archive inventory, file bytes, Linux line
endings and embedded commit before writing it. Record the full revision,
archive basename and SHA-256 before any separately authorized upload.

```powershell
$rev = Read-Host 'Full reviewed Git commit hash'
if ($rev -cnotmatch '^[a-f0-9]{40}$') { throw 'Enter a full lowercase commit hash' }
$archiveName = "ops-$rev-$((Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')).tar.gz"
$archive = "data/$archiveName"
git check-ignore --quiet --no-index -- $archive
if ($LASTEXITCODE -ne 0) { throw 'Archive destination must be ignored' }
if (-not (Test-Path -LiteralPath data)) {
    New-Item -ItemType Directory -Path data -ErrorAction Stop | Out-Null
}
$archiveDir = Get-Item -LiteralPath data -Force -ErrorAction Stop
if (-not $archiveDir.PSIsContainer -or ($archiveDir.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'Archive destination must be a regular directory'
}
uv run --offline --no-sync python -B scripts/package_release.py $rev --output $archive
if ($LASTEXITCODE -ne 0) { throw 'Release archive creation failed' }
```

After separate upload approval, copy the archive with the operator's
approved host and identity:

```powershell
$vps = 'ubuntu@REPLACE_WITH_APPROVED_VPS'
$identity = "$env:USERPROFILE\.ssh\REPLACE_WITH_APPROVED_IDENTITY"
scp -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -i $identity $archive "${vps}:viralclip-stage/"
if ($LASTEXITCODE -ne 0) { throw 'Source upload failed' }
```


## Risks to keep in view

- Both collectors, readers and any backup work share a two-core host and
  compete for I/O, CPU and disk.
- A missed 10, 30 or 60-minute sample cannot be backfilled. Measure every
  observation gap and keep it explicit.
- If a live database fails, preserve its DB/WAL/SHM, exclude its writer under
  incident authorization and restore to a fresh isolated path. Obtain a loss
  decision before any live recovery.
  [Recovery safeguards](BACKUP_AND_MONITORING.md#monitoring-and-restore)
