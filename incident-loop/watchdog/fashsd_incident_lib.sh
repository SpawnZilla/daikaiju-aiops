#!/bin/bash
# ============================================================
# NEW 2026-10-15 (S2 / C2) -- NOT YET DEPLOYED, NOT YET RUN on the real edge-node.
# fashsd_incident_lib.sh -- incident records + attempt cap for pi5_watchdog.sh
# Deploy to: /opt/kaiju-spine/watchdog/   (sourced by pi5_watchdog.sh; needs jq)
#
# One open incident per service: $KAIJU_INCIDENT_DIR/<service>.json
# Resolved incidents move to $KAIJU_INCIDENT_DIR/resolved/<service>/<epoch>.json
# Decisions (the operator, 2026-10-15): 4 attempts per incident (one per hourly cycle),
# then stop dispatching and send ONE ntfy report; the incident clears when the
# service passes; a new incident on a service whose previous CAPPED incident
# resolved less than 24h ago starts already capped (flap guard).
# Every function degrades to a no-op (never breaks a watchdog cycle) if jq or
# the incident directory is unavailable; then no cap applies (old behaviour).
# ============================================================

: "${KAIJU_INCIDENT_DIR:=/var/lib/kaiju-watchdog/incidents}"
: "${KAIJU_MAX_ATTEMPTS:=4}"
: "${KAIJU_FLAP_WINDOW_MIN:=1440}"

_inc_ready() {
    command -v jq >/dev/null 2>&1 || return 1
    mkdir -p "$KAIJU_INCIDENT_DIR/resolved" 2>/dev/null || return 1
    [ -w "$KAIJU_INCIDENT_DIR" ] || return 1
    return 0
}

# service names become file names: allow only [A-Za-z0-9._-]
_inc_file() {
    case "$1" in
        ""|*[!A-Za-z0-9._-]*) return 1 ;;
    esac
    echo "$KAIJU_INCIDENT_DIR/$1.json"
}

_inc_log() {
    if declare -F _log >/dev/null 2>&1; then _log "$1"; fi
}

# $1=service $2=container. Creates the open incident if none exists.
incident_ensure_open() {
    _inc_ready || return 1
    local svc="$1" f now flap=false rf
    f=$(_inc_file "$svc") || return 1
    if [ -f "$f" ] && jq -e '.status=="open"' "$f" >/dev/null 2>&1; then
        return 0
    fi
    now=$(date '+%Y-%m-%d %H:%M:%S')
    if [ -d "$KAIJU_INCIDENT_DIR/resolved/$svc" ]; then
        while IFS= read -r rf; do
            [ -z "$rf" ] && continue
            if jq -e '.capped==true' "$rf" >/dev/null 2>&1; then
                flap=true
                break
            fi
        done < <(find "$KAIJU_INCIDENT_DIR/resolved/$svc" -name '*.json' -mmin "-${KAIJU_FLAP_WINDOW_MIN}" 2>/dev/null)
    fi
    jq -n --arg s "$svc" --arg c "$2" --arg now "$now" --argjson flap "$flap" \
        '{service:$s, container:$c, status:"open", first_seen:$now, last_seen:$now, attempts:[], capped:$flap, flap:$flap, report_sent:false}' \
        > "$f.tmp" && mv "$f.tmp" "$f"
    if [ "$flap" = true ]; then
        _inc_log "${svc}: flap guard -- a capped incident on this service resolved less than ${KAIJU_FLAP_WINDOW_MIN} min ago; new incident starts capped, no automatic fix"
    else
        _inc_log "${svc}: incident opened (${f})"
    fi
}

# $1=service. Exit 0 if the open incident is capped (no more automatic attempts).
incident_is_capped() {
    local f
    _inc_ready || return 1
    f=$(_inc_file "$1") || return 1
    [ -f "$f" ] && jq -e '.capped==true' "$f" >/dev/null 2>&1
}

incident_attempt_count() {
    local f
    f=$(_inc_file "$1") || { echo 0; return 0; }
    if [ -f "$f" ]; then jq -r '.attempts|length' "$f" 2>/dev/null || echo 0; else echo 0; fi
}

# $1=service $2=script $3=fix_exit(number) $4=health http code $5=fail|pass
incident_record_attempt() {
    _inc_ready || return 1
    local f now
    f=$(_inc_file "$1") || return 1
    [ -f "$f" ] || return 1
    now=$(date '+%Y-%m-%d %H:%M:%S')
    jq --arg now "$now" --arg sc "$2" --argjson fx "${3:-0}" --arg code "$4" --arg res "$5" \
       --argjson max "$KAIJU_MAX_ATTEMPTS" \
       '.attempts += [{time:$now, script:$sc, fix_exit:$fx, code:$code, result:$res}]
        | .last_seen=$now | .last_code=$code
        | .capped = (.capped or ($res=="fail" and (.attempts|length) >= $max))' \
       "$f" > "$f.tmp" && mv "$f.tmp" "$f"
}

# Plain-text report for the ntfy message.
incident_report() {
    local f
    f=$(_inc_file "$1") || return 1
    [ -f "$f" ] || return 1
    jq -r --argjson max "$KAIJU_MAX_ATTEMPTS" \
       '"Service: \(.service) (container \(.container))\nFirst seen: \(.first_seen)\nLast seen: \(.last_seen)\nAttempts: \(.attempts|length) of \($max), automatic fixes stopped"
        + (if .flap then "\nFlap guard: a capped incident on this service resolved less than 24h ago" else "" end)
        + ([.attempts[] | "\n- \(.time) \(.script) exit=\(.fix_exit) health=\(.code)"] | join(""))' "$f"
}

incident_report_sent() {
    local f
    f=$(_inc_file "$1") || return 1
    [ -f "$f" ] && jq -e '.report_sent==true' "$f" >/dev/null 2>&1
}

incident_mark_reported() {
    local f
    f=$(_inc_file "$1") || return 1
    [ -f "$f" ] || return 1
    jq '.report_sent=true' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
}

# Closes the open incident for $1 (service now passes). Keeps it under resolved/.
incident_resolve() {
    _inc_ready || return 1
    local svc="$1" f now dest
    f=$(_inc_file "$svc") || return 1
    [ -f "$f" ] || return 0
    jq -e '.status=="open"' "$f" >/dev/null 2>&1 || return 0
    now=$(date '+%Y-%m-%d %H:%M:%S')
    mkdir -p "$KAIJU_INCIDENT_DIR/resolved/$svc" || return 1
    dest="$KAIJU_INCIDENT_DIR/resolved/$svc/$(date +%s).json"
    if jq --arg now "$now" '.status="resolved" | .resolved_at=$now' "$f" > "$dest"; then
        rm -f "$f"
        _inc_log "${svc}: incident resolved (kept at ${dest})"
        return 0
    fi
    rm -f "$dest"
    return 1
}

# $1 = newline-separated list of services failing THIS cycle.
# Resolves every open incident whose service is not in that list.
incident_resolve_healthy() {
    _inc_ready || return 0
    local f svc
    for f in "$KAIJU_INCIDENT_DIR"/*.json; do
        [ -f "$f" ] || continue
        svc=$(basename "$f" .json)
        if ! printf '%s\n' "$1" | grep -qxF -- "$svc"; then
            incident_resolve "$svc"
        fi
    done
}
