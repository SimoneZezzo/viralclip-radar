#!/usr/bin/env bash
set -eu

collector_health_result() {
    local status
    case "$2" in
        0) status=HEALTHY ;;
        1) status=DEGRADED ;;
        *) status=FAILED ;;
    esac
    printf '%s: %s (exit %s)\n' "$1" "$status" "$2"
}

health_both() {
    local v_rc=0 vi_rc=0
    sudo -u viralclip env PYTHON_DOTENV_DISABLED=1 \
        /opt/viralclip-radar/.venv/bin/python -B -m viralclip \
        --db /var/lib/viralclip-radar/viralclip.sqlite3 health || v_rc=$?
    sudo -u viralclip-gta-vi env PYTHON_DOTENV_DISABLED=1 \
        /opt/viralclip-gta-vi/.venv/bin/python -B -m viralclip \
        --db /var/lib/viralclip-gta-vi/gta-vi.sqlite3 health || vi_rc=$?
    collector_health_result 'GTA V' "$v_rc"
    collector_health_result 'GTA VI' "$vi_rc"
    [[ $v_rc -eq 0 && $vi_rc -eq 0 ]]
}

health_both
