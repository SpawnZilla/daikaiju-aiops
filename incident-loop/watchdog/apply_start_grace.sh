#!/bin/bash
# Adds a startup grace period to pi5_watchdog.sh (curl-FAIL branch only).
# Run as root on the edge-node.  Usage: sudo bash apply_start_grace.sh [target]
set -u
T="${1:-/opt/kaiju-spine/watchdog/pi5_watchdog.sh}"
[ -f "$T" ] || { echo "ABORT: $T not found"; exit 1; }
if grep -q '_in_start_grace' "$T"; then echo "Already applied: $T"; exit 0; fi
TMP=$(mktemp); BAK="$T.bak-startgrace-$(date +%Y%m%d%H%M%S)"
cp -p "$T" "$BAK" || exit 1
python3 - "$T" "$TMP" <<'PY'
import sys
src, out = sys.argv[1], sys.argv[2]
s = open(src).read()
a1 = "# --- S2: incident records + attempt cap (no-op stubs if the lib is not installed) ---\n"
a2 = "        # --- S2: open/refresh the incident; stop dispatching once it is capped ---\n"
if s.count(a1) != 1 or s.count(a2) != 1:
    sys.exit("ABORT: anchor lines not found exactly once")
f = '''# --- Startup grace (2026-11-05): a curl FAIL on a container that just started (Watchtower update, recreate) is not a failure yet ---
: "${KAIJU_START_GRACE_SECONDS:=900}"
_in_start_grace() {
    # $1=container. True only if running, not restarting, never auto-restarted, started < grace seconds ago.
    local info running restarting restarts started started_s age
    info=$(docker inspect -f '{{.State.Running}}|{{.State.Restarting}}|{{.RestartCount}}|{{.State.StartedAt}}' "$1" 2>/dev/null) || return 1
    IFS='|' read -r running restarting restarts started <<< "$info"
    [ "$running" = "true" ] && [ "$restarting" = "false" ] && [ "$restarts" = "0" ] || return 1
    started_s=$(date -d "$started" +%s 2>/dev/null) || return 1
    age=$(( $(date +%s) - started_s ))
    [ "$age" -ge 0 ] && [ "$age" -lt "$KAIJU_START_GRACE_SECONDS" ]
}

'''
b = '''        GRACE_CONTAINER=$(kaiju_service_field "$SVC_IDX" "container")
        if _in_start_grace "$GRACE_CONTAINER"; then
            _log "${svc}: curl FAIL but ${GRACE_CONTAINER} started under ${KAIJU_START_GRACE_SECONDS}s ago (update/recreate) -- startup grace, no incident, no fix; re-checked next cycle"
            continue
        fi

'''
s = s.replace(a1, f + a1).replace(a2, b + a2)
open(out, "w").write(s)
PY
[ $? -eq 0 ] || { echo "ABORT: patch step failed, nothing changed"; rm -f "$TMP"; exit 1; }
if ! bash -n "$TMP"; then echo "ABORT: syntax check failed, nothing changed"; rm -f "$TMP"; exit 1; fi
cat "$TMP" > "$T" && rm -f "$TMP"
echo "Applied. Backup: $BAK"
echo "Rollback: sudo cp -p $BAK $T"
