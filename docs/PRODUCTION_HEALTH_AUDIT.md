# GTA V and GTA VI production health audit

Audit date **2026-11-19** (Europe/Rome). The historical inspection did not have an authenticated VPS shell. The subsequent local source baseline `8fefbf957c3c81712d6c0cbdb26b4118fd3bd75f` contains both offline fixes. The [project tracker](../PROJECT_STATUS.md) records the test evidence and the later operator samples. The currently installed revision and VPS state are **UNKNOWN**.

## Executive summary

| Check | GTA V | GTA VI |
| --- | --- | --- |
| Collector overall | UNKNOWN / NOT VERIFIED | UNKNOWN / NOT VERIFIED |
| Actual Twitch and SQLite progress | UNKNOWN / NOT VERIFIED | UNKNOWN / NOT VERIFIED |
| Database integrity and game isolation | UNKNOWN / NOT VERIFIED | UNKNOWN / NOT VERIFIED |
| Backup freshness and availability | UNKNOWN / NOT VERIFIED | UNKNOWN / NOT VERIFIED |
| Restore protection | UNKNOWN on VPS. Category guard verified offline. | UNKNOWN on VPS. Category guard verified offline. |
| Production monitoring | UNKNOWN / NOT VERIFIED | UNKNOWN / NOT VERIFIED |
| Restart and recovery | UNKNOWN / NOT VERIFIED. Boot enablement previously reported. | DEGRADED for unattended reboot recovery on the reported `disabled` policy. Running-process recovery unverified. |

The last operator inspection reported GTA V active and enabled, with 33,363 clips, 318,867 observations, zero operational errors over the prior hour and no significant backlog. It reported GTA VI active under its dedicated account, disabled at boot and using a separate database of approximately 46 MB, with recent WAL and HTTP log activity and a local backup. That report supplied no UTC sample timestamps, GTA VI row or job counts, or results of SQLite integrity checks. It establishes what was reported at that inspection.

## Evidence and limits

- The initial SSH attempt hit the workspace sandbox. An escalated, non-interactive OpenSSH attempt using the named identity and strict host-key checking reached SSH authentication and returned `Permission denied (publickey,password)`. Windows reported that the key path exists and the SSH agent was stopped and disabled. The remote `date -u` command never executed. Live PIDs, uptime, resource usage, logs, counts, last activity in UTC, scheduled jobs, backup markers, integrity and deployed code remain unavailable.
- The repository GTA V unit selects the category by name and uses `viralclip` with `/var/lib/viralclip-radar/viralclip.sqlite3`. The GTA VI unit uses `viralclip-gta-vi` with `/var/lib/viralclip-gta-vi/gta-vi.sqlite3` and dispatches through `viralclip.gta_vi run`. Both use `Restart=on-failure` and startup authorization conditions. The checked-in delays are 15 seconds for GTA V and 30 for GTA VI. Start limits are five and three starts respectively per 300 seconds. GTA VI also sets `Nice=10`, a 35% CPU quota and a 512 MiB memory limit. Installed overrides, dependencies, resource headroom and recovery history require live inspection.
- GTA VI's offline-reviewed `resolve` command requires an exact Helix Get Games match by name and a matching lookup by ID. The current pinned ID is `1867279146`, previously checked with authenticated Helix on 2026-11-19 per the project status. The `run` path validates the pinned ID, distinct paths and existing schema before passing the ID to the shared collector. It does not redo the two-way lookup as part of `run`. A successful empty discovery still writes a completed run and can advance the checkpoint. Failed discovery writes run/error state. A separate `gta_vi health` command is unnecessary for this shared schema, as the common read-only health check accepts a GTA VI database path.
- The shared collector schedules 10m, 30m, 60m, 6h and 24h observations, processes due jobs before discovery and uses a per-database OS lock. Health uses recent complete discovery, checkpoint age, job backlog, P95 lateness and error counts. In the five-minute configuration, discovery or watermark older than 10 minutes is degraded and older than 30 minutes is critical. Job lateness over five minutes is degraded and over 15 minutes or exhausted retries is critical. Empty successful discovery and recent HTTP 2xx can demonstrate monitoring even when clip and observation counts stay flat.
- In the historical checkout, a consistent GTA V-only bundle passed the restore verifier without an independently supplied category. The baseline now requires the expected game ID for operations backup and restore and verifies it against the SQLite rows. The two profiles share Restic selectors for legacy compatibility and still require independent repositories.
- In the historical runbook, `health_both` under Bash `errexit` skipped GTA VI when GTA V returned 1. The baseline helper evaluates and reports both exit codes before returning the combined result.
- The existing Python environment ran all 125 offline tests successfully. The first run used a missing temporary-directory parent and produced fixture setup errors. A rerun with a fresh workspace temporary path passed. Ruff lint and format checks passed. The manual audit helper passed `bash -n`; its SQLite, category and HTTP queries were exercised against synthetic WAL databases and closed local backup files for both categories.

