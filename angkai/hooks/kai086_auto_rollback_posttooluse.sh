#!/bin/bash
# kai086_auto_rollback_posttooluse.sh --  companion PostToolUse
# hook. Thin shim; all logic lives in kai086_auto_rollback_gate.py. Never
# blocks -- PostToolUse hooks run after the action already happened.
# Registered independently in settings.json's PostToolUse array, AFTER
# 's own sandbox_snapshot_posttooluse.sh entry (this hook restores
# from a backup taken by 's PRE hook, so it depends on that
# mechanism already being in place -- see the  deployment guide).
HOOKS_DIR="${KAI076_HOOKS_DIR:-/srv/angkai/.claude/hooks}"
/usr/bin/python3 "$HOOKS_DIR/kai086_auto_rollback_gate.py"
exit 0
