#!/bin/bash
# ============================================================
# ✅ TESTED 2026-07-23 — see kaiju-gais-package/fashsd/tests/TESTING.md
# ⚠️ NEW FUNCTIONS ADDED 2026-09-06, NOT YET TESTED:
# kaiju_drive_expected_subdirs, kaiju_drive_index_by_name,
# kaiju_service_index_by_name (schema v1.3, for FM-06/FM-07). Do not
# remove this warning until they've gone through tests/run_tests.sh.
# ⚠️ kaiju_clock_drift_threshold_ms ADDED 2026-09-20 (merge,
# pi5_watchdog.sh depends on it) — also NOT YET TESTED.
# ============================================================
# fashsd_config_lib.sh — shared config-loading functions for Kaiju Spine FASHSD
# Part of the Kaiju Spine packaged product (the FASHSD design notes)
#
# Source this file at the top of any FASHSD script:
#   source /opt/kaiju-spine/watchdog/fashsd_config_lib.sh
#
# Requires: yq (YAML CLI parser). Two different tools share this name:
#   - mikefarah/yq (Go binary) — native YAML, quotes stripped by default
#   - kislyuk/yq (Python, wraps jq) — this is Debian/Ubuntu's `apt install yq`
# This library targets kislyuk/yq syntax (uses `-r` for raw/unquoted
# output, since it's a jq wrapper and JSON-quotes strings by default).
# CONFIRMED 2026-07-23 via live test: `apt install yq` on Debian installs
# kislyuk/yq, not mikefarah/yq — this was a wrong assumption in the
# original design and caused all string-returning functions to return
# JSON-quoted values (e.g. '"fake-service-a"' instead of fake-service-a)
# until fixed here. Bootstrap installer must document which yq it expects.
#
# Requires: yq (YAML CLI parser). Bootstrap installer installs this as a
# Kaiju Spine dependency during Phase 5 (FASHSD setup).

: "${KAIJU_CONFIG:=/etc/kaiju-spine/services.yaml}"

# fail loudly and immediately if the config file is missing — every
# FASHSD script depends on it, so a silent empty-config run is worse
# than a hard stop (Rule 14 principle applied to runtime, not just briefs)
if [ ! -f "$KAIJU_CONFIG" ]; then
    echo "FATAL: Kaiju Spine config not found at $KAIJU_CONFIG" >&2
    echo "FASHSD cannot run without a config file. Re-run the bootstrap" >&2
    echo "installer's FASHSD step, or check KAIJU_CONFIG env var." >&2
    exit 1
fi

if ! command -v yq >/dev/null 2>&1; then
    echo "FATAL: yq not found. FASHSD requires yq for config parsing." >&2
    echo "Install: apt install yq  (Debian/Ubuntu)" >&2
    exit 1
fi

# --- Topology ---
kaiju_topology_mode() {
    yq -r '.topology.mode' "$KAIJU_CONFIG"
}

kaiju_target_mac() {
    yq -r '.topology.target_node.mac' "$KAIJU_CONFIG"
}

kaiju_target_ip() {
    yq -r '.topology.target_node.ip' "$KAIJU_CONFIG"
}

# --- Services ---
kaiju_service_count() {
    yq -r '.services | length' "$KAIJU_CONFIG"
}

# Usage: kaiju_service_field <index> <field>
# e.g. kaiju_service_field 0 name
kaiju_service_field() {
    local idx="$1"
    local field="$2"
    yq -r ".services[$idx].$field" "$KAIJU_CONFIG"
}

# Returns a newline-separated, de-duplicated list of every compose_dir
# in the config — used by fix scripts (e.g. FM-01) that need to validate
# a compose_dir argument against the set of known-good directories,
# without hardcoding that set.
kaiju_known_compose_dirs() {
    local count
    count=$(kaiju_service_count)
    for i in $(seq 0 $((count - 1))); do
        yq -r ".services[$i].compose_dir" "$KAIJU_CONFIG"
    done | sort -u
}

# --- Network Groups ---
# Added 2026-07-29 for (FM-03 gluetun-style generalization).
# Schema (kaiju_fashsd_config.example.yaml):
#   network_groups:
#     - owner: "gluetun"
#       dependents: ["radarr", "sonarr", ...]
#       compose_dir: "/mnt/hola2/compose/arr"
#       verify_via: "qbittorrent"

