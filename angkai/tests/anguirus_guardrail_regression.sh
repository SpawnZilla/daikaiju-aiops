#!/bin/bash
# ============================================================
# angkai_guardrail_regression.sh --  Layer D
#
# Consolidated regression suite for the whole Angkai guardrail
# hook chain (/076/081/082/086) plus the  Layer A
# subagent-block flag. Built 2026-09-25 by consolidating the
# individual live/offline tests already proven, one at a time, over
# the course of that same session, into one repeatable script that
# can be re-run any time ANY of these files change, to catch a
# regression in one hook silently breaking another.
#
# DESIGN: every fixture that touches state (/082/086) runs
# against the REAL, currently-deployed hook scripts (found by their
# real absolute paths -- this is deliberately NOT testing copies),
# but with EVERY piece of file-based state (snapshot store, backup
# store, settings.json, task_released.json, production_signatures.conf)
# pointed at a fresh temp sandbox via each script's own existing env-
# var overrides. This means: real code, fully isolated inputs/outputs.
# No sudo needed, safe to run at any time (including while a real
# Angkai task might be in flight), and every run starts completely
# clean.
#
# Fixtures 1 and 2 (the launch-runner flag check, and
# validate-kaiju-relay-path.sh) are STATELESS -- they write nothing
# anywhere, so they run directly against the real deployed files with
# no isolation needed at all.
#
# Run from anywhere:
#   bash angkai_guardrail_regression.sh
# ============================================================

set -uo pipefail

REAL_HOOKS_DIR="/srv/angkai/.claude/hooks"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "═══════════════════════════════════════════════════════"
echo "ANGKAI GUARDRAIL REGRESSION SUITE — $(date '+%Y-%m-%d %H:%M:%S')"
echo "═══════════════════════════════════════════════════════"

# ─────────────────────────────────────────────────────────
echo ""
echo "── FIXTURE 1:  Layer A -- launch runner blocks subagent spawn ──"
# Since  (2026-10-18) the launch command is built by the exec adapters, not by the runner itself, so the flag is checked where it now lives:
# the unboxed adapter the runner imports, and (Phase L) the installed box wrapper.
ADP=/srv/angkai/staging//exec_agent_adapters/claude_code.py
BW=/usr/local/sbin/angkai-box-run
if [ -r "$ADP" ] && grep -q '"--disallowedTools", "Task(\*)"' "$ADP"; then
    pass "claude_code adapter (used by the runner) launches with --disallowedTools Task(*)"
else
    fail "the --disallowedTools Task(*) flag is MISSING from $ADP --  Layer A mitigation has regressed"
fi
if [ -r "$BW" ]; then
    grep -q "disallowedTools 'Task(\*)'" "$BW" && pass "box wrapper launches with --disallowedTools Task(*)" || fail "box wrapper lacks --disallowedTools Task(*)"
else
    echo "  SKIP: box wrapper not installed/readable"
fi

# ─────────────────────────────────────────────────────────
echo ""
echo "── FIXTURE 2:  -- relative-path bypass stays fixed ──"
# NOT fully stateless as originally assumed -- CHECK 4 (duplicate-read
# blocker) writes a per-session read-log to disk
# (session_reads_<SESSION_ID>.log) that PERSISTS between script runs.
# A real bug in an earlier version of this script reused a STATIC
# session_id across runs, which meant a SECOND run of this suite
# correctly got blocked by CHECK 4 as a genuine duplicate read of
# AIOPS_INDEX.md from the FIRST run's leftover log -- not a
# regression at all, just this script colliding with its own past
# runs. Fixed: a fresh, unique session_id every run, plus cleaning up
# its own read-log afterward so it never leaves anything behind for a
# future run to collide with either.
REGRESSION_SESSION_ID="regression-test-legit-$(date +%s%N)"
ATTACK_RESULT=$(echo '{"session_id":"regression-test-attack","tool_name":"Write","tool_input":{"file_path":"../../etc/passwd","content":"x"},"cwd":"/srv/kaiju-vault/angkai"}' | bash "$REAL_HOOKS_DIR/validate-kaiju-relay-path.sh" 2>&1)
ATTACK_EXIT=$?
[ "$ATTACK_EXIT" = "2" ] && pass "relative-path attack string (../../etc/passwd) correctly BLOCKED (exit 2)" || fail "relative-path attack string did NOT block (exit $ATTACK_EXIT) -- REGRESSION, this is the exact bug  fixed"

