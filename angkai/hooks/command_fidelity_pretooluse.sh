#!/bin/bash
# command_fidelity_pretooluse.sh
#  Section 13 — Command-fidelity hard-stop (companion to action_budget_pretooluse.sh)
#
# Closes the gap exposed by Incident #3 (2026-08-24): a task authorized for
# exactly one Bash call (git clone, HTTPS form) still let a SECOND, DIFFERENT
# command (git clone, SSH form) reach the approval prompt — because
# action_budget_pretooluse.sh only counts call VOLUME, not command CONTENT.
# A substituted/modified command still counts as "1 call" against the
# budget, so volume-only enforcement had nothing to block on.
#
# This script closes that gap: when a task is issued with a literal
# authorized command string (task_authorized_command.txt), any Bash tool
# call whose command text does not match that string EXACTLY is blocked
# outright — no fuzzy matching, no "close enough," no normalization beyond
# leading/trailing whitespace trimming. A single-character difference
# (https vs a git@ SSH prefix, an extra flag, a different path) is a block.
#
# Input contract confirmed live against validate-kaiju-relay-path.sh
# (2026-08-24): the harness pipes a single JSON object on stdin; tool name
# is at .tool_name, command text for Bash calls is at .tool_input.command.
# This script uses the exact same INPUT=$(cat) + jq -r extraction pattern,
# not env vars (the earlier draft guessed env vars — wrong, corrected here).
#
# Fail-open-on-omission, same rationale as action_budget_pretooluse.sh:
# an empty/missing task_authorized_command.txt means this check is not
# active for the current session — it's opt-in per task, set by whoever
# issues the task. Ordinary unscoped Angkai work is unaffected.
#
# Wiring: add to the SAME PreToolUse matcher entry as
# validate-kaiju-relay-path.sh and action_budget_pretooluse.sh. Order:
# validate-kaiju-relay-path.sh (CHECK 0-5, CHECK 2b) ->
# action_budget_pretooluse.sh (call-volume budget) ->
# command_fidelity_pretooluse.sh (this script, call-content match)
# — volume check runs first since it's cheaper and catches the more common
# failure shape; content check runs second as a narrower comparison only
# reached once the call is already within budget.
#
# Scope: this script only inspects Bash tool calls. Read/Write/Edit/
# mcp__vault__* calls remain governed entirely by
# validate-kaiju-relay-path.sh's existing allowlists (CHECK 2/2b/3/4/5) —
# this script does not touch or duplicate that logic.

set -euo pipefail

HOOKS_DIR="/srv/angkai/.claude/hooks"
AUTH_CMD_FILE="$HOOKS_DIR/task_authorized_command.txt"
LOG_FILE="$HOOKS_DIR/action_budget_audit.log"

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" >> "$LOG_FILE" 2>/dev/null || true
}

# Read and parse stdin exactly once, same convention as
# validate-kaiju-relay-path.sh (INPUT=$(cat), then jq -r extraction).
INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only relevant to Bash tool calls — pass through everything else untouched.
if [[ "$TOOL_NAME" != "Bash" ]]; then
  exit 0
fi

# No authorized-command constraint set for this task — fail open, same
# opt-in design as the budget filter.
if [[ ! -s "$AUTH_CMD_FILE" ]]; then
  log "FIDELITY_CHECK_NO_CONSTRAINT_SET pass-through tool=Bash"
  exit 0
fi

AUTHORIZED="$(cat "$AUTH_CMD_FILE")"
# Trim only leading/trailing whitespace — do NOT normalize internal
# whitespace, quoting, or argument order. Exact-match is the point.
AUTHORIZED="$(printf '%s' "$AUTHORIZED" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
PROPOSED="$(printf '%s' "$COMMAND" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"

if [[ "$PROPOSED" != "$AUTHORIZED" ]]; then
  echo "BLOCKED: command-fidelity hard-stop. This task authorized exactly this command: '$AUTHORIZED'. The proposed command was: '$PROPOSED'. These do not match exactly." >&2
  echo "Escalating to the operator -- no substituted or modified commands permitted, only the literal authorized command. If the authorized command genuinely needs to change, STOP and report to Mokaima -- do not substitute unilaterally." >&2
  log "COMMAND_FIDELITY_MISMATCH authorized='$AUTHORIZED' proposed='$PROPOSED' — BLOCKING, escalate to the operator"
  exit 2
fi

log "COMMAND_FIDELITY_MATCH command='$PROPOSED'"
exit 0
