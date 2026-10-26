#!/bin/bash
# ============================================================
# TESTED 2026-09-08 (Round 3) — see kaiju-gais-package/fashsd/tests/TESTING.md
# ============================================================
# fm03_gluetun_unhealthy.sh — Kaiju Spine config-driven gluetun/network-
# namespace-owner remediation.
#
# Generalized from Kaidosho's FM-03 (the reference runbook REMEDIATION DECISION TREE,
# confirmed 2026-07-12): restart the network-namespace owner, verify
# it's healthy, THEN restart its dependents (never route this symptom
# through the generic FM-01 single-container restart — MABS FM-13).
#
# Deploy to: /opt/kaiju-spine/watchdog/
#
# CORRECTION NOTE (Mokaima, 2026-08-03): an earlier MABS-brief draft of
# this task referenced three functions that do not exist in
# fashsd_config_lib.sh (kaiju_known_dependent_services,
# kaiju_validate_gluetun_namespace, kaiju_health_check_count), and
# claimed GlueTun facts not present in the reference deployment service index (port
# 8080 is actually qBittorrent's port there, not GlueTun's own; no
# "gluetun_net" namespace name appears anywhere in the vault). This script
# uses the REAL functions (kaiju_network_group_count/field/dependents)
# and the REAL schema (owner/dependents/compose_dir/verify_via —
# kaiju_fashsd_config.example.yaml, no port/namespace fields exist for
# network_groups). It does not attempt a docker-inspect namespace
# string comparison, since nothing in the vault establishes that as Kaidosho's
# actual verification method — the reference runbook's confirmed method is restart +
# health check + a real curl check from the verify_via container.

: "${KAIJU_LIB_DIR:=/opt/kaiju-spine/watchdog}"
source "$KAIJU_LIB_DIR/fashsd_config_lib.sh"

: "${KAIJU_LOG_DIR:=/var/log/kaiju-watchdog}"
mkdir -p "$KAIJU_LOG_DIR" 2>/dev/null || KAIJU_LOG_DIR="/tmp/kaiju-watchdog-fallback"
mkdir -p "$KAIJU_LOG_DIR"

LOG="$KAIJU_LOG_DIR/watchdog.log"

_log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') | fm03_gluetun | $1" >> "$LOG"
}

# --- Owner health check -----------------------------------------------
# Uses docker's own HEALTHCHECK status, same signal the reference runbook's original
# FM-03 note names ("docker inspect gluetun | grep healthy"). Retried
# via kaiju_retry_check so a container mid-restart isn't declared
# unhealthy on the first probe.
_kaiju_owner_healthy() {
    local owner="$1"
    local status
    status=$(docker inspect --format='{{.State.Health.Status}}' "$owner" 2>/dev/null)
    [ "$status" = "healthy" ]
}

# --- Dependent connectivity check --------------------------------------
# the reference runbook requires "real curl (not just health status)" from a dependent
# after restart, not just a status field. No specific target URL is
# documented anywhere in the vault for this check — the closest confirmed
# precedent is FM-07 (`docker exec prowlarr curl -s https://nyaa.si`).
# NOT CONFIRMED: whether nyaa.si is the right target for every
# verify_via container generally, or just prowlarr specifically. This
# is left as an explicit override so Gorkaige can set the real target
# per network_group before this ships — do not treat the default below
# as validated.
: "${KAIJU_FM03_VERIFY_URL:=https://nyaa.si}"

_kaiju_verify_via_curl() {
    local container="$1"
    local code
    code=$(docker exec "$container" curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$KAIJU_FM03_VERIFY_URL" 2>/dev/null)
    [ "$code" = "200" ]
}

# --- Main loop over network_groups -------------------------------------
GROUP_COUNT=$(kaiju_network_group_count)

if [ "$GROUP_COUNT" -eq 0 ]; then
    _log "No network_groups configured. Nothing to check."
    echo "No network_groups configured in $KAIJU_CONFIG — nothing to check."
    exit 0
fi

OVERALL_FAIL=0

for i in $(seq 0 $((GROUP_COUNT - 1))); do
    OWNER=$(kaiju_network_group_field "$i" "owner")
    COMPOSE_DIR=$(kaiju_network_group_field "$i" "compose_dir")
    VERIFY_VIA=$(kaiju_network_group_field "$i" "verify_via")

    if _kaiju_owner_healthy "$OWNER"; then
        _log "${OWNER}: already healthy, no action taken"
        continue
    fi

    _log "${OWNER}: unhealthy — restarting (compose_dir: ${COMPOSE_DIR})"

    (cd "$COMPOSE_DIR" && docker compose restart "$OWNER") >>"$LOG" 2>&1

    if ! kaiju_retry_check "_kaiju_owner_healthy '$OWNER'" 4 15; then
        # CAVEAT (Round 3 testing, 2026-09-08): this log line describes
        # this script's OWN explicit dependent-restart loop below, not
        # the dependent container's actual restart state. Confirmed
        # live: for a dependent using `network_mode: service:<owner>`,
        # Docker Compose itself cascade-restarts the dependent the
        # instant `docker compose restart <owner>` runs, a few lines up
        # from here — independent of whether the owner ever becomes
        # healthy. The fail-safe still correctly prevents THIS script
        # from explicitly restarting the dependent again, but it does
        # not prevent Compose's own implicit restart from having
        # already happened. See tests/TESTING.md Round 3 notes.
        _log "${OWNER}: FAILED to become healthy after restart + retries. NOT restarting dependents via this script's own loop (fail-safe) — note Compose may have already cascade-restarted network_mode:service dependents as a side effect of the owner restart above."
        OVERALL_FAIL=1
        continue
    fi

    _log "${OWNER}: healthy after restart. Restarting dependents."

    DEPENDENTS=()
    while IFS= read -r dep; do
        DEPENDENTS+=("$dep")
    done < <(kaiju_network_group_dependents "$i")

    for dep in "${DEPENDENTS[@]}"; do
        (cd "$COMPOSE_DIR" && docker compose restart "$dep") >>"$LOG" 2>&1
        _log "${dep}: restarted (dependent of ${OWNER})"
    done

    # Real curl check per the reference runbook, not just container/health status.
    if [ -n "$VERIFY_VIA" ]; then
        if kaiju_retry_check "_kaiju_verify_via_curl '$VERIFY_VIA'" 4 10; then
            _log "${OWNER} group: verified via real curl from ${VERIFY_VIA} (${KAIJU_FM03_VERIFY_URL})"
        else
            _log "${OWNER} group: dependents restarted but curl verification via ${VERIFY_VIA} FAILED — manual check needed"
            OVERALL_FAIL=1
        fi
    else
        _log "${OWNER} group: no verify_via configured, skipping curl check (config gap, not a script bug)"
    fi
done

exit $OVERALL_FAIL
