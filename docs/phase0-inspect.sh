#!/usr/bin/env bash
# Standalone Phase 0 operator inspection. Reads only, with each SQLite probe write-confined.
set -u -o pipefail

vcr_read() {
  local label="$1" output
  shift
  if output=$("$@" 2>/dev/null); then
    printf 'PASS %s\n%s\n' "$label" "$output"
  else
    printf 'UNKNOWN %s: lettura incompleta o non disponibile\n' "$label"
    if [ -n "$output" ]; then printf '%s\n' "$output"; fi
  fi
}

vcr_resources() {
  vcr_read DISK df -hP /var/lib/viralclip-radar /var/lib/viralclip-gta-vi
  vcr_read INODES df -iP /var/lib/viralclip-radar /var/lib/viralclip-gta-vi
  vcr_read RAM free -m
  vcr_read CPU nproc
  vcr_read LOAD uptime
}

vcr_inventory() {
  local prefix task suffix unit props rc path
  for prefix in viralclip viralclip-gta-vi; do
    for task in backup monitor; do
      for suffix in service timer; do
        unit="$prefix-$task.$suffix"
        rc=0
        props=$(systemctl show --no-pager -p LoadState -p ActiveState \
          -p UnitFileState -p FragmentPath -p DropInPaths "$unit" 2>/dev/null) || rc=$?
        if printf '%s\n' "$props" | grep -qx 'LoadState=not-found'; then
          printf 'PASS INVENTORY %s: assente\n' "$unit"
        elif [ "$rc" -eq 0 ] && [ -n "$props" ]; then
          printf 'PASS INVENTORY %s\n%s\n' "$unit" "$props"
        else
          printf 'UNKNOWN INVENTORY %s\n' "$unit"
        fi
      done
    done
  done
  vcr_read TIMER_RUNNING systemctl list-timers --all --full --no-pager
  vcr_read TIMER_INSTALLED systemctl list-unit-files --type=timer --no-pager
  vcr_read SERVICE_INSTALLED systemctl list-unit-files --type=service --no-pager
  vcr_read CRON_NAMES sudo -n -- find /etc/crontab /etc/cron.d \
    /etc/cron.hourly /etc/cron.daily /etc/cron.weekly /etc/cron.monthly \
    /var/spool/cron/crontabs -maxdepth 1 \( -type f -o -type l \) -print
  for path in /opt/viralclip-ops /etc/viralclip/ops /etc/viralclip/gta-vi-ops; do
    vcr_read "OPS_PATH $path" sudo -n -- stat -c '%F %a %U:%G' -- "$path"
  done
  if command -v uv >/dev/null 2>&1; then
    printf 'PASS UV: disponibile nel PATH della shell\n'
  else
    printf 'UNKNOWN UV: non trovato nel PATH della shell\n'
  fi
  printf 'UNKNOWN OTHER_SCHEDULES: confermare cron manuali o esterni con operatore\n'
  vcr_resources
}

