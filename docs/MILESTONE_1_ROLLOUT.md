# Milestone 1 operations rollout for GTA V and GTA VI

**CONDITIONAL GO for an operations-only rollout.** In the operator's 2026-11-19 samples, both collectors advanced and both databases passed integrity and category checks. The current VPS state and installed revision are **UNKNOWN**. Production acceptance depends on the gates below and separate authorization for phases 1–8. The rollback in phase 9 is for this first installation. Keep a single Linux shell for the authorized phases and record the outputs privately.

## Local release review

| Gate | Reviewed result |
| --- | --- |
| Backup and restore compatibility | The two backup `ExecStart` lines match the CLI and supply distinct expected IDs. Restore requires the same independent ID, schema v2, category evidence and the existing integrity and manifest checks. Legacy manifests work when the category is provable from SQLite. |
| Live database and writer isolation | The package includes unit examples for tests. The installation allowlist names exactly eight operations files. Backup has a writable exception only beneath its own backup root, and the monitor requires a read-only mount. No install or rollback command starts a collector, migrates a database, or replaces a live file. The rollout gates compare both PIDs and DB device/inode/link counts. |
| Offsite isolation | Restic selectors are shared across profiles for compatibility with legacy bundles. Distinct provider scopes and repository IDs are mandatory before backups can prune. Restore rejects cross-game bundles even when storage is configured incorrectly. |
| Credentials | The archive file types are checked locally. Production secrets stay in root-owned profile files and the jobs obtain them through `LoadCredential`. The heartbeat path also uses its profile's own credential. |

The local source baseline `8fefbf957c3c81712d6c0cbdb26b4118fd3bd75f` includes the restore category guard and the preflight that reports both health results. The [project tracker](../PROJECT_STATUS.md) records the offline evidence. Linux mount enforcement, live service configuration, repository ownership and actual alert delivery remain acceptance gates.

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

| Game | Backup service and timer | Monitor service and timer | Expected game ID |
| --- | --- | --- | --- |
| GTA V | `viralclip-backup.service` and `viralclip-backup.timer`, 03:30 UTC | `viralclip-monitor.service` and `viralclip-monitor.timer`, every 5 minutes | `32982` |
| GTA VI | `viralclip-gta-vi-backup.service` and `viralclip-gta-vi-backup.timer`, 04:15 UTC | `viralclip-gta-vi-monitor.service` and `viralclip-gta-vi-monitor.timer`, every 5 minutes | `1867279146` |

## 1. LINUX VPS — authorized change, make online recovery copies

Run after approval. Existing applications provide `storage.backup` for a SQLite online copy and temporary restore test. Both copies use a new isolated directory with a writable mount only for the output. A standalone candidate is copied to the operator's private staging directory for off-VPS verification. Allow a few extra database-sized files plus the normal backup staging reserve.

