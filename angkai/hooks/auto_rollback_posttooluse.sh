#!/bin/bash
# auto_rollback_posttooluse.sh --  companion PostToolUse
# hook. Thin shim; all logic lives in auto_rollback_gate.py. Never
# blocks -- PostToolUse hooks run after the action already happened.
# Registered independently in settings.json's PostToolUse array, AFTER
# the sandbox_snapshot_posttooluse.sh entry (this hook restores
# from a backup taken by the earlier PRE hook, so it depends on that
# mechanism already being in place -- see the  deployment guide).
HOOKS_DIR="${ANGKAI_SNAPSHOT_HOOKS_DIR:-/srv/angkai/.claude/hooks}"
/usr/bin/python3 "$HOOKS_DIR/auto_rollback_gate.py"
exit 0
