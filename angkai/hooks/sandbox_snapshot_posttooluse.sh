#!/bin/bash
# sandbox_snapshot_posttooluse.sh --  companion PostToolUse hook.
# Re-baselines every gated target this call just touched, so the NEXT
# PreToolUse check in this task has a fresh snapshot to compare against.
# Never blocks -- PostToolUse hooks run after the action already happened.
# Registered independently in settings.json (alongside audit_log_posttooluse.sh),
# NOT inside pretooluse_chain.sh -- see the  deployment guide for the
# real settings.json hook-registration format, confirmed before wiring.
HOOKS_DIR="${KAI076_HOOKS_DIR:-/srv/angkai/.claude/hooks}"
/usr/bin/python3 "$HOOKS_DIR/sandbox_snapshot_gate.py" post
exit 0