```bash
set -euo pipefail
umask 077
v=/var/lib/viralclip-radar
vi=/var/lib/viralclip-gta-vi
ops=/opt/viralclip-ops
stage="$HOME/viralclip-stage"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
pid() { systemctl show "$1" -p MainPID --value; }
vp=$(pid viralclip-collector.service)
vip=$(pid viralclip-gta-vi.service)
[[ $vp =~ ^[1-9][0-9]*$ && $vip =~ ^[1-9][0-9]*$ && $vp != "$vip" ]]
systemctl is-active --quiet viralclip-collector.service
systemctl is-active --quiet viralclip-gta-vi.service
[[ $(systemctl show viralclip-gta-vi.service -p UnitFileState --value) == disabled ]]
db_identity() { sudo stat -Lc '%d:%i:%h' -- "$v/viralclip.sqlite3" "$vi/gta-vi.sqlite3"; }
db_inodes=$(db_identity)
mapfile -t db_files <<< "$db_inodes"
[[ ${#db_files[@]} == 2 && ${db_files[0]} == *:1 && ${db_files[1]} == *:1 && ${db_files[0]} != "${db_files[1]}" ]]
same_collectors() {
    [[ $(pid viralclip-collector.service) == "$vp" && $(pid viralclip-gta-vi.service) == "$vip" \
        && $(db_identity) == "$db_inodes" ]]
}
unit_stems=(viralclip-backup viralclip-monitor viralclip-gta-vi-backup viralclip-gta-vi-monitor)
units=()
timers=()
sudo test ! -e "$ops"
sudo test ! -L "$ops"
for stem in "${unit_stems[@]}"; do
    timers+=("$stem.timer")
    for suffix in service timer; do
        unit="$stem.$suffix"
        units+=("$unit")
        [[ $(systemctl show "$unit" -p LoadState --value) == not-found ]]
        sudo test ! -e "/etc/systemd/system/$unit"
        sudo test ! -L "/etc/systemd/system/$unit"
    done
done
mkdir -p -m 0700 -- "$stage"
[[ $(realpath -e -- "$stage") == "$stage" && $(stat -c '%a %u' "$stage") == "700 $(id -u)" ]]
anchor=$(mktemp -d "$stage/anchor-$stamp.XXXXXX")
operator=$(id -un)
operator_group=$(id -gn)
capacity_gate() {
    sudo /usr/bin/python3 -B - "$v" "$vi" "$stage" <<'PY'
import shutil
import sys
from pathlib import Path

v, vi, stage = map(Path, sys.argv[1:])
databases = (v / 'viralclip.sqlite3', vi / 'gta-vi.sqlite3')
size = sum(p.stat().st_size for db in databases for p in (db, Path(str(db) + '-wal')))
for root in (v, vi, stage):
    total, _, free = shutil.disk_usage(root)
    reserve = max(total // 5, 3 * size + 1024**3)
    print(root, 'free bytes', free, 'required', reserve)
    if free < reserve:
        raise SystemExit('Insufficient rollout capacity')
PY
}
make_anchor() {
    local label=$1 account=$2 app=$3 state=$4 db=$5 drill py
    py="$app/.venv/bin/python"
    [[ $(sudo realpath -e -- "$state/$db") == "$state/$db" ]] || return 1
    sudo -u "$account" mkdir -p -m 0700 -- "$state/restore-drills" || return
    [[ $(sudo realpath -e -- "$state/restore-drills") == "$state/restore-drills" ]] || return 1
    drill=$(sudo -u "$account" mktemp -d "$state/restore-drills/pre-rollout-$stamp.XXXXXX") || return
    sudo systemd-run --wait --pipe --collect -p Type=exec -p "User=$account" -p "Group=$account" \
        -p UMask=0077 -p ProtectSystem=strict -p ProtectHome=true -p PrivateTmp=true -p "ReadWritePaths=$drill" \
        --setenv=PYTHON_DOTENV_DISABLED=1 "$py" -B -m viralclip.storage.backup \
        --source "$state/$db" "$drill/$db" || return
    mkdir -m 0700 -- "$anchor/$label" || return
    sudo -u "$account" env PYTHON_DOTENV_DISABLED=1 "$py" -B -m viralclip.deployment \
        manifest "$drill/$db" > "$anchor/$label/manifest.json" || return
    sudo install -o "$operator" -g "$operator_group" -m 0600 \
        "$drill/$db" "$anchor/$label/$db"
}
capacity_gate
v_anchor_rc=0 vi_anchor_rc=0
make_anchor gta-v viralclip /opt/viralclip-radar "$v" viralclip.sqlite3 || v_anchor_rc=$?
make_anchor gta-vi viralclip-gta-vi /opt/viralclip-gta-vi "$vi" gta-vi.sqlite3 || vi_anchor_rc=$?
printf 'Recovery copy exits. GTA V %s, GTA VI %s\n' "$v_anchor_rc" "$vi_anchor_rc"
[[ $v_anchor_rc == 0 && $vi_anchor_rc == 0 ]]
same_collectors
basename "$anchor"
```

If either existing module, path, mount, or check fails, stop this phase. The live database file and its sidecars stay in place. The copied DB is a consistent point in time and the latest observation in its manifest is its recovery watermark.

## 2. WINDOWS POWERSHELL — authorized transfer, verify both anchors and package the release

Run from the reviewed repository root. Use the private, access-restricted, encrypted Windows storage used for operational data before copying the closed artifacts into ignored `data/`. Set the host and identity placeholders from the operator's approved private configuration. The SSH key authenticates through the local terminal. The closed artifacts contain Twitch metadata and remain private.

