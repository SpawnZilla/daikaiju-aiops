#!/bin/bash
# pretooluse_chain.sh
#  — PreToolUse hook coordination wrapper (fixes INCIDENT #049)
set -euo pipefail

HOOKS_DIR="/srv/angkai/.claude/hooks"
LOG_FILE="$HOOKS_DIR/pretooluse_chain_audit.log"

HOOKS=(
  "$HOOKS_DIR/task_release_pretooluse.sh"
  "$HOOKS_DIR/validate-kaiju-relay-path.sh"
  "$HOOKS_DIR/action_budget_pretooluse.sh"
  "$HOOKS_DIR/command_fidelity_pretooluse.sh"
  "$HOOKS_DIR/sandbox_proof_pretooluse.sh"
  "$HOOKS_DIR/sandbox_snapshot_pretooluse.sh"
)

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" >> "$LOG_FILE" 2>/dev/null || true
}

INPUT="$(cat)"

STAGE_NUM=0
for HOOK in "${HOOKS[@]}"; do
  STAGE_NUM=$((STAGE_NUM + 1))
  STAGE_NAME="$(basename "$HOOK")"

  if [[ ! -e "$HOOK" ]]; then
    log "CHAIN_ERROR stage=$STAGE_NUM name=$STAGE_NAME MISSING -- fail-closed"
    echo "BLOCKED: PreToolUse chain stage $STAGE_NUM ($STAGE_NAME) is missing from disk. Escalating to the operator -- refusing to silently skip a safety stage." >&2
    exit 2
  fi
  if [[ ! -x "$HOOK" ]]; then
    log "CHAIN_ERROR stage=$STAGE_NUM name=$STAGE_NAME NOT_EXECUTABLE -- fail-closed"
    echo "BLOCKED: PreToolUse chain stage $STAGE_NUM ($STAGE_NAME) is not executable. Escalating to the operator -- refusing to silently skip a safety stage." >&2
    exit 2
  fi

  STAGE_STDERR="$(mktemp)"
  set +e
  printf '%s' "$INPUT" | "$HOOK" >/dev/null 2>"$STAGE_STDERR"
  STAGE_EXIT=$?
  set -e

  if [[ "$STAGE_EXIT" -eq 0 ]]; then
    log "CHAIN_PASS stage=$STAGE_NUM name=$STAGE_NAME"
    rm -f "$STAGE_STDERR"
    continue
  fi

  log "CHAIN_BLOCKED stage=$STAGE_NUM name=$STAGE_NAME exit=$STAGE_EXIT -- short-circuiting, later stages SKIPPED"
  cat "$STAGE_STDERR" >&2
  rm -f "$STAGE_STDERR"
  exit "$STAGE_EXIT"
done

log "CHAIN_ALL_PASS stages=$STAGE_NUM"
exit 0
