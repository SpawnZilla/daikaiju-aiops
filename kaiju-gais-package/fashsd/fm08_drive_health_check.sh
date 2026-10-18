#!/bin/bash
# ============================================================
# NOT YET LIVE-TESTED against real pi-node infrastructure —
# logic-tested only (Mokaima's sandbox, mocked smartctl). Written
# 2026-09-14 to close the gap flagged in this package's own
# README.md ("Remaining Kaiju OS package work"). Re-run through
# tests/run_tests.sh (or a manual live invocation) before trusting
# this in production, per this project's standing verification
# discipline.
# ============================================================
# fm08_drive_health_check.sh — Kaiju OS config-driven SMART/drive
# health check.
# Deploy to: /opt/kaiju-os/watchdog/
#
# No Kaidosho original to generalize from -- this is new, following the
# same config-driven loop pattern app_curl_check.sh already
# established for services[] (kaiju_drive_count/kaiju_drive_field
# from fashsd_config_lib.sh, PASS/FAIL/SKIP counters, same
# watchdog.log line format, same overall exit-code convention).
#
# For each entry in drives[] with smart_check: true, runs
# `smartctl -H <device>` and reports its overall-health verdict.
# Drives with smart_check missing/false/null are SKIPped, not
# failed -- not every configured drive is necessarily a real
# physical disk smartctl can query (e.g. a network mount or a USB
# enclosure that doesn't pass SMART through). Also SKIPs (rather
# than fails) a drive whose device path doesn't exist, or where
# smartctl itself reports it can't read SMART data for that device
# (some USB bridges/enclosures) -- both are configuration/hardware
# facts, not evidence of drive failure.
#
# This is a detection/report script, not a remediation (FM-##) fix
# script -- there is no automated fix for failing SMART data, only
# an alert. It follows the app_curl_check.sh reporting shape (PASS/
# FAIL/SKIP summary line + individual watchdog.log entries) so it
# plugs into the same orchestrator pattern as everything else in
# this package, but it never attempts a `docker compose up`-style
# remediation the way FM-01/02/05/etc. do -- there's nothing this
# script itself could safely automate for a real failing disk.

: "${KAIJU_LIB_DIR:=/opt/kaiju-os/watchdog}"
source "$KAIJU_LIB_DIR/fashsd_config_lib.sh"

: "${KAIJU_LOG_DIR:=/var/log/kaiju-watchdog}"
mkdir -p "$KAIJU_LOG_DIR" 2>/dev/null || KAIJU_LOG_DIR="/tmp/kaiju-watchdog-fallback"
mkdir -p "$KAIJU_LOG_DIR"

LOG="$KAIJU_LOG_DIR/watchdog.log"
PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0
FAIL_LINES=""

if ! command -v smartctl >/dev/null 2>&1; then
    echo "FATAL: smartctl not found. Install: apt install smartmontools (Debian/Ubuntu)" >&2
    exit 1
fi

DRIVE_COUNT=$(kaiju_drive_count)

if [ "$DRIVE_COUNT" -eq 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') | fm08_drive_health | No drives configured. Nothing to check." >> "$LOG"
    echo "No drives configured in ${KAIJU_CONFIG} — nothing to check."
    exit 0
fi

for i in $(seq 0 $((DRIVE_COUNT - 1))); do
    NAME=$(kaiju_drive_field "$i" "name")
    DEVICE=$(kaiju_drive_field "$i" "device")
    SMART_CHECK=$(kaiju_drive_field "$i" "smart_check")
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

    if [ "$SMART_CHECK" != "true" ]; then
        echo "$TIMESTAMP | fm08_drive_health | ${NAME}: SKIP (smart_check not enabled)" >> "$LOG"
        SKIP_COUNT=$((SKIP_COUNT + 1))
        continue
    fi

    if [ -z "$DEVICE" ] || [ "$DEVICE" = "null" ]; then
        echo "$TIMESTAMP | fm08_drive_health | ${NAME}: SKIP (no device configured)" >> "$LOG"
        SKIP_COUNT=$((SKIP_COUNT + 1))
        continue
    fi

    if [ ! -e "$DEVICE" ]; then
        echo "$TIMESTAMP | fm08_drive_health | ${NAME}: SKIP (device $DEVICE not present)" >> "$LOG"
        SKIP_COUNT=$((SKIP_COUNT + 1))
        continue
    fi

    SMART_OUTPUT=$(smartctl -H "$DEVICE" 2>&1)
    SMART_EXIT=$?

    # smartctl's exit code is a bitmask -- bit 0 (command-line/device-
    # open failure) and bit 1 (device open/SMART-not-supported) both
    # mean "couldn't get a real answer", not "drive is failing" --
    # those are SKIP, not FAIL. Bits 2-7 relate to actual SMART/self-test
    # findings and are only meaningful if we got a real health verdict
    # in the first place, so the overall-health STRING (PASSED/FAILED)
    # is the primary signal here, exit code is only used to distinguish
    # "couldn't check" from "checked, and here's the verdict".
    if [ $((SMART_EXIT & 3)) -ne 0 ]; then
        echo "$TIMESTAMP | fm08_drive_health | ${NAME}: SKIP (smartctl could not query $DEVICE -- unsupported device/bridge, or needs root)" >> "$LOG"
        SKIP_COUNT=$((SKIP_COUNT + 1))
        continue
    fi

    if echo "$SMART_OUTPUT" | grep -qi "PASSED"; then
        echo "$TIMESTAMP | fm08_drive_health | ${NAME}: PASS (SMART overall-health: PASSED, $DEVICE)" >> "$LOG"
        PASS_COUNT=$((PASS_COUNT + 1))
    elif echo "$SMART_OUTPUT" | grep -qi "FAILED"; then
        echo "$TIMESTAMP | fm08_drive_health | ${NAME}: FAIL (SMART overall-health: FAILED, $DEVICE)" >> "$LOG"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        FAIL_LINES="${FAIL_LINES}FAIL: ${NAME} (SMART overall-health: FAILED, $DEVICE)\n"
    else
        # smartctl ran and returned a clean exit code, but its output
        # didn't contain a recognizable PASSED/FAILED verdict string --
        # treat as SKIP (ambiguous), not FAIL (a wrongly-parsed FAIL
        # would be a false alert, worse than a missed one for this
        # detection-only script).
        echo "$TIMESTAMP | fm08_drive_health | ${NAME}: SKIP (smartctl ran but returned no recognizable PASSED/FAILED verdict for $DEVICE)" >> "$LOG"
        SKIP_COUNT=$((SKIP_COUNT + 1))
    fi
done

echo "PASS: ${PASS_COUNT}  FAIL: ${FAIL_COUNT}  SKIP: ${SKIP_COUNT}"
if [ $FAIL_COUNT -gt 0 ]; then
    printf "%b" "$FAIL_LINES"
fi

[ $FAIL_COUNT -eq 0 ] && exit 0 || exit 1
