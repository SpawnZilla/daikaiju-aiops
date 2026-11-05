#!/bin/bash
# ============================================================
# NEW 2026-10-15 -- NOT YET RUN through tests/run_tests.sh and NOT YET
# LIVE-TESTED against the real FM-12 condition. Sandbox-tested only,
# against a mocked docker/journalctl/curl (10 scenarios + 4 assertions,
# see test_fm12_mocked.sh in this folder). Run it once by hand against the real svcuser config
# before trusting it in an automated cycle.
# ============================================================
# fm12_missing_image_snapshot.sh -- Kaiju OS config-driven FM-12 fix script
#
# FM-12: the container is ABSENT and `docker compose up -d` fails with
# "failed to stat parent: ... overlayfs/snapshots/<n>/fs: no such file or
# directory" -- the image's layer snapshot is missing from containerd
# while Docker still lists the image. Seen 2026-10-15 on lidarr.
# Runbook: angkai/staging//FM-12_container_missing_image_snapshot_missing.md
# Deploy to: /opt/kaiju-spine/watchdog/
#
# Usage: fm12_missing_image_snapshot.sh <container_name> <compose_dir>
# Same arguments as fm01_container_exited.sh so the orchestrator can
# dispatch it the same way. Exit 0 = fixed and verified. Exit 1 = not
# fixed or deliberately stopped; the reason is in watchdog.log.
#
# What it does, in order (every stop is a FAIL line plus exit 1, never a retry):
#   1. Validates the compose dir against the config allowlist (same as fm01).
#   2. Confirms the container is absent and the compose file defines the service.
#   3. Kernel-log precheck: stops if the last 2 hours show EXT4-fs errors,
#      I/O errors, a journal abort or a read-only remount (that is FM-10).
#      If the kernel log cannot be read, it logs that and continues: the
#      repair removes only a re-pullable image, never data.
#   4. Plain `docker compose up -d <service>`. If it works, done. If the
#      error is not the snapshot signature, stops (a different failure).
#   5. Shared-image check: stops if ANY container uses the same image.
#   6. `docker rmi -f <image>`, `docker compose pull <service>`,
#      `docker compose up -d <service>`. If the snapshot error comes back,
#      stops (no second attempt). Otherwise verifies running + health_url.
# It never runs `compose down` and never touches bind mounts.

: "${KAIJU_LIB_DIR:=/opt/kaiju-spine/watchdog}"
source "$KAIJU_LIB_DIR/fashsd_config_lib.sh"

: "${KAIJU_LOG_DIR:=/var/log/kaiju-watchdog}"
mkdir -p "$KAIJU_LOG_DIR" 2>/dev/null || KAIJU_LOG_DIR="/tmp/kaiju-watchdog-fallback"
mkdir -p "$KAIJU_LOG_DIR/snapshots" 2>/dev/null || true

# Timing knobs (defaults are the production values; tests override them)
: "${FM12_PLAIN_WAIT:=10}"
: "${FM12_SETTLE_SECONDS:=20}"
: "${FM12_HEALTH_TRIES:=6}"
: "${FM12_HEALTH_INTERVAL:=10}"
: "${FM12_KERNEL_WINDOW:=-2 hours}"

SIGNATURE_RE='failed to stat parent'
KERNEL_ERR_RE='EXT4-fs (error|warning)|I/O error|Aborting journal|Remounting filesystem read-only'

_log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') | FM-12 | $1" >> "$KAIJU_LOG_DIR/watchdog.log"
}

_fail() {
    _log "FAIL: $1"
    echo "FAIL: $1"
    exit 1
}

_running() {
    local out
    out=$(docker ps --filter "name=$CONTAINER_NAME" --filter "status=running" --format '{{.Names}}')
    [ "$out" = "$CONTAINER_NAME" ]
}