vcr_game() {
  local phase="$1" anchor="$2" game="$3" unit="$4" account="$5" id="$6" path="$7"
  local props load active sub pid owner started rc props_after
  rc=0
  props=$(systemctl show --no-pager -p LoadState -p ActiveState \
      -p SubState -p UnitFileState -p MainPID -p User -p NRestarts \
      -p ExecMainStartTimestampMonotonic -p MemoryCurrent -p CPUUsageNSec \
      "$unit" 2>/dev/null) || rc=$?
  if printf '%s\n' "$props" | grep -qx 'LoadState=not-found'; then
    printf 'FAIL %s SYSTEMD: servizio assente\n' "$game"
    return 0
  fi
  if [ "$rc" -ne 0 ]; then
    printf 'UNKNOWN %s SYSTEMD\n' "$game"
    return 0
  fi
  load=$(printf '%s\n' "$props" | sed -n 's/^LoadState=//p')
  active=$(printf '%s\n' "$props" | sed -n 's/^ActiveState=//p')
  sub=$(printf '%s\n' "$props" | sed -n 's/^SubState=//p')
  pid=$(printf '%s\n' "$props" | sed -n 's/^MainPID=//p')
  owner=$(printf '%s\n' "$props" | sed -n 's/^User=//p')
  started=$(printf '%s\n' "$props" | sed -n 's/^ExecMainStartTimestampMonotonic=//p')
  printf '%s SYSTEMD\n%s\n' "$game" "$props"
  printf 'UNKNOWN %s RELEASE: serve ricevuta verificabile collegata al processo\n' "$game"
  if [ -z "$load" ] || [ -z "$active" ] || [ -z "$sub" ] || [ -z "$pid" ]; then
    printf 'UNKNOWN %s PROCESS: proprieta mancanti\n' "$game"
    return 0
  fi
  if [ "$load/$active/$sub/$owner" != "loaded/active/running/$account" ] \
      || ! [[ "$pid" =~ ^[1-9][0-9]*$ ]]; then
    printf 'FAIL %s PROCESS: servizio, PID o account inatteso\n' "$game"
    return 0
  fi
  if ! [[ "$started" =~ ^[1-9][0-9]*$ ]]; then
    printf 'UNKNOWN %s PROCESS: timestamp di avvio non disponibile\n' "$game"
    return 0
  fi
  printf 'PASS %s PROCESS pid=%s\n' "$game" "$pid"

  if timeout 45s sudo -n -u "$account" -- /usr/bin/python3 -I -B - \
      "$phase" "$anchor" "$game" "$id" "$path" "$pid" 2>/dev/null <<'VCR_SQL'
import ctypes, os, platform, sqlite3, stat, sys, time
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

def emit(result, check, detail=""):
    print(result, game, check, detail, flush=True)

def utc(value):
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None:
        raise ValueError("missing offset")
    return stamp.astimezone(timezone.utc)

def fmt(stamp):
    return stamp.isoformat(timespec="microseconds").replace("+00:00", "Z")

def inspect(db, phase, anchor, expected, now):
    q = db.execute
    if q("SELECT MAX(version) FROM schema_migrations").fetchone()[0] != 2:
        emit("UNKNOWN", "SQLITE", "schema diverso da v2")
        return
    if q("PRAGMA journal_mode").fetchone()[0] != "wal":
        emit("FAIL", "SQLITE", "journal mode diverso da WAL")
        return
    cutoff, hour = fmt(now), fmt(now - timedelta(hours=1))
    wrong = {}
    for table in ("games", "clips", "collection_runs", "discovery_checkpoints"):
        wrong[table] = q(f"SELECT COUNT(*) FROM {table} WHERE game_id IS NOT ?",
                         (expected,)).fetchone()[0]
    known = q("SELECT COUNT(*) FROM games WHERE game_id=?", (expected,)).fetchone()[0]
    emit("FAIL" if any(wrong.values()) else "PASS" if known == 1 else "UNKNOWN",
         "CATEGORY", f"expected={expected} present={known} wrong_rows={wrong}")

    if phase == "A":
        integrity = q("PRAGMA integrity_check(1)").fetchall() == [("ok",)]
        fk = q("SELECT COUNT(*) FROM pragma_foreign_key_check").fetchone()[0]
        links = q("""SELECT COUNT(*) FROM jobs j LEFT JOIN clip_snapshots s USING(snapshot_id)
             WHERE j.status='completed' AND (s.snapshot_id IS NULL OR
             s.clip_id IS NOT j.clip_id OR s.source IS NOT 'scheduled' OR
             s.observed_at IS NOT j.completed_at OR s.observed_at<j.due_at OR
             (s.target_age_seconds IS NOT NULL AND s.target_age_seconds<>j.target_age_seconds))
             """).fetchone()[0]
        schedule = q("""SELECT COUNT(*) FROM jobs j JOIN clips c USING(clip_id)
            WHERE j.target_age_seconds NOT IN (600,1800,3600,21600,86400)
            OR julianday(j.due_at) IS NULL OR julianday(c.created_at) IS NULL
            OR ABS((julianday(j.due_at)-julianday(c.created_at))*86400-j.target_age_seconds)>0.002
            """).fetchone()[0]
        emit("PASS" if integrity and fk == links == schedule == 0 else "FAIL", "INTEGRITY",
             f"integrity_ok={integrity} fk_violations={fk} bad_completed_links={links} bad_schedule={schedule}")

    cp = q("SELECT MAX(watermark) FROM discovery_checkpoints WHERE game_id=?",
           (expected,)).fetchone()[0]
    n_runs, last_run = q("""SELECT COUNT(*), MAX(finished_at) FROM collection_runs
         WHERE game_id=? AND status='completed' AND potentially_truncated=0
         AND error_summary IS NULL""", (expected,)).fetchone()
    flagged = q("""SELECT COUNT(*) FROM collection_runs WHERE game_id=?
                    AND finished_at>=? AND potentially_truncated=1""",
                (expected, hour)).fetchone()[0]
    total, last = q("SELECT COUNT(*), MAX(observed_at) FROM clip_snapshots").fetchone()
    scheduled, last_sched = q("""SELECT COUNT(*), MAX(observed_at)
                                 FROM clip_snapshots WHERE source='scheduled'""").fetchone()
    queue = dict(q("SELECT status, COUNT(*) FROM jobs GROUP BY status"))
    overdue, oldest = q("""SELECT COUNT(*), MIN(due_at) FROM jobs
           WHERE due_at<=? AND status IN ('pending','running','failed')""", (cutoff,)).fetchone()
    exhausted = q("SELECT COUNT(*) FROM jobs WHERE status='failed' AND attempts>=3").fetchone()[0]
    errors = q("SELECT COUNT(*) FROM operational_errors WHERE occurred_at>=? AND occurred_at<=?",
               (hour, cutoff)).fetchone()[0]
    due = q("""SELECT COUNT(*) FROM jobs WHERE due_at>? AND due_at<=? AND status<>'missed'""",
            (anchor, cutoff)).fetchone()[0] if phase == "B" else None
    for value in (cp, last_run, last, last_sched, oldest):
        if value is not None and utc(value) > now:
            emit("FAIL", "TIME", "timestamp futuro")
            return
    known_status = ("pending", "running", "completed", "missed", "failed", "unavailable")
    if set(queue) - set(known_status):
        emit("UNKNOWN", "QUEUE", "stato job inatteso")
        return
    stamp = lambda value: fmt(utc(value)) if value is not None else "none"
    oldest_s = round((now - utc(oldest)).total_seconds(), 1) if oldest else 0
    emit("PASS", "READINGS",
         f"utc={cutoff} checkpoint={stamp(cp)} last_discovery={stamp(last_run)} "
         f"complete_runs={n_runs} flagged_1h={flagged} snapshots={total} last_obs={stamp(last)} "
         f"scheduled={scheduled} last_scheduled={stamp(last_sched)}")
    emit("PASS", "QUEUE",
         f"counts={ {key: queue.get(key, 0) for key in known_status} } "
         f"overdue={overdue} oldest_s={oldest_s} exhausted={exhausted} "
         f"errors_1h={errors} due_since_A={due}")
    stale = any((now - utc(t)).total_seconds() > 600 for t in (cp, last_run) if t)
    bad = stale or oldest_s > 300 or exhausted or queue.get("failed", 0) or errors
    emit("FAIL" if bad else "PASS" if cp and last_run else "UNKNOWN", "HEALTH_PHASE0",
         "soglie discovery 600s, coda 300s, errori recenti e job falliti")

def deny_fs_writes():
    # Linux x86_64/arm64. Deny write, remove, create, link/rename and truncate.
    if sys.platform != "linux" or platform.machine() not in ("x86_64", "aarch64"):
        raise OSError("Landlock architecture unsupported")
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    rights = ctypes.c_uint64((1 << 1) | sum(1 << n for n in range(4, 15)))
    fd = libc.syscall(444, ctypes.byref(rights), ctypes.c_size_t(8), 0)
    if fd < 0:
        raise OSError(ctypes.get_errno(), "Landlock ABI >= 3 required")
    try:
        if libc.prctl(38, ctypes.c_ulong(1), 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "Cannot set no_new_privs")
        if libc.syscall(446, fd, 0) != 0:
            raise OSError(ctypes.get_errno(), "Cannot enforce Landlock")
    finally:
        os.close(fd)

def probe(phase, anchor, expected, path, pid):
    files = (path, Path(str(path) + "-wal"), Path(str(path) + "-shm"))
    stats = []
    for file in files:
        meta = file.lstat()
        if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1 or file.resolve() != file:
            emit("FAIL", "ISOLATION", "file di stato non regolare, alias o symlink")
            return
        stats.append(meta)
    base = stats[0]
    emit("PASS", "FILES",
         f"db_dev={base.st_dev} db_inode={base.st_ino} db_bytes={base.st_size} "
         f"wal_bytes={stats[1].st_size} shm_bytes={stats[2].st_size}")
    uncertain = False
    try:
        for fd in (Path("/proc") / pid / "fd").iterdir():
            try:
                held = fd.stat()
            except FileNotFoundError:
                continue
            except OSError:
                uncertain = True
                continue
            if (held.st_dev, held.st_ino) == (base.st_dev, base.st_ino):
                emit("PASS", "PID_DB_LINK", f"pid={pid}")
                break
        else:
            emit("UNKNOWN" if uncertain else "FAIL", "PID_DB_LINK", "DB non confermato nei file aperti")
    except OSError:
        emit("UNKNOWN", "PID_DB_LINK", "metadati fd non accessibili")
    try:
        deny_fs_writes()
    except OSError:
        emit("UNKNOWN", "SQLITE", "protezione Landlock non disponibile; DB non aperto")
        return
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
        deadline = time.monotonic() + 30
        db.set_progress_handler(lambda: time.monotonic() > deadline, 10000)
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA temp_store=MEMORY")
        db.execute("BEGIN")
        db.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
        inspect(db, phase, anchor, expected, datetime.now(timezone.utc))

if __name__ == "__main__":
    phase, anchor, game, expected, filename, pid = sys.argv[1:]
    try:
        probe(phase, anchor, expected, Path(filename), pid)
    except (OSError, sqlite3.Error, ValueError, TypeError, OverflowError) as exc:
        emit("UNKNOWN", "SQLITE_OR_FILES", type(exc).__name__)
VCR_SQL
  then
    :
  else
    rc=$?
    printf 'UNKNOWN %s INSPECTION: sudo non disponibile, accesso negato o timeout (exit %s)\n' "$game" "$rc"
  fi
  if props_after=$(systemctl show --no-pager -p MainPID -p ExecMainStartTimestampMonotonic \
      "$unit" 2>/dev/null) && [ -n "$props_after" ]; then
    if [ "$(printf '%s\n' "$props_after" | sed -n 's/^MainPID=//p')" = "$pid" ] &&
        [ "$(printf '%s\n' "$props_after" | sed -n 's/^ExecMainStartTimestampMonotonic=//p')" = "$started" ]; then
      printf 'PASS %s PROCESS_STABLE\n' "$game"
    else
      printf 'FAIL %s PROCESS_STABLE: cambiato durante il campione\n' "$game"
    fi
  else
    printf 'UNKNOWN %s PROCESS_STABLE\n' "$game"
  fi
}

