#!/bin/bash
# action_budget_pretooluse.sh
#  Section 13 — Action-budget hard-stop
#
# Enforces a per-task tool-call budget (max_tool_calls) set by whoever
# issues the task (Mokaima or the operator directly). Once the budget is
# exhausted, ANY further tool call is blocked — regardless of which
# tool it is. This is distinct from CHECK 2b (which blocks a specific
# tool, EnterPlanMode); this fires purely on call *volume*, closing
# the gap exposed by Incident #2 (2026-08-24), where Angkai chained
# 5+ unauthorized commands on a task explicitly scoped to exactly one.
#
# PATCHED 2026-08-24 (/ Section 13 validation v2 FAIL —
# two findings fixed together): session-scoped counter (Finding 2) +
# brief-read exemption via ANG_BRIEF_BASENAME (Finding 1). See prior
# changelog entries in version control / staging history for detail.
#
# PATCHED AGAIN 2026-08-25 (/ Section 13 validation v4 —
# EXIT-CODE BUG, more significant than Findings 1+2 combined): every
# BLOCKED path in this script used `exit 1`. Claude Code's PreToolUse
# hook protocol only treats `exit 2` as an actual block — any other
# non-zero exit code is logged as a "non-blocking status code" error
# but the tool call PROCEEDS ANYWAY. Confirmed via direct ground-truth
# check: v4's systemctl call showed BUDGET_EXCEEDED/BLOCKING in this
# hook's own audit log, yet the real command executed (verified via
# the session's .jsonl transcript tool_result block matching the operator's
# independent manual systemctl check — same PID, same args, same task
# count). This means EVERY prior "BLOCKED" claim logged by this script
# — including the git-clone Incident #3 "live-fire proven" result —
# may never have actually stopped anything; those calls may have gone
# through and only appeared blocked in the log. validate-kaiju-relay-
# path.sh's CHECK 0-4, which DO have confirmed real live-fire catch
# evidence, use `exit 2` for their BLOCKED paths — that is the actual
# mechanism difference. Every `exit 1` on a BLOCKED path in this
# script is changed to `exit 2` below. command_fidelity_pretooluse.sh
# and output_shape_stophook.py have NOT yet been audited for the same
# bug — flagged as an immediate follow-up, not assumed fixed here.
# AUDITED 2026-08-25: both are clean (see AIOPS_PENDING.md for detail).
#
# PATCHED A THIRD TIME 2026-08-25 (v5 validation run, TOOL-NAME
# MISMATCH — same bug class as ): the brief-read exemption's
# case-match list checked for `mcp__vault__read_file`, a tool name that
# does not exist in this environment. The real tool name, confirmed
# via direct grep of a live session transcript, is
# `mcp__vault__read_text_file`. Because the brief-read never matched
# IS_READ_TOOL, the exemption never fired even with ANG_BRIEF_BASENAME
# correctly set — the brief-read fell straight through and was counted
# as the session's call #1 every time, exactly as observed in every
# prior validation attempt (v2 through v5). Fixed by correcting the
# case-match list below.  CHECK 4 (the original source of this
# exemption pattern) very likely has the identical wrong tool name and
# has NOT yet been checked — flagged as a follow-up, not assumed fixed.
#
# Convention match: same fail-closed-by-default, flag-file-driven
# pattern as CHECK 2b (plan_mode_allowed.txt) — absence/zero budget
# means "no budget set," which this script treats as "no limit
# enforced by THIS check" (see NOTE below) so it never blocks
# ordinary multi-step tasks that were never given a budget.
#
# Wiring (settings.json): unchanged — same PreToolUse hook entry,
# matcher unchanged (Read|Write|Edit|Bash|mcp__vault__.*|EnterPlanMode).
#
# Task-issuing side responsibility (Mokaima / the operator):
# before launching Angkai on a budgeted task, write the integer
# budget to task_budget.txt (one integer, nothing else) AT THE
# CORRECT PATH (/srv/angkai/.claude/hooks/task_budget.txt — NOT
# /srv/angkai/task_budget.txt, a real staging mistake found and
# fixed 2026-08-25), AND ensure ANG_BRIEF_BASENAME is set at launch to
# the brief's own filename (per 's existing requirement and the
# corrected standard launch command in state-doc). Omitting
# task_budget.txt, or leaving it empty, means no budget is enforced by
# this script for that session — CHECK 2b and the other existing
# filters still apply independently. No per-session counter cleanup
# step needed — counter files are self-isolating by session_id.

