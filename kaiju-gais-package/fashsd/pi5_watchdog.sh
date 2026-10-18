#!/bin/bash
# ============================================================
# pi5_watchdog.sh, Kaiju OS config-driven orchestrator (every branch run live,
# Rounds 5+6 PASS 2026-09-25; see fashsd/tests/TESTING.md)
# Deploy to: /opt/kaiju-os/watchdog/
# Calls the 9 tested Kaiju OS FASHSD scripts (see
# kaiju-gais-package/fashsd/README.md, tested 2026-07-23 through
# 2026-09-08) based on symptoms detected against services.yaml.
# ============================================================

: "${KAIJU_LIB_DIR:=/opt/kaiju-os/watchdog}"
source "$KAIJU_LIB_DIR/fashsd_config_lib.sh"

: "${KAIJU_LOG_DIR:=/var/log/kaiju-watchdog}"
mkdir -p "$KAIJU_LOG_DIR" 2>/dev/null || KAIJU_LOG_DIR="/tmp/kaiju-watchdog-fallback"
mkdir -p "$KAIJU_LOG_DIR"

LOG="$KAIJU_LOG_DIR/watchdog.log"
CRIT=0

_log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') | pi5_watchdog | $1" >> "$LOG"
}

_alert() {
    # $1=title $2=message $3=priority
    if [ -x "$KAIJU_LIB_DIR/watchdog_notify.sh" ]; then
        "$KAIJU_LIB_DIR/watchdog_notify.sh" "$1" "$2" "$3"
    else
        _log "ALERT (no watchdog_notify.sh present): $1 - $2"
    fi
}

_log "=== Watchdog cycle start ==="

# --- STEP 1: Docker daemon check ---
if [ "$(systemctl is-active docker 2>/dev/null)" != "active" ]; then
    _log "Docker daemon not active — dispatching fm02_daemon_down.sh"
    "$KAIJU_LIB_DIR/fm02_daemon_down.sh"
    if [ $? -ne 0 ]; then
        CRIT=1
        _log "fm02_daemon_down.sh FAILED — daemon still not healthy"
    else
        _log "fm02_daemon_down.sh PASS — daemon recovered"
    fi
    _log "Skipping remaining checks this cycle (daemon was down)"
    if [ "$CRIT" -eq 1 ]; then
        _alert "Kaiju Watchdog CRIT" "Docker daemon down, fm02 recovery FAILED" "urgent"
        "$KAIJU_LIB_DIR/wol_trigger.sh"
    fi
    _log "=== Watchdog cycle end ==="
    exit $CRIT
fi

# --- STEP 2: Container exited scan, network-group-aware dispatch ---
EXITED=$(docker ps -a --filter "status=exited" --format '{{.Names}}')
if [ -n "$EXITED" ]; then
    while IFS= read -r cname; do
        [ -z "$cname" ] && continue

        IS_OWNER=false
        GROUP_COUNT=$(kaiju_network_group_count)
        for gi in $(seq 0 $((GROUP_COUNT - 1))); do
            OWNER=$(kaiju_network_group_field "$gi" "owner")
            if [ "$OWNER" = "$cname" ]; then
                IS_OWNER=true
                break
            fi
        done

        if [ "$IS_OWNER" = true ]; then
            _log "${cname}: exited, is a network_group owner — dispatching fm03_gluetun_unhealthy.sh"
            "$KAIJU_LIB_DIR/fm03_gluetun_unhealthy.sh"
            if [ $? -ne 0 ]; then
                CRIT=1
                _log "fm03 FAILED for ${cname}"
            fi
        else
            SVC_IDX=$(kaiju_service_index_by_name "$cname")
            if [ -z "$SVC_IDX" ]; then
                _log "${cname}: exited, not found in services[] — cannot dispatch fm01, alerting only"
                CRIT=1
                continue
            fi
            COMPOSE_DIR=$(kaiju_service_field "$SVC_IDX" "compose_dir")
            _log "${cname}: exited, dispatching fm01_container_exited.sh (compose_dir: ${COMPOSE_DIR})"
            "$KAIJU_LIB_DIR/fm01_container_exited.sh" "$cname" "$COMPOSE_DIR"
            if [ $? -ne 0 ]; then
                CRIT=1
                _log "fm01 FAILED for ${cname}"
            fi
        fi
    done <<< "$EXITED"
