# Final operations rollout for GTA V and GTA VI

The backup and deployment instructions below record the original OVH
rollout. M1-02 is cancelled. Use the
[current collection and monitoring plan](MILESTONE_1_ROLLOUT.md#current-collection-and-monitoring-plan)
and the read-only checks below for present operations.

The read-only preflight can run on its own. The rollout sections require
separate deployment approval and install only operations units. The general
[backup and recovery guide](BACKUP_AND_MONITORING.md) describes restic
retention, health severities and the single-writer recovery rules.

## 0. Ubuntu read-only preflight

Run the [read-only health script](../deploy/dual-collector-health.sh) in the
existing authorized shell. From the repository root in Windows PowerShell,
prepare the script for the clipboard. Paste the generated block into the
Ubuntu shell and keep that shell for any later rollout gates.

```powershell
$healthScript = (Get-Content -Raw -LiteralPath .\deploy\dual-collector-health.sh).Replace("`r`n", "`n").TrimEnd()
@('health_both() {', "    bash -s <<'VIRALCLIP_HEALTH'", $healthScript, 'VIRALCLIP_HEALTH', '}', 'health_both', '') -join "`n" | Set-Clipboard
```

If the reviewed checkout is already available on Ubuntu, define the same
command using its absolute path to the script and run it.

```bash
health_both() { bash /path/to/reviewed/checkout/deploy/dual-collector-health.sh; }
health_both
```

The commands open both databases read-only. Both results are printed before the combined command returns `0`
for two passes or `1` if either check returned nonzero. The report prints each
original exit code. Health code `1` is DEGRADED and the gate labels `2` or
higher as FAILED. Stop the rollout if either check returns nonzero.

Use the [phase 0 read-only inventory](MILESTONE_1_ROLLOUT.md#0-linux-vps--read-only-inventory-and-baseline)
to verify independent service PIDs, game identity, live progress and backup
evidence before any approved rollout.

## 1. Windows PowerShell — package the reviewed source

Run [the shared packaging procedure](MILESTONE_1_ROLLOUT.md#package-a-reviewed-git-revision)
from the repository root. It selects files from the exact reviewed commit,
checks the archive inventory and prints its SHA-256. Keep the PowerShell shell
with `$archive` set, and supply the host and identity from the operator's
approved private configuration before the authorized transfer.

```powershell
$vps = 'ubuntu@REPLACE_WITH_APPROVED_VPS'
$identity = "$env:USERPROFILE\.ssh\REPLACE_WITH_APPROVED_IDENTITY"
ssh -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -i $identity $vps 'umask 077; mkdir -p ~/viralclip-stage; chmod 700 ~/viralclip-stage'
if ($LASTEXITCODE -ne 0) { throw 'SSH staging failed' }
scp -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -i $identity $archive "${vps}:viralclip-stage/"
if ($LASTEXITCODE -ne 0) { throw 'Upload failed' }
[IO.Path]::GetFileName($archive)
```

Expected: source, dependencies, units and tests only. Use an existing trusted
SSH host key. The SHA-256 identifies the exact reviewed archive.

## 2. Ubuntu SSH — capture baseline and install isolated tools

Keep this shell for subsequent commands. A first installation uses a new
`/opt/viralclip-ops` directory. If it already exists, stop and review the
existing installation before replacing it. Match the reviewed operations
code with both updated backup unit files. Their `ExecStart` commands provide
the expected game IDs now required by the backup CLI.

```bash
set -eu
health_both
v=/var/lib/viralclip-radar
vi=/var/lib/viralclip-gta-vi
base="$HOME/viralclip-stage"
archive="$base/REPLACE_WITH_WINDOWS_ARCHIVE_NAME"
expected='REPLACE_WITH_WINDOWS_SHA256'
printf '%s  %s\n' "${expected,,}" "$archive" | sha256sum -c -
pid() { systemctl show "$1" -p MainPID --value; }
vp=$(pid viralclip-collector.service)
vip=$(pid viralclip-gta-vi.service)
test "$vp" -gt 0
test "$vip" -gt 0
test "$vp" != "$vip"
df -B1 "$v" "$vi"
sudo du -sh "$v" "$vi"
sudo apt-get install -y restic ca-certificates
test ! -e /opt/viralclip-ops
sudo install -d -m 0755 -o "$(id -un)" -g "$(id -gn)" /opt/viralclip-ops
tar -xzf "$archive" -C /opt/viralclip-ops
cd /opt/viralclip-ops
export UV_LINK_MODE=copy
uv sync --locked --python /usr/bin/python3
uv run --no-sync pytest
uv sync --locked --no-dev --no-editable --python /usr/bin/python3
sudo chown -R root:root /opt/viralclip-ops
sudo chmod -R a+rX,go-w /opt/viralclip-ops
```

Expected: two distinct collector PIDs, healthy and advancing observations.
Plan for concurrent backup even though timers are staggered. Budget the
OS/journal, both active DBs plus WAL, two local retained copies per game,
and free staging space of at least `max(20% of filesystem, 2 × (V DB+WAL +
VI DB+WAL) + 1 GiB)` on the shared disk. Each service enforces its own
single-game reserve and reports critical below 10% free. Use the larger
combined reserve as the operator gate. Measure both growth rates weekly.
The former GTA V rate of 77–80 MB/day is historical. Do not extrapolate
GTA VI's first hour to a month. Schedule remote restore drills away from
backup runs and allow three database-size copies in the drill filesystem.

## 3. Ubuntu SSH — configure independent destinations

Create two private restic repositories in independent bucket prefixes or
separate buckets on an off-VPS S3-compatible provider. Supply HTTPS endpoint,
region, bucket and prefix, a scoped access key and secret with list/read/write/
delete permissions for each prefix, and independent restic passwords. Save
recovery access and passwords elsewhere. Use distinct optional heartbeat
URLs supporting POST and `/fail`. An empty file gives journal-only alerts.
Do not supply Twitch credentials. Before using these first-install commands,
inspect and preserve any existing operations configuration.

```bash
for profile in ops gta-vi-ops; do
    dir="/etc/viralclip/$profile"
    sudo install -d -m 0700 "$dir"
    template=deploy/backup.env.example
    if [ "$profile" = gta-vi-ops ]; then template=deploy/gta-vi-backup.env.example; fi
    sudo test ! -e "$dir/backup.env"
    sudo install -o root -g root -m 0600 "$template" "$dir/backup.env"
    for key in s3-access-key s3-secret-key restic-password alert-url; do
        sudo test ! -e "$dir/$key"
        sudo install -o root -g root -m 0600 /dev/null "$dir/$key"
    done
    sudoedit "$dir/backup.env" "$dir/s3-access-key" "$dir/s3-secret-key" "$dir/restic-password" "$dir/alert-url"
done
sudo install -d -o viralclip -g viralclip -m 0700 "$v/backups" "$v/restore-drills"
sudo install -d -o viralclip-gta-vi -g viralclip-gta-vi -m 0700 "$vi/backups" "$vi/restore-drills"
sudo /opt/viralclip-ops/.venv/bin/python -B - <<'PY'
from pathlib import Path
from dotenv import dotenv_values

a, b = (Path("/etc/viralclip") / name for name in ("ops", "gta-vi-ops"))
repos = [str(dotenv_values(p / "backup.env", interpolate=False).get("RESTIC_REPOSITORY") or "").rstrip("/") for p in (a, b)]
if any(not r.startswith("s3:https://") or "example.net" in r for r in repos):
    raise SystemExit("Configure real private HTTPS S3 repositories")
if repos[0] == repos[1] or any(x.startswith(y + "/") for x, y in (repos, repos[::-1])):
    raise SystemExit("Repositories must have separate non-overlapping prefixes")
for key in ("s3-access-key", "s3-secret-key", "restic-password", "alert-url"):
    x, y = ((p / key).read_bytes().strip() for p in (a, b))
    if (key != "alert-url" and (not x or not y)) or (x and x == y):
        raise SystemExit("Missing or shared " + key)
print("Operations profiles are distinct")
PY
remote() {
    account=$1; profile=$2; shift 2
    dir="/etc/viralclip/$profile"
    sudo systemd-run --wait --pipe --collect -p "User=$account" -p "Group=$account" \
        -p UMask=0077 -p "EnvironmentFile=$dir/backup.env" \
        -p "LoadCredential=s3-access-key:$dir/s3-access-key" \
        -p "LoadCredential=s3-secret-key:$dir/s3-secret-key" \
        -p "LoadCredential=restic-password:$dir/restic-password" \
        /opt/viralclip-ops/.venv/bin/python -B -m viralclip.operations "$@"
}
# Use init-remote once only for each new, empty repository.
remote viralclip ops init-remote
remote viralclip-gta-vi gta-vi-ops init-remote
v_repo_rc=0 vi_repo_rc=0
remote viralclip ops check-remote || v_repo_rc=$?
remote viralclip-gta-vi gta-vi-ops check-remote || vi_repo_rc=$?
printf 'Repository check exits. GTA V %s, GTA VI %s\n' "$v_repo_rc" "$vi_repo_rc"
[[ $v_repo_rc -eq 0 && $vi_repo_rc -eq 0 ]]
```

If a repository is already initialized, skip its initialization and run
its check. Independently verify provider IAM scope. Retention defaults to
two local copies and seven daily plus four weekly remote snapshots per game,
with overlap. Storage, API calls, egress and versioned deleted objects can
incur charges. Confirm limits before enabling pruning and avoid lifecycle
expiry of current restic objects. A daily backup can lose up to roughly a
day of observations after a healthy last run, and more after failures.

## 4. Ubuntu SSH — verify before enabling timers

```bash
cd /opt/viralclip-ops
for unit in viralclip-{backup,monitor}.{service,timer} viralclip-gta-vi-{backup,monitor}.{service,timer}; do
    sudo install -m 0644 "deploy/$unit" "/etc/systemd/system/$unit"
done
sudo systemd-analyze verify /etc/systemd/system/viralclip-{backup,monitor}.{service,timer} /etc/systemd/system/viralclip-gta-vi-{backup,monitor}.{service,timer}
sudo systemctl daemon-reload
operations_rc=0
for profile in viralclip viralclip-gta-vi; do
    for task in backup monitor; do
        service="$profile-$task.service"
        start_rc=0 journal_rc=0
        sudo systemctl start "$service" || start_rc=$?
        sudo journalctl -u "$service" -n 40 --no-pager || journal_rc=$?
        printf '%s start exit %s, journal exit %s\n' "$service" "$start_rc" "$journal_rc"
        if [[ $start_rc -ne 0 || $journal_rc -ne 0 ]]; then operations_rc=1; fi
    done
done
health_both || operations_rc=1
test "$operations_rc" -eq 0
stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
v_restore_rc=0 vi_restore_rc=0
remote viralclip ops restore-latest "$v/restore-drills/$stamp" --expected-game-id 32982 || v_restore_rc=$?
remote viralclip-gta-vi gta-vi-ops restore-latest "$vi/restore-drills/$stamp" --expected-game-id 1867279146 || vi_restore_rc=$?
printf 'Restore drill exits. GTA V %s, GTA VI %s\n' "$v_restore_rc" "$vi_restore_rc"
health_both
[[ $v_restore_rc -eq 0 && $vi_restore_rc -eq 0 ]]
test "$(pid viralclip-collector.service)" = "$vp"
test "$(pid viralclip-gta-vi.service)" = "$vip"
```

Require **isolation probe passed** for all four services. The probe runs
inside each service's hardened namespace. It checks that the DB and present
WAL/SHM mounts are read-only, queries the live WAL, and verifies the expected
access to backups. Backup probes create and remove a scratch file only in
their own backup directory. Monitor probes require that directory to be
read-only. Expect a local manifest and verified upload for each game, and
two restic downloads that pass manifest, expected game ID and SQLite restore checks. Record
their watermarks and elapsed time. Monitor output includes retained-hour
HTTP attempt/error/429 counts. Verify optional heartbeat delivery separately.
If anything fails, leave timers disabled and diagnose the operations units.
No collector restart is required. Confirm the two original PIDs after any retry.

Once both profiles pass acceptance:

```bash
sudo systemctl enable --now viralclip-{backup,monitor}.timer viralclip-gta-vi-{backup,monitor}.timer
systemctl list-timers 'viralclip*'
sudo test -f /etc/viralclip/gta-vi-authorized
sudo systemctl enable viralclip-gta-vi.service
systemctl is-enabled viralclip-gta-vi.service
test "$(pid viralclip-gta-vi.service)" = "$vip"
```

Confirm 03:30 UTC for GTA V, 04:15 UTC for GTA VI, and five-minute monitors.
Persistent timers can run a catch-up backup when enabled. The last enable
command sets reboot persistence without starting or restarting the collector.
Native reboot behavior remains unverified until an approved reboot drill.

## 5. Rollback and recovery

```bash
sudo systemctl disable --now viralclip-{backup,monitor}.timer viralclip-gta-vi-{backup,monitor}.timer
systemctl list-timers 'viralclip*'
# If undoing the new GTA VI boot configuration, omit --now.
sudo systemctl disable viralclip-gta-vi.service
health_both
test "$(pid viralclip-collector.service)" = "$vp"
test "$(pid viralclip-gta-vi.service)" = "$vip"
```

An already executing operations job can finish. Preserve backups, markers
and credentials while diagnosing. If an upload fails, the prior offsite
marker and verified local copies remain. For real recovery, restore the
affected game's repository to a fresh isolated path using its own `remote`
profile with its independently selected expected game ID. Verify its manifest
and compare its observation watermark to the
last known production watermark. With separate authorization, stop and
exclude **only the affected writer** before a controlled replacement.
Preserve its original SQLite/WAL/SHM for diagnosis, verify the new copy and
record any lost interval before restarting. Never merge divergent copies
automatically. Rehearse retrieval on an independent host periodically.
