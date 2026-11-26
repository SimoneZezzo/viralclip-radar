# Windows 11 collector supervision

> **Closed on 2026-11-26.** The collectors are stopped and all collected data
> is deleted. This document is kept as a record of the design and procedures;
> any production state, date or count below is historical.

The supervised task is staged disabled. The project commands below generate an
XML file or work with a local pause marker. Registration, enablement and the
handoff from the foreground collector require a separately approved rollout.

## Design

| Approach | Tradeoff |
| --- | --- |
| Startup shortcut or logon script | Simple interactive setup. Startup waits for logon and offers no built-in crash restart policy. |
| Task Scheduler with a boot trigger | Starts before logon under the operator's account and provides bounded restart policy, instance policy and task results. |
| Windows service wrapper | Can offer service-specific controls, but adds an installation, service account and integration work. |

Use Task Scheduler. The definition delays its boot action by 30 seconds, runs
with least privilege, retries a failed task up to three times at one-minute
intervals, ignores another start of the same task, and has no task execution
time limit. The battery flags permit a run on battery and the task never
requests wake. A boot trigger, the password logon mode, and the scheduler
settings are described by Microsoft. [Boot trigger](https://learn.microsoft.com/en-us/windows/win32/taskschd/boottrigger),
[account logon modes](https://learn.microsoft.com/en-us/windows/win32/taskschd/principal-logontype),
[task definition schema](https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-schema).

The runner uses the existing virtual environment and collector entry point,
with the same explicit GTA V category and approved local database path. Before
opening the collector it checks the configured path, credentials presence,
single-game configuration, interval, lookback, WAL mode and applied schema
without a database writer. The runner also refuses a checkout with pending
new migrations relative to its approved schema. The existing database
byte-range lock remains the guard across the foreground and supervised
launchers. A competing collector is rejected before discovery or Twitch
requests. Use one canonical local path and leave the lock file in place.

The runner uses a persistent pause marker and raises the same Python
interrupt as a foreground Ctrl+C when it sees the marker. Normal collector
cleanup runs. It may take time to return from blocking HTTP or a rate-limit
sleep. A failed or unexpected exit returns nonzero to Task Scheduler. A
deliberate pause returns zero and survives reboot. Task Scheduler restarts a
crashed process, while an alive but stalled collector requires investigation
via read-only health. A power loss, sleep or delayed restart can still cause
unrecoverable gaps. Overdue work follows the collector's existing recovery
rules and retains its actual later observation times. No watchdog kills a
running process.

## Offline preparation

From the repository root, use the SID of the same Windows account that owns
the current collector. For the observed default database and timing:

```powershell
$python = '.\.venv\Scripts\python.exe'
$db = (Resolve-Path 'data/viralclip.sqlite3').Path
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& $python -B -m viralclip.windows_supervision --db $db prepare --sid $sid --game "Grand Theft Auto V" --interval 300 --lookback 30 --output data/supervision/windows-task
```

This writes `collector.xml` under the new ignored directory and performs no
Windows registration or SQLite access. The XML contains local paths and the
account SID. Keep it local. It contains no password, Twitch credentials or
environment contents.

## Read-only checks and verified backup

Run these from a second PowerShell terminal at the repository root while the
existing collector keeps running. Process changes require explicit
authorization.

```powershell
uv run --no-sync viralclip health
$backup = 'data/backups/collector-' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') +
    '-' + [guid]::NewGuid().ToString('N').Substring(0,8) + '.sqlite3'
git check-ignore --quiet -- $backup
if ($LASTEXITCODE -ne 0) { throw 'Backup path must be ignored' }
uv run --no-sync python -B -m viralclip.storage.backup $backup
if ($LASTEXITCODE -ne 0) { throw 'Backup or restore verification failed' }
```

The backup opens the configured SQLite source read-only, uses the online
backup API and refuses existing destinations. Its restore drill writes a
separate temporary database under the destination directory and compares
counts, job states, timestamps and relationships with the backup. Select
another source with `--source PATH`. If `uv` cannot access its cache, use
`.\.venv\Scripts\python.exe -B -m viralclip` or
`.\.venv\Scripts\python.exe -B -m viralclip.storage.backup` instead.

These helpers record collection progress and the collector process chain.
Pass a UTC launch boundary to `Get-CollectorMarks` after a restart to measure
the observation gap around it.

```powershell
function Get-CollectorMarks([string]$Boundary = 'none') {
@'
import sqlite3, sys
from contextlib import closing
from datetime import datetime
from viralclip.config import load_settings

uri = load_settings().db_path.resolve().as_uri() + "?mode=ro"
with closing(sqlite3.connect(uri, uri=True, timeout=2)) as db:
    db.execute("PRAGMA query_only = ON")
    db.execute("BEGIN")
    for label, sql in [
        ("Latest successful discovery", "SELECT MAX(finished_at) FROM collection_runs "
         "WHERE status='completed' AND potentially_truncated=0 AND error_summary IS NULL"),
        ("Observations", "SELECT COUNT(*) FROM clip_snapshots"),
        ("Latest observation", "SELECT MAX(observed_at) FROM clip_snapshots"),
        ("Scheduled observations", "SELECT COUNT(*) FROM clip_snapshots WHERE source='scheduled'"),
        ("Latest scheduled observation", "SELECT MAX(observed_at) FROM clip_snapshots "
         "WHERE source='scheduled'"),
    ]:
        print(label, db.execute(sql).fetchone()[0])
    if sys.argv[1] != "none":
        before, after = db.execute(
            "SELECT MAX(CASE WHEN observed_at < ? THEN observed_at END), "
            "MIN(CASE WHEN observed_at >= ? THEN observed_at END) FROM clip_snapshots",
            (sys.argv[1], sys.argv[1]),
        ).fetchone()
        print("Last observation before launch boundary", before)
        print("First observation after launch boundary", after)
        if before and after:
            print("Observed measurement gap in seconds",
                  (datetime.fromisoformat(after) - datetime.fromisoformat(before)).total_seconds())
'@ | .\.venv\Scripts\python.exe -B - $Boundary
}

function Get-CollectorProcesses {
    Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='uv.exe' OR Name='viralclip.exe'" -ErrorAction Stop |
        Where-Object { $_.CommandLine -match '(?i)viralclip.*\bcollect\b.*--loop' } |
        Select-Object Name, ProcessId, ParentProcessId, CreationDate
}

Get-CollectorMarks
Get-CollectorProcesses
```

If a backup fails, retry with a fresh ignored destination after checking free
space, locks and access. If restore verification fails, keep the artifact for
diagnosis and leave the live database in place.

## Proposed production activation checklist

1. **Before approval**, choose a handoff window and confirm the unchanged
   configuration is available under the task account, including any environment
   values supplied by the foreground shell. Verify the account can access the
   repository, installed Python environment, local database and writable logs.
   Verify a recent online backup and restore drill, free space, current
   `HEALTHY` status and the original single process chain. Record the latest
   discovery, scheduled snapshot and overdue jobs using the
   [read-only checks](#read-only-checks-and-verified-backup).
2. **After explicit approval**, open Task Scheduler and import
   `data/supervision/windows-task/collector.xml` as
   **ViralClip Radar Collector**. Confirm the task is **Disabled**, has the
   approved account, boot trigger and single-instance policy, and is set to
   run whether the user is logged on or not. Supply the Windows account
   password only in the Windows prompt. A Windows Hello PIN or the S4U
   no-password option is unsuitable for this network collector. If account
   rights or registration fail, leave the foreground collector in place and
   resolve the blocker before continuing.
3. Run the preflight and health commands below. Confirm the task remains
   disabled and the marker is clear. Press **Ctrl+C once** in the original
   collector terminal and wait for its prompt and for the verified process
   chain to exit. If any owner remains, stop the rollout. Record the launch
   boundary, enable the task and start it exactly once:

   ```powershell
   $task = 'ViralClip Radar Collector'
   $launchUtc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.ffffff'Z'")
   Enable-ScheduledTask -TaskName $task -ErrorAction Stop
   Start-ScheduledTask -TaskName $task -ErrorAction Stop
   ```

4. Confirm one new process chain, lifecycle startup, fresh HTTP JSONL events,
   a successful discovery and scheduled observations. Recheck health and
   overdue jobs after one normal discovery interval and at about ten minutes.
   Measure the observation gap and document recovered, late or unavailable
   jobs. A first successful task run leaves boot and native restart behavior
   unverified. Plan a separate authorized reboot and crash-recovery drill.
5. **Rollback on failure:** request the persistent pause, disable the task to
   prevent future starts, and wait for the task and collector process chain to
   exit. Check task state, last result, lifecycle, HTTP logs and health. Only
   after confirming there is no owner, return to the previous foreground
   command with the same directory and configuration:

   ```powershell
   uv run --no-sync viralclip collect --game "Grand Theft Auto V" --loop
   ```

   Keep the task disabled and its pause marker in place until another approved
   attempt. If an exit cannot be verified, leave SQLite and the lock alone and
   diagnose ownership before any launch. Preserve the database and logs.

## Operator controls after activation

```powershell
$python = '.\.venv\Scripts\python.exe'
$db = (Resolve-Path 'data/viralclip.sqlite3').Path
$task = 'ViralClip Radar Collector'
& $python -B -m viralclip.windows_supervision --db $db preflight --interval 300 --lookback 30
& $python -B -m viralclip.windows_supervision --db $db state
& $python -B -m viralclip --db $db health
Get-ScheduledTask -TaskName $task | Select-Object TaskName,State
Get-ScheduledTaskInfo -TaskName $task | Select-Object LastRunTime,LastTaskResult
Get-Content -LiteralPath "$db.viralclip-supervision/lifecycle.jsonl" -Tail 20
```

Use task state, lifecycle and health together. A zero task result can mean a
deliberate pause while data stops advancing. The bounded lifecycle log retains
three files of roughly 512 KiB each. It records lifecycle events, sanitized
exception types and exit codes. The existing HTTP JSONL and read-only SQLite
health continue to describe Twitch and snapshot activity. Consult Task Scheduler
history if available for account or startup errors before Python runs.

For a planned stop, use the pause command and wait for the task and process
chain to exit. Avoid the Task Scheduler **End** action during ordinary operation.

```powershell
& $python -B -m viralclip.windows_supervision --db $db pause
```

After confirming exit and with authorization to resume, clear the marker,
enable the task if it was disabled, and start one task instance:

```powershell
& $python -B -m viralclip.windows_supervision --db $db resume
Enable-ScheduledTask -TaskName $task -ErrorAction Stop
Start-ScheduledTask -TaskName $task -ErrorAction Stop
```

Clearing the marker alone launches nothing. A password change, account policy,
inaccessible local files, missing dependencies or persistent crash can consume
the retry budget. Resolve the cause and verify task and process state before
restarting. Operational controls leave SQLite, the schedule and Twitch settings
in place.