fi

# --- STEP 3/4: App-level curl check, dispatch + re-check on FAIL ---
CURL_OUTPUT=$("$KAIJU_LIB_DIR/app_curl_check.sh" 2>&1)
CURL_EXIT=$?
_log "app_curl_check.sh exit=${CURL_EXIT}"

if [ "$CURL_EXIT" -ne 0 ]; then
    FAILED_SERVICES=$(echo "$CURL_OUTPUT" | grep '^FAIL:' | sed -E 's/^FAIL: ([^ ]+).*/\1/')
    while IFS= read -r svc; do
        [ -z "$svc" ] && continue
        SVC_IDX=$(kaiju_service_index_by_name "$svc")
        if [ -z "$SVC_IDX" ]; then
            _log "${svc}: curl FAIL but not found in services[] — cannot dispatch, alerting only"
            CRIT=1
            continue
        fi
        DNS_URL=$(kaiju_service_field "$SVC_IDX" "dns_check_url")

        if [ -n "$DNS_URL" ] && [ "$DNS_URL" != "null" ]; then
            _log "${svc}: curl FAIL, has dns_check_url — dispatching fm07_dns_failure.sh"
            "$KAIJU_LIB_DIR/fm07_dns_failure.sh" "$svc"
            FIX_EXIT=$?
        else
            _log "${svc}: curl FAIL, no dns_check_url configured — no matching fix script exists (Kaiju OS package has no FM-09 equivalent). Best-effort: dispatching fm01_container_exited.sh, then re-checking curl regardless of fm01's own result."
            CONTAINER=$(kaiju_service_field "$SVC_IDX" "container")
            COMPOSE_DIR=$(kaiju_service_field "$SVC_IDX" "compose_dir")
            "$KAIJU_LIB_DIR/fm01_container_exited.sh" "$CONTAINER" "$COMPOSE_DIR"
            FIX_EXIT=$?
        fi

        # Re-check this ONE service's curl status regardless of the fix
        # script's own exit code — fm01 only verifies container-running,
        # not curl reachability, so a fm01 PASS does not prove the real
        # symptom cleared (confirmed design decision, 2026-09-08).
        RECHECK_URL=$(kaiju_service_field "$SVC_IDX" "health_url")
        RECHECK_EXPECT=$(kaiju_service_field "$SVC_IDX" "expected_code")
        RECHECK_TIMEOUT=$(kaiju_service_field "$SVC_IDX" "timeout_seconds")
        RECHECK_CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time "$RECHECK_TIMEOUT" "$RECHECK_URL" 2>/dev/null)

        if [ "$RECHECK_CODE" = "$RECHECK_EXPECT" ]; then
            _log "${svc}: curl re-check PASS (${RECHECK_CODE}) after fix (fix script exit was ${FIX_EXIT})"
        else
            _log "${svc}: curl re-check STILL FAILING (${RECHECK_CODE}, expected ${RECHECK_EXPECT}) after fix (fix script exit was ${FIX_EXIT}) — alerting"
            CRIT=1
        fi
    done <<< "$FAILED_SERVICES"
fi

# --- STEP 5/6: Drive checks — not mounted vs. mounted-but-broken ---
DRIVE_COUNT=$(kaiju_drive_count)
for di in $(seq 0 $((DRIVE_COUNT - 1))); do
    DNAME=$(kaiju_drive_field "$di" "name")
    DMOUNT=$(kaiju_drive_field "$di" "mount_point")

    if ! mountpoint -q "$DMOUNT" 2>/dev/null; then
        _log "${DNAME}: not mounted — dispatching fm05_drive_not_mounted.sh"
        "$KAIJU_LIB_DIR/fm05_drive_not_mounted.sh" "$DNAME"
        [ $? -ne 0 ] && CRIT=1 && _log "fm05 FAILED for ${DNAME}"
        continue
    fi

    SUBDIR_MISSING=false
    while IFS= read -r subdir; do
        [ -z "$subdir" ] && continue
        [ ! -d "$DMOUNT/$subdir" ] && SUBDIR_MISSING=true
    done < <(kaiju_drive_expected_subdirs "$di")

    if [ "$SUBDIR_MISSING" = true ]; then
        _log "${DNAME}: mounted but expected_subdirs missing (ghost mount) — dispatching fm06_ghost_mount.sh"
        "$KAIJU_LIB_DIR/fm06_ghost_mount.sh" "$DNAME"
        [ $? -ne 0 ] && CRIT=1 && _log "fm06 FAILED for ${DNAME}"
    fi