```powershell
$vps = 'ubuntu@REPLACE_WITH_APPROVED_VPS'
$identity = "$env:USERPROFILE\.ssh\REPLACE_WITH_APPROVED_IDENTITY"
$anchorId = Read-Host 'Paste the anchor directory basename printed on Linux'
if ($anchorId -notmatch '^anchor-\d{8}T\d{6}Z\.[a-zA-Z0-9]+$') { throw 'Unexpected anchor basename' }
$anchorCopy = "data/$anchorId"
if (Test-Path -LiteralPath $anchorCopy) { throw 'Local destination already exists' }
git check-ignore --quiet -- $anchorCopy
if ($LASTEXITCODE -ne 0) { throw 'Backup destination must be ignored' }
scp -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -i $identity -r "${vps}:viralclip-stage/$anchorId" $anchorCopy
if ($LASTEXITCODE -ne 0) { throw 'Anchor transfer failed' }
$py = '.\.venv\Scripts\python.exe'
& $py -B -m viralclip.deployment verify "$anchorCopy/gta-v/viralclip.sqlite3" "$anchorCopy/gta-v/manifest.json" --expected-game-id 32982
$vCode = $LASTEXITCODE
& $py -B -m viralclip.deployment verify "$anchorCopy/gta-vi/gta-vi.sqlite3" "$anchorCopy/gta-vi/manifest.json" --expected-game-id 1867279146
$viCode = $LASTEXITCODE
if ($vCode -ne 0 -or $viCode -ne 0) { throw "Anchor verification failed. GTA V $vCode, GTA VI $viCode" }
foreach ($file in @("$anchorCopy/gta-v/manifest.json", "$anchorCopy/gta-vi/manifest.json")) {
    $manifest = Get-Content -Raw -LiteralPath $file | ConvertFrom-Json
    $manifest | Select-Object sha256, bytes
    $manifest.metrics | Select-Object latest_observation_utc, clips, clip_snapshots
}
```

### Package a reviewed Git revision

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

### Upload the reviewed archive

After transfer approval, use the privately verified host and identity
variables from the anchor transfer above.

```powershell
scp -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -i $identity $archive "${vps}:viralclip-stage/"
if ($LASTEXITCODE -ne 0) { throw 'Source upload failed' }
```

## 3. LINUX VPS — authorized change, configure independent private profiles

Use two approved dedicated offsite S3 repositories. Verify actual bucket and prefix boundaries in the provider console and verify each key's policy allows operations only within its own repository. The current backup starts retention and pruning after a successful upload. Any existing repository with uncertain ownership is a stop condition. Confirm an existing repository contains only the intended game's backups or use a provider-confirmed, approved empty prefix. Arrange two independent alert checks that accept HTTPS `POST` and `/fail`, with a missed-heartbeat threshold around 15 minutes.

```bash
read -r -p 'Reviewed archive basename: ' archive_name
read -r -p 'Recorded archive SHA-256: ' expected
[[ $archive_name =~ ^ops-[a-f0-9]{40}-[0-9]{8}T[0-9]{6}Z\.tar\.gz$ && $expected =~ ^[A-Fa-f0-9]{64}$ ]]
archive="$stage/$archive_name"
printf '%s  %s\n' "${expected,,}" "$archive" | sha256sum -c -
for profile in ops gta-vi-ops; do
    dir="/etc/viralclip/$profile"
    sudo test ! -L "$dir"
    if ! sudo test -d "$dir"; then sudo install -d -o root -g root -m 0700 "$dir"; fi
    [[ $(sudo stat -c '%a %u %g' "$dir") == '700 0 0' ]]
    template=deploy/backup.env.example
    if [[ $profile == gta-vi-ops ]]; then template=deploy/gta-vi-backup.env.example; fi
    sudo test ! -L "$dir/backup.env"
    if ! sudo test -e "$dir/backup.env"; then
        template_copy=$(mktemp "$stage/template.XXXXXX")
        tar -xOzf "$archive" "$template" > "$template_copy"
        sudo install -o root -g root -m 0600 "$template_copy" "$dir/backup.env"
        rm -- "$template_copy"
    fi
    for key in s3-access-key s3-secret-key restic-password alert-url; do
        sudo test ! -L "$dir/$key"
        if ! sudo test -e "$dir/$key"; then sudo install -o root -g root -m 0600 /dev/null "$dir/$key"; fi
    done
    for file in backup.env s3-access-key s3-secret-key restic-password alert-url; do
        sudo test -f "$dir/$file"
        [[ $(sudo stat -c '%a %u %g %h' "$dir/$file") == '600 0 0 1' ]]
    done
    sudoedit "$dir/backup.env" "$dir/s3-access-key" "$dir/s3-secret-key" "$dir/restic-password" "$dir/alert-url"
done
```

