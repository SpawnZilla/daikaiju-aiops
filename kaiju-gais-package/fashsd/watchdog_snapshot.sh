#!/bin/bash
# ============================================================
# NOT YET LIVE-TESTED against real pi-node infrastructure —
# logic-tested only (Mokaima's sandbox, mocked docker). Written
# 2026-09-14 to close the gap flagged in this package's own
# README.md ("Remaining Kaiju OS package work"). Re-run through
# tests/run_tests.sh (or a manual live invocation) before trusting
# this in production, per this project's standing verification
# discipline.
# ============================================================
# watchdog_snapshot.sh — Kaiju OS config-driven pre-remediation
# snapshot utility.
# Deploy to: /opt/kaiju-os/watchdog/
#
# Referenced by fm01_container_exited.sh, fm02_daemon_down.sh, and
# fm05_drive_not_mounted.sh (all three already handle its absence
# gracefully — see each script's own snapshot step). This is the
# first real implementation; none of the three needed any change to
# start using it, since this script matches the exact calling
# contract they already assumed.
#
# Usage: watchdog_snapshot.sh <name> <keep_count> [compose_dir]
#   <name>        A label for what's being snapshotted: a real
#                 container name (fm01/fm05-style), or a pseudo-name
#                 such as "docker-daemon" (fm02) or "<drive>_mount"
#                 (fm05). Not validated against config here — every
#                 caller already validates its own argument before
#                 invoking this script.
#   <keep_count>  How many prior snapshots for this <name> to retain
#                 (oldest deleted first). Every current caller passes 1.
#   [compose_dir] Optional. Only used if <name> is a real, currently
#                 inspectable container — captures `docker compose
#                 logs` from that directory too. Omitted by fm02/fm05
#                 (neither call is container-specific).
#
# Writes one timestamped snapshot file to
# $KAIJU_LOG_DIR/snapshots/<safe-name>_<timestamp>.log containing
# whatever of the following are actually available — never fails the
# caller's remediation attempt over a missing piece:
#   - `docker inspect <name>` + `docker logs --tail 200 <name>`,
#     only if <name> resolves to a real, currently inspectable container
#   - `docker compose logs --tail 200` from compose_dir, only if given
#     AND <name> is a real container (a pseudo-name with a compose_dir
#     doesn't make sense and is silently skipped)
#   - `df -h` — always, cheap, and directly useful for drive-related
#     remediation snapshots (fm05/fm06 territory)
#   - invocation metadata (hostname, timestamp, exact args) for
#     traceability
#
# Contract with callers: ONLY the final snapshot file path is ever
# printed to real stdout (matching fm01/fm02/fm05's existing
# `SNAPSHOT_PATH=$(...)` capture) — every other message goes to
# stderr or into the snapshot file itself. Exits 0 unless the log
# directory itself cannot be created, since a snapshot failure should
# never block the remediation it precedes.

: "${KAIJU_LOG_DIR:=/var/log/kaiju-watchdog}"
SNAPSHOT_DIR="$KAIJU_LOG_DIR/snapshots"
mkdir -p "$SNAPSHOT_DIR" 2>/dev/null || {
    echo "FATAL: cannot create $SNAPSHOT_DIR" >&2
    exit 1
}

if [ $# -lt 2 ]; then
    echo "Usage: $0 <name> <keep_count> [compose_dir]" >&2
    exit 1
fi

NAME="$1"
KEEP_COUNT="$2"
COMPOSE_DIR="${3:-}"

TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
SAFE_NAME=$(printf '%s' "$NAME" | tr -c 'A-Za-z0-9_.-' '_')
SNAPSHOT_FILE="$SNAPSHOT_DIR/${SAFE_NAME}_${TIMESTAMP}.log"

{
    echo "=== Kaiju OS watchdog snapshot ==="
    echo "name: $NAME"
    echo "keep_count: $KEEP_COUNT"
    echo "compose_dir: ${COMPOSE_DIR:-<none>}"
    echo "hostname: $(hostname 2>/dev/null || echo unknown)"
    echo "timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
    echo

    IS_CONTAINER=false
    if command -v docker >/dev/null 2>&1 && docker inspect "$NAME" >/dev/null 2>&1; then
        IS_CONTAINER=true
    fi

    if [ "$IS_CONTAINER" = true ]; then
        echo "--- docker inspect $NAME ---"
        docker inspect "$NAME" 2>&1 || echo "(docker inspect failed)"
        echo
        echo "--- docker logs --tail 200 $NAME ---"
        docker logs --tail 200 "$NAME" 2>&1 || echo "(docker logs failed)"
        echo

        if [ -n "$COMPOSE_DIR" ] && [ -d "$COMPOSE_DIR" ]; then
            echo "--- docker compose logs --tail 200 (from $COMPOSE_DIR) ---"
            (cd "$COMPOSE_DIR" && docker compose logs --tail 200 2>&1) || echo "(docker compose logs failed)"
            echo
        fi
    else
        echo "--- $NAME is not a real, currently inspectable container (pseudo-name, e.g. docker-daemon or a drive-mount label, or a container that's actually gone) -- skipping docker inspect/logs ---"
        echo
    fi

    echo "--- df -h ---"
    df -h 2>&1 || echo "(df failed)"
} > "$SNAPSHOT_FILE" 2>&1

# Rotate: keep only the KEEP_COUNT most recent snapshots for this NAME.
# shellcheck disable=SC2012
ls -1t "$SNAPSHOT_DIR/${SAFE_NAME}_"*.log 2>/dev/null | tail -n +$((KEEP_COUNT + 1)) | while IFS= read -r OLD; do
    rm -f "$OLD"
done

echo "$SNAPSHOT_FILE"
exit 0
