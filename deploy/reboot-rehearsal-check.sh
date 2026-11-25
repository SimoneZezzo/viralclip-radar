#!/usr/bin/env bash
# Read-only evidence for the M1 reboot rehearsal: run it before the reboot and again
# after reconnecting, then compare (new boot ID, same units enabled and active, timers
# scheduled, collection advancing). It changes nothing on the host.
set -u

collectors="viralclip-collector.service viralclip-gta-vi.service"
timers="viralclip-reliability@viralclip.timer viralclip-reliability@viralclip-gta-vi.timer"

echo "utc_now=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "boot_id=$(cat /proc/sys/kernel/random/boot_id)"
echo "booted_at=$(uptime -s)"
for unit in $collectors $timers; do
    systemctl show "$unit" -p Id -p UnitFileState -p ActiveState -p SubState \
        -p MainPID -p NRestarts -p ActiveEnterTimestamp | paste -sd ' '
done
systemctl list-timers --all --no-pager | grep -F viralclip-reliability || echo "timers: none listed"
df -h / | tail -1
df -i / | tail -1
# Append deploy/dual-collector-health.sh to this script's input for the read-only health
# of both databases (see docs/M1_RELIABILITY_HARDENING.md, reboot rehearsal).
