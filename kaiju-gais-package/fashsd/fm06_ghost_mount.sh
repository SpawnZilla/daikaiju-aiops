#!/bin/bash
# ============================================================
# TESTED 2026-09-08 (Round 3) — see kaiju-gais-package/fashsd/tests/TESTING.md
# ============================================================
# fm06_ghost_mount.sh — Kaiju OS config-driven ghost-mount recovery.
#
# Generalized from Kaidosho's FM-06 (hola3-only): force-unmount a
# drive twice (lazy unmount, matches the original's exact `umount -l`
# x2 pattern — preserved unchanged per MABS Rule 16, architecture
# preservation), remount via fstab, then verify by checking configured
# expected_subdirs exist — not just that mountpoint(1) succeeds.
#
# Deploy to: /opt/kaiju-os/watchdog/
#
# Generalization notes (Mokaima, 2026-09-06):
#   - Takes a drive name as an argument, same calling convention as
#     the already-tested fm05_drive_not_mounted.sh.
#   - Hardcoded /mnt/hola3 + 3 hardcoded subdirs (docker-data,
#     containerd-data, compose) -> looked up via
#     kaiju_drive_index_by_name() + kaiju_drive_field()/
#     kaiju_drive_expected_subdirs() (schema v1.3, see that file's
#     changelog).
#   - Original fix logic (umount -l x2, then mount, then verify)
#     preserved exactly — only call-site values changed.
#   - If a drive has zero expected_subdirs configured, this falls back
#     to a plain mountpoint(1) check (same as FM-05) rather than
#     failing — a drive with nothing configured to verify shouldn't be
#     unable to use this fix at all.

: "${KAIJU_LIB_DIR:=/opt/kaiju-os/watchdog}"
source "$KAIJU_LIB_DIR/fashsd_config_lib.sh"

: "${KAIJU_LOG_DIR:=/var/log/kaiju-watchdog}"
mkdir -p "$KAIJU_LOG_DIR" 2>/dev/null || KAIJU_LOG_DIR="/tmp/kaiju-watchdog-fallback"
mkdir -p "$KAIJU_LOG_DIR"

LOG="$KAIJU_LOG_DIR/watchdog.log"

_log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') | fm06_ghost_mount | $1" >> "$LOG"
}

if [ $# -ne 1 ]; then
    echo "Usage: $0 <drive_name>" >&2
    exit 1
fi

drive_name="$1"

DRIVE_IDX=$(kaiju_drive_index_by_name "$drive_name")
if [ -z "$DRIVE_IDX" ]; then
    echo "Error: drive_name '$drive_name' not found in $KAIJU_CONFIG" >&2
    _log "FAIL: drive_name '$drive_name' not found in config"
    exit 1
fi

MOUNT_POINT=$(kaiju_drive_field "$DRIVE_IDX" mount_point)

_log "Starting ghost-mount recovery for $drive_name ($MOUNT_POINT)"

echo "Force-unmounting $MOUNT_POINT (x2, lazy)..."
sudo umount -l "$MOUNT_POINT" 2>/dev/null
sudo umount -l "$MOUNT_POINT" 2>/dev/null

echo "Remounting via fstab..."
sudo mount "$MOUNT_POINT"
sleep 5

# Build the expected-subdirs list. Empty list -> fall back to a plain
# mountpoint(1) check (see header note above).
EXPECTED_SUBDIRS=()
while IFS= read -r subdir; do
    [ -n "$subdir" ] && EXPECTED_SUBDIRS+=("$subdir")
done < <(kaiju_drive_expected_subdirs "$DRIVE_IDX")

VERIFY_OK=1
if [ "${#EXPECTED_SUBDIRS[@]}" -eq 0 ]; then
    _log "${drive_name}: no expected_subdirs configured, falling back to plain mountpoint check"
    mountpoint -q "$MOUNT_POINT" || VERIFY_OK=0
else
    for subdir in "${EXPECTED_SUBDIRS[@]}"; do
        if [ ! -d "$MOUNT_POINT/$subdir" ]; then
            _log "${drive_name}: expected subdir '$subdir' missing after remount"
            VERIFY_OK=0
        fi
    done
fi

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
if [ "$VERIFY_OK" -eq 1 ]; then
    echo "$TIMESTAMP | fm06_ghost_mount | PASS: $drive_name ghost-mount recovery successful" >> "$LOG"
    echo "PASS: $drive_name ghost-mount recovery successful"
    exit 0
else
    echo "$TIMESTAMP | fm06_ghost_mount | FAIL: $drive_name ghost-mount recovery failed" >> "$LOG"
    echo "FAIL: $drive_name ghost-mount recovery failed"
    exit 1
fi
