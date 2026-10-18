#!/bin/bash
# ============================================================
# ⚠️  MUST PRIORITY — this script IS the untested-scripts test suite.
# Run this before removing the MUST PRIORITY warnings anywhere else.
# ============================================================
# run_tests.sh — Kaiju OS FASHSD test runner
#
# Run from this directory (kaiju-gais-package/fashsd/tests/):
#   chmod +x run_tests.sh
#   ./run_tests.sh          # runs steps 1-5 (safe, mostly read-only)
#   ./run_tests.sh 6        # prints step 6 manual instructions only
#   ./run_tests.sh 7        # prints step 7 manual instructions only (fm02, restarts Docker daemon)
#   ./run_tests.sh 8        # prints step 8 manual instructions only (fm05, disposable loopback drive)
#   ./run_tests.sh 9        # prints step 9 manual instructions only (fm03, disposable owner+dependent stack)
#   ./run_tests.sh 10       # prints step 10 manual instructions only (fm06, disposable loopback drive)
#   ./run_tests.sh 11       # prints step 11 manual instructions only (fm07, disposable container)
#   ./run_tests.sh 12       # prints step 12 manual instructions only (fm04, restarts ALL configured services)
#   ./run_tests.sh 13       # prints step 13 manual instructions only (fm01 schema v1.5 service: field, disposable container)
#   ./run_tests.sh 14       # prints step 14 instructions only (watchdog_notify.sh, real ntfy send, confirmation prompt)
#   ./run_tests.sh 15       # prints step 15 manual instructions only (pi5_watchdog.sh orchestration dispatch, disposable container)
#   ./run_tests.sh 16       # prints step 16 instructions only (pi5_watchdog.sh daemon-down branch, HIGH BLAST RADIUS)
#   ./run_tests.sh 17       # prints step 17 instructions only (pi5_watchdog.sh curl-fail WITH dns_check_url dispatch)
#   ./run_tests.sh 18       # prints step 18 instructions only (pi5_watchdog.sh curl-fail WITHOUT dns_check_url, best-effort fallback)
#   ./run_tests.sh 19       # prints step 19 instructions only (pi5_watchdog.sh network-group owner branch)
#   ./run_tests.sh 20       # prints step 20 instructions only (pi5_watchdog.sh drive-not-mounted branch)
#   ./run_tests.sh 21       # prints step 21 instructions only (pi5_watchdog.sh ghost-mount branch)
#   ./run_tests.sh 22       # prints step 22 instructions only (pi5_watchdog.sh clock-drift branch, HIGH BLAST RADIUS)
#
# This script does NOT touch real Kaidosho services except step 3's read-only
# curl checks. It does NOT run steps 6-13 automatically — those need
# manual setup first (disposable container/drive, or accepting a full
# Docker daemon restart for step 7 — instructions printed below).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FASHSD_DIR="$(dirname "$SCRIPT_DIR")"
PASS=0
FAIL=0

# Scripts are not deployed to /opt/kaiju-os/watchdog/ yet — point them
# at this test location instead, and use a /tmp log dir since
# /var/log/kaiju-watchdog requires root and doesn't exist pre-deploy.
export KAIJU_LIB_DIR="$FASHSD_DIR"
export KAIJU_LOG_DIR="/tmp/kaiju-fashsd-test-logs"
mkdir -p "$KAIJU_LOG_DIR"
rm -f "$KAIJU_LOG_DIR/watchdog.log"  # start each run with a clean log

pass() { echo "  ✅ PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  ❌ FAIL: $1"; FAIL=$((FAIL+1)); }

print_step6() {
    echo ""
    echo "── STEP 6: fm01_container_exited.sh (MANUAL — not automated) ──"
    echo "  This test actually restarts a container, so it is NOT run"
    echo "  automatically. Do this by hand:"
    echo ""
    echo "  1. mkdir -p /tmp/kaiju-fm01-test && cd /tmp/kaiju-fm01-test"
    echo "  2. cat > docker-compose.yml << 'EOF'"
    echo "     services:"
    echo "       kaiju-test-nginx:"
    echo "         image: nginx:alpine"
    echo "         container_name: kaiju-test-nginx"
    echo "         ports:"
    echo "           - \"8199:80\""
    echo "     EOF"
    echo "  3. docker compose up -d"
    echo "  4. curl -s -o /dev/null -w '%{http_code}' http://localhost:8199"
    echo "     (confirm this prints 200 before continuing)"
    echo "  5. docker stop kaiju-test-nginx   # simulate the FM-01 trigger"
    echo "  6. export KAIJU_CONFIG=$SCRIPT_DIR/step6_throwaway_container.yaml"
    echo "     export KAIJU_LIB_DIR=$FASHSD_DIR"
    echo "     export KAIJU_LOG_DIR=$KAIJU_LOG_DIR"
    echo "  7. bash $FASHSD_DIR/fm01_container_exited.sh kaiju-test-nginx /tmp/kaiju-fm01-test"
    echo "  8. Confirm output says PASS and container is running again:"
    echo "     docker ps --filter name=kaiju-test-nginx"
    echo "  9. Cleanup: docker compose down && rm -rf /tmp/kaiju-fm01-test"
}