LEGIT_RESULT=$(echo "{\"session_id\":\"$REGRESSION_SESSION_ID\",\"tool_name\":\"Read\",\"tool_input\":{\"path\":\"AIOPS_INDEX.md\"},\"cwd\":\"/srv/kaiju-vault\"}" | bash "$REAL_HOOKS_DIR/validate-kaiju-relay-path.sh" 2>&1)
LEGIT_EXIT=$?
[ "$LEGIT_EXIT" = "0" ] && pass "legitimate relative path still passes clean (exit 0)" || fail "legitimate relative path was WRONGLY blocked (exit $LEGIT_EXIT) -- the fix may have become too aggressive"
# Clean up this run's own read-log immediately -- never leave anything
# for a future run to collide with, same lesson as the failure above.
rm -f "$REAL_HOOKS_DIR/session_reads_${REGRESSION_SESSION_ID}.log"

# ─────────────────────────────────────────────────────────
echo ""
echo "── FIXTURES 3-5: /082/086 -- isolated sandbox, real deployed code ──"
SANDBOX=$(mktemp -d /tmp/angkai-regression-XXXXXX)
echo "  Sandbox: $SANDBOX"

# Copy the one stable, rarely-changing dependency (production_matcher.py)
# fresh from the real deployed location, so imports resolve inside the
# sandbox -- always the CURRENT real version, never a stale cached copy.
cp "$REAL_HOOKS_DIR/production_matcher.py" "$SANDBOX/"

# A scratch, throwaway production_signatures.conf naming a scratch path
# -- never touches the real shared conf file, no sudo needed.
mkdir -p "$SANDBOX/scratch-target-dir"
echo "good content v1" > "$SANDBOX/scratch-target-dir/target.txt"
cat > "$SANDBOX/production_signatures.conf" << EOF
path|$SANDBOX/scratch-target-dir|regression test scratch target
EOF

# A scratch task_released.json with a KNOWN, deterministic task_id --
# never depends on whatever a real live task happens to be at the
# moment this suite runs.
python3 -c "
import json
json.dump({'task_id': 'REGRESSION-TEST', 'status': 'released', 'target_agent': 'angkai', 'payload_ref': 'regression-suite'}, open('$SANDBOX/task_released.json', 'w'))
"

export KAI076_HOOKS_DIR="$SANDBOX"
export KAI076_SNAPSHOT_DIR="$SANDBOX/snapshots"
export KAI076_DEFAULT_CWD="$SANDBOX"
export KAI082_HOOKS_DIR="$SANDBOX"
export KAI086_BACKUP_DIR="$SANDBOX/backups"

# A scratch settings.json, seeded with the same shape real Graft
# entries take, so the "nothing else got touched" assertion means
# something -- never touches the real live settings.json.
cat > "$SANDBOX/settings.json" << 'EOF'
{"permissions": {"allow": ["Bash(graft:*)", "mcp__graft__graft_find_code"]}}
EOF
export KAI082_SETTINGS_PATH="$SANDBOX/settings.json"

TARGET="$SANDBOX/scratch-target-dir/target.txt"

echo ""
echo "  -- : baseline / match / mismatch --"
BASELINE_JSON="{\"session_id\":\"regression\",\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$TARGET\"},\"cwd\":\"$SANDBOX\"}"
echo "$BASELINE_JSON" | python3 "$REAL_HOOKS_DIR/sandbox_snapshot_gate.py" pre > /dev/null 2>&1
BASELINE_EXIT=$?
[ "$BASELINE_EXIT" = "0" ] && pass "first touch establishes baseline, ALLOWED (exit 0)" || fail "first touch was blocked (exit $BASELINE_EXIT), expected a clean baseline"

echo "$BASELINE_JSON" | python3 "$REAL_HOOKS_DIR/sandbox_snapshot_gate.py" pre > /dev/null 2>&1
MATCH_EXIT=$?
[ "$MATCH_EXIT" = "0" ] && pass "unchanged target on second touch, ALLOWED (exit 0)" || fail "unchanged target was blocked (exit $MATCH_EXIT), expected a clean match"

echo "external change" >> "$TARGET"
echo "$BASELINE_JSON" | python3 "$REAL_HOOKS_DIR/sandbox_snapshot_gate.py" pre > /dev/null 2>&1
MISMATCH_EXIT=$?
[ "$MISMATCH_EXIT" = "2" ] && pass "externally-changed target correctly BLOCKED (exit 2)" || fail "externally-changed target was NOT blocked (exit $MISMATCH_EXIT) -- REGRESSION, 's core purpose"

