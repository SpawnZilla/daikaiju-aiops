#!/bin/bash
# release_task.sh -- atomically releases a task to Angkai by writing
# task_released.json AND task_budget.txt together, from one set of
# values, in a single script run.
#
# WHY THIS EXISTS (2026-08-28): task_release_pretooluse.sh (checks
# task_released.json) and action_budget_pretooluse.sh (checks
# task_budget.txt) are two independent hooks, each reading its own
# file, written by two independent manual steps. Nothing ever
# guaranteed those two writes happened together -- exactly the gap
# that caused a live block today: task_released.json was written
# fresh for , but task_budget.txt still held "1" from an
# unrelated task days earlier (Aug 26), because writing it wasn't
# part of the same action. This is the second confirmed instance of
# this general shape of bug -- see Troubleshooting_Journal.md
# INCIDENT #052 (a different pair of stale manifest files, same root
# cause: no single atomic release action).
#
# This script is the canonical single write-path going forward.
# Anything that releases a task to Angkai -- Mokaima acting
# manually, or eventually the gateway-driven automated dispatch --
# should call this instead of writing either file independently.
#
# Usage: release_task.sh <task_id> <target_agent> <payload_ref> <max_tool_calls>
#
# NOTE: this file was written via MCP filesystem write, which does
# NOT preserve/set an execute bit (see INCIDENT #053 -- the same
# class of gap that broke pretooluse_chain.sh). It needs an explicit
# one-time `chmod +x` before it can be run. Flagging this here so the
# exact same bug isn't quietly reintroduced by this script itself.
#
#  FIX (2026-08-30, "Mokaima help 1.1 Full Auto"): the first
# real automated call to this script (Mokaima's review_bakaidah_output,
# confirm_auto_release=True, running as USER) failed with Permission
# denied on task_released.json -- confirmed root cause via direct
# file inspection: task_budget.txt was 664 (group-writable) but
# task_released.json was 600 (owner-only, no group bits), a plain
# permission inconsistency between the two files this script writes
# together, not the broader directory-level EACCES class from part 7.
# `cat >`/`printf >` redirection overwrites CONTENT but never touches
# an existing file's permission bits, so this could persist silently
# regardless of how many times the script ran as angkai. Fix: explicit
# chmod 664 on both files after every write, unconditionally -- makes
# the script self-healing on permissions regardless of which user
# runs it or what mode the files happened to have before, rather than
# relying on whatever mode existed at file-creation time.

set -euo pipefail

HOOKS_DIR="/srv/angkai/.claude/hooks"

# PROTECTED_REGULAR FIX (2026-09-26): the hooks dir is now sticky + group-writable
# (lockdown) and fs.protected_regular=2, so `cat >` / `printf >` (O_CREAT opens) of
# these angkai-owned files are refused by the kernel for any other user. Update in
# place WITHOUT O_CREAT; create only if missing. Keeps the files angkai-owned.
write_inplace() {
  python3 -c '
import os, sys
p = sys.argv[1]; data = sys.stdin.buffer.read()
if os.path.exists(p):
    with open(p, "r+b") as f:
        f.seek(0); f.write(data); f.truncate()
else:
    with open(p, "xb") as f:
        f.write(data)
' "$1"
}

#  CHMOD FIX (2026-10-03): since the 2026-09-26 change the two files are
# angkai-owned and this script usually runs as USER, so `chmod 664` always failed
# with 'Operation not permitted' (hidden by `|| true`) while the in-place write
# had already worked through the group-write bit. chmod only when the caller
# owns the file; otherwise check the group-write bit and say so on stderr if it
# is missing (a later in-place write by a non-owner would then fail).
ensure_mode() {
  local f="$1" mode
  if [[ -O "$f" ]]; then
    chmod 664 "$f" || echo "WARNING: chmod 664 failed on $f" >&2
  else
    mode="$(stat -c %a "$f")"
    if (( (8#$mode & 8#020) == 0 )); then
      echo "WARNING: $f is mode $mode, owned by another user and not group-writable; a later release by a non-owner may fail" >&2
    fi
  fi
}

if [[ $# -ne 4 ]]; then
  echo "Usage: release_task.sh <task_id> <target_agent> <payload_ref> <max_tool_calls>" >&2
  exit 1
fi

TASK_ID="$1"
TARGET_AGENT="$2"
PAYLOAD_REF="$3"
MAX_TOOL_CALLS="$4"

if ! [[ "$MAX_TOOL_CALLS" =~ ^[0-9]+$ ]] || [[ "$MAX_TOOL_CALLS" -eq 0 ]]; then
  echo "ERROR: max_tool_calls must be a positive integer, got '$MAX_TOOL_CALLS'" >&2
  exit 1
fi

write_inplace "$HOOKS_DIR/task_released.json" <<EOF2
{
  "task_id": "$TASK_ID",
  "status": "released",
  "target_agent": "$TARGET_AGENT",
  "payload_ref": "$PAYLOAD_REF"
}
EOF2
ensure_mode "$HOOKS_DIR/task_released.json"

printf '%s' "$MAX_TOOL_CALLS" | write_inplace "$HOOKS_DIR/task_budget.txt"
ensure_mode "$HOOKS_DIR/task_budget.txt"

echo "Released task '$TASK_ID' to '$TARGET_AGENT' (payload_ref=$PAYLOAD_REF, budget=$MAX_TOOL_CALLS)"
