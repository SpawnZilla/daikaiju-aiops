#!/bin/bash
# ============================================================
# ✅ TESTED 2026-07-23 — see kaiju-gais-package/fashsd/tests/TESTING.md
# ⚠️ MODIFIED 2026-09-13: added a --force-recreate retry
# for stale-network-ID exits ("failed to set up container networking:
# network <id> not found" — watchtower/portainer-agent, 2026-09-12).
# The original plain `up -d` path is UNCHANGED and still carries its
# 2026-07-23 test-suite pass — it's tried first, and only on its
# failure does the new retry logic engage. NOT YET LIVE-VERIFIED
# against a real stale-network exit specifically (an earlier incident fixed
# that one manually, before this script change existed) — force a real
# stale-network exit again and confirm the automatic retry recovers it
# before trusting this in production.
# ⚠️ MODIFIED 2026-09-15: container name is no
# longer assumed to equal the Compose service name. Both `docker compose
# up -d` calls below now resolve the real compose-service argument via
# fashsd_config_lib.sh's new kaiju_service_compose_name() (schema v1.5's
# optional per-service `service:` field, falls back to the container
# name unchanged when absent — zero behavior change for every service
# that doesn't set it). NOT YET run through tests/run_tests.sh with this
# change in place — do that before trusting it live.
# ============================================================
# fm01_container_exited.sh — Kaiju Spine config-driven FM-01 fix script
# Generalized from Kaidosho's fm01_container_exited.sh.
# Deploy to: /opt/kaiju-spine/watchdog/
#
# ORIGINAL Kaidosho SCRIPT: hardcoded ALLOWED_DIRS array with 14 literal Kaidosho
# compose paths. This version derives the allowed set from the Kaiju Spine
# config's services[].compose_dir field instead. Snapshot/restart/verify
# logic is UNCHANGED from the original except for the new force-recreate
# retry added below.

: "${KAIJU_LIB_DIR:=/opt/kaiju-spine/watchdog}"
source "$KAIJU_LIB_DIR/fashsd_config_lib.sh"

if [ $# -lt 2 ]; then
    echo "Usage: $0 <container_name> <compose_dir>" >&2
    exit 1
fi

CONTAINER_NAME="$1"
COMPOSE_DIR="$2"

# --- UNCHANGED: config-derived allowlist replaces Kaidosho's hardcoded ALLOWED_DIRS array ---
VALID_DIR=false
while IFS= read -r dir; do
    if [ "$COMPOSE_DIR" = "$dir" ]; then
        VALID_DIR=true
        break
    fi
done < <(kaiju_known_compose_dirs)

if [ "$VALID_DIR" = false ]; then
    echo "Error: $COMPOSE_DIR is not a compose directory known to Kaiju Spine config" >&2
    echo "Known directories: $(kaiju_known_compose_dirs | tr '\n' ' ')" >&2
    exit 1
fi

# --- NEW 2026-09-15: resolve the real Compose service-name
# argument, in case it differs from the container name (see schema v1.5
# / kaiju_service_compose_name() docstring above its definition).
COMPOSE_ARG=$(kaiju_service_compose_name "$CONTAINER_NAME")
if [ "$COMPOSE_ARG" != "$CONTAINER_NAME" ]; then
    echo "Note: container '$CONTAINER_NAME' maps to compose service '$COMPOSE_ARG' (schema v1.5 service: field)"
fi

# --- UNCHANGED from original: snapshot ---
: "${KAIJU_LOG_DIR:=/var/log/kaiju-watchdog}"
mkdir -p "$KAIJU_LOG_DIR" 2>/dev/null || KAIJU_LOG_DIR="/tmp/kaiju-watchdog-fallback"
mkdir -p "$KAIJU_LOG_DIR/snapshots" 2>/dev/null || true

SNAPSHOT_PATH="(skipped)"
if [ -x "$KAIJU_LIB_DIR/watchdog_snapshot.sh" ]; then
    SNAPSHOT_PATH=$("$KAIJU_LIB_DIR/watchdog_snapshot.sh" "$CONTAINER_NAME" 1 "$COMPOSE_DIR")
    echo "Snapshot saved to: $SNAPSHOT_PATH"
else
    echo "NOTE: watchdog_snapshot.sh not found at $KAIJU_LIB_DIR — not yet"
    echo "packaged in kaiju-gais-package/fashsd/ (see README.md). Skipping"
    echo "snapshot step, proceeding directly to restart."
fi

# --- first attempt, plain up -d (this is the 2026-07-23 tested path) ---
# MODIFIED 2026-09-15: uses $COMPOSE_ARG (resolved above), not
# $CONTAINER_NAME directly -- identical value for every service that
# doesn't set schema v1.5's optional service: field.
echo "Restarting container $CONTAINER_NAME (compose arg: $COMPOSE_ARG)..."
cd "$COMPOSE_DIR" && docker compose up -d "$COMPOSE_ARG"

echo "Sleeping for 10 seconds..."
sleep 10

echo "Verifying container is running..."
VERIFY_RESULT=$(docker ps --filter "name=$CONTAINER_NAME" --filter "status=running" --format '{{.Names}}')

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
if [ -n "$VERIFY_RESULT" ] && [ "$VERIFY_RESULT" = "$CONTAINER_NAME" ]; then
    echo "$TIMESTAMP | FM-01 | PASS: Container $CONTAINER_NAME is running (plain up -d)" >> "$KAIJU_LOG_DIR/watchdog.log"
    echo "PASS: Container $CONTAINER_NAME is running"
    exit 0
fi

# --- NEW 2026-09-13: plain up -d didn't bring it up.
# Log the exit error for the record, then retry once with
# --force-recreate before declaring FAIL — this is the known fix for
# the stale-network-ID exit class, and a container still down after a
# clean up -d is broken either way.
EXIT_ERROR=$(docker inspect --format '{{.State.Error}}' "$CONTAINER_NAME" 2>/dev/null)
echo "First attempt (plain up -d) did not bring $CONTAINER_NAME up. Exit error: ${EXIT_ERROR:-<none>}"

if echo "$EXIT_ERROR" | grep -qi "network"; then
    echo "Stale-network-ID signature detected -- retrying with --force-recreate."
else
    echo "No recognized stale-network signature -- retrying with --force-recreate anyway as a last resort before declaring FAIL."
fi

cd "$COMPOSE_DIR" && docker compose up -d --force-recreate "$COMPOSE_ARG"

echo "Sleeping for 10 seconds..."
sleep 10

echo "Verifying container is running (after --force-recreate)..."
VERIFY_RESULT=$(docker ps --filter "name=$CONTAINER_NAME" --filter "status=running" --format '{{.Names}}')

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
if [ -n "$VERIFY_RESULT" ] && [ "$VERIFY_RESULT" = "$CONTAINER_NAME" ]; then
    echo "$TIMESTAMP | FM-01 | PASS: Container $CONTAINER_NAME is running (required --force-recreate)" >> "$KAIJU_LOG_DIR/watchdog.log"
    echo "PASS: Container $CONTAINER_NAME is running (required --force-recreate)"
    exit 0
else
    echo "$TIMESTAMP | FM-01 | FAIL: Container $CONTAINER_NAME is not running (plain up -d and --force-recreate both failed)" >> "$KAIJU_LOG_DIR/watchdog.log"
    echo "FAIL: Container $CONTAINER_NAME is not running"
    exit 1
fi