The historical access probe and offline checks used these commands. The `ssh-add` output was suppressed and only its exit code was read. Set any host and identity placeholders from the operator's approved private configuration before an authorized probe.

```powershell
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\REPLACE_WITH_APPROVED_IDENTITY" ubuntu@REPLACE_WITH_APPROVED_VPS 'date -u +%FT%TZ'
ssh-add -l *> $null
Get-Service ssh-agent | Select-Object Status,StartType
$auditTemp = Join-Path (Get-Location) ('.pytest-production-audit-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider --basetemp $auditTemp
.\.venv\Scripts\ruff.exe check --no-cache .
.\.venv\Scripts\ruff.exe format --check --no-cache .
& 'C:\Program Files\Git\bin\bash.exe' -n docs/production-health-readonly.sh
git diff --check
```

## Findings, in priority order

| Severity | Finding | Evidence |
| --- | --- | --- |
| HIGH | The historical restore could accept a self-consistent wrong-game bundle. | Fixed offline in the baseline. Production version and repository separation are UNKNOWN. |
| HIGH | The historical preflight could skip GTA VI after a GTA V health failure. | Fixed offline in the baseline. Both exit codes are checked in synthetic Bash tests. |
| HIGH | GTA VI will not be pulled in by ordinary boot enablement while its unit is `disabled`. A separate dependency or operator action could still start it. | Operator-reported boot state. Live dependency graph and start history unverified. |
| MEDIUM | Production audit visibility is unavailable from this session. A stale checkpoint, stuck queue, corrupt DB or stale backup could go undetected by this audit. | Confirmed SSH authentication barrier. Those production failures were not observed. |
| MEDIUM | The monitor appends HTTP failure and no-telemetry summaries without changing severity on that basis. | Confirmed in reviewed source. Production alert delivery and underlying service response unverified. |
| MEDIUM | Both collectors and backup jobs share a VPS. Simultaneous snapshots, backup staging or journal growth could compete for capacity. | Potential risk. Live disk, memory and CPU headroom unverified. |

## Required actions

1. **Immediately.** Run the read-only commands below for both units in an existing authorized SSH session. Compare two samples at least six minutes apart. Check current integrity, category IDs, deployment paths, independent PIDs, discovery and job advancement, backlog, and backup watermarks. Preserve the active collectors and the current GTA VI boot policy during inspection.
2. **Before unattended dual-collector operation.** Follow the [gated rollout](MILESTONE_1_ROLLOUT.md) with separately authorized changes. Confirm the deployed revision requires a game ID for backup and restore and reports both health results. Verify repository separation and one isolated restore and one delivered failure alert per profile. Confirm shared headroom and decide how GTA VI should recover after a VPS reboot.
3. **Later.** Add an alert for stale/missing HTTP telemetry or sustained transport failures, retain periodic capacity measurements, and verify crash or reboot recovery during an approved drill.

## Run the pending read-only checks

From the repository root in PowerShell, format the local audit helper as a Bash here-document. The clipboard contains only the helper text. Open the existing trusted SSH connection and authenticate locally in the terminal.

```powershell
$auditScript = (Get-Content -Raw -LiteralPath .\docs\production-health-readonly.sh).Replace("`r`n", "`n").TrimEnd()
@("bash -s -- full <<'VIRALCLIP_AUDIT'", $auditScript, 'VIRALCLIP_AUDIT', '') -join "`n" | Set-Clipboard
ssh -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\REPLACE_WITH_APPROVED_IDENTITY" ubuntu@REPLACE_WITH_APPROVED_VPS
```

In the authenticated Ubuntu shell, run `sudo -v` if needed, then paste and execute the clipboard block. It reads effective systemd properties, PID ownership, cgroups and reverse dependencies, uptime, host capacity, sanitized journal and HTTP summaries, local backup artifacts and UTC watermarks. Each database query runs as its service account. The script uses SQLite `mode=ro` and `query_only` with existing WAL sidecars and bounds the read transaction. SQLite can use the existing shared-memory file for reader coordination. Schema inspection precedes application queries for each database. If an installed schema differs, use its reported table and column names to adapt the affected queries. Missing data is reported as unavailable. [SQLite WAL read-only behavior](https://sqlite.org/wal.html#read_only_databases)

At least six minutes after the first sample, paste the same block with its first line changed to `bash -s -- sample <<'VIRALCLIP_AUDIT'`. For GTA V compare complete run timestamps and checkpoint, HTTP discovery and refresh successes, new snapshots, completed jobs and the oldest overdue age. Use the same signals for GTA VI, handling zero discovered clips as a valid result if successful runs and the checkpoint advance. A scheduled job can only demonstrate live refresh when the database has a due job. Check the file device/inode pairs, service account, process command, open files and category result independently for each game.

If the production units use the documented operations directories, optionally list offsite snapshot metadata from their existing Restic profiles. Run this away from active backup or prune windows. The command ends in `snapshots` and disables repository locks and local caching. It reports profile names, distinctness, timestamps and counts. It does not validate the game identity or availability of the snapshots' database contents. [Restic snapshot listing](https://restic.readthedocs.io/en/stable/045_working_with_repos.html#listing-all-snapshots), [Restic read-only flags](https://restic.readthedocs.io/en/stable/manual_rest.html)

```bash
sudo -n /opt/viralclip-ops/.venv/bin/python -I -B - <<'PY'
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