`sudoedit` keeps secrets out of shell arguments and history. Use `backup.env` for the repository and retention settings only. The four credential files hold one value each. Setup output, shell history, the archive and manifests contain no credential values. Current collector environments are outside these operations profiles.

## 4. LINUX VPS — authorized change, install the reviewed operations code

If `/usr/bin/restic` is absent, install it with the approved Ubuntu package command. Record its version and build the isolated Python environment from the supplied lockfile. The full test suite runs with synthetic fixtures before any persistent operations units are installed.

```bash
if [[ ! -x /usr/bin/restic ]]; then sudo apt-get install -y restic ca-certificates; fi
/usr/bin/restic version
sudo test ! -e "$ops"
sudo test ! -L "$ops"
sudo mkdir -m 0755 -- "$ops"
sudo chown "$operator:$operator_group" "$ops"
tar -xzf "$archive" -C "$ops"
cd "$ops"
export UV_LINK_MODE=copy
uv sync --locked --python /usr/bin/python3
uv run --no-sync pytest
uv sync --locked --no-dev --no-editable --python /usr/bin/python3
sudo chown -R root:root "$ops"
sudo chmod -R a+rX,go-w "$ops"
ops_python="$ops/.venv/bin/python"
"$ops_python" -B -m viralclip.operations backup --help
"$ops_python" -B -m viralclip.operations restore-latest --help
same_collectors
```

## 5. LINUX VPS — validate Restic isolation before the first prune

