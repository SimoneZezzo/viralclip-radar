# Linux VPS deployment and single-writer cutover

This is a staged runbook. Provisioning, installing on a real host and moving
production each require explicit authorization. Keep the Windows loop
collecting during VM setup and synthetic testing.

## Compatibility and capacity

Use Ubuntu 24.04 LTS on ARM64 or x86-64. Use its Python 3.12 and rebuild the
environment on the VM. The collector uses HTTPX, python-dotenv and standard
library SQLite. The locked runtime packages have portable wheels. Check the
dev tooling separately on the target. The Windows virtual environment is
host-specific. Verify DNS, UTC time sync, outbound HTTPS and the system CA
setup on the VM before any authorized live request.

SQLite uses WAL on the local disk and the Linux collector uses a nonblocking
`fcntl.flock` on a sibling lock file. Use a local filesystem, such as ext4.
Avoid network mounts, aliases and paths under `/home` for the service.
SQLite backup artifacts are portable across these CPUs when the destination
SQLite can read the schema. The unit sends SIGINT so the existing CLI uses
its Ctrl+C cleanup. systemd can forcibly stop a process that exceeds the
120-second shutdown timeout. Inspect the journal and database after such a
stop. Restart-on-failure and startup rate limiting handle crashes. A
still-running stalled collector requires a health check and operator review.
[systemd service semantics](https://freedesktop.org/software/systemd/man/latest/systemd.service.html)

The measured Windows worker used about 30 MiB of resident memory in a
point sample. A verified backup with 201,458 observations was 106,352,640
bytes, about 101 MiB after roughly 31 hours since the first observation.
That suggests about 80 MiB/day at the initial volume, with considerable
variation by game activity. Size for the OS, SQLite/WAL, two temporary
backup-sized files during a restore drill, and retained backups. A starting
estimate is 1 vCPU, 2 GiB RAM and 25–50 GiB of local disk. Re-measure actual growth and
peak memory before changing size, cadence or categories. The collector
needs only SSH administration and outbound DNS/HTTPS. SQLite, logs and
health stay local. There is no web server or separate database service.

### Provider

Production runs on an OVH Ubuntu VPS with 2 vCores, 4 GB RAM and 40 GB of
disk. Any other small Ubuntu 24.04 VPS with at least the starting resources
and local persistent storage works with the same SSH and installation
procedure; a provider change needs separate cost approval. Confirm included
disk, egress, backup charges and firewall rules with the provider. No
provider SDK, database or agent is required by the collector. The earlier
Oracle Always Free notes are preserved in Git
(`git show b10cf94:docs/LINUX_DEPLOYMENT.md`).

## Install on an authorized VM, with the service disabled

1. Verify the VM's SSH host key against the provider's trusted console.
   Check `uname -m`, `python3 --version`, `timedatectl status` and
   `df -h`. Install Ubuntu packages `python3 python3-venv ca-certificates`
   and `git` for the local tests. Obtain the official `uv` binary for the VM architecture. Record
   the version. Build from a reviewed source-only release made from the
   intended working tree. Include `src/`, `tests/`, `deploy/`,
   `pyproject.toml`, `uv.lock`, `.python-version` and `README.md`. Exclude
   `.env`, `.git`, `.venv`, `data/`, logs and bytecode. Transfer the release
   privately via SSH and record its SHA-256. The reviewed working tree
   may include changes absent from a Git HEAD archive.

   ```powershell
   $release = "data/viralclip-release-$([guid]::NewGuid().ToString('N')).tar.gz"
   tar.exe --exclude=__pycache__ --exclude='*.pyc' -czf $release pyproject.toml uv.lock .python-version README.md src tests deploy
   if ($LASTEXITCODE -ne 0) { throw 'Source archive creation failed' }
   Get-FileHash -Algorithm SHA256 -LiteralPath $release
   ```

   Check the archive listing before transferring it to the SSH account's
   private staging directory. Compare the uploaded file with `sha256sum`
   before extracting it.
2. On the VM, build with the reviewed release in a fresh
   `/opt/viralclip-radar` directory. Give the SSH administrator temporary
   ownership for the build. Run the tests in a VM-local environment
   with `uv sync --locked --python /usr/bin/python3` and
   `uv run --no-sync pytest`. Then install the runtime environment:

   ```bash
   set -eu
   : "${release:?set release to the verified source archive path}"
   test ! -e /opt/viralclip-radar
   sudo install -d -m 0755 -o "$(id -un)" -g "$(id -gn)" /opt/viralclip-radar
   tar -xzf "$release" -C /opt/viralclip-radar
   cd /opt/viralclip-radar
   uv sync --locked --python /usr/bin/python3
   uv run --no-sync pytest
   uv sync --locked --no-dev --no-editable --python /usr/bin/python3
   sudo chown -R root:root /opt/viralclip-radar
   sudo chmod -R a+rX,go-w /opt/viralclip-radar
   ```

3. Create a dedicated account and restricted directories. Use the template
   only on the Linux host and enter the existing credentials there with a
   protected editor. Never print or copy the live Windows `.env`. The unit
   reads a root-owned environment file and disables dotenv fallback.

   ```bash
   sudo useradd --system --user-group --home-dir /var/lib/viralclip-radar --no-create-home --shell /usr/sbin/nologin viralclip
   sudo install -d -o root -g root -m 0700 /etc/viralclip
   sudo install -d -o viralclip -g viralclip -m 0700 /var/lib/viralclip-radar
   sudo install -m 0600 deploy/collector.env.example /etc/viralclip/collector.env
   sudoedit /etc/viralclip/collector.env
   sudo install -m 0644 deploy/viralclip-collector.service /etc/systemd/system/viralclip-collector.service
   sudo systemd-analyze verify /etc/systemd/system/viralclip-collector.service
   sudo systemctl daemon-reload
   ```

Keep the unit disabled and `/etc/viralclip/production-authorized` absent.
The root-owned marker is a local guard against accidental activation,
with no cross-host locking effect. Rehearse transfer validation using a
synthetic DB in a separate path. Verify systemd launch/restart/SIGINT behavior
on a harmless test process before authorizing the production handoff. The
service startup guard requires the approved existing path and schema v2,
credentials, 300-second discovery, 30-minute lookback and no extra category IDs.
The unit passes the same explicit GTA V category as Windows.

## Production cutover, only after separate authorization

1. Confirm Linux is inactive and disabled, its state path is empty, its
   production marker is absent and its target configuration matches Windows.
   Verify a recent backup/restore, current Windows health, and the current
   single collector chain. Record latest discovery and observation timestamps.
2. **Stop Windows first.** Press Ctrl+C in its original terminal. Wait for
   cleanup and verify the entire old process chain has exited. Confirm no
   scheduled task or other mechanism will restart it. Leave Windows stopped
   throughout transfer and Linux operation. If ownership is uncertain, abort.
3. Take the **final** backup only after Windows has stopped. The backup helper
   uses SQLite's online backup API, includes committed WAL data and verifies
   a temporary restore. The transfer manifest adds SHA-256, counts, latest
   observation, schema, validated links and outstanding jobs by target.
   Use an unused ignored destination:

   ```powershell
   $python = '.\.venv\Scripts\python.exe'
   $backup = "data/backups/final-windows-$([guid]::NewGuid().ToString('N')).sqlite3"
   git check-ignore --quiet -- $backup
   if ($LASTEXITCODE -ne 0) { throw 'Backup path must be ignored' }
   & $python -B -m viralclip.storage.backup --source data/viralclip.sqlite3 $backup
   if ($LASTEXITCODE -ne 0) { throw 'Final backup or restore verification failed' }
   $lines = & $python -B -m viralclip.deployment manifest $backup
   if ($LASTEXITCODE -ne 0) { throw 'Transfer manifest failed' }
   $lines | Set-Content -Encoding ascii "$backup.json"
   ```

4. Transfer **only the closed standalone backup and its manifest** over
   SSH into a private, mode-0700 staging directory. Never transfer the live
   main file, WAL, SHM or lock file by filesystem copy. On Linux, set
   `incoming` to the received standalone DB and `manifest` to its JSON.
   Verify the staged artifact, install it without replacing another file
   and verify the installed copy. Keep the incoming backup for rollback
   until acceptance. Run in an SSH shell that stops on failure:

   ```bash
   set -eu
   app=/opt/viralclip-radar/.venv/bin/python
   db=/var/lib/viralclip-radar/viralclip.sqlite3
   : "${incoming:?set incoming to the received backup path}"
   : "${manifest:?set manifest to the received JSON path}"
   "$app" -B -m viralclip.deployment verify "$incoming" "$manifest"
   sudo sh -eu -c '
       db=$1
       for path in "$db" "$db-wal" "$db-shm" "$db-journal" "$db.collector.lock"; do
           if [ -e "$path" ] || [ -L "$path" ]; then
               echo "Existing database or sidecar; abort installation" >&2
               exit 1
           fi
       done
       stage=$(mktemp "${db}.incoming.XXXXXX")
       trap '\''rm -f -- "$stage"'\'' EXIT
       install -o viralclip -g viralclip -m 0600 -- "$2" "$stage"
       ln -T -- "$stage" "$db"
   ' sh "$db" "$incoming"
   sudo "$app" -B -m viralclip.deployment verify "$db" "$manifest"
   ```

   These comparisons verify the artifact and its deployed bytes, SQLite
   integrity and foreign keys, snapshot links, job states and timestamps.
   SQLite uses DELETE journaling for the transfer file. The normal collector
   opens it in WAL mode on first start. Avoid `init-db` as a migration step.

5. Reconfirm Windows is stopped and remains disabled. Record UTC launch time,
   then create the authorization marker and start exactly the one unit:

   ```bash
   date -u +%FT%T.%NZ
   sudo install -m 0600 /dev/null /etc/viralclip/production-authorized
   sudo systemctl enable --now viralclip-collector.service
   ```

## Acceptance, health and backups

```bash
sudo systemctl show viralclip-collector.service -p ActiveState -p SubState -p MainPID -p NRestarts
sudo journalctl -u viralclip-collector.service -n 50 --no-pager
sudo -u viralclip env PYTHON_DOTENV_DISABLED=1 /opt/viralclip-radar/.venv/bin/python -B -m viralclip --db /var/lib/viralclip-radar/viralclip.sqlite3 health
sudo tail -n 15 /var/lib/viralclip-radar/viralclip.sqlite3.http.jsonl
df -h /var/lib/viralclip-radar
sudo du -sh /var/lib/viralclip-radar
sudo journalctl --disk-usage
```

Confirm one collecting PID, fresh OAuth/Helix JSONL, a new completed
discovery and new scheduled observations. Repeat after one discovery
interval and about ten minutes. Check overdue-job recovery, failed jobs,
genuine timestamps, clock sync and recurring restart counts. HTTP JSONL
rotates to roughly 20 MiB, and the unit rate-limits console logs. Use the
VM's journald storage limits and monitor disk usage. Investigate free
space below 20%, or sooner if two backup-sized files plus retention will
not fit. Run these commands over SSH. No monitoring ports are needed.

Set `last` to the manifest's `metrics.latest_observation_utc`. Measure the
gap using stored UTC snapshots:

```bash
sudo -u viralclip /opt/viralclip-radar/.venv/bin/python -B - "$last" <<'PY'
from contextlib import closing
from datetime import datetime
import sqlite3, sys

uri = "file:/var/lib/viralclip-radar/viralclip.sqlite3?mode=ro"
with closing(sqlite3.connect(uri, uri=True)) as db:
    db.execute("PRAGMA query_only=ON")
    first = db.execute(
        "SELECT MIN(observed_at) FROM clip_snapshots WHERE observed_at > ?", (sys.argv[1],)
    ).fetchone()[0]
if first is None:
    raise SystemExit("No post-transfer observation yet")
print("Last pre-transfer / first post-transfer:", sys.argv[1], first)
print("Observation gap seconds:", (datetime.fromisoformat(first) -
      datetime.fromisoformat(sys.argv[1])).total_seconds())
PY
```

Document the gap and late/unavailable jobs. This elapsed time includes
normal polling. Existing recovery takes actual current measurements and
does not recreate historical snapshots. Verify boot and native restart
later in separately approved drills.

Take periodic application-consistent backups while Linux runs, using the
already verified helper. Use a private off-server destination with
encrypted storage, transfer only closed artifacts over SSH, and verify
the manifest at the destination. Review retention against available
storage, for example seven daily and four weekly copies when capacity
permits. Provider volume backups can supplement this process. Rehearse
restoration regularly to a temporary path and verify hashes and
integrity. An online backup can fail if SQLite is busy for too long.
Check disk, repeat with a new filename and retain the last verified copy.

```bash
set -eu
sudo install -d -o viralclip -g viralclip -m 0700 /var/lib/viralclip-radar/backups
backup="/var/lib/viralclip-radar/backups/collector-$(date -u +%Y%m%dT%H%M%S)-$$.sqlite3"
sudo -u viralclip /opt/viralclip-radar/.venv/bin/python -B -m viralclip.storage.backup --source /var/lib/viralclip-radar/viralclip.sqlite3 "$backup"
umask 077
sudo -u viralclip /opt/viralclip-radar/.venv/bin/python -B -m viralclip.deployment manifest "$backup" > "$HOME/$(basename "$backup").json"
```

## Rollback

- **Before Linux collected any production data:** remove its authorization
  marker, disable/stop it and verify no Linux owner. Resume Windows from the
  unchanged original database. If Linux might have written anything, use
  the authoritative Linux rollback below.
- **After Linux collected:** remove its marker, disable and gracefully
  stop the unit, and verify no remaining owner. Generate and verify a final
  standalone Linux backup and manifest while it is stopped. Transfer it back
  privately and verify both before resuming Windows. Stage it under a new
  local ignored path, leave the old Windows DB archived in place, and launch
  exactly one Windows collector using `--db` on the newly verified copy.
  Record the new authoritative path and the gap. Resume Linux only after a
  new supervised handoff.
- If the authoritative Linux data is unreachable, keep Windows stopped
  while assessing recovery from the latest off-server backup. Resuming an
  older snapshot would lose later Linux records and needs an explicit
  loss decision. Keep any divergent copies separate for diagnosis.

```bash
sudo rm -f -- /etc/viralclip/production-authorized
sudo systemctl disable --now viralclip-collector.service
sudo systemctl show viralclip-collector.service -p ActiveState -p MainPID
```

The unit, transfer checker and synthetic rehearsal were prepared on
Windows. No Linux VM, native ARM64 runtime or live systemd deployment
has been verified. The checklist calls out the VM-only checks.
