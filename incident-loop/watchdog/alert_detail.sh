#!/bin/bash
# L-alert-detail (2026-10-31): make the end-of-cycle CRIT ntfy alert say WHAT failed, for /opt/kaiju-spine/watchdog/pi5_watchdog.sh (run on the edge-node).
# The alert body lists this cycle's failing log lines (service, HTTP code vs expected, fix exit), host, time, and the Wake-on-LAN note.
# Usage: sudo bash alert_detail.sh check | apply | rollback
W=${W:-/opt/kaiju-spine/watchdog/pi5_watchdog.sh}
TAG=bak-alertdetail-20261031
case "$1" in
check)
    echo "already patched: $(grep -c CRIT_DETAIL "$W")"
    echo "cycle-start line occurrences: $(grep -cF -- '_log "=== Watchdog cycle start ==="' "$W") (need 1)"
    echo "generic alert occurrences: $(grep -cF -- '"One or more unresolved issues this cycle' "$W") (need 1)"; bash -n "$W" && echo "syntax OK" ;;
apply)
    exec 9>"${LOCK:-/run/dd-watchdog.lock}" && flock -w 900 9 || { echo "STOP: could not get the watchdog lock"; exit 1; }
    [ "$(grep -c CRIT_DETAIL "$W")" = 0 ] || { echo "STOP: already patched"; exit 1; }
    cp -p "$W" "$W.$TAG" || exit 1
    python3 -I - "$W" <<'PY' || { echo "PATCH FAILED, restoring"; cp -p "$W.$TAG" "$W"; exit 1; }
import sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
old_a = '_log "=== Watchdog cycle start ==="\n'
new_a = old_a + 'CYCLE_START_LINE=$(wc -l < "$LOG" 2>/dev/null || echo 0)\n'
old_b = '_alert "Kaiju Watchdog CRIT" "One or more unresolved issues this cycle — see $LOG" "urgent"'
new_b = ('CRIT_DETAIL=$(tail -n +"$((CYCLE_START_LINE + 1))" "$LOG" 2>/dev/null | grep -E \'FAIL|ABSENT|STILL|cannot|drift|not mounted|ghost\' | sed -E \'s/^[0-9-]+ [0-9:]+ \\| [A-Za-z0-9_]+ \\| //\' | cut -c1-220 | tail -8)\n'
         '    _alert "Kaiju Watchdog CRIT" "Unresolved on $(hostname) at $(date \'+%H:%M:%S\'):\n'
         '${CRIT_DETAIL:-no detail captured}\n'
         'A Wake-on-LAN packet is sent after this alert.\n'
         'Log: $LOG" "urgent"')
assert s.count(old_a) == 1, "cycle-start count %d" % s.count(old_a)
assert s.count(old_b) == 1, "alert count %d" % s.count(old_b)
open(p, "w", encoding="utf-8").write(s.replace(old_a, new_a).replace(old_b, new_b))
PY
    bash -n "$W" && grep -q CRIT_DETAIL "$W" && echo "applied, syntax OK; backup $W.$TAG" || { echo "CHECK FAILED, restoring"; cp -p "$W.$TAG" "$W"; exit 1; } ;;
rollback)
    cp -p "$W.$TAG" "$W" && echo restored ;;
*) echo "usage: sudo bash $0 check|apply|rollback"; exit 2 ;;
esac