done

# --- STEP 6.5: SMART/drive health check (fm08, detection-only) ---
# No dispatch on FAIL -- fm08 has no automated remediation, it only
# reports. A FAIL here means a real disk is reporting a failing SMART
# overall-health verdict and needs a human, not a restart.
"$KAIJU_LIB_DIR/fm08_drive_health_check.sh" > /dev/null 2>&1
FM08_EXIT=$?
_log "fm08_drive_health_check.sh exit=${FM08_EXIT}"
[ "$FM08_EXIT" -ne 0 ] && CRIT=1 && _log "fm08 reported a FAILING drive -- see watchdog.log's own fm08_drive_health lines above for which one"

# --- STEP 7: Clock drift detection ---
KAIJU_CLOCK_DRIFT_THRESHOLD_MS=$(kaiju_clock_drift_threshold_ms)
DRIFT_DETECTED=false

if command -v timedatectl >/dev/null 2>&1 && timedatectl timesync-status >/dev/null 2>&1; then
    OFFSET_RAW=$(timedatectl timesync-status 2>/dev/null | grep -oP 'Offset:\s*\K[-0-9.]+(?=(us|ms|s))')
    OFFSET_UNIT=$(timedatectl timesync-status 2>/dev/null | grep -oP 'Offset:\s*[-0-9.]+\K(us|ms|s)')
    if [ -n "$OFFSET_RAW" ]; then
        case "$OFFSET_UNIT" in
            us) OFFSET_MS=$(awk "BEGIN{printf \"%.0f\", ($OFFSET_RAW)/1000}") ;;
            ms) OFFSET_MS=$(awk "BEGIN{printf \"%.0f\", ($OFFSET_RAW)}") ;;
            s)  OFFSET_MS=$(awk "BEGIN{printf \"%.0f\", ($OFFSET_RAW)*1000}") ;;
            *)  OFFSET_MS=0 ;;
        esac
        OFFSET_ABS=${OFFSET_MS#-}
        _log "Clock offset: ${OFFSET_MS}ms (threshold: ${KAIJU_CLOCK_DRIFT_THRESHOLD_MS}ms)"
        [ "$OFFSET_ABS" -ge "$KAIJU_CLOCK_DRIFT_THRESHOLD_MS" ] && DRIFT_DETECTED=true
    else
        _log "timesync-status ran but Offset line not parseable — falling back to binary sync check"
        [ "$(timedatectl status | grep -c 'System clock synchronized: yes')" -eq 0 ] && DRIFT_DETECTED=true
    fi
else
    _log "timedatectl timesync-status unavailable — falling back to binary sync check"
    [ "$(timedatectl status | grep -c 'System clock synchronized: yes')" -eq 0 ] && DRIFT_DETECTED=true
fi

if [ "$DRIFT_DETECTED" = true ]; then
    _log "Clock drift detected — dispatching fm04_clock_drift.sh (highest blast radius: restarts ALL configured services)"
    "$KAIJU_LIB_DIR/fm04_clock_drift.sh"
    [ $? -ne 0 ] && CRIT=1 && _log "fm04 FAILED"
fi

# --- STEP 8: End-of-cycle alerting + WoL ---
if [ "$CRIT" -eq 1 ]; then
    _alert "Kaiju Watchdog CRIT" "One or more unresolved issues this cycle — see $LOG" "urgent"
    "$KAIJU_LIB_DIR/wol_trigger.sh"
fi

_log "=== Watchdog cycle end (CRIT=$CRIT) ==="
exit $CRIT