print_step7() {
    echo ""
    echo "── STEP 7: fm02_daemon_down.sh (MANUAL — not automated) ──"
    echo "  ⚠️  This test restarts the ENTIRE Docker daemon on this host —"
    echo "  every container restarts, not just the throwaway one below."
    echo "  Only run this when a brief full-host container restart is"
    echo "  acceptable right now. Do this by hand:"
    echo ""
    echo "  1. mkdir -p /tmp/kaiju-fm02-test && cd /tmp/kaiju-fm02-test"
    echo "  2. cat > docker-compose.yml << 'EOF'"
    echo "     services:"
    echo "       kaiju-test-nginx:"
    echo "         image: nginx:alpine"
    echo "         container_name: kaiju-test-nginx"
    echo "         ports:"
    echo "           - \"8198:80\""
    echo "     EOF"
    echo "  3. docker compose up -d"
    echo "  4. curl -s -o /dev/null -w '%{http_code}' http://localhost:8198"
    echo "     (confirm this prints 200 before continuing)"
    echo "  5. export KAIJU_CONFIG=$SCRIPT_DIR/step7_fm02_throwaway.yaml"
    echo "     export KAIJU_LIB_DIR=$FASHSD_DIR"
    echo "     export KAIJU_LOG_DIR=$KAIJU_LOG_DIR"
    echo "  6. bash $FASHSD_DIR/fm02_daemon_down.sh"
    echo "     (this WILL restart Docker system-wide — expect every"
    echo "     container on this host to briefly go down and come back)"
    echo "  7. Confirm output says PASS, docker is active, container"
    echo "     count meets the threshold, and the throwaway nginx is"
    echo "     running again: docker ps --filter name=kaiju-test-nginx"
    echo "  8. Also confirm your REAL Kaidosho services came back up correctly"
    echo "     after the daemon restart — this is the main real-world risk,"
    echo "     not just the throwaway container"
    echo "  9. Cleanup: docker compose down && rm -rf /tmp/kaiju-fm02-test"
}

print_step8() {
    echo ""
    echo "── STEP 8: fm05_drive_not_mounted.sh (MANUAL — not automated) ──"
    echo "  This test mounts a drive, so it uses a disposable loopback"
    echo "  image + a TEMPORARY fstab entry — never a real drive or an"
    echo "  existing fstab entry. Do this by hand:"
    echo ""
    echo "  1. sudo mkdir -p /mnt/kaiju-test-drive"
    echo "  2. dd if=/dev/zero of=/tmp/kaiju-fm05-test.img bs=1M count=16"
    echo "  3. mkfs.ext4 /tmp/kaiju-fm05-test.img"
    echo "  4. sudo losetup /dev/loop-kaiju-test /tmp/kaiju-fm05-test.img 2>/dev/null || \\"
    echo "     sudo losetup -f /tmp/kaiju-fm05-test.img   # note the loop device it picks"
    echo "  5. Add ONE temporary line to /etc/fstab (note it for removal in"
    echo "     step 9 — use the actual loop device from step 4, e.g. /dev/loop0):"
    echo "     /dev/loopN  /mnt/kaiju-test-drive  ext4  defaults  0  0"
    echo "  6. sudo mount /mnt/kaiju-test-drive   # confirm it mounts cleanly"
    echo "     sudo umount /mnt/kaiju-test-drive  # then unmount — this"
    echo "     simulates the FM-05 trigger condition (configured, not mounted)"
    echo "  7. export KAIJU_CONFIG=$SCRIPT_DIR/step8_fm05_throwaway.yaml"
    echo "     export KAIJU_LIB_DIR=$FASHSD_DIR"
    echo "     export KAIJU_LOG_DIR=$KAIJU_LOG_DIR"
    echo "  8. bash $FASHSD_DIR/fm05_drive_not_mounted.sh kaiju-test-drive"
    echo "  9. Confirm output says PASS and it's mounted: mountpoint -q /mnt/kaiju-test-drive"
    echo "  10. Cleanup: sudo umount /mnt/kaiju-test-drive; sudo losetup -d /dev/loopN;"
    echo "      remove the fstab line added in step 5; rm /tmp/kaiju-fm05-test.img;"
    echo "      sudo rmdir /mnt/kaiju-test-drive"
    echo ""
    echo "  Also worth testing once, same config: run with a WRONG drive name"
    echo "  (e.g. 'nonexistent-drive') and confirm it correctly errors with"
    echo "  'drive_name must be one of: kaiju-test-drive' rather than crashing."
}

# Early exit: if called with 6/7/8, print ONLY that step's manual
# instructions and stop — do not run steps 1-5. This is what the
# usage comment at the top of this file has always promised; it was
# not actually implemented until 2026-07-27 (caught mid-run when
# `./run_tests.sh 7` ran the full 1-5 sequence instead of just
# printing step 7 as documented).
print_step9() {
    echo ""
    echo "STEP 9: fm03_gluetun_unhealthy.sh (MANUAL - not automated)"
    echo "  Needs a disposable owner+dependent stack sharing a network"
    echo "  namespace. Full setup in step9_fm03_throwaway.yaml's header."
    echo "  1. mkdir -p /tmp/kaiju-fm03-test && cd /tmp/kaiju-fm03-test"
    echo "  2. Write docker-compose.yml: kaiju-test-owner (HEALTHCHECK-"
    echo "     bearing image) + kaiju-test-dep (network_mode:"
    echo "     service:kaiju-test-owner, curl installed, sleep infinity)"
    echo "  3. docker compose up -d, confirm owner reports healthy"
    echo "  4. export KAIJU_CONFIG=$SCRIPT_DIR/step9_fm03_throwaway.yaml"
    echo "     export KAIJU_LIB_DIR=$FASHSD_DIR"
    echo "     export KAIJU_LOG_DIR=$KAIJU_LOG_DIR"
    echo "  5. bash $FASHSD_DIR/fm03_gluetun_unhealthy.sh"
    echo "  6. Confirm PASS, both containers up"
    echo "  7. Cleanup: docker compose down && rm -rf /tmp/kaiju-fm03-test"
}

print_step10() {
    echo ""
    echo "STEP 10: fm06_ghost_mount.sh (MANUAL - not automated)"
    echo "  Same disposable-loopback pattern as step 8. Full setup in"
    echo "  step10_fm06_throwaway.yaml's header."
    echo "  1. Create a loopback image + filesystem (as in step 8)"
    echo "  2. Inside it, mkdir kaiju-subdir-a kaiju-subdir-b"
    echo "  3. Add a TEMPORARY fstab entry, mount point"
    echo "     /mnt/kaiju-test-ghost-drive, mount once to confirm"
    echo "  4. export KAIJU_CONFIG=$SCRIPT_DIR/step10_fm06_throwaway.yaml"
    echo "     export KAIJU_LIB_DIR=$FASHSD_DIR"
    echo "     export KAIJU_LOG_DIR=$KAIJU_LOG_DIR"
    echo "  5. bash $FASHSD_DIR/fm06_ghost_mount.sh kaiju-test-ghost-drive"
    echo "  6. Confirm PASS: mountpoint -q /mnt/kaiju-test-ghost-drive"
    echo "  7. Also test once with a WRONG drive name for a clean error"
    echo "  8. Cleanup: same as step 8"
}

