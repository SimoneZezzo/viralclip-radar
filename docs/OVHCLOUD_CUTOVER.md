# OVHcloud VPS-1 production checklist

Target: OVHcloud VPS-1 in Canada, Ubuntu 24.04 LTS, 2 vCores, 4 GB RAM and
40 GB SSD. Confirm the assigned image, architecture and disk in the OVHcloud
Control Panel. This checklist uses the existing
[Linux unit and security model](LINUX_DEPLOYMENT.md). Staging and cutover are
separate. **Leave Windows collecting until the cutover is explicitly authorized.**

## 1. Stage Linux while Windows continues collecting

**Windows PowerShell, repository root.** Set the SSH login from the OVHcloud
console. Verify the host key against the provider console on first connection.
Use an SSH key, restrict inbound TCP 22 to the operator's source address, and
keep all application ports closed. This example assumes a fresh VM.

```powershell
$Vps = 'ubuntu@REPLACE_WITH_VPS_ADDRESS'
$py = '.\.venv\Scripts\python.exe'
$release = "data/viralclip-release-$([guid]::NewGuid().ToString('N')).tar.gz"
tar.exe --exclude=__pycache__ --exclude='*.pyc' -czf $release pyproject.toml uv.lock .python-version README.md src tests deploy
if ($LASTEXITCODE -ne 0) { throw 'Release creation failed' }
tar.exe -tzf $release
Get-FileHash -Algorithm SHA256 -LiteralPath $release
ssh $Vps 'umask 077; install -d -m 0700 "$HOME/viralclip-stage"'
if ($LASTEXITCODE -ne 0) { throw 'SSH staging failed' }
scp $release "${Vps}:viralclip-stage/release.tar.gz"
if ($LASTEXITCODE -ne 0) { throw 'Release upload failed' }
ssh $Vps
```

Expected: the archive lists source, synthetic tests and deployment templates.
Check it excludes credentials, local databases, logs and virtual environments.
Keep the release and its printed hash. Shared staging uses the SSH account's
private home directory. Use a fresh stage or confirm any existing upload
belongs to this operation.

**Linux SSH shell.** Set `expected` to the SHA-256 printed on Windows. Obtain the
official uv binary for the VM architecture, then use the pinned project lock.

```bash
set -eu
uname -m
. /etc/os-release
printf '%s\n' "$PRETTY_NAME"
timedatectl status
df -h /
sudo apt-get update
sudo apt-get install -y python3 python3-venv ca-certificates curl git
python3 --version
curl -fsSLo "$HOME/viralclip-stage/uv-install.sh" https://astral.sh/uv/install.sh
# Review the official installer before running it as your SSH user.
sh "$HOME/viralclip-stage/uv-install.sh"
export PATH="$HOME/.local/bin:$PATH"
uv --version
expected='REPLACE_WITH_WINDOWS_RELEASE_SHA256'
printf '%s  %s\n' "${expected,,}" "$HOME/viralclip-stage/release.tar.gz" | sha256sum -c -
test ! -e /opt/viralclip-radar
sudo install -d -m 0755 -o "$(id -un)" -g "$(id -gn)" /opt/viralclip-radar
tar -xzf "$HOME/viralclip-stage/release.tar.gz" -C /opt/viralclip-radar
cd /opt/viralclip-radar
uv sync --locked --python /usr/bin/python3
uv run --no-sync pytest
uv sync --locked --no-dev --no-editable --python /usr/bin/python3
sudo chown -R root:root /opt/viralclip-radar
sudo chmod -R a+rX,go-w /opt/viralclip-radar
sudo useradd --system --user-group --home-dir /var/lib/viralclip-radar --no-create-home --shell /usr/sbin/nologin viralclip
sudo install -d -o root -g root -m 0700 /etc/viralclip
sudo install -d -o viralclip -g viralclip -m 0700 /var/lib/viralclip-radar
sudo install -o root -g root -m 0600 deploy/collector.env.example /etc/viralclip/collector.env
sudoedit /etc/viralclip/collector.env
sudo install -m 0644 deploy/viralclip-collector.service /etc/systemd/system/viralclip-collector.service
sudo systemd-analyze verify /etc/systemd/system/viralclip-collector.service
sudo systemctl daemon-reload
sudo systemctl show viralclip-collector.service -p ActiveState -p UnitFileState -p MainPID
sudo test ! -e /etc/viralclip/production-authorized
sudo test ! -e /var/lib/viralclip-radar/viralclip.sqlite3
```