vcr_sample() {
  local phase="$1" anchor="$2"
  printf '\nSAMPLE %s UTC %s\n' "$phase" "$(date -u +%FT%TZ)"
  vcr_resources
  vcr_game "$phase" "$anchor" GTA_V viralclip-collector.service viralclip 32982 \
    /var/lib/viralclip-radar/viralclip.sqlite3
  vcr_game "$phase" "$anchor" GTA_VI viralclip-gta-vi.service viralclip-gta-vi 1867279146 \
    /var/lib/viralclip-gta-vi/gta-vi.sqlite3
}

usage() {
  printf '%s\n' 'Usage: bash phase0-inspect.sh inventory | sample-a | sample-b A_ANCHOR'
}

main() {
  local started finished now anchor
  case "$#:${1:-}" in
    1:inventory)
      vcr_inventory ;;
    1:sample-a)
      started=$(date -u +%s) || return 2
      anchor=$(date -u -d "@$started" +%Y-%m-%dT%H:%M:%S.000000Z) || return 2
      vcr_sample A "$anchor"
      finished=$(date -u +%s) || return 2
      # Round the end up so B's six-minute guard cannot accept an early sample.
      finished=$((finished + 1))
      printf 'A_ANCHOR=%s:%s\n' "$started" "$finished" ;;
    2:sample-b)
      if ! [[ "$2" =~ ^([1-9][0-9]{9}):([1-9][0-9]{9})$ ]]; then
        printf 'UNKNOWN SAMPLE B: usare il valore A_ANCHOR di A\n'
        return 2
      fi
      started=${BASH_REMATCH[1]}
      finished=${BASH_REMATCH[2]}
      now=$(date -u +%s) || return 2
      if [ "$finished" -lt "$started" ] || [ "$((now - finished))" -lt 360 ]; then
        printf 'UNKNOWN SAMPLE B: ancora non valida o meno di sei minuti dalla fine di A\n'
        return 2
      fi
      anchor=$(date -u -d "@$started" +%Y-%m-%dT%H:%M:%S.000000Z) || return 2
      vcr_sample B "$anchor" ;;
    *) usage; return 2 ;;
  esac
}

main "$@"
