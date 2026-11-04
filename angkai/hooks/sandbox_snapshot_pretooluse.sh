#!/bin/bash
# sandbox_snapshot_pretooluse.sh -- , a SEPARATE sibling stage to
# 's sandbox_proof_pretooluse.sh in pretooluse_chain.sh (per the operator's
# 2026-09-19 decision, and the 2026-09-20 design finalization: event-
# adjacency snapshot check, not a time-window gate; wired synchronously
# into this same chain, not the pi-node watchdog).
# Thin shim: all logic lives in sandbox_snapshot_gate.py (fails closed).
HOOKS_DIR="${KAI076_HOOKS_DIR:-/srv/angkai/.claude/hooks}"
exec /usr/bin/python3 "$HOOKS_DIR/sandbox_snapshot_gate.py" pre
