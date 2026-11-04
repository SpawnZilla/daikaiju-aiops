#!/bin/bash
# test_fm12_mocked.sh -- mocked-docker scenario tests for fm12_missing_image_snapshot.sh
# Usage: bash test_fm12_mocked.sh [path/to/fm12_missing_image_snapshot.sh]
# Needs: bash, jq. Touches nothing outside a mktemp directory; no real docker.
# Written 2026-10-15. 10 scenarios; prints [ok]/[FAIL] per scenario and exits 1 on any FAIL.

SCRIPT="${1:-$(dirname "$0")/fm12_missing_image_snapshot.sh}"
T=$(mktemp -d /tmp/fm12test.XXXXXX)
mkdir -p "$T/bin" "$T/lib" "$T/arr" "$T/other"

cat > "$T/bin/docker" <<'EOF'
#!/bin/bash
S="$MOCK_STATE"
cmd="$1"; shift
case "$cmd" in
  inspect) [ -f "$S/exists" ] && exit 0; echo "Error: No such object" >&2; exit 1;;
  compose)
    sub="$1"; shift
    case "$sub" in
      config)
        if [ "$1" = "--services" ]; then echo gluetun; echo lidarr; echo sonarr; exit 0; fi
        if [ "$1" = "--format" ]; then echo '{"services":{"lidarr":{"image":"lscr.io/linuxserver/lidarr:latest"},"sonarr":{"image":"x"}}}'; exit 0; fi;;
      pull) echo pull >> "$S/calls"; touch "$S/pulled"; exit 0;;
      up)
        echo "up" >> "$S/calls"
        if [ -f "$S/up_other_error" ]; then echo "Error response from daemon: some other error" >&2; exit 1; fi
        if [ -f "$S/up_ok_first" ]; then touch "$S/running"; exit 0; fi
        if [ -f "$S/pulled" ] && [ ! -f "$S/repeat_error" ]; then touch "$S/running"; exit 0; fi
        echo "failed to stat parent: stat /var/lib/containerd/x/snapshots/4878/fs: no such file or directory" >&2; exit 1;;
    esac;;
  image) [ "$1" = inspect ] && { echo sha256:abc; exit 0; };;
  ps)
    args="$*"
    case "$args" in
      *ancestor=*) [ -f "$S/shared" ] && echo prowlarr2; exit 0;;
      *status=running*) [ -f "$S/running" ] && echo lidarr; exit 0;;
    esac;;
  rmi) echo "rmi" >> "$S/calls"; exit 0;;
esac
exit 0
EOF
cat > "$T/bin/journalctl" <<'EOF'
#!/bin/bash
S="$MOCK_STATE"
[ -f "$S/journal_denied" ] && { echo "No journal files were opened due to insufficient permissions." >&2; exit 1; }
if [ -f "$S/kernel_err" ]; then echo "Oct 15 06:00:01 kernel: EXT4-fs error (device sdj1): ext4_find_entry"; fi
echo "Oct 15 06:00:02 kernel: usb 1-2: new high-speed USB device"
exit 0
EOF
cat > "$T/bin/curl" <<'EOF'
#!/bin/bash
cat "$MOCK_STATE/curlcode" 2>/dev/null || printf 200
EOF
chmod +x "$T/bin/"*
cat > "$T/lib/fashsd_config_lib.sh" <<'EOF'
kaiju_known_compose_dirs() { echo "$MOCK_COMPOSE_DIR"; }
kaiju_service_compose_key() { echo "$1"; }
kaiju_service_index_by_name() { [ "$1" = lidarr ] && echo 3; }
kaiju_service_field() { case "$2" in health_url) echo http://localhost:8686/ping;; expected_code) echo 200;; timeout_seconds) echo 10;; esac; }
EOF

BAD=0
run() { # name expect_exit "flags" curlcode compose_dir expect_text
    name="$1"; exp="$2"; flags="$3"; code="${4:-200}"; dir="${5:-$T/arr}"; want="$6"
    S="$T/state_$name"; rm -rf "$S" "$T/log_$name"; mkdir -p "$S" "$T/log_$name"
    for f in $flags; do touch "$S/$f"; done
    printf "%s" "$code" > "$S/curlcode"
    out=$(PATH="$T/bin:$PATH" MOCK_STATE="$S" MOCK_COMPOSE_DIR="$T/arr" KAIJU_LIB_DIR="$T/lib" KAIJU_LOG_DIR="$T/log_$name" \
        FM12_PLAIN_WAIT=0 FM12_SETTLE_SECONDS=0 FM12_HEALTH_TRIES=3 FM12_HEALTH_INTERVAL=0 \
        bash "$SCRIPT" lidarr "$dir" 2>&1); rc=$?
    ups=$(grep -c '^up' "$S/calls" 2>/dev/null); ups=${ups:-0}
    rmi=$(grep -c '^rmi' "$S/calls" 2>/dev/null); rmi=${rmi:-0}
    log=$(cat "$T/log_$name/watchdog.log" 2>/dev/null)
    st=FAIL
    if [ "$rc" = "$exp" ] && { [ -z "$want" ] || echo "$log$out" | grep -q "$want"; }; then st=ok; fi
    [ "$st" = FAIL ] && BAD=1
    echo "[$st] $name rc=$rc(exp $exp) up_calls=$ups rmi=$rmi"
    eval "UPS_$name=$ups; RMI_$name=$rmi"
}

run A_success 0 "" 200 "" "recreated after image re-pull; http://localhost:8686/ping returned 200"
run B_shared 1 "shared" 200 "" "used by other container"
run C_kernel_err 1 "kernel_err" 200 "" "see FM-10"
run D_repeat_error 1 "repeat_error" 200 "" "Same snapshot error"
run E_other_error 1 "up_other_error" 200 "" "not the FM-12 snapshot signature"
run F_plain_up_ok 0 "up_ok_first" 200 "" "no repair needed"
run G_container_exists 1 "exists" 200 "" "belong to FM-01"
run H_journal_denied 0 "journal_denied" 200 "" "precheck SKIPPED"
run I_health_fail 1 "" 302 "" "returned 302"
run J_bad_dir 1 "" 200 "$T/other" "not a compose directory"

chk() { if [ "$2" = "$3" ]; then echo "[ok] $1"; else echo "[FAIL] $1 (got $2, want $3)"; BAD=1; fi; }
chk "C: no up call before the kernel precheck stops it" "$UPS_C_kernel_err" 0
chk "D: exactly 2 up calls (plain + one repair, no third)" "$UPS_D_repeat_error" 2
chk "B: shared image is never removed" "$RMI_B_shared" 0
chk "E: other errors never trigger rmi" "$RMI_E_other_error" 0

rm -rf "$T"
[ "$BAD" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $BAD