Profile checks below verify nonoverlapping configured paths, distinct nonempty credentials and separate repository IDs. Confirm the provider-side key scope from phase 3 as well. Configuration comparison by itself cannot resolve aliased endpoints. The repository ID check uses the same systemd credentials and environment as the installed backup units. [Restic repository IDs and `cat config`](https://restic.readthedocs.io/en/stable/100_references.html#config).

```bash
sudo "$ops_python" -I -B - <<'PY'
from pathlib import Path
from urllib.parse import urlsplit
from dotenv import dotenv_values

profiles = [Path('/etc/viralclip') / n for n in ('ops', 'gta-vi-ops')]
repos = [(dotenv_values(p / 'backup.env', interpolate=False).get('RESTIC_REPOSITORY') or '').rstrip('/') for p in profiles]
for repo in repos:
    endpoint = urlsplit(repo[3:])
    if (not repo.startswith('s3:https://') or not endpoint.hostname or endpoint.hostname == 's3.example.net'
            or not endpoint.path.strip('/') or endpoint.username is not None
            or endpoint.password is not None or endpoint.query or endpoint.fragment):
        raise SystemExit('Supply approved HTTPS bucket/prefix values')
if repos[0] == repos[1] or any(x.startswith(y + '/') for x, y in (repos, repos[::-1])):
    raise SystemExit('Overlapping repository paths')
for key in ('s3-access-key', 's3-secret-key', 'restic-password', 'alert-url'):
    a, b = ((p / key).read_bytes().strip() for p in profiles)
    if not a or not b or a == b:
        raise SystemExit('Missing or shared profile value for ' + key)
print('Local operations profiles have separate configuration')
PY

repo_command() {
    local account=$1 profile=$2 output_parent=$3 dir
    shift 3
    dir="/etc/viralclip/$profile"
    local args=()
    if [[ -n $output_parent ]]; then args+=(-p "ReadWritePaths=$output_parent"); fi
    sudo systemd-run --quiet --wait --pipe --collect -p Type=exec -p "User=$account" -p "Group=$account" \
        -p UMask=0077 -p ProtectSystem=strict -p ProtectHome=true -p PrivateTmp=true "${args[@]}" \
        -p "EnvironmentFile=$dir/backup.env" \
        -p "LoadCredential=s3-access-key:$dir/s3-access-key" \
        -p "LoadCredential=s3-secret-key:$dir/s3-secret-key" \
        -p "LoadCredential=restic-password:$dir/restic-password" "$ops_python" -I -B "$@"
}
repo_id() {
    repo_command "$1" "$2" '' -c '
import json, re, subprocess
from viralclip.operations import _restic_environment
try:
    result = subprocess.run(["/usr/bin/restic", "--no-lock", "--no-cache", "--json", "cat", "config"],
                            env=_restic_environment(), stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=30, check=True)
    identity = json.loads(result.stdout)["id"]
    if not re.fullmatch(r"[0-9a-f]{64}", identity):
        raise ValueError
except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
    raise SystemExit("Repository ID lookup failed. Check profile and repository privately.") from None
print(identity)
'
}
```

**LINUX VPS — conditional write.** Run only for the profile whose approved prefix the provider confirms is empty. Set `profile_to_initialize` to that one profile when prompted. Skip this block when both repositories already exist. A failed ID lookup alone is insufficient evidence to initialize a repository.

```bash
read -r -p 'Confirmed empty profile (ops or gta-vi-ops): ' profile_to_initialize
case "$profile_to_initialize" in
    ops) repo_command viralclip ops '' -m viralclip.operations init-remote ;;
    gta-vi-ops) repo_command viralclip-gta-vi gta-vi-ops '' -m viralclip.operations init-remote ;;
    *) printf 'Unexpected profile\n' >&2; false ;;
esac
```

**LINUX VPS — repository ID reads and structural checks.** `check-remote` can create a temporary Restic lock. Run away from other repository work.

```bash
v_repo_rc=0 vi_repo_rc=0
v_repo=$(repo_id viralclip ops) || v_repo_rc=$?
vi_repo=$(repo_id viralclip-gta-vi gta-vi-ops) || vi_repo_rc=$?
printf 'Repository ID lookup exits. GTA V %s, GTA VI %s\n' "$v_repo_rc" "$vi_repo_rc"
[[ $v_repo_rc == 0 && $vi_repo_rc == 0 && -n $v_repo && -n $vi_repo && $v_repo != "$vi_repo" ]]
printf 'Distinct repository ID prefixes. GTA V %.12s, GTA VI %.12s\n' "$v_repo" "$vi_repo"
v_repo_rc=0 vi_repo_rc=0
repo_command viralclip ops '' -m viralclip.operations check-remote || v_repo_rc=$?
repo_command viralclip-gta-vi gta-vi-ops '' -m viralclip.operations check-remote || vi_repo_rc=$?
printf 'Repository structure exits. GTA V %s, GTA VI %s\n' "$v_repo_rc" "$vi_repo_rc"
[[ $v_repo_rc == 0 && $vi_repo_rc == 0 ]]
```

## 6. LINUX VPS — authorized change, install only operations units and run initial backups

Check capacity again, then start the backup jobs serially to reduce I/O pressure. The mount probes must pass. The first successful upload for each game is immediately followed by that profile's configured retention; phase 5 and the off-VPS anchors must already have passed.

```bash
capacity_gate
for pair in "viralclip:$v" "viralclip-gta-vi:$vi"; do
    account=${pair%%:*}
    state=${pair#*:}
    sudo -u "$account" mkdir -p -m 0700 -- "$state/backups"
    [[ $(sudo realpath -e -- "$state/backups") == "$state/backups" ]]
    [[ $(sudo stat -c '%a %U:%G' "$state/backups") == "700 $account:$account" ]]
done
unit_paths=()
for unit in "${units[@]}"; do
    sudo test ! -e "/etc/systemd/system/$unit"
    sudo test ! -L "/etc/systemd/system/$unit"
    unit_paths+=("$ops/deploy/$unit")
done
sudo systemd-analyze verify "${unit_paths[@]}"
for unit in "${units[@]}"; do
    sudo install -o root -g root -m 0644 "$ops/deploy/$unit" "/etc/systemd/system/$unit"
done
sudo systemctl daemon-reload
same_collectors

run_pair() {
    local task=$1 prefix rc result=0
    for prefix in viralclip viralclip-gta-vi; do
        rc=0
        sudo systemctl start "$prefix-$task.service" || rc=$?
        printf '%s-%s start exit %s\n' "$prefix" "$task" "$rc"
        if [[ $rc != 0 ]]; then result=1; fi
        if ! sudo journalctl -u "$prefix-$task.service" -n 35 --utc --no-pager; then result=1; fi
    done
    return "$result"
}
run_pair backup
same_collectors
```

Require `Isolation probe passed`, `Local backup verified` and `Encrypted off-server upload completed` for both profiles, plus successful service results. A pruning failure can leave the local/offsite markers fresh while the service fails. Use the service result as a separate gate.

## 7. LINUX VPS — authorized change, verify isolated restores and alerts

Run each restore into a fresh path under its own `restore-drills`. Match the downloaded manifest to the bundle named by the current upload marker. This tests the actual first upload for each profile, including the expected game ID, without replacing any database.

```bash
verify_drill() (
    set -euo pipefail
    account=$1 profile=$2 state=$3 game=$4
    drill="$state/restore-drills/remote-$stamp"
    [[ $(sudo realpath -e -- "$state/restore-drills") == "$state/restore-drills" ]] || exit 1
    repo_command "$account" "$profile" "$state/restore-drills" -m viralclip.operations \
        restore-latest "$drill" --expected-game-id "$game" || exit 1
    sudo -u "$account" "$ops_python" -I -B - "$state" "$drill" "$game" <<'PY'
import json, re, sys
from pathlib import Path

state, drill = map(Path, sys.argv[1:3])
game = sys.argv[3]
root = state / 'backups'
marker = json.loads((root / 'latest-offsite.json').read_text())
bundle = marker['bundle']
if not re.fullmatch(r'[0-9]{8}T[0-9]{6}\.[0-9]{6}Z', bundle):
    raise SystemExit('Invalid offsite success marker')
restored, = drill.rglob('manifest.json')
local = root / bundle / 'manifest.json'
manifest = json.loads(local.read_text())
if manifest != json.loads(restored.read_text()) or manifest.get('game_id') != game:
    raise SystemExit('Restored manifest differs from the successful upload')
print('Verified game', game, 'upload UTC', marker['timestamp'], 'observation UTC',
      manifest['metrics']['latest_observation_utc'], 'SHA-256', manifest['sha256'])
PY
)
v_drill_rc=0 vi_drill_rc=0
verify_drill viralclip ops "$v" 32982 || v_drill_rc=$?
verify_drill viralclip-gta-vi gta-vi-ops "$vi" 1867279146 || vi_drill_rc=$?
printf 'Restore exits. GTA V %s, GTA VI %s\n' "$v_drill_rc" "$vi_drill_rc"
[[ $v_drill_rc == 0 && $vi_drill_rc == 0 ]]
run_pair monitor
same_collectors
```

Each monitor must report a successful mount probe, `Operations health: HEALTHY`, and recent local/offsite markers. Verify that regular heartbeat delivery is visible in each external check. The following synthetic failure sends the same payload as the monitor without stopping a collector or changing its database. It deliberately generates an external incident for each profile. Confirm both failure notifications arrive before sending the next normal heartbeats.

```bash
alert_test() {
    local account=$1 profile=$2
    sudo systemd-run --quiet --wait --pipe --collect -p Type=exec -p "User=$account" -p "Group=$account" \
        -p UMask=0077 -p ProtectSystem=strict -p ProtectHome=true -p PrivateTmp=true \
        -p "LoadCredential=alert-url:/etc/viralclip/$profile/alert-url" "$ops_python" -I -B -c '
from viralclip.operations import _credentials_dir, _heartbeat
try:
    if not (_credentials_dir() / "alert-url").read_bytes().strip():
        raise ValueError
    _heartbeat(1)
except (OSError, ValueError):
    raise SystemExit("Synthetic failure heartbeat could not be sent") from None
print("Synthetic failure heartbeat sent. Confirm recipient delivery.")
'
}
v_alert_rc=0 vi_alert_rc=0
alert_test viralclip ops || v_alert_rc=$?
alert_test viralclip-gta-vi gta-vi-ops || vi_alert_rc=$?
printf 'Synthetic alert exits. GTA V %s, GTA VI %s\n' "$v_alert_rc" "$vi_alert_rc"
[[ $v_alert_rc == 0 && $vi_alert_rc == 0 ]]
```

**LINUX VPS — after verifying external receipts.** Confirm both checks also recover after this command.

```bash
run_pair monitor
same_collectors
```

## 8. LINUX VPS — authorized change, activate the rollout and decide boot recovery

After both independent profiles pass, activate only the four operations timers. Persistent backup timers may catch up missed appointments immediately. Check shared capacity first. Enable GTA VI for VPS boots only after accepting the prior results and explicitly approving the boot-policy change. `enable` adds boot activation without starting the already running service. Check that its authorization marker and current start condition exist. No collector restart or VPS reboot is involved in this rollout. [systemctl enable and disable behavior](https://www.freedesktop.org/software/systemd/man/latest/systemctl.html).

```bash
capacity_gate
sudo systemctl enable --now "${timers[@]}"
systemctl list-timers --all "${timers[@]}" --no-pager
for timer in "${timers[@]}"; do
    systemctl is-enabled "$timer"
    systemctl is-active "$timer"
done
same_collectors
```

**LINUX VPS — separate boot-policy approval.** If approval is withheld, leave GTA VI disabled and record who starts it after a reboot. That remains an unattended Milestone 1 gap.

```bash
sudo test -f /etc/viralclip/gta-vi-authorized
[[ $(systemctl show viralclip-gta-vi.service -p ConditionResult --value) == yes ]]
sudo systemctl enable viralclip-gta-vi.service
systemctl is-enabled viralclip-gta-vi.service
systemctl is-enabled viralclip-collector.service
same_collectors
```

Finish with read-only `health_both` and the audit `sample` twice at least six minutes apart. Compare against the Phase 0 baseline. Record two healthy timer-driven monitor executions and one successful timer-driven upload for each game before closing Milestone 1. A later separately authorized reboot drill can prove actual automatic recovery.

**LINUX VPS — read-only scheduled execution evidence.** Correlate timer trigger timestamps with service results and journal messages. Keep these later checks separate from the manual starts in phases 6 and 7.

```bash
systemctl list-timers --all "${timers[@]}" --no-pager
for stem in "${unit_stems[@]}"; do
    systemctl show "$stem.timer" "$stem.service" -p Id -p LastTriggerUSec \
        -p ExecMainStartTimestamp -p ExecMainExitTimestamp -p Result
    sudo journalctl -u "$stem.service" --since '36 hours ago' -n 50 --utc --no-pager
done
same_collectors
```

## 9. LINUX VPS — authorized rollback of operations only

Roll back if either game shows sustained scheduler degradation or stalled progress after the rollout, a writer or database alias is unexpected, a mount probe fails, a restore differs, or disk/alerts fail the acceptance gates. If timers are still disabled, stop the current phase and preserve its evidence. If timers were activated, disable only those timers. Leave any backup already running to finish and inspect its result. Disable GTA VI boot activation only if it was changed in phase 8 and the goal is to revert that change. Its running collector stays active.

```bash
sudo systemctl disable --now viralclip-backup.timer viralclip-gta-vi-backup.timer \
    viralclip-monitor.timer viralclip-gta-vi-monitor.timer
systemctl show viralclip-backup.service viralclip-gta-vi-backup.service \
    viralclip-monitor.service viralclip-gta-vi-monitor.service --no-pager \
    -p Id -p ActiveState -p Result
systemctl show viralclip-collector.service viralclip-gta-vi.service --no-pager \
    -p Id -p MainPID -p ActiveState -p UnitFileState
```

```bash
# Only when rolling back the approved GTA VI boot-policy change.
sudo systemctl disable viralclip-gta-vi.service
systemctl show viralclip-gta-vi.service -p MainPID -p ActiveState -p UnitFileState
```

Keep the operations files, backups, markers, and configuration for diagnosis. Operations rollback leaves both live observation histories in place, including observations newer than every backup. Verify that both PIDs and SQLite device/inode pairs match the baseline and that jobs and watermarks advance. If a live database itself fails, first preserve the current DB/WAL/SHM and exclude its writer under separate incident authorization. Verify a backup restored to a fresh isolated path, compare its watermark with the last known observation, and obtain the loss decision before any live recovery. An older recovery copy can lose all later observations and the views Twitch reported at those times cannot be reconstructed. [Recovery safeguards](BACKUP_AND_MONITORING.md#monitoring-and-restore).

## Acceptance and risk

- Baseline and post-rollout evidence shows two independent healthy services, the same distinct PIDs and database inodes, zero foreign-key and wrong-category records, and successful discovery, observations and scheduled jobs advancing. Use the audit to track unexpected gaps, exhausted jobs and overdue ages. Empty successful discovery can be valid.
- Both closed pre-rollout anchors verify by game and SHA-256 outside the VPS. Each Restic repository uses a separate confirmed prefix, scoped credentials and repository ID. Each latest scheduled backup is visible locally and offsite. Both fresh offsite restore drills verify the same game, hash and latest observation as their upload manifests.
- All four operations timers are active and enabled with the expected schedule. Both monitor and backup mount probes pass. Each external check demonstrably receives a failure and a recovery message. The GTA VI boot-policy decision and recovery evidence are recorded. A disabled GTA VI requires an operator and leaves unattended reboot recovery open.
- Collector downtime planned is zero. SQLite readers and Restic can still compete for I/O, CPU and disk on the shared two-core host. If a collector unexpectedly exits, hold the rollout, capture the last actual measurement and resume under its normal supervisor policy. Measure the observation gap; a missed 10/30/60-minute sample cannot be backfilled. Daily successful remote copies imply up to roughly a day of possible observation loss after a database failure, with a longer gap after missed backups. Operations rollback does not restore data.

## Later research — GTA VI discovery and early coverage

The reviewed collector caps a discovery window at ten pages when a continuation cursor remains. It also marks a window potentially truncated at 900 returned rows, and shares a 20-page budget across an initial window and any minute-aligned subdivisions. A tenth page can also be the natural end. Ten pages by itself does not prove the cap was hit, and a checkpoint can advance after a flagged parent if its subdivisions cover the window. The operator reported advancing checkpoints and repeated ten-page activity. Confirm the deployed code and inspect the persisted run flags before attributing those cycles to the reviewed cap. Twitch orders game searches by view count and returns roughly 1,000 results across pages. High-volume windows can therefore omit clips disproportionately from the low-view tail. The number of omitted clips is unknown from these samples. [Twitch Get Clips documentation](https://dev.twitch.tv/docs/api/reference/clips#get-clips).

The operator described GTA VI's 10-minute missed-at-discovery coverage as substantial. The supplied evidence has no numerator or denominator. The following optional read-only check reports pages and coverage counts on the current VPS schema. Run it separately from backup jobs. Use all due 600-second `view_snapshot` jobs for the missed-at-discovery denominator, and a separate strict metric for the fraction with **any actual observation by 10 minutes**. Unavailable and later observations belong to their own interpretations.

**LINUX VPS — read-only research sampling.**

```bash
sudo -u viralclip-gta-vi /usr/bin/python3 -B - <<'PY'
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

path = Path('/var/lib/viralclip-gta-vi/gta-vi.sqlite3')
if not all(Path(str(path) + suffix).is_file() for suffix in ('', '-wal', '-shm')):
    raise SystemExit('Live DB or WAL sidecar unavailable')
with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
    db.execute('PRAGMA query_only=ON')
    db.execute('BEGIN')
    now = datetime.now(UTC)
    iso = lambda t: t.isoformat(timespec='microseconds').replace('+00:00', 'Z')
    for row in db.execute('''
        SELECT status, pages_seen, potentially_truncated, COUNT(*), MAX(clips_seen),
               SUM(new_clips), MAX(window_end)
        FROM collection_runs WHERE started_at >= ?
        GROUP BY status, pages_seen, potentially_truncated ORDER BY 1, 2, 3
    ''', (iso(now - timedelta(hours=6)),)):
        print('run grouping (status, pages, flagged, runs, max fetched, new, latest end)', row)
    for row in db.execute('''
        SELECT substr(c.created_at,1,10) AS utc_day, COUNT(*),
               SUM(j.status='missed'), ROUND(100.0 * AVG(j.status='missed'), 2),
               SUM(EXISTS (SELECT 1 FROM clip_snapshots s WHERE s.clip_id=j.clip_id
                           AND s.observed_at BETWEEN c.created_at AND j.due_at))
        FROM jobs j JOIN clips c USING (clip_id)
        WHERE j.job_type='view_snapshot' AND j.target_age_seconds=600 AND j.due_at<=?
        GROUP BY utc_day ORDER BY utc_day
    ''', (iso(now),)):
        print('10m (UTC creation day, due, missed at discovery, missed %, strictly observed)', row)
PY
```

Track this as a future data-quality milestone. Measure flags and residual window gaps by hour, quantiles of discovery lag, and early-feature eligibility by game and UTC cohort. Evaluate a bounded smaller-window pilot against the current strategy only after separate approval and measure its effect on coverage and snapshot latency. Neither the cap observations nor the 10-minute coverage finding changes the operations rollout commands.