print_step11() {
    echo ""
    echo "STEP 11: fm07_dns_failure.sh (MANUAL - not automated)"
    echo "  1. mkdir -p /tmp/kaiju-fm07-test && cd /tmp/kaiju-fm07-test"
    echo "  2. Write docker-compose.yml: kaiju-test-dns (curl installed,"
    echo "     sleep infinity)"
    echo "  3. docker compose up -d, confirm running"
    echo "  4. export KAIJU_CONFIG=$SCRIPT_DIR/step11_fm07_throwaway.yaml"
    echo "     export KAIJU_LIB_DIR=$FASHSD_DIR"
    echo "     export KAIJU_LOG_DIR=$KAIJU_LOG_DIR"
    echo "  5. bash $FASHSD_DIR/fm07_dns_failure.sh kaiju-test-dns"
    echo "  6. Confirm PASS"
    echo "  7. Also test once against a service with no dns_check_url"
    echo "     configured, confirm a clean FAIL not a crash"
    echo "  8. Cleanup: docker compose down && rm -rf /tmp/kaiju-fm07-test"
}

print_step12() {
    echo ""
    echo "STEP 12: fm04_clock_drift.sh (MANUAL - not automated)"
    echo "  WARNING: restarts EVERY configured service (see fm04's own"
    echo "  header for the restart-scope decision/reasoning) AND forces"
    echo "  a real NTP daemon toggle. Test against a disposable services"
    echo "  list first, never real Kaidosho services."
    echo "  1. Bring up 1-2 disposable containers (e.g. step 11's stack)"
    echo "  2. Point KAIJU_CONFIG at a config listing only those as services[]"
    echo "  3. bash $FASHSD_DIR/fm04_clock_drift.sh"
    echo "  4. Confirm PASS and the disposable container(s) restarted"
    echo "  5. Cleanup: docker compose down in whichever throwaway dir(s) used"
}

print_step13() {
    echo ""
    echo "STEP 13: fm01_container_exited.sh schema v1.5 'service:' field (MANUAL - not automated)"
    echo " Exercises: container name != Compose"
    echo "  service name. Two cases against step13_fm01_v15_throwaway.yaml:"
    echo "  (a) container name genuinely differs from its Compose service"
    echo "      name (Scanopy-shaped, uses the new service: field), and"
    echo "  (b) companion regression check with NO service: field set,"
    echo "      confirming the pre-v1.5 fallback path is unchanged."
    echo ""
    echo "  Case (a) — differing names:"
    echo "  1. mkdir -p /tmp/kaiju-fm01-v15-test && cd /tmp/kaiju-fm01-v15-test"
    echo "  2. cat > docker-compose.yml << 'EOF'"
    echo "     name: kaijufm01v15"
    echo "     services:"
    echo "       server:"
    echo "         image: nginx:alpine"
    echo "         ports:"
    echo "           - \"8197:80\""
    echo "     EOF"
    echo "     (no container_name: override -- Compose will name the real"
    echo "     container 'kaijufm01v15-server-1', mirroring Scanopy's shape)"
    echo "  3. docker compose up -d"
    echo "  4. curl -s -o /dev/null -w '%{http_code}' http://localhost:8197"
    echo "     (confirm this prints 200 before continuing)"
    echo "  5. docker stop kaijufm01v15-server-1   # simulate the FM-01 trigger"
    echo "  6. export KAIJU_CONFIG=$SCRIPT_DIR/step13_fm01_v15_throwaway.yaml"
    echo "     export KAIJU_LIB_DIR=$FASHSD_DIR"
    echo "     export KAIJU_LOG_DIR=$KAIJU_LOG_DIR"
    echo "  7. bash $FASHSD_DIR/fm01_container_exited.sh kaijufm01v15-server-1 /tmp/kaiju-fm01-v15-test"
    echo "  8. PASS condition: output includes the \"Note: container '...'"
    echo "     maps to compose service '...'\" line, docker compose up -d"
    echo "     succeeds (not \"no such service\"), and:"
    echo "     docker ps --filter name=kaijufm01v15-server-1  confirms running"
    echo "  9. Cleanup: docker compose down && rm -rf /tmp/kaiju-fm01-v15-test"
    echo ""
    echo "  Case (b) — companion regression check, no service: field:"
    echo "  1. mkdir -p /tmp/kaiju-fm01-v15-fallback && cd /tmp/kaiju-fm01-v15-fallback"
    echo "  2. cat > docker-compose.yml << 'EOF'"
    echo "     services:"
    echo "       kaiju-test-v15-fallback:"
    echo "         image: nginx:alpine"
    echo "         container_name: kaiju-test-v15-fallback"
    echo "         ports:"
    echo "           - \"8196:80\""
    echo "     EOF"
    echo "  3. docker compose up -d"
    echo "  4. docker stop kaiju-test-v15-fallback"
    echo "  5. bash $FASHSD_DIR/fm01_container_exited.sh kaiju-test-v15-fallback /tmp/kaiju-fm01-v15-fallback"
    echo "     (same KAIJU_CONFIG/LIB_DIR/LOG_DIR exports as case (a) --"
    echo "     step13_fm01_v15_throwaway.yaml lists both entries)"
    echo "  6. PASS condition: NO 'maps to compose service' note printed"
    echo "     (container name and service name are identical here), plain"
    echo "     up -d still works, docker ps confirms running -- byte-for-byte"
    echo "     the same behavior as step 6's pre-v1.5 test"
    echo "  7. Cleanup: docker compose down && rm -rf /tmp/kaiju-fm01-v15-fallback"
}