kaiju_network_group_count() {
    yq -r '.network_groups | length' "$KAIJU_CONFIG"
}

# Usage: kaiju_network_group_field <index> <field>
# For scalar fields only (owner, compose_dir, verify_via) — NOT dependents,
# which is a list. Use kaiju_network_group_dependents for that.
kaiju_network_group_field() {
    local idx="$1"
    local field="$2"
    yq -r ".network_groups[$idx].$field" "$KAIJU_CONFIG"
}

# Returns dependents for the given network_groups index, one per line
# (same list-handling pattern as kaiju_known_compose_dirs — never returns
# a delimited string, since yq's raw output for list elements is
# newline-separated per element, not comma-joined).
kaiju_network_group_dependents() {
    local idx="$1"
    local count
    count=$(yq -r ".network_groups[$idx].dependents | length" "$KAIJU_CONFIG")
    for i in $(seq 0 $((count - 1))); do
        yq -r ".network_groups[$idx].dependents[$i]" "$KAIJU_CONFIG"
    done
}

# --- Drives ---
kaiju_drive_count() {
    yq -r '.drives | length' "$KAIJU_CONFIG"
}

kaiju_drive_field() {
    local idx="$1"
    local field="$2"
    yq -r ".drives[$idx].$field" "$KAIJU_CONFIG"
}

# Returns expected_subdirs for the given drives[] index, one per line
# (list field, same handling pattern as kaiju_network_group_dependents
# -- never a delimited string). Added schema v1.3 (2026-09-06) for
# FM-06-style ghost-mount recovery. Empty/absent list -> zero lines,
# not an error -- callers should treat zero expected_subdirs as
# "nothing extra to verify beyond mountpoint(1)", not a config bug.
kaiju_drive_expected_subdirs() {
    local idx="$1"
    local count
    count=$(yq -r ".drives[$idx].expected_subdirs | length" "$KAIJU_CONFIG" 2>/dev/null)
    [ -z "$count" ] || [ "$count" = "null" ] && return 0
    for i in $(seq 0 $((count - 1))); do
        yq -r ".drives[$idx].expected_subdirs[$i]" "$KAIJU_CONFIG"
    done
}

# Returns the drives[] index matching a given drive name, or empty if
# not found. Added for FM-06 (takes a drive name argument, same
# calling convention as FM-05, needs to look up its own index rather
# than assume index 0).
kaiju_drive_index_by_name() {
    local name="$1"
    local count
    count=$(kaiju_drive_count)
    for i in $(seq 0 $((count - 1))); do
        if [ "$(kaiju_drive_field "$i" name)" = "$name" ]; then
            echo "$i"
            return 0
        fi
    done
    return 1
}

# Returns the services[] index matching a given service name, or empty
# if not found. Added for FM-07 (takes a service name argument, needs
# to look up its own index the same way kaiju_drive_index_by_name does
# for drives).
kaiju_service_index_by_name() {
    local name="$1"
    local count
    count=$(kaiju_service_count)
    for i in $(seq 0 $((count - 1))); do
        if [ "$(kaiju_service_field "$i" name)" = "$name" ]; then
            echo "$i"
            return 0
        fi
    done
    return 1
}

