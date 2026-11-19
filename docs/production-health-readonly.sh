#!/usr/bin/env bash
# Stream to Bash inside an existing, authorized VPS SSH session.
set +e
set -o pipefail
export TZ=UTC LC_ALL=C

phase=${1:-sample}
if [[ $phase != sample && $phase != full ]]; then
    printf '%s\n' 'Usage: bash -s -- [sample|full]'
    exit 2
fi

date -u +%FT%TZ
uptime
free -m
nproc
df -hP / /var/lib
df -iP / /var/lib
systemctl list-timers --all 'viralclip*' --no-pager

journal_summary() {
    sudo -n journalctl -q --utc --since '24 hours ago' -u "$1" --no-pager -o json |
        /usr/bin/python3 -B -c '
import collections, datetime, json, sys
counts, latest = collections.Counter(), {}
last = None
for line in sys.stdin:
    row = json.loads(line)
    last = datetime.datetime.fromtimestamp(int(row["__REALTIME_TIMESTAMP"]) / 1e6, datetime.UTC)
    msg = row.get("MESSAGE", "")
    msg = msg.lower() if isinstance(msg, str) else ""
    counts["entries"] += 1
    flags = {
        "priority_warning_or_higher": int(row.get("PRIORITY", 7)) <= 4,
        "failure_text": any(s in msg for s in ("failed", "error", "traceback", "out of memory")),
        "scheduled_restart": "scheduled restart job" in msg,
        "oom_text": "out of memory" in msg or "oom-kill" in msg,
        "http_429_text": "429" in msg and "http" in msg,
        "local_backup_verified": "local backup verified:" in msg,
        "offsite_upload_completed": "encrypted off-server upload completed:" in msg,
        "isolation_probe_passed": "isolation probe passed:" in msg,
        "health_degraded": "degraded" in msg,
        "health_critical": "critical" in msg,
    }
    for name, flag in flags.items():
        if flag:
            counts[name] += 1
            latest[name] = last.isoformat()
print("Journal last 24h:", dict(counts), "latest entry:", last, "latest events:", latest)
' || printf 'Journal unavailable for %s\n' "$1"
}