if [ $# -lt 2 ]; then
    echo "Usage: $0 <container_name> <compose_dir>" >&2
    exit 1
fi

CONTAINER_NAME="$1"
COMPOSE_DIR="$2"

# --- 1. config-derived allowlist (same as fm01) ---
VALID_DIR=false
while IFS= read -r dir; do
    if [ "$COMPOSE_DIR" = "$dir" ]; then
        VALID_DIR=true
        break
    fi
done < <(kaiju_known_compose_dirs)

if [ "$VALID_DIR" = false ]; then
    echo "Error: $COMPOSE_DIR is not a compose directory known to Kaiju OS config" >&2
    echo "Known directories: $(kaiju_known_compose_dirs | tr '\n' ' ')" >&2
    exit 1
fi

COMPOSE_ARG=$(kaiju_service_compose_key "$CONTAINER_NAME")

# --- 2. container must be absent; compose file must define the service ---
if docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    _fail "Container $CONTAINER_NAME exists -- this is not FM-12 (container-exists cases belong to FM-01)"
fi

if ! (cd "$COMPOSE_DIR" && docker compose config --services 2>/dev/null) | grep -qx "$COMPOSE_ARG"; then
    _fail "Compose file in $COMPOSE_DIR does not define service $COMPOSE_ARG -- nothing to recreate"
fi

# --- 3. kernel-log precheck (FM-10 guard) ---
KERNEL_HITS=""
KERNEL_READ_OK=true
if command -v journalctl >/dev/null 2>&1; then
    KERNEL_LOG=$(journalctl -k --since "$FM12_KERNEL_WINDOW" --no-pager 2>/dev/null)
    if [ $? -ne 0 ]; then
        KERNEL_READ_OK=false
    else
        KERNEL_HITS=$(echo "$KERNEL_LOG" | grep -iE "$KERNEL_ERR_RE" | tail -3)
    fi
else
    KERNEL_READ_OK=false
fi

if [ -n "$KERNEL_HITS" ]; then
    _fail "Kernel log (last ${FM12_KERNEL_WINDOW#-}) shows drive/filesystem errors -- stopping before any repair, see FM-10. First hit: $(echo "$KERNEL_HITS" | head -1)"
fi
if [ "$KERNEL_READ_OK" = false ]; then
    _log "NOTE: kernel log could not be read -- drive-error precheck SKIPPED (UNKNOWN), continuing"
fi

# --- optional snapshot, same contract as fm01 ---
if [ -x "$KAIJU_LIB_DIR/watchdog_snapshot.sh" ]; then
    SNAPSHOT_PATH=$("$KAIJU_LIB_DIR/watchdog_snapshot.sh" "$CONTAINER_NAME" 1 "$COMPOSE_DIR")
    echo "Snapshot saved to: $SNAPSHOT_PATH"
fi

# --- 4. plain up -d first ---
echo "Trying plain docker compose up -d $COMPOSE_ARG ..."
UP_OUT=$(cd "$COMPOSE_DIR" && docker compose up -d "$COMPOSE_ARG" 2>&1)
sleep "$FM12_PLAIN_WAIT"
if _running; then
    _log "PASS: Container $CONTAINER_NAME is running (plain up -d worked, no repair needed)"
    echo "PASS: Container $CONTAINER_NAME is running"
    exit 0
fi
if ! echo "$UP_OUT" | grep -qi "$SIGNATURE_RE"; then
    _fail "Container $CONTAINER_NAME still absent but the error is not the FM-12 snapshot signature -- different failure, stopping. Error: $(echo "$UP_OUT" | tail -1)"
fi
_log "FM-12 signature confirmed for $CONTAINER_NAME (failed to stat parent on create)"

# --- 5. image + shared-image check ---
IMAGE_REF=$(cd "$COMPOSE_DIR" && docker compose config --format json 2>/dev/null | jq -r --arg s "$COMPOSE_ARG" '.services[$s].image // empty' 2>/dev/null)
if [ -z "$IMAGE_REF" ]; then
    _fail "Could not read the image for service $COMPOSE_ARG from the compose file (is jq installed?) -- stopping"
fi

IMAGE_ID=$(docker image inspect --format '{{.Id}}' "$IMAGE_REF" 2>/dev/null)
if [ -n "$IMAGE_ID" ]; then
    USERS=$( { docker ps -a --filter "ancestor=$IMAGE_REF" --format '{{.Names}}'; docker ps -a --filter "ancestor=$IMAGE_ID" --format '{{.Names}}'; } | grep -v '^$' | sort -u | tr '\n' ' ')
    if [ -n "$USERS" ]; then
        _fail "Image $IMAGE_REF is used by other container(s): ${USERS}-- not removing a shared image, a human must decide"
    fi
    # --- 6a. remove the broken image record ---
    echo "Removing image $IMAGE_REF ..."
    docker rmi -f "$IMAGE_REF" >/dev/null 2>&1 || _fail "docker rmi -f $IMAGE_REF failed -- stopping"
else
    _log "NOTE: image $IMAGE_REF not present locally -- skipping rmi, pulling fresh"
fi

# --- 6b. pull + recreate ---
echo "Pulling $COMPOSE_ARG ..."
(cd "$COMPOSE_DIR" && docker compose pull "$COMPOSE_ARG" >/dev/null 2>&1) || _fail "docker compose pull $COMPOSE_ARG failed -- stopping"

echo "Creating $COMPOSE_ARG ..."
UP_OUT=$(cd "$COMPOSE_DIR" && docker compose up -d "$COMPOSE_ARG" 2>&1)
if echo "$UP_OUT" | grep -qi "$SIGNATURE_RE"; then
    _fail "Same snapshot error after the re-pull for $CONTAINER_NAME -- stopping, no second attempt. Check the containerd store and the kernel log (FM-10)"
fi

sleep "$FM12_SETTLE_SECONDS"
if ! _running; then
    _fail "Container $CONTAINER_NAME is not running after re-pull and up -d. Last output: $(echo "$UP_OUT" | tail -1)"
fi

# --- verify against the service's own health_url, like the orchestrator does ---
SVC_IDX=$(kaiju_service_index_by_name "$CONTAINER_NAME")
if [ -n "$SVC_IDX" ]; then
    HEALTH_URL=$(kaiju_service_field "$SVC_IDX" "health_url")
    EXPECT=$(kaiju_service_field "$SVC_IDX" "expected_code")
    TMO=$(kaiju_service_field "$SVC_IDX" "timeout_seconds")
    if [ -n "$HEALTH_URL" ] && [ "$HEALTH_URL" != "null" ]; then
        TRY=1
        CODE=""
        while [ "$TRY" -le "$FM12_HEALTH_TRIES" ]; do
            CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time "${TMO:-10}" "$HEALTH_URL" 2>/dev/null)
            [ "$CODE" = "$EXPECT" ] && break
            TRY=$((TRY + 1))
            [ "$TRY" -le "$FM12_HEALTH_TRIES" ] && sleep "$FM12_HEALTH_INTERVAL"
        done
        if [ "$CODE" != "$EXPECT" ]; then
            _fail "Container $CONTAINER_NAME is running but $HEALTH_URL returned ${CODE:-none} (expected $EXPECT) after $FM12_HEALTH_TRIES checks"
        fi
        _log "PASS: Container $CONTAINER_NAME recreated after image re-pull; $HEALTH_URL returned $CODE"
        echo "PASS: Container $CONTAINER_NAME recreated, health check $CODE"
        exit 0
    fi
fi

_log "PASS: Container $CONTAINER_NAME recreated after image re-pull (no health_url configured, running only)"
echo "PASS: Container $CONTAINER_NAME is running"
exit 0
