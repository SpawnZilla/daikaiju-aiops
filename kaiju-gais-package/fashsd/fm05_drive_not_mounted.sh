#!/bin/bash
# ============================================================
# ✅ TESTED 2026-07-27 — see kaiju-gais-package/fashsd/tests/TESTING.md
# Banner correction 2026-09-08: this file still carried the pre-test
# UNTESTED warning despite TESTING.md recording the removal as done
# on 2026-07-27 — Round 2 results (Step 8) confirmed PASS, doc update
# never reached this file. No code change, banner only.
# ============================================================
# fm05_drive_not_mounted.sh — Kaiju Spine config-driven drive remount fix
# Generalized from Kaidosho's fm05_drive_not_mounted.sh.
# Deploy to: /opt/kaiju-spine/watchdog/

: "${KAIJU_LIB_DIR:=/opt/kaiju-spine/watchdog}"
source "$KAIJU_LIB_DIR/fashsd_config_lib.sh"

: "${KAIJU_LOG_DIR:=/var/log/kaiju-watchdog}"
mkdir -p "$KAIJU_LOG_DIR" 2>/dev/null || KAIJU_LOG_DIR="/tmp/kaiju-watchdog-fallback"
mkdir -p "$KAIJU_LOG_DIR"

LOG="$KAIJU_LOG_DIR/watchdog.log"

# Validate drive name against config
DRIVE_COUNT=$(kaiju_drive_count)
VALID_NAMES=""
for i in $(seq 0 $((DRIVE_COUNT - 1))); do
    VALID_NAMES="$VALID_NAMES $(kaiju_drive_field "$i" name)"
done

if [ $# -ne 1 ]; then
    echo "Usage: $0 <drive_name>" >&2
    echo "drive_name must be one of:$VALID_NAMES" >&2
    exit 1
fi
drive_name=$1

VALID_DRIVE=false
for i in $(seq 0 $((DRIVE_COUNT - 1))); do
    CONFIG_DRIVE_NAME=$(kaiju_drive_field "$i" "name")
    if [ "$CONFIG_DRIVE_NAME" = "$drive_name" ]; then
        VALID_DRIVE=true
        break
    fi
done
if [ "$VALID_DRIVE" = false ]; then
    echo "Error: drive_name must be one of:$VALID_NAMES" >&2
    exit 1
fi

# Set up logging (snapshot dir is created by watchdog_snapshot.sh itself,
# under $KAIJU_LOG_DIR -- the old hardcoded /var/log mkdir here ignored
# KAIJU_LOG_DIR and failed for non-root runs; removed 2026-09-25, Round 6)
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
echo "$TIMESTAMP | FM-05 | Starting fix for $drive_name" >> "$LOG"

# Take snapshot
"$KAIJU_LIB_DIR/watchdog_snapshot.sh" "${drive_name}_mount" 1

# Run the fix command
sudo mount "/mnt/$drive_name"

# Sleep
sleep 5

# Run verification
if mountpoint -q "/mnt/$drive_name"; then
    # Verify passed
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    echo "$TIMESTAMP | FM-05 | PASS: $drive_name is mounted" >> "$LOG"
    exit 0
else
    # Verify failed
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    echo "$TIMESTAMP | FM-05 | FAIL: $drive_name is not mounted" >> "$LOG"
    exit 1
fi