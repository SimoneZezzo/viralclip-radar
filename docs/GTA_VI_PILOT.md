# GTA VI launch collector pilot

**Prepared for review.** Keep the existing GTA V service, unit, account, data
and credentials in place. Do not install or start this pilot before separate
authorization. The live authenticated name lookup and reverse ID lookup on
November 19, 2026 returned **Grand Theft Auto VI, 1867279146**. [Helix Get Games](https://dev.twitch.tv/docs/api/reference/games)

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