print_step14() {
    echo ""
    echo "STEP 14: watchdog_notify.sh (SEMI-AUTOMATED -- sends a real ntfy"
    echo "  notification to your configured ntfy channel, clearly"
    echo "  marked as a package test. Round 5, added 2026-09-25 -- this"
    echo "  script had NO dedicated test anywhere before this.)"
    echo ""
    echo "  Requires KAIJU_NTFY_USER / KAIJU_NTFY_PASS to already be exported"
    echo "  in this shell (the packaged watchdog_notify.sh deliberately never"
    echo "  hardcodes a credential -- see its own header comment). If unset,"
    echo "  this step will still run but the ntfy server will likely reject"
    echo "  it with a 401/403 -- that's a valid, informative test result too,"
    echo "  not a script bug."
    echo ""
    read -p "  Send a real test notification to your ntfy channel now? [y/N] " -n 1 -r RUN_STEP14
    echo ""
    if [[ $RUN_STEP14 =~ ^[Yy]$ ]]; then
        export KAIJU_CONFIG="$SCRIPT_DIR/step14_watchdog_notify.yaml"
        STEP14_OUTPUT=$(bash "$FASHSD_DIR/watchdog_notify.sh" \
            "[Kaiju OS package test]" \
            "Round 5 watchdog_notify.sh test -- ignore, not a real alert." \
            "default" 2>&1)
        STEP14_EXIT=$?
        echo "  Output: $STEP14_OUTPUT"
        [ "$STEP14_EXIT" = "0" ] && pass "watchdog_notify.sh exited 0 (check your phone for the real notification)" || fail "exit code $STEP14_EXIT -- check KAIJU_NTFY_USER/PASS and network reachability"
        LOGLINE=$(tail -1 "$KAIJU_LOG_DIR/watchdog.log" 2>/dev/null)
        echo "$LOGLINE" | grep -q "Kaiju OS package test" && pass "log line format matches the established convention" || fail "log line missing or malformed: '$LOGLINE'"
    else
        echo "  Skipped (re-run this script and answer 'y' when ready)."
    fi
}

print_step15() {
    echo ""
    echo "STEP 15: pi5_watchdog.sh orchestration dispatch (MANUAL -- not"
    echo "  automated). Round 5, added 2026-09-25. Tests the ORCHESTRATOR's"
    echo "  own detection+dispatch logic (STEP 2's container-exited branch,"
    echo "  the most fundamental one) end to end -- not fm01 directly (that's"
    echo "  already covered by step 6), but whether pi5_watchdog.sh correctly"
    echo "  DETECTS an exited container, looks it up via"
    echo "  kaiju_service_index_by_name, and DISPATCHES fm01 with the right"
    echo "  compose_dir on its own, then continues on to its later steps"
    echo "  (curl re-check) without erroring."
    echo ""
    echo "  KNOWN GAP, stated plainly: this covers ONE of pi5_watchdog.sh's 8"
    echo "  internal branches (container-exited, non-owner). The other 7"
    echo "  (daemon-down, curl-fail dispatch with/without dns_check_url,"
    echo "  network-group owner/dependent restart, drive-not-mounted,"
    echo "  ghost-mount, clock-drift) are each already tested at the FM-"
    echo "  script level (steps 7/9-12) but NOT yet re-exercised through the"
    echo "  orchestrator's own detection loop the way this step does for"
    echo "  container-exited. A future Round 6 covering those remains open."
    echo ""
    echo "  1. mkdir -p /tmp/kaiju-watchdog-test && cd /tmp/kaiju-watchdog-test"
    echo "  2. cat > docker-compose.yml << 'EOF'"
    echo "     services:"
    echo "       kaiju-test-watchdog-nginx:"
    echo "         image: nginx:alpine"
    echo "         container_name: kaiju-test-watchdog-nginx"
    echo "         ports:"
    echo "           - \"8195:80\""
    echo "     EOF"
    echo "  3. docker compose up -d"
    echo "  4. curl -s -o /dev/null -w '%{http_code}' http://localhost:8195"
    echo "     (confirm this prints 200 before continuing)"
    echo "  5. docker stop kaiju-test-watchdog-nginx   # simulate the trigger"
    echo "  6. export KAIJU_CONFIG=$SCRIPT_DIR/step15_watchdog_orchestration.yaml"
    echo "     export KAIJU_LIB_DIR=$FASHSD_DIR"
    echo "     export KAIJU_LOG_DIR=$KAIJU_LOG_DIR"
    echo "  7. bash $FASHSD_DIR/pi5_watchdog.sh"
    echo "  8. PASS condition, check $KAIJU_LOG_DIR/watchdog.log for:"
    echo "     - a line showing the container was detected exited and NOT a"
    echo "       network_group owner (dispatches fm01, not fm03)"
    echo "     - fm01_container_exited.sh's own PASS line for this container"
    echo "     - the later curl-check step (STEP 3/4) PASSing for this same"
    echo "       service now that it's back up -- confirms the orchestrator's"
    echo "       later phases correctly see the fix that its own earlier"
    echo "       phase made, not just that fm01 itself worked in isolation"
    echo "     - exit code 0 (no CRIT -- everything resolved within the cycle)"
    echo "     docker ps --filter name=kaiju-test-watchdog-nginx  confirms running"
    echo "  9. Cleanup: docker compose down && rm -rf /tmp/kaiju-watchdog-test"
}