inspect_state() {
    sudo -n -u "$1" -- /usr/bin/python3 -B - "$2" "$3" "$4" "$5" "$phase" <<'PY'
import collections
import json
import os
import sqlite3
import sys
import time
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

path, category, pid, app, phase = sys.argv[1:]
path = Path(path)
state = path.parent
now = datetime.now(UTC)
cutoff = now.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
print('Sample UTC:', cutoff, 'expected game ID:', category)

for name in (path.name, path.name + '-wal', path.name + '-shm', path.name + '.collector.lock'):
    item = state / name
    try:
        st = item.stat()
        print(name, 'device/inode:', (st.st_dev, st.st_ino), 'links:', st.st_nlink,
              'symlink:', item.is_symlink(), 'bytes:', st.st_size,
              'mtime UTC:', datetime.fromtimestamp(st.st_mtime, UTC).isoformat())
    except OSError:
        print(name, 'unavailable')

if pid.isdecimal() and int(pid) > 0:
    proc = Path('/proc') / pid
    try:
        argv = (proc / 'cmdline').read_bytes().decode(errors='replace').split('\0')
        allowed = {f'{app}/.venv/bin/python', '-Bu', '-u', '-B', '-m', 'viralclip',
                   'viralclip.gta_vi', '--db', str(path), 'collect', '--game', '--game-id',
                   'Grand Theft Auto V', 'Grand Theft Auto VI', category, '--loop', 'run'}
        print('Collector argv:', [arg if arg in allowed else '<redacted>' for arg in argv if arg])
        handles = set()
        for fd in (proc / 'fd').iterdir():
            try:
                handles.add(os.readlink(fd))
            except FileNotFoundError:
                continue
        print('Expected state files held by MainPID:',
              [suffix or '(database)' for suffix in ('', '-wal', '-shm', '.collector.lock')
               if str(path) + suffix in handles])
    except OSError as exc:
        print('MainPID command or file handles unavailable:', type(exc).__name__)
    try:
        env = dict(entry.split(b'=', 1) for entry in (proc / 'environ').read_bytes().split(b'\0')
                   if b'=' in entry)
        checks = {'VIRALCLIP_DB_PATH': str(path), 'DISCOVERY_INTERVAL_SECONDS': '300',
                  'DISCOVERY_LOOKBACK_MINUTES': '10' if category == '1867279146' else '30',
                  'PYTHON_DOTENV_DISABLED': '1', 'VIRALCLIP_HTTP_LOG_DIR': str(state)}
        if category == '1867279146':
            checks['VIRALCLIP_GTA_VI_GAME_ID'] = category
        print('MainPID config matches expected:',
              {key: ('unset' if key.encode() not in env else env[key.encode()] == value.encode())
               for key, value in checks.items()})
        print('Additional category lists set:', bool(env.get(b'VIRALCLIP_GAMES')),
              bool(env.get(b'VIRALCLIP_GAME_IDS')),
              'Twitch credential fields present:',
              all(env.get(key) for key in (b'TWITCH_CLIENT_ID', b'TWITCH_CLIENT_SECRET')))
        log_value = env.get(b'VIRALCLIP_HTTP_LOG_DIR', b'')
        # Read only the expected state log location. Existing logs can predate this process.
        if log_value not in (b'', os.fsencode(state)):
            print('Current HTTP log configuration differs from the inspected state directory.')
    except OSError as exc:
        print('MainPID config unavailable:', type(exc).__name__)


def query(db, label, sql, args=()):
    try:
        print(label, db.execute(sql, args).fetchall())
    except sqlite3.Error as exc:
        print(label, 'unavailable:', getattr(exc, 'sqlite_errorname', type(exc).__name__))


def inspect_db(db):
    db.execute('PRAGMA query_only=ON')
    db.execute('BEGIN')
    db.execute('SELECT COUNT(*) FROM sqlite_master').fetchone()
    sampled = datetime.now(UTC)
    cutoff = sampled.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    since = (sampled - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    print('SQLite snapshot UTC:', cutoff)
    # Inspect actual schema independently for each database before using any collector query.
    query(db, 'Live schema (table, column)', '''
        SELECT m.name, p.name FROM sqlite_master m JOIN pragma_table_info(m.name) p
        WHERE m.type='table' ORDER BY m.name, p.cid''')
    query(db, 'Journal mode', 'PRAGMA journal_mode')
    query(db, 'Schema migrations', 'SELECT version FROM schema_migrations ORDER BY version')
    query(db, 'Game identity (expected/other game rows)',
          'SELECT COUNT(*) FILTER (WHERE game_id=?), COUNT(*) FILTER (WHERE game_id IS NOT ?) FROM games',
          (category, category))
    for table in ('clips', 'collection_runs', 'discovery_checkpoints'):
        query(db, f'{table} (total, wrong category)',
              f'SELECT COUNT(*), COUNT(*) FILTER (WHERE game_id IS NOT ?) FROM {table}', (category,))
    query(db, 'Latest clip first seen UTC', 'SELECT MAX(first_seen_at) FROM clips')
    query(db, 'Checkpoints (expected category, watermark UTC)',
          'SELECT game_id=?, watermark FROM discovery_checkpoints', (category,))
    query(db, 'Recent runs (status, count, clips, new, flagged, errors, last finish UTC)', '''
        SELECT status, COUNT(*), SUM(clips_seen), SUM(new_clips), SUM(potentially_truncated),
               COUNT(error_summary), MAX(finished_at) FROM collection_runs
        WHERE finished_at>=? OR status='running' GROUP BY status''', (since,))
    query(db, 'Latest complete, unflagged discovery UTC', '''
        SELECT MAX(finished_at) FROM collection_runs WHERE status='completed'
        AND potentially_truncated=0 AND error_summary IS NULL''')
    query(db, 'Latest 12 runs (start, finish, window end UTC, status, requests, pages, new, flagged)', '''
        SELECT started_at, finished_at, window_end, status, request_count, pages_seen,
               new_clips, potentially_truncated FROM collection_runs ORDER BY run_id DESC LIMIT 12''')
    query(db, 'Observations (source, total, last hour, latest UTC)', '''
        SELECT source, COUNT(*), COUNT(*) FILTER (WHERE observed_at>=?), MAX(observed_at)
        FROM clip_snapshots GROUP BY source''', (since,))
    query(db, 'Largest observation gap in sampled hour (seconds)', '''
        SELECT ROUND(MAX((julianday(t)-julianday(prev))*86400),1) FROM (
          SELECT t, LAG(t) OVER (ORDER BY t) AS prev FROM (
            SELECT observed_at AS t FROM clip_snapshots WHERE observed_at BETWEEN ? AND ?
            UNION ALL SELECT ? UNION ALL SELECT ?))''', (since, cutoff, since, cutoff))
    query(db, 'Jobs (target seconds, status, total, overdue, oldest overdue UTC, exhausted, completed last hour, latest completion UTC)', '''
        SELECT target_age_seconds, status, COUNT(*),
               COUNT(*) FILTER (WHERE due_at<=? AND status IN ('pending','running','failed')),
               MIN(due_at) FILTER (WHERE due_at<=? AND status IN ('pending','running','failed')),
               COUNT(*) FILTER (WHERE status='failed' AND attempts>=3),
               COUNT(*) FILTER (WHERE status='completed' AND completed_at>=?),
               MAX(completed_at) FILTER (WHERE status='completed')
        FROM jobs GROUP BY target_age_seconds, status ORDER BY target_age_seconds, status''',
          (cutoff, cutoff, since))
    query(db, 'Operational errors (last hour, latest recorded UTC)', '''
        SELECT COUNT(*) FILTER (WHERE occurred_at>=?), MAX(occurred_at) FROM operational_errors''',
          (since,))
    query(db, 'Recent linked-job lateness (target seconds, samples, P95 seconds)', '''
        WITH delays AS (
          SELECT j.target_age_seconds, (julianday(s.observed_at)-julianday(j.due_at))*86400 AS delay
          FROM jobs j JOIN clip_snapshots s USING (snapshot_id)
          WHERE j.status='completed' AND j.completed_at BETWEEN ? AND ?
          AND s.clip_id=j.clip_id AND s.observed_at=j.completed_at AND s.source='scheduled'
        ), ranked AS (
          SELECT *, ROW_NUMBER() OVER (PARTITION BY target_age_seconds ORDER BY delay) AS position,
                 COUNT(*) OVER (PARTITION BY target_age_seconds) AS samples FROM delays
        )
        SELECT target_age_seconds, samples, ROUND(delay,3) FROM ranked
        WHERE position=(95*samples+99)/100 ORDER BY target_age_seconds''', (since, cutoff))
    if phase == 'full':
        try:
            check = db.execute('PRAGMA integrity_check').fetchall()
            print('Integrity check:', 'ok' if check == [('ok',)] else f'{len(check)} reported issues')
            query(db, 'Foreign-key violations', 'SELECT COUNT(*) FROM pragma_foreign_key_check')
        except sqlite3.Error as exc:
            print('Integrity check incomplete:', getattr(exc, 'sqlite_errorname', type(exc).__name__))
        query(db, 'Invalid completed-job links, timestamp or schedule rows', '''
            SELECT COUNT(*) FILTER (WHERE j.status='completed' AND (s.clip_id IS NOT j.clip_id
                       OR s.source IS NOT 'scheduled' OR s.observed_at IS NOT j.completed_at
                       OR s.observed_at<j.due_at)),
                   COUNT(*) FILTER (WHERE julianday(j.due_at) IS NULL
                       OR ABS((julianday(j.due_at)-julianday(c.created_at))*86400-j.target_age_seconds)>0.002
                       OR j.target_age_seconds NOT IN (600,1800,3600,21600,86400))
            FROM jobs j JOIN clips c USING (clip_id) LEFT JOIN clip_snapshots s USING (snapshot_id)''')
        query(db, 'Invalid observation timestamps or ages', '''
            SELECT COUNT(*) FROM clip_snapshots s JOIN clips c USING (clip_id)
            WHERE julianday(s.observed_at) IS NULL OR julianday(c.created_at) IS NULL
            OR s.observed_at>? OR s.age_seconds<0
            OR ABS((julianday(s.observed_at)-julianday(c.created_at))*86400-s.age_seconds)>0.002''',
              (cutoff,))


try:
    # Live WAL inspection requires existing sidecars. Skip a missing/to-be-created sidecar.
    if not all(part.is_file() and not part.is_symlink() for part in
               (path, Path(str(path) + '-wal'), Path(str(path) + '-shm'))):
        raise FileNotFoundError
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
        deadline = time.monotonic() + 30
        db.set_progress_handler(lambda: time.monotonic() > deadline, 10000)
        inspect_db(db)
except (OSError, sqlite3.Error) as exc:
    print('Live SQLite sample unavailable:', getattr(exc, 'sqlite_errorname', type(exc).__name__))

attempts = collections.Counter()
latest = {}
min_remaining = {}
files = 0
endpoints = {'oauth_token', 'token_validation', 'game_lookup', 'category_search',
             'clip_discovery', 'clip_refresh', 'clips_discovery', 'clips_refresh', 'clips_by_id'}
for suffix in ('', '.1', '.2', '.3'):
    try:
        with (state / (path.name + '.http.jsonl' + suffix)).open(encoding='utf-8') as stream:
            files += 1
            for line in stream:
                try:
                    item = json.loads(line)
                    stamp = datetime.fromisoformat(item['timestamp'])
                    if item.get('event') != 'http_request' or not now-timedelta(hours=1) <= stamp <= now:
                        continue
                    endpoint, status = item.get('endpoint'), item.get('status')
                    endpoint = endpoint if endpoint in endpoints else 'other'
                    status = status if type(status) is int and 100 <= status <= 599 else 'no HTTP status'
                    attempts[endpoint, status] += 1
                    latest[endpoint, status] = max(stamp, latest.get((endpoint, status), stamp))
                    budget = item.get('rate_limit_remaining')
                    if type(budget) is int and budget >= 0:
                        min_remaining[endpoint] = min(budget, min_remaining.get(endpoint, budget))
                except (ValueError, KeyError, TypeError, AttributeError):
                    continue
    except OSError:
        continue
print('HTTP logs read:', files)
print('HTTP last hour (endpoint, status, attempts, latest UTC):',
      [(endpoint, status, count, latest[endpoint, status].astimezone(UTC).isoformat())
       for (endpoint, status), count in attempts.items()])
print('Minimum reported remaining API budget by endpoint:', min_remaining)

if phase == 'full':
    root = state / 'backups'
    for kind in ('local', 'offsite'):
        try:
            marker = json.loads((root / f'latest-{kind}.json').read_text(encoding='utf-8'))
            stamp = datetime.fromisoformat(marker['timestamp'])
            age = round((now - stamp).total_seconds()/3600, 2)
            print(f'{kind} success marker UTC:', stamp.astimezone(UTC).isoformat(), 'age hours:', age)
        except (OSError, KeyError, ValueError, TypeError):
            print(f'{kind} success marker missing or invalid')
    artifacts = []
    for item in (*root.glob('*/*'), *root.glob('*'), *state.glob('*')):
        try:
            if (item.suffix in ('.sqlite3', '.db') and item.is_file()
                    and not item.is_symlink() and not item.samefile(path)):
                artifacts.append((item.stat().st_mtime, item))
        except OSError:
            continue
    print('Backup database candidates in state/backups:', len(artifacts))
    for _, item in sorted(artifacts, reverse=True)[:3]:
        try:
            st = item.stat()
            print('Backup candidate:', item.relative_to(state), 'bytes:', st.st_size,
                  'mtime UTC:', datetime.fromtimestamp(st.st_mtime, UTC).isoformat(),
                  'has manifest:', item.with_name('manifest.json').is_file())
            if any(Path(str(item) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')):
                print('Backup identity unavailable: sidecars present')
                continue
            with item.open('rb') as file:
                if file.read(20)[18:20] != b'\x01\x01':
                    print('Backup identity unavailable: not a standalone DELETE-mode candidate')
                    continue
            with closing(sqlite3.connect(item.as_uri() + '?mode=ro&immutable=1', uri=True)) as copy:
                copy.execute('PRAGMA query_only=ON')
                query(copy, 'Backup identity (expected, other games)', '''
                    SELECT COUNT(*) FILTER (WHERE game_id=?), COUNT(*) FILTER (WHERE game_id IS NOT ?)
                    FROM games''', (category, category))
                query(copy, 'Backup latest observation UTC', 'SELECT MAX(observed_at) FROM clip_snapshots')
        except (OSError, sqlite3.Error):
            print('Backup identity unavailable')
PY
}

audit() {
    local unit=$1 account=$2 db=$3 category=$4 app=$5 profile=$6 pid
    printf '\n%s\n' "=== $unit ==="
    systemctl show "$unit" --no-pager -p LoadState -p ActiveState -p SubState -p MainPID \
        -p UnitFileState -p Result -p ExecMainStartTimestamp -p ExecMainExitTimestamp \
        -p ExecMainStatus -p NRestarts -p Restart -p RestartUSec -p StartLimitBurst \
        -p StartLimitIntervalUSec -p ConditionResult -p User -p WorkingDirectory -p ControlGroup \
        -p MemoryCurrent -p MemoryHigh -p MemoryMax -p CPUUsageNSec -p CPUQuotaPerSecUSec -p Nice
    systemctl list-dependencies --reverse --all "$unit" --no-pager
    pid=$(systemctl show "$unit" -p MainPID --value)
    if [[ $pid =~ ^[1-9][0-9]*$ ]]; then
        ps -p "$pid" -o pid,ppid,user,etimes,pcpu,pmem,rss,comm
    fi
    inspect_state "$account" "$db" "$category" "$pid" "$app" || printf 'State inspection failed for %s\n' "$unit"
    if [[ $phase == full ]]; then
        journal_summary "$unit"
        for job in "$profile-backup" "$profile-monitor"; do
            systemctl show "$job.service" "$job.timer" --no-pager -p Id -p LoadState -p ActiveState \
                -p UnitFileState -p Result -p EnvironmentFiles -p ExecMainStartTimestamp \
                -p ExecMainExitTimestamp -p NextElapseUSecRealtime -p LastTriggerUSec
            journal_summary "$job.service"
        done
    fi
}

audit viralclip-collector.service viralclip /var/lib/viralclip-radar/viralclip.sqlite3 32982 /opt/viralclip-radar viralclip
audit viralclip-gta-vi.service viralclip-gta-vi /var/lib/viralclip-gta-vi/gta-vi.sqlite3 1867279146 /opt/viralclip-gta-vi viralclip-gta-vi