Enter only the existing Twitch credentials with the protected editor. Keep
the template's explicit database/log paths, 300-second discovery interval,
30-minute lookback and empty extra category IDs. Expected: Ubuntu 24.04,
synchronized clock, Python 3.12, archive `OK`, all tests passing, no unit
verification errors, `inactive`, `disabled`, `MainPID=0`. Keep the service
disabled and the authorization marker absent. The test suite includes the
synthetic SQLite transfer and restore rehearsal. No production Twitch
credentials or dataset are needed by the tests.

## 2. Record the baseline and check storage

**Windows PowerShell.** Run the health command here before authorization and
again immediately before the handoff. Check only selected process metadata.

```powershell
& $py -B -m viralclip --db data/viralclip.sqlite3 health
if ($LASTEXITCODE -ne 0) { throw 'Review Windows health before cutover' }
function Get-CollectorChain {
    Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='uv.exe' OR Name='viralclip.exe'" -ErrorAction Stop |
        Where-Object { $_.CommandLine -match '(?i)viralclip.*\bcollect\b' } |
        Select-Object Name,ProcessId,ParentProcessId,CreationDate
}
$original = @(Get-CollectorChain)
$original
```

Expected: `HEALTHY` and one collector chain. Confirm the PIDs belong to the
original terminal and that no Windows supervision task or other restart mechanism
is enabled.
If process inspection is denied, resolve ownership before stopping anything.

**Linux SSH shell.** These storage commands are safe while the service is
disabled. Use actual available filesystem bytes for budgeting.

```bash
df -B1 /var/lib/viralclip-radar
findmnt -T /var/lib/viralclip-radar
sudo du -sh /var/lib/viralclip-radar
sudo journalctl --disk-usage
free -m
```

The Windows read on November 19 at 11:55:43 Europe/Rome measured a
**152,858,624-byte** SQLite database with a **4,231,272-byte** WAL and
**32,768-byte** SHM. SQLite reported WAL mode, 4,096-byte pages and no free
pages. The observed WAL size is a point sample. A stalled reader or heavier
write burst can increase it. Never remove live WAL or SHM files.

The recent growth estimate is roughly **77–80 MB/day**, or **2.3–2.4 GB per
30 days**, at the current volume. That puts the main database near **2.5 GB
in 30 days**, **7.1–7.4 GB in 90 days** and **14–15 GB in 180 days** if growth
continues linearly. This excludes Ubuntu, WAL, logs, staging and backup
copies. Use one recent verified local backup and retain seven daily and four
weekly copies off-server, budget permitting. A backup with the temporary
restore check needs room for **two additional database-sized files**. Keep
at least the larger of **20% free filesystem space** or **two current
database sizes plus 1 GB** available before backup. Track DB, WAL and free
space weekly, and plan disk expansion before that reserve is consumed.
Avoid holding analyst read transactions open against production.

## 3. Cut over only with explicit authorization

1. Confirm the unit remains disabled and inactive, its state DB path and
   marker are absent, and both hosts' clocks agree. Confirm a tested backup
   and enough free space on both machines. Record the preflight health output.
2. In the original Windows collector terminal press **Ctrl+C once**, wait
   for `Collection stopped.` and the prompt, then return to the PowerShell
   terminal used for preflight. Disable any Windows restart mechanism as
   part of the authorized handoff if one has since been enabled.
3. Take the final backup **only after all Windows collector PIDs exit**.
   Keep the original Windows database and its files in place.

```powershell
$oldIds = @($original | ForEach-Object { $_.ProcessId })
if ($oldIds.Count -eq 0) { throw 'Original collector ownership is unverified' }
if (Get-Process -Id $oldIds -ErrorAction SilentlyContinue) { throw 'Old process remains' }
if (@(Get-CollectorChain).Count -ne 0) { throw 'A collector is still present' }
$backup = "data/backups/final-windows-$([guid]::NewGuid().ToString('N')).sqlite3"
git check-ignore --quiet -- $backup
if ($LASTEXITCODE -ne 0) { throw 'Backup must be Git-ignored' }
& $py -B -m viralclip.storage.backup --source data/viralclip.sqlite3 $backup
if ($LASTEXITCODE -ne 0) { throw 'Backup or test restore failed' }
$lines = & $py -B -m viralclip.deployment manifest $backup
if ($LASTEXITCODE -ne 0) { throw 'Transfer manifest failed' }
$lines | Set-Content -Encoding ascii -LiteralPath "$backup.json"
& $py -B -m viralclip.deployment verify $backup "$backup.json"
if ($LASTEXITCODE -ne 0) { throw 'Final local verification failed' }
$id = [IO.Path]::GetFileName($backup)
scp $backup "$backup.json" "${Vps}:viralclip-stage/"
if ($LASTEXITCODE -ne 0) { throw 'Transfer failed; leave Linux disabled' }
$id
```