print_step16() {
    echo ""
    echo "STEP 16: pi5_watchdog.sh orchestration -- daemon-down branch (MANUAL,"
    echo "  HIGH BLAST RADIUS -- restarts the ENTIRE Docker daemon on this"
    echo "  host, same warning class as step 7). Round 6, added 2026-09-25."
    echo "  Tests STEP 1 of pi5_watchdog.sh: does the orchestrator correctly"
    echo "  detect the daemon is down and dispatch fm02_daemon_down.sh"
    echo "  ON ITS OWN (fm02 itself is already tested directly, step 7 --"
    echo "  this is the orchestrator's own detection+dispatch logic)."
    echo ""
    echo "  1. export KAIJU_CONFIG=$SCRIPT_DIR/step16_daemon_down_orchestrator.yaml"
    echo "     export KAIJU_LIB_DIR=$FASHSD_DIR"
    echo "     export KAIJU_LOG_DIR=$KAIJU_LOG_DIR"
    echo "  2. sudo systemctl stop docker   # every container on this host stops"
    echo "  3. bash $FASHSD_DIR/pi5_watchdog.sh; echo \"exit: \$?\""
    echo "  4. PASS condition, check \$KAIJU_LOG_DIR/watchdog.log for:"
    echo "     - \"Docker daemon not active -- dispatching fm02_daemon_down.sh\""
    echo "     - \"fm02_daemon_down.sh PASS -- daemon recovered\""
    echo "     - \"Skipping remaining checks this cycle (daemon was down)\""
    echo "     - exit code 0"
    echo "     systemctl is-active docker  confirms active again"
    echo "  5. Confirm your REAL Kaidosho services came back up correctly after the"
    echo "     daemon restart -- this is the main real-world risk here"
    echo "  6. Cleanup: none needed beyond confirming real services are healthy"
}

print_step17() {
    echo ""
    echo "STEP 17: pi5_watchdog.sh orchestration -- curl-fail WITH dns_check_url"
    echo "  (MANUAL, disposable container). Round 6, added 2026-09-25. Tests"
    echo "  STEP 3/4: does the orchestrator correctly choose fm07 (not the"
    echo "  no-dns-check fallback) because dns_check_url IS configured for this"
    echo "  service. fm07's own DNS-fix logic is already tested directly"
    echo "  (step 11) -- this tests the orchestrator's DISPATCH DECISION only,"
    echo "  so the health_url just needs to genuinely fail (any reason), not a"
    echo "  real DNS break."
    echo ""
    echo "  1. mkdir -p /tmp/kaiju-orch-dns-test && cd /tmp/kaiju-orch-dns-test"
    echo "  2. cat > docker-compose.yml << 'EOF'"
    echo "     services:"
    echo "       kaiju-test-orch-dns:"
    echo "         image: nginx:alpine"
    echo "         container_name: kaiju-test-orch-dns"
    echo "         ports:"
    echo "           - \"8194:80\""
    echo "     EOF"
    echo "  3. docker compose up -d   # container stays UP; only its /nonexistent-path"
    echo "     # health_url (see the step17 config) will genuinely 404"
    echo "  4. export KAIJU_CONFIG=$SCRIPT_DIR/step17_curlfail_dns_orchestrator.yaml"
    echo "     export KAIJU_LIB_DIR=$FASHSD_DIR"
    echo "     export KAIJU_LOG_DIR=$KAIJU_LOG_DIR"
    echo "  5. bash $FASHSD_DIR/pi5_watchdog.sh; echo \"exit: \$?\""
    echo "  6. PASS condition, check \$KAIJU_LOG_DIR/watchdog.log for:"
    echo "     - \"kaiju-test-orch-dns: curl FAIL, has dns_check_url --"
    echo "       dispatching fm07_dns_failure.sh\""
    echo "     (the recheck afterward will likely still show FAILING, since the"
    echo "     404 is a config mismatch fm07's restart can't fix -- that's"
    echo "     expected and fine, this step tests the DISPATCH choice, not"
    echo "     whether the symptom clears)"
    echo "  7. Cleanup: docker compose down && rm -rf /tmp/kaiju-orch-dns-test"
}

print_step18() {
    echo ""
    echo "STEP 18: pi5_watchdog.sh orchestration -- curl-fail WITHOUT"
    echo "  dns_check_url, best-effort fm01 fallback (MANUAL, disposable"
    echo "  container). Round 6, added 2026-09-25. GENUINELY ORCHESTRATOR-"
    echo "  UNIQUE logic -- no FM script tests this branch directly, since it's"
    echo "  pi5_watchdog.sh's OWN best-effort fallback for a symptom with no"
    echo "  matching fix script (no FM-09 equivalent exists in this package)."
    echo "  Also tests the confirmed design decision that the post-fix"
    echo "  curl-recheck runs REGARDLESS of the fix script's own exit code."
    echo ""
    echo "  1. mkdir -p /tmp/kaiju-orch-nodns-test && cd /tmp/kaiju-orch-nodns-test"
    echo "  2. cat > docker-compose.yml << 'EOF'"
    echo "     services:"
    echo "       kaiju-test-orch-nodns:"
    echo "         image: nginx:alpine"
    echo "         container_name: kaiju-test-orch-nodns"
    echo "         ports:"
    echo "           - \"8193:80\""
    echo "     EOF"
    echo "  3. docker compose up -d"
    echo "  4. export KAIJU_CONFIG=$SCRIPT_DIR/step18_curlfail_nodns_orchestrator.yaml"
    echo "     export KAIJU_LIB_DIR=$FASHSD_DIR"
    echo "     export KAIJU_LOG_DIR=$KAIJU_LOG_DIR"
    echo "  5. bash $FASHSD_DIR/pi5_watchdog.sh; echo \"exit: \$?\""
    echo "  6. PASS condition, check \$KAIJU_LOG_DIR/watchdog.log for:"
    echo "     - \"kaiju-test-orch-nodns: curl FAIL, no dns_check_url configured"
    echo "       -- no matching fix script exists ... Best-effort: dispatching"
    echo "       fm01_container_exited.sh\""
    echo "     - a curl re-check STILL FAILING line afterward (expected -- the"
    echo "       404 is a config issue fm01's restart genuinely cannot fix,"
    echo "       which is exactly why this design decision exists)"
    echo "     - exit code 1 (CRIT=1, correctly escalated since the symptom"
    echo "       didn't actually clear)"
    echo "  7. Cleanup: docker compose down && rm -rf /tmp/kaiju-orch-nodns-test"
}

