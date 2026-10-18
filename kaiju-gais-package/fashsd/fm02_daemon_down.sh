#!/bin/bash
# ============================================================
# ✅ TESTED 2026-07-27 — see kaiju-gais-package/fashsd/tests/TESTING.md
# COVERAGE GAP CLOSED 2026-09-25 (Round 6 Step 16): the real daemon-down
# path (Docker + docker.socket genuinely stopped) was exercised live via
# pi5_watchdog.sh -- daemon recovered, PASS. Original 2026-07-27 note
# kept below for history.
# (was) KNOWN COVERAGE GAP: the daemon-down recovery path itself (Docker
# genuinely stopped) was not exercised — `systemctl start docker` is
# a no-op when Docker is already running, which it was during testing.
# All other logic (snapshot skip, compose loop, verify/threshold) is
# confirmed correct. See TESTING.md Round 2 results for detail.
# ============================================================
# fm02_daemon_down.sh — Kaiju OS config-driven Docker daemon + full-stack restart
# Generalized from Kaidosho's fm02_daemon_down.sh.
# Deploy to: /opt/kaiju-os/watchdog/

: "${KAIJU_LIB_DIR:=/opt/kaiju-os/watchdog}"
source "$KAIJU_LIB_DIR/fashsd_config_lib.sh"

: "${KAIJU_LOG_DIR:=/var/log/kaiju-watchdog}"
mkdir -p "$KAIJU_LOG_DIR" 2>/dev/null || KAIJU_LOG_DIR="/tmp/kaiju-watchdog-fallback"
mkdir -p "$KAIJU_LOG_DIR"

LOG="$KAIJU_LOG_DIR/watchdog.log"

# Step 1-2: Snapshot (graceful skip if not yet packaged, matches
# fm01_container_exited.sh's established pattern — watchdog_snapshot.sh
# is not yet part of kaiju-gais-package/fashsd/, see README.md)
SNAPSHOT_PATH="(skipped)"
if [ -x "$KAIJU_LIB_DIR/watchdog_snapshot.sh" ]; then
    SNAPSHOT_PATH=$("$KAIJU_LIB_DIR/watchdog_snapshot.sh" "docker-daemon" 1)
    echo "Snapshot saved to: $SNAPSHOT_PATH"
else
    echo "NOTE: watchdog_snapshot.sh not found at $KAIJU_LIB_DIR — not yet"
    echo "packaged in kaiju-gais-package/fashsd/ (see README.md). Skipping"
    echo "snapshot step, proceeding directly to restart."
fi

# Step 3: Run the fix commands
echo "Restarting Docker daemon..."
sudo systemctl start docker

echo "Waiting 15 seconds for Docker to start..."
sleep 15

echo "Restarting all services..."
# Loop over all compose dirs from config and start services
MINIMUM_EXPECTED_CONTAINERS=$(kaiju_service_count)
COMPOSE_DIRS=$(kaiju_known_compose_dirs)
while IFS= read -r COMPOSE_DIR; do
    if [ -n "$COMPOSE_DIR" ] && [ -d "$COMPOSE_DIR" ]; then
        TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
        echo "$TIMESTAMP | fm02_daemon_down | Starting services in $COMPOSE_DIR..." >> "$LOG"
        cd "$COMPOSE_DIR" && docker compose down
        cd "$COMPOSE_DIR" && docker compose up -d
    fi
done <<< "$COMPOSE_DIRS"

# Step 4: Sleep for 10 seconds
echo "Sleeping for 10 seconds..."
sleep 10

# Step 5: Run the verify command
echo "Verifying Docker daemon is active and container count meets threshold..."
VERIFY_RESULT=$(systemctl is-active docker)
CONTAINER_COUNT=$(docker ps -q | wc -l)

# Step 6: Log the result
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
if [ "$VERIFY_RESULT" = "active" ] && [ "$CONTAINER_COUNT" -ge "$MINIMUM_EXPECTED_CONTAINERS" ]; then
    echo "$TIMESTAMP | FM-02 | PASS: Docker daemon is active and $CONTAINER_COUNT containers are running (threshold: $MINIMUM_EXPECTED_CONTAINERS)" >> "$LOG"
    echo "PASS: Docker daemon is active and $CONTAINER_COUNT containers are running (threshold: $MINIMUM_EXPECTED_CONTAINERS)"
    exit 0
else
    echo "$TIMESTAMP | FM-02 | FAIL: Docker daemon is $VERIFY_RESULT and only $CONTAINER_COUNT containers are running (threshold: $MINIMUM_EXPECTED_CONTAINERS)" >> "$LOG"
    echo "FAIL: Docker daemon is $VERIFY_RESULT and only $CONTAINER_COUNT containers are running (threshold: $MINIMUM_EXPECTED_CONTAINERS)"
    exit 1
fi