echo ""
echo "  -- : arm/disarm + health-check file handling --"
ARM_OUTPUT=$(python3 "$REAL_HOOKS_DIR/arm_authorized_command.py" REGRESSION-TEST "echo regression" "false" 2>&1)
echo "$ARM_OUTPUT" | grep -q "ARMED task 'REGRESSION-TEST'" && pass "arm writes the expected confirmation" || fail "arm output looked wrong: $ARM_OUTPUT"
[ -f "$SANDBOX/task_authorized_command.txt" ] && [ "$(cat "$SANDBOX/task_authorized_command.txt")" = "echo regression" ] && pass "task_authorized_command.txt written correctly" || fail "task_authorized_command.txt missing or wrong"
[ -f "$SANDBOX/task_health_check.txt" ] && [ "$(cat "$SANDBOX/task_health_check.txt")" = "false" ] && pass "task_health_check.txt written correctly (opt-in health check)" || fail "task_health_check.txt missing or wrong"
python3 -c "
import json
d = json.load(open('$SANDBOX/settings.json'))
assert 'Bash(echo regression)' in d['permissions']['allow'], 'new rule missing'
assert 'Bash(graft:*)' in d['permissions']['allow'], 'original Graft rule lost'
assert 'mcp__graft__graft_find_code' in d['permissions']['allow'], 'original Graft rule lost'
print('OK')
" > /tmp/kai082_check.out 2>&1
grep -q "^OK$" /tmp/kai082_check.out && pass "settings.json: new rule added, both original Graft entries preserved" || fail "settings.json check failed: $(cat /tmp/kai082_check.out)"

echo ""
echo "  -- : rollback fires on health-check failure --"
# Uses a SEPARATE, dedicated target from the  section above --
# reusing that target caused a real bug in an earlier version of this
# script: the  mismatch test above deliberately leaves ITS
# target's real content ahead of its recorded snapshot (that's the
# point of that test), so reusing it here meant this section's own
# first `pre` call ALSO hit that stale mismatch and silently blocked
# (exit code was discarded), meaning no fresh backup was ever saved
# for the "simulated bad fix" state -- rollback then correctly used
# the only backup that DID exist (the original baseline), which was
# still the right restore for THAT backup, just not what a test reusing
# the same target should have expected. Every step below now checks
# its own exit code explicitly so a silent block can never hide again.
TARGET2="$SANDBOX/scratch-target-dir/target2.txt"
echo "clean state v1" > "$TARGET2"
POST_JSON="{\"session_id\":\"regression\",\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$TARGET2\"},\"cwd\":\"$SANDBOX\"}"

echo "$POST_JSON" | python3 "$REAL_HOOKS_DIR/sandbox_snapshot_gate.py" pre > /dev/null 2>&1
PRE1_EXIT=$?
[ "$PRE1_EXIT" = "0" ] && pass " setup: fresh baseline for target2 established (exit 0)" || fail " setup: baseline for target2 unexpectedly blocked (exit $PRE1_EXIT) -- cannot proceed with this fixture"

if [ "$PRE1_EXIT" = "0" ]; then
    echo "simulated bad fix" > "$TARGET2"
    echo "$POST_JSON" | python3 "$REAL_HOOKS_DIR/sandbox_snapshot_gate.py" post > /dev/null 2>&1
    POST_EXIT=$?
    [ "$POST_EXIT" = "0" ] && pass " setup: re-baseline after simulated fix succeeded (exit 0)" || fail " setup: re-baseline unexpectedly failed (exit $POST_EXIT)"

    # The gate's ntfy URL is hardcoded (real alert channel), so this fixture used to send a REAL urgent
    # " AUTO-ROLLBACK FIRED" alert on every run. Point curl at a dead proxy (and blank no_proxy) for this one call only;
    # the gate then logs NOTIFY_FAILED in the sandbox log, which is asserted below.
    echo "$POST_JSON" | http_proxy=http://127.0.0.1:9 https_proxy=http://127.0.0.1:9 no_proxy= NO_PROXY= python3 "$REAL_HOOKS_DIR/kai086_auto_rollback_gate.py" > /dev/null 2>&1
    ROLLBACK_GATE_EXIT=$?
    grep -q "NOTIFY_FAILED" "$SANDBOX/kai086_auto_rollback.log" 2>/dev/null && pass " fixture did NOT send a real ntfy alert (notification was blocked, NOTIFY_FAILED logged)" || fail " fixture may have sent a REAL ntfy alert (no NOTIFY_FAILED in the sandbox log)"
    [ "$ROLLBACK_GATE_EXIT" = "0" ] && pass "rollback gate ran without error (exit 0, PostToolUse never blocks)" || fail "rollback gate itself errored unexpectedly (exit $ROLLBACK_GATE_EXIT)"

    RESTORED_CONTENT2=$(cat "$TARGET2" 2>/dev/null)
    if echo "$RESTORED_CONTENT2" | grep -q "clean state v1"; then
        pass "file content genuinely restored to its pre-call state after a failing health check"
    else
        fail "file content was NOT restored -- REGRESSION, 's core purpose. Got: $RESTORED_CONTENT2"
    fi
fi