# Returns the Compose SERVICE name to use for `docker compose up -d
# <arg>`, given a real Docker CONTAINER name. Added 2026-09-15 (
# generalized from an earlier incident -- Scanopy's own fix used a
# container_name: override in its compose file instead of this
# mechanism, since this function didn't exist yet).
#
# Compose's container name and service name are NOT guaranteed to be
# the same string -- Compose auto-generates a container name
# (<project>-<service>-<N>) whenever a service has no explicit
# `container_name:` override, so `docker compose up -d <container-name>`
# can fail with "no such service" even though the container is real and
# known to this config.
#
# Schema v1.5 (2026-09-15) adds an OPTIONAL `service:` field per
# services[] entry, alongside the existing required `container:` field.
# This function looks up the services[] entry whose `container` field
# matches the given container name, then:
#   - if that entry has a non-null/non-empty `service` field, returns it
#   - otherwise falls back to returning the container name itself
#     UNCHANGED -- this is the original, still-correct behavior for the
#     other 18+ services that don't need the field at all
#   - if no services[] entry matches the container name at all, also
#     falls back to the container name unchanged (fail-open to the
#     pre-v1.5 behavior, never a new failure mode of its own)
kaiju_service_compose_name() {
    local container_name="$1"
    local idx count svc_field
    count=$(kaiju_service_count)
    for idx in $(seq 0 $((count - 1))); do
        if [ "$(kaiju_service_field "$idx" container)" = "$container_name" ]; then
            svc_field=$(kaiju_service_field "$idx" service)
            if [ -n "$svc_field" ] && [ "$svc_field" != "null" ]; then
                echo "$svc_field"
            else
                echo "$container_name"
            fi
            return 0
        fi
    done
    # No matching services[] entry -- fail open, unchanged pre-v1.5 behavior
    echo "$container_name"
    return 0
}

# --- Alerting ---
kaiju_ntfy_topic() {
    yq -r '.alerting.ntfy_topic' "$KAIJU_CONFIG"
}

kaiju_ntfy_url() {
    local self_hosted
    self_hosted=$(yq -r '.alerting.ntfy_self_hosted_url' "$KAIJU_CONFIG")
    if [ -n "$self_hosted" ] && [ "$self_hosted" != "null" ] && [ "$self_hosted" != "" ]; then
        echo "$self_hosted"
    else
        echo "https://ntfy.sh"
    fi
}

# --- Watchdog ---
kaiju_watchdog_interval_minutes() {
    yq -r '.watchdog.interval_minutes' "$KAIJU_CONFIG"
}

# --- Retry helper (added 2026-08-01) ---
# Merged in from kaiju-relay/retry_helper.sh so every FASHSD script gets
# it for free via the existing `source fashsd_config_lib.sh` convention,
# instead of a second file every script has to remember to source. Content
# is unchanged from retry_helper.sh's own kaiju_retry_check() -- that file
# already 4-way tested this logic in isolation (immediate pass, exhausted
# retries, recovery on attempt 3, default-args) during dosho wan prep
# 2026-07-31. This copy has NOT been separately re-tested here -- same
# function body, not re-verified after the copy/paste. Re-run
# retry_helper.sh's own self-tests against this copy before trusting it
# live, or better, diff the two to confirm they stayed identical.
# PURPOSE: health-check scripts should retry a failed check up to N times
# before declaring FAIL, not act on a single-shot result -- reduces
# false-positive failure/alert-flapping from transient blips.
kaiju_retry_check() {
    # Usage: kaiju_retry_check "<command to eval, must return 0/1>" [max_attempts] [delay_seconds]
    local check_cmd="$1"
    local max_attempts="${2:-4}"
    local delay_seconds="${3:-5}"
    local attempt=1

    while [ "$attempt" -le "$max_attempts" ]; do
        if eval "$check_cmd"; then
            echo "kaiju_retry_check: PASS on attempt $attempt/$max_attempts" >&2
            return 0
        fi
        echo "kaiju_retry_check: attempt $attempt/$max_attempts failed" >&2
        attempt=$((attempt + 1))
        if [ "$attempt" -le "$max_attempts" ]; then
            sleep "$delay_seconds"
        fi
    done

    echo "kaiju_retry_check: FAIL after $max_attempts attempts" >&2
    return 1
}

# --- Clock drift threshold (added for pi5_watchdog.sh) ---
# Returns watchdog.clock_drift_threshold_ms from config, or 2000 (ms)
# if the field is absent — same optional-field-with-default pattern
# as kaiju_ntfy_url()'s self_hosted_url fallback. NOT YET TESTED
# (merged in alongside pi5_watchdog.sh/watchdog_notify.sh, 2026-09-20;
# this function itself has no separate test-suite entry yet).
kaiju_clock_drift_threshold_ms() {
    local val
    val=$(yq -r '.watchdog.clock_drift_threshold_ms' "$KAIJU_CONFIG" 2>/dev/null)
    if [ -z "$val" ] || [ "$val" = "null" ]; then
        echo 2000
    else
        echo "$val"
    fi
}
