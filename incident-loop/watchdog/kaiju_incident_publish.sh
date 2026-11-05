#!/bin/bash
# ============================================================
# NEW 2026-10-15 (S3a) -- NOT YET DEPLOYED.
# kaiju_incident_publish.sh -- edge-node -> intake-host incident hand-off
# Deploy to: /opt/kaiju-spine/watchdog/  (root:root 755). Needs jq, python3, curl.
#
# Usage:  kaiju_incident_publish.sh --sweep
# Looks at OPEN incident records ($KAIJU_INCIDENT_DIR/<service>.json). For each it
# publishes, once, an "opened" event, and a "capped" event once the incident is
# capped. Delivery = HTTP 2xx from the ntfy topic; a marker file is written only
# then, so an undelivered event is retried on the next sweep.
# Nothing pending -> exits 0 without touching the network (intake-host is not woken).
# Something pending -> intake-host is woken (wol_trigger.sh) if ntfy does not answer,
# then waits up to KAIJU_WAKE_WAIT_S seconds.
# Each message is JSON signed with HMAC-SHA256 (key file, root-only). It carries bounded EVIDENCE
# (container state + redacted log tail, collected on the edge-node at publish time) for the read-only diagnosis.
# Credentials: /etc/kaiju-os/incident.env (root-only):
#   KAIJU_INCIDENT_URL=http://192.0.2.45:<port>
#   KAIJU_INCIDENT_TOPIC=<incident-topic>
#   KAIJU_INCIDENT_USER=kaiju-incident-writer
#   KAIJU_INCIDENT_PASS=...
#   KAIJU_INCIDENT_KEY_FILE=/etc/kaiju-os/incident.key
# Exit: 0 nothing pending or all delivered; 1 something undelivered; 2 not configured.
# ============================================================

: "${KAIJU_INCIDENT_ENV:=/etc/kaiju-os/incident.env}"
[ -r "$KAIJU_INCIDENT_ENV" ] && . "$KAIJU_INCIDENT_ENV"

: "${KAIJU_INCIDENT_DIR:=/var/lib/kaiju-watchdog/incidents}"
: "${KAIJU_PUBLISHED_DIR:=/var/lib/kaiju-watchdog/published}"
: "${KAIJU_LIB_DIR:=/opt/kaiju-spine/watchdog}"
: "${KAIJU_LOG_DIR:=/var/log/kaiju-watchdog}"
: "${KAIJU_INCIDENT_URL:=http://192.0.2.45:<port>}"
: "${KAIJU_INCIDENT_TOPIC:=<incident-topic>}"
: "${KAIJU_INCIDENT_KEY_FILE:=/etc/kaiju-os/incident.key}"
: "${KAIJU_WAKE_WAIT_S:=150}"
: "${KAIJU_WAKE_POLL_S:=5}"
: "${KAIJU_EVIDENCE_LOG_BYTES:=1800}"   # log-tail budget inside the message
: "${KAIJU_INCIDENT_MAX_BYTES:=3900}"    # signed body limit (ntfy rejects > 4096 incl. sig)

LOG="$KAIJU_LOG_DIR/incident_publish.log"
mkdir -p "$KAIJU_LOG_DIR" 2>/dev/null
_plog() { echo "$(date '+%Y-%m-%d %H:%M:%S') | $1" >> "$LOG" 2>/dev/null; }

[ "$1" = "--sweep" ] || { echo "usage: $0 --sweep" >&2; exit 2; }

for dep in jq python3 curl; do
    command -v "$dep" >/dev/null 2>&1 || { _plog "missing dependency: $dep"; exit 2; }
done
[ -r "$KAIJU_INCIDENT_KEY_FILE" ] || { _plog "key file not readable: $KAIJU_INCIDENT_KEY_FILE"; exit 2; }
[ -n "$KAIJU_INCIDENT_USER" ] && [ -n "$KAIJU_INCIDENT_PASS" ] || { _plog "writer credentials not set in $KAIJU_INCIDENT_ENV"; exit 2; }
[ -d "$KAIJU_INCIDENT_DIR" ] || exit 0
mkdir -p "$KAIJU_PUBLISHED_DIR" 2>/dev/null || { _plog "cannot create $KAIJU_PUBLISHED_DIR"; exit 2; }

_incident_id() { printf '%s|%s' "$1" "$2" | sha256sum | cut -c1-16; }