print_step19() {
    echo ""
    echo "STEP 19: pi5_watchdog.sh orchestration -- network-group OWNER branch"
    echo "  (MANUAL, disposable owner+dependent stack). Round 6, added"
    echo "  2026-09-25. Tests STEP 2: does the orchestrator correctly identify"
    echo "  an exited container as a network_group OWNER (via"
    echo "  kaiju_network_group_field lookup) and dispatch fm03 instead of"
    echo "  fm01 -- fm03's own remediation logic is already tested directly"
    echo "  (step 9), this tests the orchestrator's IDENTIFICATION step."
    echo ""
    echo "  1. mkdir -p /tmp/kaiju-orch-networkgroup-test && cd /tmp/kaiju-orch-networkgroup-test"
    echo "  2. Write docker-compose.yml: kaiju-test-orch-owner (a HEALTHCHECK-"
    echo "     bearing image) + kaiju-test-orch-dep (network_mode:"
    echo "     service:kaiju-test-orch-owner, curl installed, sleep infinity)"
    echo "     -- same shape as step 9's own disposable stack"
    echo "  3. docker compose up -d, confirm owner reports healthy"
    echo "  4. docker stop kaiju-test-orch-owner   # simulate the trigger"
    echo "  5. export KAIJU_CONFIG=$SCRIPT_DIR/step19_networkgroup_orchestrator.yaml"
    echo "     export KAIJU_LIB_DIR=$FASHSD_DIR"
    echo "     export KAIJU_LOG_DIR=$KAIJU_LOG_DIR"
    echo "  6. bash $FASHSD_DIR/pi5_watchdog.sh; echo \"exit: \$?\""
    echo "  7. PASS condition, check \$KAIJU_LOG_DIR/watchdog.log for:"
    echo "     - \"kaiju-test-orch-owner: exited, is a network_group owner --"
    echo "       dispatching fm03_gluetun_unhealthy.sh\" (NOT fm01)"
    echo "     - fm03's own real remediation output following it"
    echo "     docker ps  confirms both containers running again"
    echo "  8. Cleanup: docker compose down && rm -rf /tmp/kaiju-orch-networkgroup-test"
}

print_step20() {
    echo ""
    echo "STEP 20: pi5_watchdog.sh orchestration -- drive-not-mounted branch"
    echo "  (MANUAL, disposable loopback drive). Round 6, added 2026-09-25."
    echo "  Tests STEP 5: does the orchestrator correctly detect a configured"
    echo "  drive is not mounted and dispatch fm05 -- fm05's own remediation"
    echo "  is already tested directly (step 8), this tests the orchestrator's"
    echo "  own drive-scanning loop."
    echo ""
    echo "  1. Set up a disposable loopback drive exactly as in step 8 (steps"
    echo "     1-6 there), named kaiju-test-orch-drive, mount point"
    echo "     /mnt/kaiju-test-orch-drive -- end with it UNMOUNTED (the"
    echo "     trigger condition: configured, not mounted)"
    echo "  2. export KAIJU_CONFIG=$SCRIPT_DIR/step20_drivenotmounted_orchestrator.yaml"
    echo "     export KAIJU_LIB_DIR=$FASHSD_DIR"
    echo "     export KAIJU_LOG_DIR=$KAIJU_LOG_DIR"
    echo "  3. bash $FASHSD_DIR/pi5_watchdog.sh; echo \"exit: \$?\""
    echo "  4. PASS condition, check \$KAIJU_LOG_DIR/watchdog.log for:"
    echo "     - \"kaiju-test-orch-drive: not mounted -- dispatching"
    echo "       fm05_drive_not_mounted.sh\""
    echo "     - fm05's own PASS line"
    echo "     mountpoint -q /mnt/kaiju-test-orch-drive  confirms mounted"
    echo "  5. Cleanup: same teardown as step 8 (unmount, losetup -d, remove"
    echo "     the fstab line, rm the image, rmdir the mount point)"
}

print_step21() {
    echo ""
    echo "STEP 21: pi5_watchdog.sh orchestration -- ghost-mount branch (MANUAL,"
    echo "  disposable loopback drive). Round 6, added 2026-09-25. Tests"
    echo "  STEP 6: does the orchestrator correctly distinguish a drive that"
    echo "  IS mounted but missing expected_subdirs from one that's simply not"
    echo "  mounted (step 20), and dispatch fm06 instead of fm05 -- fm06's own"
    echo "  remediation is already tested directly (step 10)."
    echo ""
    echo "  1. Set up a disposable loopback drive exactly as in step 10, named"
    echo "     kaiju-test-orch-ghost, mount point /mnt/kaiju-test-orch-ghost,"
    echo "     expected_subdirs kaiju-subdir-a/kaiju-subdir-b -- end with it"
    echo "     MOUNTED but the expected subdirs genuinely missing (the ghost-"
    echo "     mount trigger condition)"
    echo "  2. export KAIJU_CONFIG=$SCRIPT_DIR/step21_ghostmount_orchestrator.yaml"
    echo "     export KAIJU_LIB_DIR=$FASHSD_DIR"
    echo "     export KAIJU_LOG_DIR=$KAIJU_LOG_DIR"
    echo "  3. bash $FASHSD_DIR/pi5_watchdog.sh; echo \"exit: \$?\""
    echo "  4. PASS condition, check \$KAIJU_LOG_DIR/watchdog.log for:"
    echo "     - NO fm05 dispatch line (the drive IS mounted, so STEP 5's"
    echo "       not-mounted check correctly does not fire)"
    echo "     - \"kaiju-test-orch-ghost: mounted but expected_subdirs missing"
    echo "       (ghost mount) -- dispatching fm06_ghost_mount.sh\""
    echo "     - fm06's own PASS line"
    echo "  5. Cleanup: same teardown as step 10"
}

