# OVH production backup and monitoring

> **Closed on 2026-11-26.** The collectors are stopped and all collected data
> is deleted. This document is kept as a record of the design and procedures;
> any production state, date or count below is historical.

The backup rollout below is historical. The operator cancelled M1-02 and
waived the unmet off-VPS requirement of M1-01. Use the
[current collection and monitoring plan](MILESTONE_1_ROLLOUT.md#current-collection-and-monitoring-plan)
for present operations.

The original [dual-collector deployment checklist](DUAL_COLLECTOR_OPERATIONS.md)
records the planned backup and restore workflow.

This stack is separate from `viralclip-collector.service`. It reads the existing
database and writes backups and markers under
`/var/lib/viralclip-radar/backups`. Install it in `/opt/viralclip-ops` so
upgrades leave the collector's directory and environment alone.

## Destination and retention

- Use a private S3-compatible bucket and dedicated restic prefix outside the
  VPS and preferably outside the OVH account. The bucket must be reachable
  over HTTPS and support S3 list, read, write and delete operations used by
  restic and its locks. Scope credentials to that bucket and prefix. Keep a
  recovery copy of the repository URL, credentials or recovery access, and
  restic password outside the VPS. Client-side encryption uses the restic
  password. Losing it can prevent recovery. [Restic S3 setup](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html#s3-compatible-storage)
- Default retention is **two verified local copies**, **seven recent daily**
  and **four weekly** snapshots in the encrypted remote repository. Policies
  can overlap. Set retention in `backup.env`. Allow adequate bucket quota and
  check billed usage. Do not expire current restic objects with a bucket
  lifecycle policy. A scoped writer can still delete this repository;
  provider-side versioning or a separate immutable copy adds protection.
  Use a dedicated repository for this service. Retention prunes it after
  successful uploads. [Restic retention](https://restic.readthedocs.io/en/v0.16.5/060_forget.html)
- The daily timer runs at **03:30 UTC** and catches up a missed run. Each job
  uses the existing online SQLite backup and temporary restore check. It
  verifies integrity, foreign keys, schedule and link consistency, writes a
  manifest with SHA-256 and counts, then publishes the closed bundle locally.
  The offsite success marker advances only after restic reports success.
  Retention runs afterward. A failed upload leaves the verified local copy
  and the previous offsite marker in place. No pruning follows a failed upload.
  [systemd timer persistence](https://www.freedesktop.org/software/systemd/man/255/systemd.timer.html)
- The 40 GB VPS has a prior measured growth rate of **77–80 MB/day**, about
  **2.3–2.4 GB per 30 days** before OS, journals and backups. The backup job
  requires available bytes of at least the larger of **20% of actual filesystem
  capacity** or **2 × (DB + WAL size) + 1 GiB** for staging the copy and temporary
  restore. The monitor warns below that reserve and raises critical below
  **10% free**. Check growth weekly. Move older copies off-server and plan
  expansion before the reserve shrinks. A prolonged upload outage can retain
  more local copies. Keep the latest verified copies, inspect any abandoned
  `.incoming-*` directories after confirming the backup unit has stopped, and
  resolve the outage before the reserve is exhausted. Avoid touching live
  SQLite WAL/SHM files.

## Install only after deployment approval

Stage a reviewed source-only release in a private SSH directory. It must
include `src`, `deploy`, `tests`, `pyproject.toml`, `uv.lock`,
`.python-version` and `README.md`. Exclude production data, `.env`, Git
metadata and the Windows virtual environment. Verify the release checksum on
the VPS. With the existing `viralclip` service account and uv installed, use
these commands on the approved host. Set `release` to the verified archive.

```bash
set -eu
: "${release:?set release to the verified archive path}"
sudo apt-get install -y restic ca-certificates
restic version
test ! -e /opt/viralclip-ops
sudo install -d -m 0755 -o "$(id -un)" -g "$(id -gn)" /opt/viralclip-ops
tar -xzf "$release" -C /opt/viralclip-ops
cd /opt/viralclip-ops
export UV_LINK_MODE=copy
uv sync --locked --python /usr/bin/python3
uv run --no-sync pytest tests/test_operations.py tests/test_backup.py tests/test_deployment.py
uv sync --locked --no-editable --no-dev --python /usr/bin/python3
sudo chown -R root:root /opt/viralclip-ops
sudo chmod -R a+rX,go-w /opt/viralclip-ops
sudo install -d -o root -g root -m 0700 /etc/viralclip/ops
sudo install -d -o viralclip -g viralclip -m 0700 /var/lib/viralclip-radar/backups
sudo install -d -o viralclip -g viralclip -m 0700 /var/lib/viralclip-radar/restore-drills
sudo install -o root -g root -m 0600 deploy/backup.env.example /etc/viralclip/ops/backup.env
for name in s3-access-key s3-secret-key restic-password alert-url; do
    sudo test ! -e "/etc/viralclip/ops/$name"
    sudo install -o root -g root -m 0600 /dev/null "/etc/viralclip/ops/$name"
done
sudoedit /etc/viralclip/ops/backup.env
sudoedit /etc/viralclip/ops/s3-access-key /etc/viralclip/ops/s3-secret-key /etc/viralclip/ops/restic-password
sudoedit /etc/viralclip/ops/alert-url
```

Fill `backup.env` with the repository endpoint, bucket/prefix, region and
retention. Keep each credential file as one secret value, separate from
Twitch configuration. Leave `alert-url` empty for journal-only monitoring,
or use a private HTTPS heartbeat URL from a service supporting POST and
`/fail`. For this five-minute cadence, configure an external missed-heartbeat
grace period around 15 minutes, and test that the notification actually
arrives. Only the status word is sent. Keep the tokenized URL private.
These are first-install commands. Preserve existing credential files when
upgrading.

Initialize the encrypted repository once. The same transient-unit helper
also supports verification and restore drills. If the repository already
exists, use `check-remote` and confirm the expected bucket and identity.

```bash
ops_remote() {
    sudo systemd-run --wait --pipe --collect \
        -p User=viralclip -p Group=viralclip -p UMask=0077 \
        -p EnvironmentFile=/etc/viralclip/ops/backup.env \
        -p LoadCredential=s3-access-key:/etc/viralclip/ops/s3-access-key \
        -p LoadCredential=s3-secret-key:/etc/viralclip/ops/s3-secret-key \
        -p LoadCredential=restic-password:/etc/viralclip/ops/restic-password \
        /opt/viralclip-ops/.venv/bin/python -B -m viralclip.operations "$@"
}
ops_remote init-remote
ops_remote check-remote
```

Install just the two new service/timer pairs. Run one backup, inspect its
result, then try the monitor before enabling the timers. The monitor may
return code 1 during a cutover lateness window. Inspect the reported reason.

```bash
cd /opt/viralclip-ops
for unit in viralclip-backup.service viralclip-backup.timer viralclip-monitor.service viralclip-monitor.timer; do
    sudo install -m 0644 "deploy/$unit" "/etc/systemd/system/$unit"
done
sudo systemd-analyze verify /etc/systemd/system/viralclip-{backup,monitor}.{service,timer}
sudo systemctl daemon-reload
sudo systemctl start viralclip-backup.service
sudo journalctl -u viralclip-backup.service -n 25 --no-pager
sudo systemctl start viralclip-monitor.service
sudo journalctl -u viralclip-monitor.service -n 45 --no-pager
```

After confirming the first backup and reviewing any monitor warnings:

```bash
sudo systemctl enable --now viralclip-backup.timer viralclip-monitor.timer
sudo systemctl list-timers viralclip-backup.timer viralclip-monitor.timer
sudo systemctl show viralclip-collector.service -p ActiveState -p SubState -p MainPID
```

Expected: a local verified bundle, successful encrypted upload, and two
scheduled timers. Compare collector PID before and after. If the backup
fails, inspect the sanitized exit code and check endpoint, credentials and
disk space before retrying. Retain the verified local backup. The hardening
in the backup unit makes the collector state read-only outside the backup
directory. Verify that Ubuntu's SQLite can open the running WAL in that
namespace during the first approved backup. A WAL access error requires
diagnosis rather than a collector restart or a live sidecar copy.

## Monitoring and restore

The monitor uses the read-only health command's checks for successful
discovery age, overdue jobs, operational errors and scheduled P95 lateness.
It checks the collector service and PID, last backup unit result, database
and WAL size, free space, and local/offsite backup timestamps. A verified
daily backup is the integrity gate. The monitor avoids running a full SQLite
integrity scan against production every five minutes.

Journal severity and return codes are 0 HEALTHY, 1 DEGRADED, 2 CRITICAL.
The external heartbeat sends a fail ping for either alert level and a normal
ping for healthy. An unavailable collector or DB, missing backup marker,
less than 10% disk free, or backup age beyond 48 hours is critical. A failed
backup, disk below the reserve, or age beyond 30 hours is at least degraded.
A cutover can elevate P95 until late observations roll out of the existing
one-hour window. Check that discovery and observations advance and no
backlog or failures accumulate. Monitoring never restarts the collector.

For a restore drill, run the helper in a separate service invocation,
preferably on an independent recovery host with enough storage. Use an
empty destination with room for about three copies of the SQLite file.
Do not use the production state path as the drill destination.

```bash
ops_remote check-remote
drill="/var/lib/viralclip-radar/restore-drills/$(date -u +%Y%m%dT%H%M%SZ)-$$"
ops_remote restore-latest "$drill" --expected-game-id 32982
```

For GTA VI use its own repository profile and `--expected-game-id 1867279146`.
Choose the expected ID from the collector being recovered. The current backup
units also pin that ID when creating a bundle. New manifests record the game
ID and the verifier checks it against both the expected ID and the SQLite
contents. Legacy version 1 manifests remain supported when SQLite proves one
matching category through clip records or a successful discovery, including a
successful discovery with zero clips. Empty databases, seed-only category
rows, mixed categories or conflicting manifest metadata fail verification.

On success, the stored SHA-256, row counts, schema, jobs and links also verify.
A new rehearsal copy and temporary restore pass after validation. Record the
tested observation timestamp and recovery time. Repeat monthly and after
credential or repository changes.

The existing Restic host/tag selectors still locate legacy bundles. Keep the
repositories separate as described in the dual-collector runbook. The restore
command rejects a wrong-game bundle selected from a misconfigured repository.
For an already available standalone bundle, verify locally without a remote
restore using `python -m viralclip.deployment verify /path/viralclip.sqlite3
/path/manifest.json --expected-game-id 32982` with the correct ID for the game.

`check-remote` checks repository structure. The restore drill exercises
actual data reads, and periodic `restic check --read-data` from the recovery
host can check all encrypted blobs if the storage and transfer budget permits.
[Restic integrity checks](https://restic.readthedocs.io/en/v0.16.5/045_working_with_repos.html)

For an actual recovery, stop and exclude the current production owner with
explicit authorization, keep its data and WAL/SHM intact for diagnosis, and
restore to a fresh path. Compare the backup watermark to the last known
production observation and obtain an explicit loss decision if the backup
is older. Follow the [single-writer cutover and rollback procedure](LINUX_DEPLOYMENT.md#production-cutover-only-after-separate-authorization)
for verification and controlled startup. Keep divergent databases separate.
Record any observation gap. Backup and monitoring timers can be removed or
disabled independently of the collector.

```bash
sudo systemctl disable --now viralclip-backup.timer viralclip-monitor.timer
sudo systemctl show viralclip-collector.service -p ActiveState -p MainPID
```

An already running backup can finish after its timer is disabled. Inspect
its state before changing credentials or cleaning staging files.
