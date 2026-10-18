#!/bin/bash
# ============================================================
# ✅ TESTED 2026-07-23 — see kaiju-gais-package/fashsd/tests/TESTING.md
# ============================================================
# wol_trigger.sh — Kaiju OS config-driven Wake-on-LAN trigger
# Generalized from Kaidosho's wol_trigger.sh.
# Deploy to: /opt/kaiju-os/watchdog/
#
# ORIGINAL Kaidosho SCRIPT: hardcoded MAC address, always sends a WoL packet
# (Kaidosho is always two-node). This version reads topology.mode from config
# first — single-node installs have nothing to wake, so this becomes a
# clean no-op instead of erroring or sending a meaningless packet.

: "${KAIJU_LIB_DIR:=/opt/kaiju-os/watchdog}"
source "$KAIJU_LIB_DIR/fashsd_config_lib.sh"

: "${KAIJU_LOG_DIR:=/var/log/kaiju-watchdog}"
mkdir -p "$KAIJU_LOG_DIR" 2>/dev/null || KAIJU_LOG_DIR="/tmp/kaiju-watchdog-fallback"
mkdir -p "$KAIJU_LOG_DIR"

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
LOG="$KAIJU_LOG_DIR/watchdog.log"

# --- NEW: topology-aware branch, absent from Kaidosho's original (Kaidosho is
# always two-node, so this check never needed to exist there) ---
MODE=$(kaiju_topology_mode)

if [ "$MODE" = "single-node" ]; then
    echo "$TIMESTAMP | wol_trigger | Skipped — single-node topology, nothing to wake" >> "$LOG"
    echo "Single-node install — WoL not applicable. No action taken."
    exit 0
fi

if [ "$MODE" != "two-node-wol" ]; then
    echo "$TIMESTAMP | wol_trigger | ERROR: unrecognized topology.mode '$MODE'" >> "$LOG"
    echo "ERROR: topology.mode in config must be 'single-node' or 'two-node-wol', got: $MODE" >&2
    exit 1
fi

TARGET_MAC=$(kaiju_target_mac)

if [ -z "$TARGET_MAC" ] || [ "$TARGET_MAC" = "null" ]; then
    echo "$TIMESTAMP | wol_trigger | ERROR: two-node-wol mode but no target MAC in config" >> "$LOG"
    echo "ERROR: topology.mode is two-node-wol but topology.target_node.mac is not set." >&2
    exit 1
fi

# --- UNCHANGED from original: send the packet, log the result ---
/usr/bin/wakeonlan "$TARGET_MAC"

EXIT_CODE=$?

echo "$TIMESTAMP | wakeonlan command | Target: $TARGET_MAC | Exit code: $EXIT_CODE" >> "$LOG"

exit $EXIT_CODE