Expected: backup and temporary restore pass integrity, foreign-key and
relationship checks. The manifest contains schema v2, actual last observation,
row counts and outstanding jobs by target. Transfer only these two closed
artifacts. A local file lock cannot coordinate the two hosts.

**Linux SSH shell.** Set `id` to the exact filename printed by Windows. Install
only after validating the incoming artifact. The hard-link operation makes the
final name exclusively and the trap removes the temporary name.

```bash
set -eu
id='REPLACE_WITH_FINAL_WINDOWS_BACKUP_BASENAME'
app=/opt/viralclip-radar/.venv/bin/python
db=/var/lib/viralclip-radar/viralclip.sqlite3
incoming="$HOME/viralclip-stage/$id"
manifest="$incoming.json"
"$app" -B -m viralclip.deployment verify "$incoming" "$manifest"
sudo sh -eu -c '
    db=$1
    for path in "$db" "$db-wal" "$db-shm" "$db-journal" "$db.collector.lock"; do
        if [ -e "$path" ] || [ -L "$path" ]; then exit 1; fi
    done
    temp=$(mktemp "${db}.incoming.XXXXXX")
    trap '\''rm -f -- "$temp"'\'' EXIT
    install -o viralclip -g viralclip -m 0600 -- "$2" "$temp"
    ln -T -- "$temp" "$db"
' sh "$db" "$incoming"
sudo "$app" -B -m viralclip.deployment verify "$db" "$manifest"
sudo systemctl show viralclip-collector.service -p ActiveState -p UnitFileState -p MainPID
sudo test ! -e /etc/viralclip/production-authorized
```

Expected: **both** verification commands report that transfer matches and
integrity and relationship checks pass. The installed bytes are identical
to the verified Windows standalone backup, preserving all snapshots, jobs,
clips, and checkpoints. The standalone transfer uses DELETE journal mode.
The collector opens the installed copy in WAL on startup. Do not initialize
an empty destination or run a probe collector.

**Reconfirm Windows remains stopped before running this final start block.**

```bash
set -eu
date -u +%FT%T.%NZ
sudo install -o root -g root -m 0600 /dev/null /etc/viralclip/production-authorized
sudo systemctl enable --now viralclip-collector.service
```

## 4. Verify after startup and define acceptance

Run these checks after start, after one discovery cycle, and at about ten
minutes. Recheck during the next day to establish sustained collection.

```bash
app=/opt/viralclip-radar/.venv/bin/python
db=/var/lib/viralclip-radar/viralclip.sqlite3
sudo systemctl show viralclip-collector.service -p ActiveState -p SubState -p MainPID -p NRestarts -p UnitFileState
sudo journalctl -u viralclip-collector.service -n 50 --no-pager
sudo -u viralclip env PYTHON_DOTENV_DISABLED=1 "$app" -B -m viralclip --db "$db" health
sudo tail -n 15 "$db.http.jsonl"
sudo stat -c '%n %s bytes' "$db" "$db-wal" "$db-shm"
df -h /var/lib/viralclip-radar
```

Expected: `active`, `running`, one nonzero collector PID, enabled unit,
fresh sanitized OAuth/Helix JSONL, advancing discovery and scheduled
observations, and `HEALTHY` as overdue work settles. Check unexpected job
failures, repeated restarts, operational errors and abnormal WAL growth.

Set `manifest` to the final Windows manifest retained in private SSH staging
if this is a new shell. Measure the gap and verify WAL mode read-only.

```bash
last=$("$app" -B -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["metrics"]["latest_observation_utc"])' "$manifest")
sudo -u viralclip "$app" -B - "$db" "$last" <<'PY'
from contextlib import closing
from datetime import datetime
from pathlib import Path
import sqlite3, sys

uri = Path(sys.argv[1]).resolve().as_uri() + "?mode=ro"
last = sys.argv[2]
with closing(sqlite3.connect(uri, uri=True, timeout=2)) as db:
    db.execute("PRAGMA query_only = ON")
    db.execute("BEGIN")
    mode = db.execute("PRAGMA journal_mode").fetchone()[0]
    first = db.execute(
        "SELECT MIN(observed_at) FROM clip_snapshots WHERE observed_at > ?", (last,)
    ).fetchone()[0]
    if mode != "wal" or first is None:
        raise SystemExit("Need WAL and a post-transfer observation before acceptance")
    print("Last Windows / first Linux observation UTC:", last, first)
    print("Observation gap seconds:", (datetime.fromisoformat(first) -
          datetime.fromisoformat(last)).total_seconds())
    print("Gap-due jobs (state, count, snapshot links):", db.execute(
        "SELECT status, COUNT(*), COUNT(snapshot_id) FROM jobs "
        "WHERE due_at > ? AND due_at <= ? GROUP BY status", (last, first)
    ).fetchall())
PY
```