print_step22() {
    echo ""
    echo "STEP 22: pi5_watchdog.sh orchestration -- clock-drift branch (MANUAL,"
    echo "  HIGH BLAST RADIUS -- restarts EVERY service[] in the config, same"
    echo "  warning class as step 12). Round 6, added 2026-09-25. Tests STEP 7:"
    echo "  does the orchestrator correctly detect drift and dispatch fm04 --"
    echo "  fm04's own remediation is already tested directly (step 12). SAFE"
    echo "  TRIGGER, no real clock skew needed: step22's config sets"
    echo "  clock_drift_threshold_ms to 1 -- any normal sub-millisecond NTP"
    echo "  jitter will legitimately exceed that and trigger DRIFT_DETECTED,"
    echo "  without touching the system clock at all."
    echo ""
    echo "  1. mkdir -p /tmp/kaiju-orch-clockdrift-test && cd /tmp/kaiju-orch-clockdrift-test"
    echo "  2. cat > docker-compose.yml << 'EOF'"
    echo "     services:"
    echo "       kaiju-test-orch-clockdrift:"
    echo "         image: nginx:alpine"
    echo "         container_name: kaiju-test-orch-clockdrift"
    echo "         ports:"
    echo "           - \"8192:80\""
    echo "     EOF"
    echo "  3. docker compose up -d"
    echo "  4. export KAIJU_CONFIG=$SCRIPT_DIR/step22_clockdrift_orchestrator.yaml"
    echo "     export KAIJU_LIB_DIR=$FASHSD_DIR"
    echo "     export KAIJU_LOG_DIR=$KAIJU_LOG_DIR"
    echo "  5. bash $FASHSD_DIR/pi5_watchdog.sh; echo \"exit: \$?\""
    echo "  6. PASS condition, check \$KAIJU_LOG_DIR/watchdog.log for:"
    echo "     - a real \"Clock offset: Nms (threshold: 1ms)\" line"
    echo "     - \"Clock drift detected -- dispatching fm04_clock_drift.sh"
    echo "       (highest blast radius: restarts ALL configured services)\""
    echo "     - fm04's own PASS line"
    echo "     docker ps --filter name=kaiju-test-orch-clockdrift  confirms"
    echo "     restarted (a fresh container start time)"
    echo "  7. Also confirm your REAL Kaidosho services were undisturbed -- this"
    echo "     config's services[] lists ONLY the disposable container,"
    echo "     confirming fm04 restarted exactly what was configured"
    echo "  8. Cleanup: docker compose down && rm -rf /tmp/kaiju-orch-clockdrift-test"
}

case "${1:-}" in
    6) print_step6; exit 0 ;;
    7) print_step7; exit 0 ;;
    8) print_step8; exit 0 ;;
    9) print_step9; exit 0 ;;
    10) print_step10; exit 0 ;;
    11) print_step11; exit 0 ;;
    12) print_step12; exit 0 ;;
    13) print_step13; exit 0 ;;
    14) print_step14; exit 0 ;;
    15) print_step15; exit 0 ;;
    16) print_step16; exit 0 ;;
    17) print_step17; exit 0 ;;
    18) print_step18; exit 0 ;;
    19) print_step19; exit 0 ;;
    20) print_step20; exit 0 ;;
    21) print_step21; exit 0 ;;
    22) print_step22; exit 0 ;;
esac

echo "═══════════════════════════════════════════════════════"
echo "KAIJU OS FASHSD TEST SUITE — $(date '+%Y-%m-%d %H:%M:%S')"
echo "═══════════════════════════════════════════════════════"

if ! command -v yq >/dev/null 2>&1; then
    echo "FATAL: yq not installed. Install with: apt install yq"
    exit 1
fi

# ─────────────────────────────────────────────────────────
echo ""
echo "── STEP 1: Config lib isolated test ──"
export KAIJU_CONFIG="$SCRIPT_DIR/step1_isolated.yaml"
source "$FASHSD_DIR/fashsd_config_lib.sh"

COUNT=$(kaiju_service_count)
[ "$COUNT" = "3" ] && pass "kaiju_service_count returned 3" || fail "kaiju_service_count returned '$COUNT', expected 3"

NAME0=$(kaiju_service_field 0 name)
[ "$NAME0" = "fake-service-a" ] && pass "kaiju_service_field 0 name = fake-service-a" || fail "got '$NAME0'"

MODE=$(kaiju_topology_mode)
[ "$MODE" = "two-node-wol" ] && pass "kaiju_topology_mode = two-node-wol" || fail "got '$MODE'"

MAC=$(kaiju_target_mac)
[ "$MAC" = "00:11:22:33:44:55" ] && pass "kaiju_target_mac correct" || fail "got '$MAC'"

DIRCOUNT=$(kaiju_known_compose_dirs | wc -l)
[ "$DIRCOUNT" = "3" ] && pass "kaiju_known_compose_dirs returned 3 unique dirs" || fail "got $DIRCOUNT dirs"

# ─────────────────────────────────────────────────────────
echo ""
echo "── STEP 2: app_curl_check.sh against harmless external URLs ──"
export KAIJU_CONFIG="$SCRIPT_DIR/step2_harmless.yaml"
STEP2_OUTPUT=$(bash "$FASHSD_DIR/app_curl_check.sh" 2>&1)
STEP2_EXIT=$?
echo "$STEP2_OUTPUT" | sed 's/^/  /'

# check_service() writes individual PASS/FAIL lines to the log FILE,
# not stdout — only the summary line + FAIL details print to stdout.
# Assert against the log file and the summary line instead.
STEP2_LOG="$KAIJU_LOG_DIR/watchdog.log"
grep -q "httpbin-200: PASS" "$STEP2_LOG" 2>/dev/null && pass "httpbin-200 correctly PASSed" || fail "httpbin-200 did not PASS as expected"
grep -q "httpbin-302: PASS" "$STEP2_LOG" 2>/dev/null && pass "httpbin-302 correctly PASSed" || fail "httpbin-302 did not PASS as expected"
echo "$STEP2_OUTPUT" | grep -q "FAIL: httpbin-expect-mismatch" && pass "deliberate mismatch correctly FAILed" || fail "deliberate mismatch did NOT fail — comparison logic may be broken"
echo "$STEP2_OUTPUT" | grep -q "^PASS: 2  FAIL: 1" && pass "summary line correct (PASS: 2  FAIL: 1)" || fail "summary line incorrect"
[ "$STEP2_EXIT" = "1" ] && pass "script exit code is 1 (expected, one deliberate FAIL present)" || fail "exit code was $STEP2_EXIT, expected 1"

