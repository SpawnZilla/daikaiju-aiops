#!/bin/bash
# task_release_pretooluse.sh --  brief section 8.2's "Angkai
# adapter": accept a task only once Mokaima has released it, never poll.
#
# Written 2026-08-27 (Daikaiju AIOps / part 7 continuation 7).
# Matches the existing PreToolUse hook family's conventions exactly
# (validate-kaiju-relay-path.sh, action_budget_pretooluse.sh): reads
# stdin JSON once via jq, exit 0 = allow, exit 2 = block with stderr.
# Registered as a new stage in pretooluse_chain.sh's HOOKS array, not
# a settings.json change -- pretooluse_chain.sh is the sole registered
# PreToolUse hook, wrapping a chain of individual stage scripts.
#
# DESIGN: "never poll" means this hook is purely reactive (checked once
# per tool call, like every other PreToolUse hook) -- it does not watch
# a queue or loop. "Accept a task only once released" means the FIRST
# tool call of a session must find a valid, matching, not-yet-consumed
# release marker or the whole session is blocked from its very first
# action. Session-scoped like CHECK 4 (session_reads_${SESSION_ID}.log)
# so every call after the first passes cheaply via a flag file, rather
# than re-parsing/re-validating the release marker on every single call.
#
# RELEASE MARKER FILE: task_released.json, written directly by Mokaima
# (real filesystem write access into /srv/angkai confirmed this
# session) once kaiju_mosura_a2a_adapter.py's review_bakaidah_output
# returns route=="release_to_angkai" (or after a human check-in
# approves a hold_for_checkin task) -- Mokaima's MCP server does NOT
# write this file itself; a human/Mokaima-session action does, keeping
# the actual release a distinct, auditable, deliberate step rather
# than something the review call does implicitly.
#
# TESTED 2026-08-27: 8/8 logic-test cases pass in Mokaima's sandbox
# (missing release file, missing ANG_BRIEF_BASENAME, valid matching
# release consumes + allows, 2nd call same session passes cheaply via
# flag even after release file is gone, new session after consumption
# blocks, mismatched brief basename blocks, wrong target_agent blocks,
# malformed release JSON blocks). NOT yet live-fire tested against a
# real Angkai session -- see the deployment guide for that step.

set -euo pipefail

HOOKS_DIR="/srv/angkai/.claude/hooks"
RELEASE_FILE="$HOOKS_DIR/task_released.json"

INPUT="$(cat)"

# 2026-11-25 external audit fix: a missing or malformed
# session_id used to fall back to "default", so every session without an
# id shared ONE authorization flag. Refuse anything that is not a real id.
SESSION_ID=$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || echo "")
if [[ ! "$SESSION_ID" =~ ^[A-Za-z0-9][A-Za-z0-9-]{7,127}$ || "$SESSION_ID" == "default" ]]; then
  echo "BLOCKED: this tool call carries no valid session_id ('$SESSION_ID')." >&2
  echo "A release can only authorize one identified session -- stop and" >&2
  echo "report this to the operator." >&2
  exit 2
fi
AUTH_FLAG="$HOOKS_DIR/session_release_authorized_${SESSION_ID}.flag"
FLAG_TTL="${ANG_RELEASE_FLAG_TTL:-21600}"   # seconds a session stays authorized (6 h)

if [[ -z "${ANG_BRIEF_BASENAME:-}" ]]; then
  echo "BLOCKED: ANG_BRIEF_BASENAME is not set for this session." >&2
  echo "The launch command must set ANG_BRIEF_BASENAME to the exact" >&2
  echo "brief filename this session is executing -- this is mandatory" >&2
  echo "for every Angkai session, not just this check." >&2
  exit 2
fi