Record the interval and any missed, late or unavailable jobs. The measurement
gap includes normal polling time. Never backfill observations.

**Accept Linux as production-ready** after the verified transfer, one writer,
stable follow-up health and growing observations, sufficient disk reserve,
and a successful independent backup and test restore. Confirm enablement
immediately, and validate actual reboot startup and failure restart in a
later authorized drill. Until that drill, describe those behaviors as configured.

## 5. Daily backup and independent verification

From the Linux SSH shell, make an application-consistent backup with the
existing helper. Use an unused filename each time. Transfer and verify it
before pruning any previous local verified backup. The temporary restore
performed by the helper is included in the free-space estimate above.

```bash
set -eu
umask 077
app=/opt/viralclip-radar/.venv/bin/python
db=/var/lib/viralclip-radar/viralclip.sqlite3
export_dir="$HOME/viralclip-stage"
sudo install -d -o viralclip -g viralclip -m 0700 /var/lib/viralclip-radar/backups
name="linux-$(date -u +%Y%m%dT%H%M%SZ)-$$.sqlite3"
backup="/var/lib/viralclip-radar/backups/$name"
sudo -u viralclip "$app" -B -m viralclip.storage.backup --source "$db" "$backup"
sudo -u viralclip "$app" -B -m viralclip.deployment manifest "$backup" > "$export_dir/$name.json"
sudo install -o "$(id -un)" -g "$(id -gn)" -m 0600 "$backup" "$export_dir/$name"
printf '%s\n' "$name"
```

On Windows or another independent backup host, use an encrypted private
destination. This Windows example assumes the repository's ignored
`data/offsite/` lives on encrypted storage. Run the daily procedure manually
until an independently approved schedule is in place. Keep the included
provider image backup as an additional recovery option.

```powershell
$name = 'REPLACE_WITH_LINUX_BACKUP_BASENAME'
New-Item -ItemType Directory -Force data/offsite | Out-Null
git check-ignore --quiet -- "data/offsite/$name"
if ($LASTEXITCODE -ne 0) { throw 'Off-server destination must be ignored' }
if ((Test-Path "data/offsite/$name") -or (Test-Path "data/offsite/$name.json")) { throw 'Use a fresh destination' }
scp "${Vps}:viralclip-stage/$name" "${Vps}:viralclip-stage/$name.json" data/offsite/
if ($LASTEXITCODE -ne 0) { throw 'Off-server transfer failed' }
& $py -B -m viralclip.deployment verify "data/offsite/$name" "data/offsite/$name.json"
if ($LASTEXITCODE -ne 0) { throw 'Off-server verification failed' }
```

Expected: verified transfer, hashes and integrity. After verification,
retain one recent verified local backup, remove redundant SSH staging
copies by exact filename, and keep seven daily and four weekly verified
off-server copies as a starting retention policy. Never prune the only
verified copy. Rehearse restore from the off-server copy regularly with
`viralclip.storage.backup --source <verified-backup> <new-scratch-file>`.

## 6. Rollback

```bash
sudo rm -f -- /etc/viralclip/production-authorized
sudo systemctl disable --now viralclip-collector.service
sudo systemctl show viralclip-collector.service -p ActiveState -p MainPID -p UnitFileState
sudo ps -u viralclip -o pid,args
```

Proceed only after Linux is inactive, disabled, with `MainPID=0` and no
collector owner. If Linux may have collected any production data, repeat
section 5 with Linux stopped to obtain its **final** verified backup. In
PowerShell, use that new backup and leave the original Windows DB archived.

```powershell
$name = 'REPLACE_WITH_VERIFIED_FINAL_LINUX_BACKUP_BASENAME'
$authoritative = "data/offsite/$name"
& $py -B -m viralclip.deployment verify $authoritative "$authoritative.json"
if ($LASTEXITCODE -ne 0) { throw 'Do not restart Windows against an unverified copy' }
& $py -B -m viralclip --db $authoritative collect --game "Grand Theft Auto V" --loop
```

If you have verified Linux never wrote production state, resume Windows
against the original `data/viralclip.sqlite3` instead. If Linux data is
unreachable, keep Windows stopped while recovering the newest verified
backup. Resuming an older copy risks data loss and requires an explicit
decision. Keep divergent backups separate. There is no automatic merge.
