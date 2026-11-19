# Milestone 1B controlled rollout on Windows

Process changes require explicit authorization. Run preflight in a second
PowerShell terminal from the repository root. Keep the original collector
terminal open. Reuse the existing database, category and environment.

## Preflight and backup

```powershell
uv run --no-sync viralclip health
$backup = 'data/backups/collector-' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') +
    '-' + [guid]::NewGuid().ToString('N').Substring(0,8) + '.sqlite3'
git check-ignore --quiet -- $backup
if ($LASTEXITCODE -ne 0) { throw 'Backup path must be ignored' }
uv run --no-sync python -B -m viralclip.storage.backup $backup
if ($LASTEXITCODE -ne 0) { throw 'Backup or restore verification failed' }
git check-ignore -- data/viralclip.sqlite3.http.jsonl data/viralclip.sqlite3.http.jsonl.3
```

The script opens the configured SQLite source read-only and uses the online
backup API. It refuses existing destinations. The restore drill uses a separate
temporary database under the destination directory and compares its counts,
job states, timestamps and relationships with the consistent backup. Keep the
validated backup local. A custom source can be selected with `--source PATH`.

Confirm workspace code and dependencies are ready, that there is room for both
backup files during the drill plus about 20 MiB of log retention, and that the
expected local log directory exists and is writable. Confirm the unchanged
credentials and category without printing their values. The commands below use
the default log path and the observed GTA V launch arguments.
If `uv` cannot access its cache, verify the existing environment before
stopping anything. The equivalent local launcher is
`.\.venv\Scripts\python.exe -B -m viralclip` followed by the same subcommand
and arguments. The backup can likewise run as
`.\.venv\Scripts\python.exe -B -m viralclip.storage.backup $backup`.

Set up a read-only measurement checkpoint in the second terminal. This also
finds the nearest recorded observations either side of a supplied UTC boundary.

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

The expected process listing is one launcher chain, possibly with several
rows. Record its PIDs. If inspection is unavailable, verify the original
chain has exited through Task Manager before launching.

## Authorized stop and restart

1. In the original collector terminal, press **Ctrl+C once**. Wait for its
   prompt and for all old collector PIDs to exit. In the second terminal run
   `Get-CollectorProcesses` and confirm no loop remains. Leave lock files alone.
2. Immediately before launch, record the boundary in the second terminal:

   ```powershell
   $launchUtc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.ffffff'Z'")
   ```

3. In the original terminal, from the same working directory and environment,
   start one foreground loop:

   ```powershell
   uv run --no-sync viralclip collect --game "Grand Theft Auto V" --loop
   ```

## Post-restart evidence

From the second terminal:

```powershell
Get-CollectorProcesses
uv run --no-sync viralclip health
Get-CollectorMarks $launchUtc
$launchTime = [DateTimeOffset]::Parse($launchUtc)
Get-Content data/viralclip.sqlite3.http.jsonl -Tail 100 |
    ConvertFrom-Json |
    Where-Object { [DateTimeOffset]$_.timestamp -ge $launchTime } |
    Select-Object timestamp, event, endpoint, status, outcome, reason, rate_limit_remaining
```

- Confirm one new chain, parseable post-start OAuth and Helix events, and a new
  successful discovery timestamp. Confirm due scheduled work produces new
  actual observations. A clip count can be unchanged during a successful poll.
- Check again after one normal discovery interval and at ten minutes. Inspect
  whether overdue jobs drain and whether failed jobs or recurring errors appear.
  Record the observed gap and any late or unavailable outcomes. The gap measures
  time between observations and also includes normal polling time.
- Verify the JSONL records contain only the documented fields. Record naturally
  observed retries, waits and renewals when they occur. A quiet interval leaves
  those live branches unverified.

## Failure handling

- If the old process has not exited or the collector reports a lock conflict,
  inspect process ownership and resolve the overlap before launching again.
- A valid collector with missing JSONL can indicate a disabled sink, an
  unexpected log directory, or filesystem/rotation errors. Check local path,
  permissions and free space. Schedule any corrective restart separately.
- If launch fails or health degrades persistently, capture sanitized errors and
  read-only health first. An authorized retry may disable telemetry for that
  launch only using `$env:VIRALCLIP_HTTP_LOG_DIR = 'off'` in the launch terminal
  and the same command after confirming the failed process is gone. If
  collection itself fails again, revert to a separately prepared known-good
  build with the same configuration after checking schema compatibility.
- If backup fails, retry with a fresh ignored destination after checking free
  space, locks and access. If restore verification fails, retain the artifact
  locally for diagnosis and defer rollout. Keep live SQLite in place during
  all rollout recovery and preserve missing intervals as gaps.