# Already validated this session -- cheap path, but the flag must name
# the same brief, carry the consumed task_id, and be younger than FLAG_TTL.
# An empty or old-format flag is not accepted.
if [[ -f "$AUTH_FLAG" ]]; then
  F_BRIEF=$(jq -r '.brief // empty' "$AUTH_FLAG" 2>/dev/null || echo "")
  F_TASK=$(jq -r '.task_id // empty' "$AUTH_FLAG" 2>/dev/null || echo "")
  F_TS=$(jq -r '.authorized_at // empty' "$AUTH_FLAG" 2>/dev/null || echo "")
  NOW=$(date +%s)
  if [[ -n "$F_BRIEF" && "$F_BRIEF" == "$ANG_BRIEF_BASENAME" && -n "$F_TASK" \
        && "$F_TS" =~ ^[0-9]+$ && "$NOW" -ge "$F_TS" && $((NOW - F_TS)) -le "$FLAG_TTL" ]]; then
    exit 0
  fi
  rm -f "$AUTH_FLAG" 2>/dev/null || true
  echo "BLOCKED: this session's authorization flag is expired, old-format," >&2
  echo "or does not match this session's brief. A new release is needed" >&2
  echo "-- stop and report this to the operator." >&2
  exit 2
fi

# ---- First tool call of this session: full validation ----

if [[ ! -s "$RELEASE_FILE" ]]; then
  echo "BLOCKED: no task has been released to you by Mokaima yet." >&2
  echo "Angkai never polls for work -- a task must be explicitly" >&2
  echo "released before any tool use is authorized. Do not proceed;" >&2
  echo "if you believe a task should have been released, stop and" >&2
  echo "report this to the operator rather than guessing or retrying." >&2
  exit 2
fi

STATUS=$(jq -r '.status // empty' "$RELEASE_FILE" 2>/dev/null || echo "")
TARGET_AGENT=$(jq -r '.target_agent // empty' "$RELEASE_FILE" 2>/dev/null || echo "")
PAYLOAD_REF=$(jq -r '.payload_ref // empty' "$RELEASE_FILE" 2>/dev/null || echo "")
TASK_ID=$(jq -r '.task_id // empty' "$RELEASE_FILE" 2>/dev/null || echo "")

if [[ -z "$STATUS" ]]; then
  echo "BLOCKED: $RELEASE_FILE exists but is not valid JSON, or is" >&2
  echo "missing a status field. Refusing to guess its intent -- stop" >&2
  echo "and report this to the operator/Mokaima." >&2
  exit 2
fi

if [[ "$STATUS" != "released" ]]; then
  echo "BLOCKED: the task release marker's status is '$STATUS', not" >&2
  echo "'released' -- it was likely already consumed by a prior" >&2
  echo "session, or was never actually released. Do not proceed." >&2
  exit 2
fi

if [[ "$TARGET_AGENT" != "angkai" ]]; then
  echo "BLOCKED: the released task's target_agent is '$TARGET_AGENT'," >&2
  echo "not 'angkai' -- this release was not meant for you." >&2
  exit 2
fi

if [[ -z "$TASK_ID" ]]; then
  echo "BLOCKED: the release marker has no task_id -- refusing to authorize" >&2
  echo "a session that cannot be tied to one task." >&2
  exit 2
fi

RELEASE_BASENAME=$(basename "$PAYLOAD_REF" 2>/dev/null || echo "")
if [[ "$RELEASE_BASENAME" != "$ANG_BRIEF_BASENAME" ]]; then
  echo "BLOCKED: the released task's payload_ref ('$PAYLOAD_REF') does" >&2
  echo "not match this session's brief (ANG_BRIEF_BASENAME='$ANG_BRIEF_BASENAME')." >&2
  echo "A release exists, but not for the brief this session is" >&2
  echo "actually running -- do not proceed on a mismatched task." >&2
  exit 2
fi

# Valid, matching, not-yet-consumed release found -- consume it (mark
# status "consumed" so it can't silently re-authorize a later session)
# and drop the session-scoped flag so every later call this session
# passes cheaply.
TMP_FILE="$(mktemp)"
jq '.status = "consumed"' "$RELEASE_FILE" > "$TMP_FILE" && mv "$TMP_FILE" "$RELEASE_FILE"
chmod 664 "$RELEASE_FILE" || true
jq -n --arg b "$ANG_BRIEF_BASENAME" --arg t "$TASK_ID" --argjson ts "$(date +%s)" \
  '{brief:$b, task_id:$t, authorized_at:$ts}' > "$AUTH_FLAG"

exit 0
