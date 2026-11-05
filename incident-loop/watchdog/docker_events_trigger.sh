#!/bin/bash
# Fires the ACTING watchdog (kaiju-watchdog.service) soon after a watched container dies, is removed,
# runs out of memory or goes unhealthy. Reads docker events (read-only); the only action is
# "systemctl start --no-block kaiju-watchdog.service". The hourly/5-min timer stays as the safety net.
: "${DOCKER:=docker}"; : "${SYSTEMCTL:=systemctl}"
: "${UNIT:=kaiju-watchdog.service}"
: "${GRACE_S:=45}"            # wait this long; a container that is Running again is ignored
: "${MIN_INTERVAL_S:=120}"    # never trigger more often than this
: "${SERVICES_YAML:=/etc/kaiju-os/services.yaml}"
: "${LOG:=/var/log/kaiju-watchdog/docker_events.log}"
: "${WATCH_LIST:=}"           # test hook: space-separated names instead of reading services.yaml
: "${EVENT_CMD:=}"
if [ -z "$EVENT_CMD" ]; then   # set outside ${:=} - the } in the format string would end the expansion early
    EVENT_CMD="$DOCKER events --filter type=container --filter event=die --filter event=destroy --filter event=oom --filter event=health_status --format '{{.Action}}|{{.Actor.Attributes.name}}'"
fi
mkdir -p "$(dirname "$LOG")" 2>/dev/null || LOG=/tmp/docker_events.log
log() { echo "$(date '+%F %T') | docker_events | $*" >> "$LOG"; }
now() { date +%s; }
declare -A PEND WATCH
last_trigger=0; last_load=0
load_watch() {
    WATCH=()
    local n
    if [ -n "$WATCH_LIST" ]; then for n in $WATCH_LIST; do WATCH[$n]=1; done
    else for n in $(grep -oP 'container:\s*"?\K[A-Za-z0-9_.-]+' "$SERVICES_YAML" 2>/dev/null); do WATCH[$n]=1; done; fi
    last_load=$(now)
}
handle() {   # $1 = "<action>|<name>"
    local action="${1%%|*}" name="${1##*|}"
    [ -n "$name" ] || return
    case "$action" in die|destroy|oom|"health_status: unhealthy") ;; *) return ;; esac
    [ -n "${WATCH[$name]}" ] || return
    if [ -z "${PEND[$name]}" ]; then PEND[$name]=$(now); log "$name: event '$action', waiting ${GRACE_S}s"; fi
}
process_pending() {
    local n todo=() st
    for n in "${!PEND[@]}"; do
        (( $(now) - PEND[$n] >= GRACE_S )) || continue
        if [ "$($DOCKER inspect -f '{{.State.Running}}' "$n" 2>/dev/null)" = "true" ]; then
            log "$n: running again after grace, no action"; unset 'PEND[$n]'; continue
        fi
        todo+=("$n")
    done
    [ ${#todo[@]} -gt 0 ] || return
    st=$($SYSTEMCTL is-active "$UNIT" 2>/dev/null)
    if [ "$st" = "active" ] || [ "$st" = "activating" ]; then
        log "watchdog already running, will see: ${todo[*]}"; for n in "${todo[@]}"; do unset 'PEND[$n]'; done; return
    fi
    (( $(now) - last_trigger >= MIN_INTERVAL_S )) || return   # keep pending, retry next loop
    log "TRIGGER $UNIT for: ${todo[*]}"
    $SYSTEMCTL start --no-block "$UNIT"; last_trigger=$(now)
    for n in "${todo[@]}"; do unset 'PEND[$n]'; done
}
load_watch; log "started, watching ${#WATCH[@]} containers, grace ${GRACE_S}s, min interval ${MIN_INTERVAL_S}s"
[ -n "$DEBUG_ECHO" ] && { eval "$EVENT_CMD"; exit; }
exec 3< <(eval "$EVENT_CMD")
while true; do
    IFS= read -r -t 2 -u 3 line; rc=$?
    if [ $rc -eq 0 ]; then handle "$line"
    elif [ $rc -le 128 ]; then log "event stream ended (docker restarting?)"; exit 1; fi
    process_pending
    (( $(now) - last_load > 300 )) && load_watch
done