set -euo pipefail

HOOKS_DIR="/srv/angkai/.claude/hooks"
BUDGET_FILE="$HOOKS_DIR/task_budget.txt"
COUNT_DIR="$HOOKS_DIR/session_counts"
LOG_FILE="$HOOKS_DIR/action_budget_audit.log"

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" >> "$LOG_FILE" 2>/dev/null || true
}

# Read the hook's stdin JSON payload once. Field names match the live
# parsing convention in validate-kaiju-relay-path.sh exactly (confirmed
# via direct source read, 2026-08-24) — do not diverge from these
# expressions without updating both hooks in lockstep.
INPUT="$(cat)"
SESSION_ID="$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)"
TOOL_NAME="$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)"
FILE_PATH="$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // empty' 2>/dev/null || true)"

if [[ -z "$SESSION_ID" ]]; then
  # Defensive fallback: if session_id is ever missing from the payload
  # (protocol change, malformed input), fail closed rather than fall
  # back to a shared/fixed counter file — that would silently
  # reintroduce Finding 2. exit 2 (not 1) — see 2026-08-25 changelog.
  log "MISSING_SESSION_ID — BLOCKING (fail-closed, cannot safely scope counter)"
  echo "BLOCKED: action-budget hook could not determine session_id from hook payload. Escalating to the operator — cannot safely enforce a per-session budget without it." >&2
  exit 2
fi

mkdir -p "$COUNT_DIR" 2>/dev/null || true
COUNT_FILE="$COUNT_DIR/task_call_count_${SESSION_ID}.txt"

# ---- BRIEF-READ EXEMPTION (Finding 1 fix, / Section 13
# validation v2, 2026-08-24) ----
# The mandatory read of the task's own brief file must not consume the
# action budget — otherwise a budget of 1 can never succeed, since the
# brief-read always arrives as call #1 and the real authorized action
# becomes call #2. Reuses the exact exemption mechanism already
# established in  CHECK 4 (same env var, same basename-match
# logic, same rationale: a known required filename, not inferred).
IS_READ_TOOL=0
case "$TOOL_NAME" in
  Read|mcp__vault__read_text_file|mcp__vault__read_file|mcp__vault__list_directory) IS_READ_TOOL=1 ;;
esac
CURRENT_BASENAME="$(basename "$FILE_PATH" 2>/dev/null || true)"
if [[ "$IS_READ_TOOL" -eq 1 ]] && [[ -n "$FILE_PATH" ]] && [[ -n "${ANG_BRIEF_BASENAME:-}" ]] && [[ "$CURRENT_BASENAME" == "$ANG_BRIEF_BASENAME" ]]; then
  log "BRIEF_READ_EXEMPT session=$SESSION_ID file=$CURRENT_BASENAME — not counted against budget"
  exit 0
fi

if [[ ! -s "$BUDGET_FILE" ]]; then
  log "NO_BUDGET_SET pass-through session=$SESSION_ID"
  exit 0
fi

BUDGET="$(tr -d '[:space:]' < "$BUDGET_FILE")"

if ! [[ "$BUDGET" =~ ^[0-9]+$ ]] || [[ "$BUDGET" -eq 0 ]]; then
  log "MALFORMED_BUDGET_FILE value='$BUDGET' session=$SESSION_ID — BLOCKING (fail-closed on bad input)"
  echo "BLOCKED: task_budget.txt is set but malformed or zero. Escalating to the operator." >&2
  exit 2
fi

CURRENT=0
if [[ -s "$COUNT_FILE" ]]; then
  CURRENT="$(tr -d '[:space:]' < "$COUNT_FILE")"
  [[ "$CURRENT" =~ ^[0-9]+$ ]] || CURRENT=0
fi

NEXT=$((CURRENT + 1))

if [[ "$NEXT" -gt "$BUDGET" ]]; then
  log "BUDGET_EXCEEDED session=$SESSION_ID budget=$BUDGET attempted_call=$NEXT — BLOCKING, escalate to the operator"
  echo "BLOCKED: action-budget hard-stop. This task was authorized for $BUDGET tool call(s); this would be call #$NEXT. Escalating to the operator — no further tool calls permitted this session without manual review." >&2
  exit 2
fi

printf '%s' "$NEXT" > "$COUNT_FILE"
log "CALL_PERMITTED session=$SESSION_ID budget=$BUDGET call=$NEXT"
exit 0