# ─────────────────────────────────────────────────────────
echo ""
echo "── STEP 3: app_curl_check.sh vs Kaidosho's REAL original (read-only, live) ──"
echo "  ⚠️  This step curls the services listed in step3_reference_real_readonly.yaml. Read-only,"
echo "  no state changes, but requires Kaidosho's services to actually be up."
read -p "  Run step 3 against live Kaidosho services now? [y/N] " -n 1 -r RUN_STEP3
echo ""
if [[ $RUN_STEP3 =~ ^[Yy]$ ]]; then
    export KAIJU_CONFIG="$SCRIPT_DIR/step3_reference_real_readonly.yaml"
    GENERALIZED_OUTPUT=$(bash "$FASHSD_DIR/app_curl_check.sh" 2>&1)
    GENERALIZED_SUMMARY=$(echo "$GENERALIZED_OUTPUT" | grep "^PASS:")

    ORIGINAL_SCRIPT="${KAIJU_ORIGINAL_APP_CURL_CHECK:-}"
    if [ -f "$ORIGINAL_SCRIPT" ]; then
        ORIGINAL_OUTPUT=$(bash "$ORIGINAL_SCRIPT" 2>&1)
        ORIGINAL_SUMMARY=$(echo "$ORIGINAL_OUTPUT" | grep "^PASS:")

        echo "  Generalized: $GENERALIZED_SUMMARY"
        echo "  Original:    $ORIGINAL_SUMMARY"

        # Compare PASS/FAIL COUNTS, not the raw summary string -- fixed
        # 2026-09-24 (Round 5) after a false FAIL: the generalized script's
        # summary line has always included a SKIP field the older original
        # script never had, so an exact
        # string match was guaranteed to differ even on identical results.
        # This bug predates the SKIP field's addition and was never caught
        # because Round 1 (2026-07-23) ran before SKIP existed.
        GEN_PASS=$(echo "$GENERALIZED_SUMMARY" | grep -oP 'PASS:\s*\K[0-9]+')
        GEN_FAIL=$(echo "$GENERALIZED_SUMMARY" | grep -oP 'FAIL:\s*\K[0-9]+')
        ORIG_PASS=$(echo "$ORIGINAL_SUMMARY" | grep -oP 'PASS:\s*\K[0-9]+')
        ORIG_FAIL=$(echo "$ORIGINAL_SUMMARY" | grep -oP 'FAIL:\s*\K[0-9]+')

        if [ -n "$GEN_PASS" ] && [ "$GEN_PASS" = "$ORIG_PASS" ] && [ "$GEN_FAIL" = "$ORIG_FAIL" ]; then
            pass "generalized and original PASS/FAIL counts match exactly ($GEN_PASS/$GEN_FAIL)"
        else
            fail "MISMATCH between generalized and original — investigate before proceeding"
        fi
    else
        echo "  ⚠️  No original script to compare against (set KAIJU_ORIGINAL_APP_CURL_CHECK to its path) — skipping comparison."
        echo "  Generalized output only:"
        echo "$GENERALIZED_OUTPUT" | sed 's/^/    /'
    fi
else
    echo "  Skipped (re-run this script and answer 'y' when ready)."
fi

# ─────────────────────────────────────────────────────────
echo ""
echo "── STEP 4: wol_trigger.sh in single-node mode (no-op expected) ──"
export KAIJU_CONFIG="$SCRIPT_DIR/step4_singlenode.yaml"
STEP4_OUTPUT=$(bash "$FASHSD_DIR/wol_trigger.sh" 2>&1)
STEP4_EXIT=$?
echo "  Output: $STEP4_OUTPUT"
echo "$STEP4_OUTPUT" | grep -qi "not applicable" && pass "single-node correctly skipped" || fail "did not skip as expected"
[ "$STEP4_EXIT" = "0" ] && pass "exit code 0" || fail "exit code $STEP4_EXIT, expected 0"

# ─────────────────────────────────────────────────────────
echo ""
echo "── STEP 5: wol_trigger.sh in two-node-wol mode (real Kaidosho MAC) ──"
echo "  ⚠️  This sends a real WoL packet to the target node's MAC. Harmless"
echo "  (no-op if already awake) but genuinely sends network traffic."
read -p "  Run step 5 now? [y/N] " -n 1 -r RUN_STEP5
echo ""
if [[ $RUN_STEP5 =~ ^[Yy]$ ]]; then
    export KAIJU_CONFIG="$SCRIPT_DIR/step5_twonode_real.yaml"
    STEP5_OUTPUT=$(bash "$FASHSD_DIR/wol_trigger.sh" 2>&1)
    STEP5_EXIT=$?
    echo "  Output: $STEP5_OUTPUT"
    [ "$STEP5_EXIT" = "0" ] && pass "wol_trigger.sh exited 0" || fail "exit code $STEP5_EXIT"
    echo "  Manually verify: tail $KAIJU_LOG_DIR/watchdog.log"
    echo "  should show a wakeonlan log line with the correct MAC."
else
    echo "  Skipped (re-run this script and answer 'y' when ready)."
fi

# ─────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────
# Default full run (no argument): print all three manual sections at
# the end, same as always — only reached here if 6/7/8 wasn't passed
# as an argument (those cases already exited above).
if [ "$FAIL" = "0" ]; then
    print_step6
    print_step7
    print_step8
    print_step9
    print_step10
    print_step11
    print_step12
    print_step13
    print_step14
    print_step15
    print_step16
    print_step17
    print_step18
    print_step19
    print_step20
    print_step21
    print_step22
fi

# ─────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "RESULTS: $PASS passed, $FAIL failed"
echo "═══════════════════════════════════════════════════════"
if [ "$FAIL" -gt 0 ]; then
    echo "❌ Do NOT remove the MUST PRIORITY warnings — failures found."
    exit 1
else
    echo "✅ Automated steps (1,2,4, and any of 3/5 you ran) passed."
    echo "   Steps 6-13, 15-22 (manual, disposable containers/drives) and step"
    echo "   14 (semi-automated, real ntfy send) still need to be run"
    echo "   individually -- see the instructions printed above, or run"
    echo "   ./run_tests.sh <N> for just one step's instructions."
fi