echo ""
echo "  -- Disarm cleanup --"
DISARM_OUTPUT=$(python3 "$REAL_HOOKS_DIR/disarm_authorized_command.py" 2>&1)
echo "$DISARM_OUTPUT" | grep -q "DISARMED" && pass "disarm completes cleanly" || fail "disarm output looked wrong: $DISARM_OUTPUT"
[ ! -s "$SANDBOX/task_authorized_command.txt" ] && [ ! -s "$SANDBOX/task_health_check.txt" ] && pass "both task files cleared after disarm" || fail "one or both task files were not cleared"
python3 -c "
import json
d = json.load(open('$SANDBOX/settings.json'))
assert 'Bash(echo regression)' not in d['permissions']['allow'], 'disarmed rule still present'
assert 'Bash(graft:*)' in d['permissions']['allow'], 'Graft rule lost on disarm'
print('OK')
" > /tmp/kai082_disarm_check.out 2>&1
grep -q "^OK$" /tmp/kai082_disarm_check.out && pass "settings.json: disarmed rule removed, Graft entries survived" || fail "disarm settings check failed: $(cat /tmp/kai082_disarm_check.out)"

rm -rf "$SANDBOX" /tmp/kai082_check.out /tmp/kai082_disarm_check.out
echo ""
echo "  Sandbox cleaned up."

# ─────────────────────────────────────────────────────────
echo ""
echo "FIXTURE:  Phase L -- hooks must be executable (fail-open guard) + box escape suite"
echo "  (a hook that cannot execute exits 126 = NON-blocking = hooks silently OFF; QW-4 once stripped the x bit)"
BAD=""; N=0
for h in "$REAL_HOOKS_DIR"/*.sh /srv/angkai/hooks/*.sh; do [ -e "$h" ] || continue; N=$((N+1)); [ -x "$h" ] || BAD="$BAD $h"; done
[ "$N" -ge 6 ] || BAD="$BAD (only $N hook scripts found -- wrong host or path?)"
[ -z "$BAD" ] && pass "every hook .sh under the hooks dirs is executable" || fail "non-executable hook script(s):$BAD"
BAD=""
[ -r /srv/angkai/.claude/settings.json ] || BAD="$BAD settings.json-unreadable"
for c in $(grep -o '"command": *"[^"]*"' /srv/angkai/.claude/settings.json | sed 's/.*: *"//; s/"$//' | grep -v '^python3 \|^node'); do [ -x "$c" ] || BAD="$BAD $c"; done
[ -z "$BAD" ] && pass "every shell command registered in settings.json exists and is executable" || fail "settings.json registers non-executable hook(s):$BAD"
BAD=""
for st in task_release_pretooluse.sh validate-kaiju-relay-path.sh action_budget_pretooluse.sh command_fidelity_pretooluse.sh sandbox_proof_pretooluse.sh sandbox_snapshot_pretooluse.sh; do grep -q "$st" "$REAL_HOOKS_DIR/pretooluse_chain.sh" || BAD="$BAD $st"; [ -x "$REAL_HOOKS_DIR/$st" ] || BAD="$BAD !x:$st"; done
[ -z "$BAD" ] && pass "all 6 PreToolUse chain stages are wired in and executable" || fail "chain stage problem:$BAD"
W=/usr/local/sbin/angkai-box-run
if [ -r "$W" ]; then
    grep -q "hook not executable, refusing to start" "$W" && pass "installed box wrapper has the hook-exec preflight" || fail "installed box wrapper lacks the hook-exec preflight (reinstall: phasel_install.sh --apply)"
else
    echo "  SKIP: box wrapper not installed/readable"
fi
if [ "${RUN_BOX:-0}" = "1" ]; then
    echo "  (RUN_BOX=1: running the 29 in-box escape tests as angkai; needs sudo)"
    sudo -u angkai timeout -k 5 120 sudo -n "$W" --selftest </dev/null > /tmp/box_regress.out 2>&1
    NP=$(grep -c '^PASS' /tmp/box_regress.out); NF=$(grep -c '^FAIL' /tmp/box_regress.out)
    [ "$NP" = "29" ] && [ "$NF" = "0" ] && pass "box escape suite: 29/29 (a1-a7 allowed, b1-b20 denied, c1-c2 connectivity)" || fail "box escape suite: $NP pass / $NF fail -- see /tmp/box_regress.out"
else
    echo "  SKIP: in-box escape suite (run with RUN_BOX=1 bash angkai_guardrail_regression.sh; uses sudo)"
fi

# ─────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "RESULTS: $PASS passed, $FAIL failed"
echo "═══════════════════════════════════════════════════════"
if [ "$FAIL" -gt 0 ]; then
    echo "❌ Regression found -- do not trust the guardrail chain until this is fixed."
    exit 1
else
    echo "✅ All fixtures passed. The full guardrail chain (/076/081/082/086)"
    echo "   plus the  Layer A subagent-block flag are all behaving as"
    echo "   proven live on 2026-09-24/25."
fi
