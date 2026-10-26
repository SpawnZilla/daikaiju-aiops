#!/bin/bash
# ============================================================
# TESTED 2026-09-08 (Round 3) — see kaiju-gais-package/fashsd/tests/TESTING.md
# ============================================================
# fm07_dns_failure.sh — Kaiju Spine config-driven DNS/outbound-
# connectivity recovery.
#
# Generalized from Kaidosho's FM-07 (Prowlarr-only): restart a
# single service and verify outbound connectivity via a real curl
# check (not just container health), same as the original's
# `docker exec prowlarr curl ... nyaa.si` pattern.
#
# Deploy to: /opt/kaiju-spine/watchdog/
#
# Generalization notes (Mokaima, 2026-09-06):
#   - Takes a service name as an argument (new — the original was
#     hardcoded to Prowlarr only, no argument at all).
#   - Hardcoded compose_dir + hardcoded https://nyaa.si check ->
#     looked up via kaiju_service_index_by_name() + compose_dir/
#     dns_check_url fields (schema v1.3).
#   - If a service has no dns_check_url configured, this fails loudly
#     rather than silently no-op'ing — a config gap, not something to
#     paper over (matches fm03's "no verify_via configured" pattern of
#     logging the gap explicitly, but this check is the ENTIRE point
#     of this script, so it's a hard FAIL here, not a skip).
#   - Original fix logic (restart, sleep 15, curl from inside the
#     container) preserved exactly — only call-site values changed.

: "${KAIJU_LIB_DIR:=/opt/kaiju-spine/watchdog}"
source "$KAIJU_LIB_DIR/fashsd_config_lib.sh"

: "${KAIJU_LOG_DIR:=/var/log/kaiju-watchdog}"
mkdir -p "$KAIJU_LOG_DIR" 2>/dev/null || KAIJU_LOG_DIR="/tmp/kaiju-watchdog-fallback"
mkdir -p "$KAIJU_LOG_DIR"

LOG="$KAIJU_LOG_DIR/watchdog.log"

_log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') | fm07_dns_failure | $1" >> "$LOG"
}

if [ $# -ne 1 ]; then
    echo "Usage: $0 <service_name>" >&2
    exit 1
fi

service_name="$1"

SERVICE_IDX=$(kaiju_service_index_by_name "$service_name")
if [ -z "$SERVICE_IDX" ]; then
    echo "Error: service_name '$service_name' not found in $KAIJU_CONFIG" >&2
    _log "FAIL: service_name '$service_name' not found in config"
    exit 1
fi

COMPOSE_DIR=$(kaiju_service_field "$SERVICE_IDX" compose_dir)
CONTAINER=$(kaiju_service_field "$SERVICE_IDX" container)
DNS_CHECK_URL=$(kaiju_service_field "$SERVICE_IDX" dns_check_url)

if [ -z "$DNS_CHECK_URL" ] || [ "$DNS_CHECK_URL" = "null" ]; then
    echo "Error: '$service_name' has no dns_check_url configured — this fix cannot verify outbound connectivity for it." >&2
    _log "FAIL: '$service_name' has no dns_check_url configured — config gap, not a script bug"
    exit 1
fi

_log "Starting DNS/outbound recovery for $service_name (compose_dir: $COMPOSE_DIR)"

echo "Restarting $service_name..."
(cd "$COMPOSE_DIR" && docker compose restart "$CONTAINER") >>"$LOG" 2>&1
sleep 15

http_code=$(docker exec "$CONTAINER" curl -s -m 10 "$DNS_CHECK_URL" -o /dev/null -w '%{http_code}' 2>/dev/null)

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
if [ "$http_code" = "200" ]; then
    echo "$TIMESTAMP | fm07_dns_failure | PASS: $service_name DNS/outbound recovery successful (verified via $DNS_CHECK_URL)" >> "$LOG"
    echo "PASS: $service_name DNS/outbound recovery successful"
    exit 0
else
    echo "$TIMESTAMP | fm07_dns_failure | FAIL: $service_name DNS/outbound recovery failed, HTTP code: $http_code" >> "$LOG"
    echo "FAIL: $service_name DNS/outbound recovery failed, HTTP code: $http_code"
    exit 1
fi
