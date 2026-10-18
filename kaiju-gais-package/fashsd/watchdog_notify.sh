#!/bin/bash
# ============================================================
# NOT YET TESTED — watchdog_notify.sh, Kaiju OS config-driven ntfy wrapper
# Deploy to: /opt/kaiju-os/watchdog/
# Generalized from Kaidosho's watchdog_notify.sh. CREDENTIAL HANDLING
# CHANGED DELIBERATELY: the original hardcoded a plaintext ntfy
# password directly in this file (a real exposure, since vault is
# git-versioned). This version NEVER hardcodes a credential — auth is
# read from KAIJU_NTFY_USER / KAIJU_NTFY_PASS environment variables,
# both optional (unauthenticated ntfy topics are valid).
# ============================================================

: "${KAIJU_LIB_DIR:=/opt/kaiju-os/watchdog}"
source "$KAIJU_LIB_DIR/fashsd_config_lib.sh"

: "${KAIJU_LOG_DIR:=/var/log/kaiju-watchdog}"
mkdir -p "$KAIJU_LOG_DIR" 2>/dev/null || KAIJU_LOG_DIR="/tmp/kaiju-watchdog-fallback"
mkdir -p "$KAIJU_LOG_DIR"

if [ $# -ne 3 ]; then
    echo "Usage: $0 <title> <message> <priority>" >&2
    exit 1
fi

TITLE="$1"
MESSAGE="$2"
PRIORITY="$3"

NTFY_URL="$(kaiju_ntfy_url)/$(kaiju_ntfy_topic)"

CURL_ARGS=(-H "Title: $TITLE" -H "Priority: $PRIORITY" -d "$MESSAGE" "$NTFY_URL")

# Only add -u if BOTH env vars are set — never partial credentials
if [ -n "$KAIJU_NTFY_USER" ] && [ -n "$KAIJU_NTFY_PASS" ]; then
    CURL_ARGS=(-u "${KAIJU_NTFY_USER}:${KAIJU_NTFY_PASS}" "${CURL_ARGS[@]}")
fi

curl "${CURL_ARGS[@]}"
EXIT_CODE=$?

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
echo "$TIMESTAMP | ${TITLE} | Exit code: ${EXIT_CODE}" >> "$KAIJU_LOG_DIR/watchdog.log"

exit $EXIT_CODE