repos = []
for name in ('ops', 'gta-vi-ops'):
    profile = Path('/etc/viralclip') / name
    try:
        config = dotenv_values(profile / 'backup.env', interpolate=False)
        repo = (config.get('RESTIC_REPOSITORY') or '').rstrip('/')
        endpoint = urlsplit(repo[3:])
        if (not repo.startswith('s3:https://') or not endpoint.hostname or not endpoint.path.strip('/')
                or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment):
            print(name, 'private HTTPS repository configuration unavailable')
            continue
        repos.append(repo)
        env = {'RESTIC_REPOSITORY': repo, 'RESTIC_PASSWORD_FILE': str(profile / 'restic-password'),
               'AWS_DEFAULT_REGION': config.get('AWS_DEFAULT_REGION') or 'us-east-1',
               'AWS_ACCESS_KEY_ID': (profile / 's3-access-key').read_text().strip(),
               'AWS_SECRET_ACCESS_KEY': (profile / 's3-secret-key').read_text().strip()}
        result = subprocess.run(
            ['/usr/bin/restic', '--no-lock', '--no-cache', '--json', 'snapshots'],
            env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=30, check=False)
        if result.returncode:
            print(name, 'snapshot listing failed, exit', result.returncode)
            continue
        snapshots = json.loads(result.stdout) or []
        timestamps = [datetime.fromisoformat(s['time']).astimezone(UTC) for s in snapshots]
        print(name, 'snapshot count:', len(snapshots), 'latest UTC:', max(timestamps, default=None))
    except (OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired):
        print(name, 'snapshot listing unavailable')
if len(repos) == 2:
    print('Configured endpoints/prefixes distinct and nonoverlapping:',
          repos[0] != repos[1] and not any(x.startswith(y + '/') for x, y in (repos, repos[::-1])))
PY
```

## Final decision

1. **Is GTA V collecting correctly right now?** Unknown. The most recent counts are historical operator evidence.
2. **Is GTA VI collecting or correctly monitoring Twitch right now?** Unknown. The prior active process and filesystem activity did not establish successful discovery and healthy scheduling.
3. **Are both databases independent and intact?** The paths, account separation and category guards are distinct in the checkout. Production inode separation, category contents, foreign keys and integrity remain unverified.
4. **Will closing VS Code, SSH or the Windows PC stop them?** System services managed by the VPS's systemd continue independently of the client session. This applies if both services are running as reported. Confirm their VPS process ownership and cgroups in the first sample. [systemd service supervision](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html)
5. **What happens after a VPS reboot?** On the reported configuration, GTA V is expected to start if startup authorization and preflight succeed. GTA VI is not enabled for ordinary boot and needs another activation path or manual start. Crash restart policy and boot activation are separate. [systemctl unit enablement](https://www.freedesktop.org/software/systemd/man/latest/systemctl.html#enable%20UNIT%E2%80%A6)
6. **Are the two previous blockers resolved?** Both were fixed and tested offline in the local baseline. The installed revision remains UNKNOWN.
7. **Is unattended dual-collector 24/7 operation ready?** No. Reboot recovery for GTA VI, end-to-end backup safety, both monitor paths and live database health lack the needed evidence.
8. **What should happen next?** Run the `full` and `sample` read-only checks, compare both collectors and record UTC results. Treat any later changes, restore drills or reboot tests as separately authorized work.

**NO-GO for signing off on unattended dual-collector 24/7 operation.** GTA VI was reported disabled at boot. Current collection, integrity, backups, monitoring and the installed revision remain UNKNOWN. Keep the existing collectors running while gathering the missing evidence.
