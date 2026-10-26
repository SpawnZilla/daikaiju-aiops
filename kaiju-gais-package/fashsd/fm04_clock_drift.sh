#!/bin/bash
# ============================================================
# TESTED 2026-09-08 (Round 3) — see tests/TESTING.md
# RESTART-SCOPE DESIGN DECISION — see header note below, REVISABLE
# ============================================================
# fm04_clock_drift.sh — Kaiju Spine config-driven clock-drift recovery.
#
# Generalized from Kaidosho's FM-04: force an NTP resync, then
# restart whichever service(s) are sensitive to clock skew (Kaidosho's
# original only restarted Prowlarr, since that was Kaidosho's one observed
# symptom).
#
# Deploy to: /opt/kaiju-spine/watchdog/
#
# RESTART-SCOPE DECISION (Mokaima, 2026-09-06, per an open design
# question in the project's planning notes — Gorkaige's instruction: propose one WITH REASONING,
# not a hard lock, revisit if it doesn't hold up):
#
#   PROPOSAL: restart ALL configured services (kaiju_service_count()
#   loop over every services[] entry), not a per-service
#   "clock_sensitive: true" flag.
#
#   REASONING: (1) clock skew is a system-level condition, not a
#   per-service one — any service doing TLS validation, JWT/token
#   expiry checks, or timestamp-based cache logic can silently
#   misbehave on drift, not just the one service where Kaidosho happened to
#   notice it (Prowlarr's DNS-provider-auth flow). A flag-based
#   allowlist requires correctly predicting in advance which services
#   are clock-sensitive — the same class of guess Kaidosho's own hardcoded
#   single-service version got wrong by being too narrow. (2) This
#   fix already forces a full daemon-level NTP resync (a rare,
#   already-disruptive event, not a routine health-check restart) —
#   the marginal cost of restarting every service in the same pass is
#   low relative to the value of not missing a second clock-sensitive
#   service Kaidosho hasn't hit yet. (3) It reuses the exact same
#   kaiju_service_count() loop pattern already tested in fm02, adding
#   zero new schema surface — a clock_sensitive flag would need a new
#   schema field, a bootstrap-installer prompt for it, and correct
#   per-service classification at install time, all avoidable here.
#
#   TRADEOFF ACCEPTED: this is more disruptive than Kaidosho's original
#   (which only ever restarted one container) — every configured
#   service gets a brief restart on every clock-drift event, not just
#   the ones that actually needed it. If this proves too disruptive in
#   practice, the clock_sensitive flag alternative is still on the
#   table (see the open design question doc) — this is a starting
#   default, not a permanent lock.
#
# Generalization notes:
#   - `sudo timedatectl set-ntp false/true` + verify-synchronized logic
#     preserved exactly — this part needed no config at all.
#   - Hardcoded "restart Prowlarr in /mnt/hola2/compose/arr" replaced
#     with a loop over every services[] entry, restarting via each
#     entry's own compose_dir/container (same generic loop shape as
#     app_curl_check.sh's services[] loop).

: "${KAIJU_LIB_DIR:=/opt/kaiju-spine/watchdog}"
source "$KAIJU_LIB_DIR/fashsd_config_lib.sh"

: "${KAIJU_LOG_DIR:=/var/log/kaiju-watchdog}"
mkdir -p "$KAIJU_LOG_DIR" 2>/dev/null || KAIJU_LOG_DIR="/tmp/kaiju-watchdog-fallback"
mkdir -p "$KAIJU_LOG_DIR"

LOG="$KAIJU_LOG_DIR/watchdog.log"

_log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') | fm04_clock_drift | $1" >> "$LOG"
}

_log "Starting clock-drift recovery"

echo "Forcing NTP resync..."
sudo timedatectl set-ntp false
sleep 2
sudo timedatectl set-ntp true
sleep 10

echo "Restarting all configured services (see header note on restart-scope decision)..."
SERVICE_COUNT=$(kaiju_service_count)
for i in $(seq 0 $((SERVICE_COUNT - 1))); do
    COMPOSE_DIR=$(kaiju_service_field "$i" compose_dir)
    CONTAINER=$(kaiju_service_field "$i" container)
    (cd "$COMPOSE_DIR" && docker compose restart "$CONTAINER") >>"$LOG" 2>&1
    _log "restarted $CONTAINER (compose_dir: $COMPOSE_DIR)"
done
sleep 5

VERIFY_RESULT=$(timedatectl status | grep -i "System clock synchronized")
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
if [[ "$VERIFY_RESULT" == *"yes"* ]]; then
    echo "$TIMESTAMP | fm04_clock_drift | PASS: System clock is synchronized, $SERVICE_COUNT services restarted" >> "$LOG"
    echo "PASS: System clock is synchronized, $SERVICE_COUNT services restarted"
    exit 0
else
    echo "$TIMESTAMP | fm04_clock_drift | FAIL: System clock is not synchronized" >> "$LOG"
    echo "FAIL: System clock is not synchronized"
    exit 1
fi