# Bounded evidence about the container, collected on the edge-node at publish time. All values are
# validated again by the intake. $1=container $2=1 include log tail, 0 state only.
# Log tail: last 40 lines of the container's logs (absent container: the watchdog log lines that name it), printable ASCII only, each line <=160 chars, obvious secrets redacted,
# newest lines kept first up to KAIJU_EVIDENCE_LOG_BYTES.
_evidence_json() {
    local c="$1" withlogs="$2" info state exitc oom restarts health lines="[]" raw
    if info=$(timeout 10 docker inspect -f '{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}|{{.RestartCount}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$c" 2>/dev/null); then
        IFS='|' read -r state exitc oom restarts health <<< "$info"
    else
        state=absent; exitc=0; oom=false; restarts=0; health=none
    fi
    if [ "$withlogs" = 1 ]; then
        if [ "$state" != absent ]; then
            raw=$(timeout 10 docker logs --tail 40 "$c" 2>&1)
        else
            # ABSENT container: it has no logs of its own. Use the last 20 watchdog log lines that name it (the fix scripts log the
            # docker compose error signature there, e.g. FM-12 'failed to stat parent'). Same cleaning, redaction and size bounds.
            raw=$(grep -F -- "$c" "$KAIJU_LOG_DIR/watchdog.log" 2>/dev/null | tail -20)
        fi
        lines=$(printf '%s\n' "$raw" | tr -cd '\11\12\40-\176' | tr '\11' ' ' | sed '/^ *$/d' \
            | sed -E 's/(Bearer|Basic) +[^ ]+/\1 [redacted]/Ig; s/((pass(word)?|passwd|secret|token|api[_-]?key|apikey|authorization|cookie)[^ =:]*[=: ]+)[^ ]+/\1[redacted]/Ig; s/[A-Za-z0-9+=_-]{40,}/[redacted]/g' \
            | cut -c1-160 | jq -R . | jq -cs --argjson max "$KAIJU_EVIDENCE_LOG_BYTES" \
              '(. | reverse) | reduce .[] as $x ({acc:[],n:0,full:false};
                 if .full then . elif (.n + ($x|length) + 1) <= $max then .acc += [$x] | .n += ($x|length) + 1 else .full = true end)
               | .acc | reverse') || lines="[]"
        [ -n "$lines" ] || lines="[]"
    fi
    jq -cn --arg st "$state" --arg ex "${exitc:-0}" --arg oom "$oom" --arg rs "${restarts:-0}" --arg h "$health" \
        --arg now "$(date '+%Y-%m-%d %H:%M:%S')" --argjson lines "$lines" \
        '{collected_at:$now, state:$st, exit_code:(($ex|tonumber?) // 0), oom:($oom=="true"), restarts:(($rs|tonumber?) // 0), health:$h, log_tail:$lines}'
}

# $1=file $2=event $3=incident_id $4=evidence json -> canonical (sorted, compact) body without sig
_canon() {
    jq -cS --arg ev "$2" --arg host "$(hostname)" --arg iid "$3" --argjson evd "$4" \
        '{schema:"kaiju-incident/1", incident_id:$iid, event:$ev, service:.service, container:.container,
          first_seen:.first_seen, last_seen:.last_seen, flap:(.flap // false),
          attempts:[.attempts[] | {time, script, fix_exit, code, result}], host:$host, evidence:$evd}' "$1"
}

# $1=file(path to open incident json) $2=event $3=incident_id -> prints signed JSON on stdout
_build_payload() {
    local f="$1" ev="$2" canon sig evid cont
    cont=$(jq -r .container "$f")
    case "$cont" in ""|-*|*[!A-Za-z0-9._-]*) return 1 ;; esac
    evid=$(_evidence_json "$cont" 1) || return 1
    canon=$(_canon "$f" "$ev" "$3" "$evid") || return 1
    if [ "$(printf '%s' "$canon" | wc -c)" -gt "$KAIJU_INCIDENT_MAX_BYTES" ]; then
        evid=$(_evidence_json "$cont" 0) || return 1
        canon=$(_canon "$f" "$ev" "$3" "$evid") || return 1
    fi
    [ "$(printf '%s' "$canon" | wc -c)" -le "$KAIJU_INCIDENT_MAX_BYTES" ] || return 1
    sig=$(printf '%s' "$canon" | python3 -c 'import hmac,hashlib,sys
k=open(sys.argv[1],"rb").read().strip()
print(hmac.new(k,sys.stdin.buffer.read(),hashlib.sha256).hexdigest())' "$KAIJU_INCIDENT_KEY_FILE") || return 1
    [ -n "$sig" ] || return 1
    printf '%s' "$canon" | jq -cS --arg sig "$sig" '. + {sig:$sig}'
}

_ntfy_up() {
    curl -fsS --max-time 5 "$KAIJU_INCIDENT_URL/v1/health" 2>/dev/null | grep -q '"healthy": *true'
}

_wake_and_wait() {
    _ntfy_up && return 0
    _plog "ntfy not answering -- sending Wake-on-LAN"
    "$KAIJU_LIB_DIR/wol_trigger.sh" >/dev/null 2>&1 || _plog "wol_trigger.sh exited non-zero"
    local waited=0
    while [ "$waited" -lt "$KAIJU_WAKE_WAIT_S" ]; do
        sleep "$KAIJU_WAKE_POLL_S"
        waited=$((waited + KAIJU_WAKE_POLL_S))
        _ntfy_up && { _plog "ntfy answered after ${waited}s"; return 0; }
    done
    _plog "ntfy still not answering after ${KAIJU_WAKE_WAIT_S}s"
    return 1
}

_post() { # $1 = payload ; credentials via a process-substituted curl config, not argv
    curl -fsS --max-time 20 -K <(printf 'user = "%s:%s"\n' "$KAIJU_INCIDENT_USER" "$KAIJU_INCIDENT_PASS") \
        -H "Title: kaiju-incident" -H "Tags: kaiju,incident" \
        -d "$1" "$KAIJU_INCIDENT_URL/$KAIJU_INCIDENT_TOPIC" >/dev/null 2>&1
}

# ---- collect pending (file|event|incident_id) ----
PENDING=()
for f in "$KAIJU_INCIDENT_DIR"/*.json; do
    [ -f "$f" ] || continue
    jq -e '.status=="open"' "$f" >/dev/null 2>&1 || continue
    svc=$(jq -r .service "$f"); first=$(jq -r .first_seen "$f")
    case "$svc" in ""|*[!A-Za-z0-9._-]*) continue ;; esac
    iid=$(_incident_id "$svc" "$first")
    [ -f "$KAIJU_PUBLISHED_DIR/$iid.opened" ] || PENDING+=("$f|opened|$iid")
    if jq -e '.capped==true' "$f" >/dev/null 2>&1 && [ ! -f "$KAIJU_PUBLISHED_DIR/$iid.capped" ]; then
        PENDING+=("$f|capped|$iid")
    fi
done

# RESOLVED (added 2026-10-31): incident was published as "opened" and the watchdog has since closed it
for f in "$KAIJU_INCIDENT_DIR"/resolved/*/*.json; do
    [ -f "$f" ] || continue
    svc=$(jq -r .service "$f" 2>/dev/null); first=$(jq -r .first_seen "$f" 2>/dev/null)
    case "$svc" in ""|*[!A-Za-z0-9._-]*) continue ;; esac
    iid=$(_incident_id "$svc" "$first")
    [ -f "$KAIJU_PUBLISHED_DIR/$iid.resolved" ] && continue
    if [ ! -f "$KAIJU_PUBLISHED_DIR/$iid.opened" ]; then
        # opened and fixed inside one watchdog cycle: it was never open at sweep time, so the feed never saw it.
        # Publish it now (recent ones only, so old history is not replayed).
        [ -n "$(find "$f" -mtime "-${KAIJU_RESOLVED_PUBLISH_DAYS:-2}" 2>/dev/null)" ] || continue
        PENDING+=("$f|opened|$iid")
    fi
    PENDING+=("$f|resolved|$iid")
done

[ "${#PENDING[@]}" -eq 0 ] && exit 0

FAIL=0
if ! _wake_and_wait; then
    _plog "${#PENDING[@]} event(s) NOT delivered (intake-host unreachable) -- will retry next sweep"
    exit 1
fi
for item in "${PENDING[@]}"; do
    IFS='|' read -r f ev iid <<< "$item"
    payload=$(_build_payload "$f" "$ev" "$iid") || { _plog "$iid $ev: could not build payload"; FAIL=1; continue; }
    if _post "$payload"; then
        : > "$KAIJU_PUBLISHED_DIR/$iid.$ev"
        _plog "$iid $ev: delivered ($(jq -r .service "$f"))"
    else
        _plog "$iid $ev: NOT delivered -- will retry next sweep"
        FAIL=1
    fi
done
exit $FAIL
