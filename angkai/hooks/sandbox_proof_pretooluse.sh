#!/bin/bash
# sandbox_proof_pretooluse.sh --  STAGE 5 of pretooluse_chain.sh.
# Thin shim: all logic lives in sandbox_proof_gate.py (which fails closed).
# If the python file is missing python exits 2 and the chain blocks -- the
# same fail-closed behavior the chain already has for a missing hook.
HOOKS_DIR="${KAI064_HOOKS_DIR:-/srv/angkai/.claude/hooks}"
exec /usr/bin/python3 "$HOOKS_DIR/sandbox_proof_gate.py"
