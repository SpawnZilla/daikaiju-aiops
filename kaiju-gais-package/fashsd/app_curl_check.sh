#!/bin/bash
# ============================================================
# ✅ TESTED 2026-07-23 — see kaiju-gais-package/fashsd/tests/TESTING.md
# ⚠️ MODIFIED 2026-09-13 — two real gaps fixed, found 2026-09-12 blocking
# app-level FASHSD coverage for Omada/Scanopy/Watchtower/Portainer-agent:
#   1. Missing-health_url skip-gap: a service with no health_url (e.g.
#      Watchtower, which has no HTTP endpoint at all) previously fell
#      through to check_service() with URL="null" and was counted as a
#      FAIL, not skipped. Now explicitly SKIPped before check_service()
#      is ever called.
#   2. No TLS/self-signed-cert support: services behind HTTPS with a
#      self-signed cert (e.g. Omada) always failed curl's cert
#      verification. New optional per-service config field
#      `insecure_tls: true` (schema v1.4) passes curl -k for that
#      service only.
# NOT YET LIVE-VERIFIED against real production services with either new
# path exercised — written against the schema/lib pattern, re-run
# tests/run_tests.sh and a real Omada/Watchtower check before trusting
# this in production.
# ============================================================
# app_curl_check.sh — Kaiju Spine config-driven app-level health check
# Generalized from Kaidosho's (FM-09) app_curl_check.sh.
# Deploy to: /opt/kaiju-spine/watchdog/
#
# ORIGINAL Kaidosho SCRIPT: 10 hardcoded check_service() call sites, one per
# Kaidosho service. This version loops over services[] from the Kaiju Spine
# config instead. The check_service() function body below is UNCHANGED
# from the original except for the insecure_tls addition — confirming
# the generalization work is in the call sites, not the check logic
# itself.

: "${KAIJU_LIB_DIR:=/opt/kaiju-spine/watchdog}"
source "$KAIJU_LIB_DIR/fashsd_config_lib.sh"

: "${KAIJU_LOG_DIR:=/var/log/kaiju-watchdog}"
mkdir -p "$KAIJU_LOG_DIR" 2>/dev/null || KAIJU_LOG_DIR="/tmp/kaiju-watchdog-fallback"
mkdir -p "$KAIJU_LOG_DIR"

LOG="$KAIJU_LOG_DIR/watchdog.log"
PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0
FAIL_LINES=""

# --- MODIFIED 2026-08-01: single-shot curl replaced with
# kaiju_retry_check() (fashsd_config_lib.sh) -- a transient blip/cold
# start no longer declares FAIL on the first bad response. Default 4
# attempts / 5s delay between, overridable via KAIJU_HEALTHCHECK_RETRIES /
# KAIJU_HEALTHCHECK_RETRY_DELAY env vars. check_service()'s own
# PASS/FAIL/log contract to callers is UNCHANGED -- same signature, same
# LOG format, same PASS_COUNT/FAIL_COUNT/FAIL_LINES side effects -- only
# the internal probe is now retried instead of single-shot.
# NOT YET LIVE-VERIFIED against real Dokaisho services or re-run through
# tests/run_tests.sh -- written against retry_helper.sh's own tested logic
# (4-way tested 2026-07-31: immediate pass, exhausted retries, recovery on
# attempt 3, default args) but this specific integration has not been
# executed. Re-run the test suite (steps 1-3, harmless/isolated checks)
# before trusting this in production.
check_service() {
    local NAME="$1"
    local URL="$2"
    local EXPECT="$3"
    local TIMEOUT="$4"
    local INSECURE="$5"
    local TIMESTAMP
    local LAST_HTTP_CODE=""
    local CURL_INSECURE_FLAG=""

    # --- NEW 2026-09-13: optional per-service -k for self-signed certs ---
    if [ "$INSECURE" = "true" ]; then
        CURL_INSECURE_FLAG="-k"
    fi

    _kaiju_curl_probe() {
        local HTTP_CODE
        HTTP_CODE=$(curl -s $CURL_INSECURE_FLAG -o /dev/null -w '%{http_code}' --max-time "$TIMEOUT" "$URL" 2>/dev/null)
        local CURL_EXIT=$?
        if [ $CURL_EXIT -ne 0 ] && [ -z "$HTTP_CODE" ]; then
            HTTP_CODE="timeout"
        fi
        LAST_HTTP_CODE="$HTTP_CODE"
        [ "$HTTP_CODE" = "$EXPECT" ]
    }

    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    if kaiju_retry_check "_kaiju_curl_probe" "${KAIJU_HEALTHCHECK_RETRIES:-4}" "${KAIJU_HEALTHCHECK_RETRY_DELAY:-5}"; then
        echo "$TIMESTAMP | app_curl | ${NAME}: PASS (${LAST_HTTP_CODE})" >> "$LOG"
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo "$TIMESTAMP | app_curl | ${NAME}: FAIL (${LAST_HTTP_CODE}) after ${KAIJU_HEALTHCHECK_RETRIES:-4} attempts" >> "$LOG"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        FAIL_LINES="${FAIL_LINES}FAIL: ${NAME} (${LAST_HTTP_CODE}, after retries)\n"
    fi
}

# --- NEW: config-driven loop replaces the 10 hardcoded call sites ---
SERVICE_COUNT=$(kaiju_service_count)

if [ "$SERVICE_COUNT" -eq 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') | app_curl | No services configured. Nothing to check." >> "$LOG"
    echo "No services configured in $KAIJU_CONFIG — nothing to check."
    exit 0
fi

for i in $(seq 0 $((SERVICE_COUNT - 1))); do
    NAME=$(kaiju_service_field "$i" "name")
    URL=$(kaiju_service_field "$i" "health_url")
    EXPECT=$(kaiju_service_field "$i" "expected_code")
    TIMEOUT=$(kaiju_service_field "$i" "timeout_seconds")
    INSECURE=$(kaiju_service_field "$i" "insecure_tls")

    # --- NEW 2026-09-13: missing-health_url skip-gap fix. yq -r returns
    # the literal string "null" for an absent/omitted key (see
    # fashsd_config_lib.sh's own kaiju_ntfy_url for the same pattern) --
    # treat that (or a genuinely empty string) as "no HTTP endpoint for
    # this service", not as a URL to curl and fail.
    if [ -z "$URL" ] || [ "$URL" = "null" ]; then
        TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
        echo "$TIMESTAMP | app_curl | ${NAME}: SKIP (no health_url configured)" >> "$LOG"
        SKIP_COUNT=$((SKIP_COUNT + 1))
        continue
    fi

    check_service "$NAME" "$URL" "$EXPECT" "$TIMEOUT" "$INSECURE"
done

echo "PASS: ${PASS_COUNT}  FAIL: ${FAIL_COUNT}  SKIP: ${SKIP_COUNT}"
if [ $FAIL_COUNT -gt 0 ]; then
    printf "%b" "$FAIL_LINES"
fi

[ $FAIL_COUNT -eq 0 ] && exit 0 || exit 1
