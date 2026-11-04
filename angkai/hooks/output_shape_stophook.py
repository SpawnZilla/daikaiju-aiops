#!/usr/bin/env python3
"""
output_shape_stophook.py
 Section 13 — output-shape companion check

Runs alongside the existing Stop hook validator (hooks/stop_hook_validator.py)
as an additional check, not a replacement. Flags Angkai turns that present
an unrequested multi-option menu to the operator when the active task's budget
(task_budget.txt) indicates a tightly-scoped, single-action task.

This check CANNOT block already-generated text (the Stop hook runs after
the model has finished its turn) — its job is detection and audit-log
flagging, not prevention. Prevention for tool calls is handled by
action_budget_pretooluse.sh (PreToolUse); this catches the text-only
failure shape from Incident #2, where Angkai surfaced a 4-option
unrequested menu without necessarily making an extra tool call to do so.

Wiring: add as an additional Stop hook entry alongside
stop_hook_validator.py in settings.json. Exit code 0 always (this never
blocks the turn from ending) — it only appends to the audit log and, if
triggered, writes an ntfy-worthy flag file for the existing exceptions
alerting pattern (section 10 of the  brief).
"""

import re
import sys
import json
from datetime import datetime, timezone
from pathlib import Path

HOOKS_DIR = Path("/srv/angkai/.claude/hooks")
BUDGET_FILE = HOOKS_DIR / "task_budget.txt"
LOG_FILE = HOOKS_DIR / "action_budget_audit.log"
FLAG_FILE = HOOKS_DIR / "output_shape_flag.txt"

# Detection patterns for an unrequested menu/options presentation.
# Deliberately narrow and literal — false positives just add a log
# line for the operator to skim, false negatives silently miss real drift,
# so bias toward catching more here rather than fewer.
MENU_PATTERNS = [
    re.compile(r"^\s*\d+\.\s*\[", re.MULTILINE),          # "1. [ ]" checklist-style options
    re.compile(r"^\s*[❯>]\s*\d+\.", re.MULTILINE),         # "❯ 1." selector-style options
    re.compile(r"what would you like me to do next", re.IGNORECASE),
    re.compile(r"should i\s*:?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\bwhich (option|approach|path) would you", re.IGNORECASE),
]


def log(message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with LOG_FILE.open("a") as f:
            f.write(f"{ts} {message}\n")
    except OSError:
        pass  # never let logging failure break the hook


def has_active_budget() -> bool:
    try:
        content = BUDGET_FILE.read_text().strip()
    except FileNotFoundError:
        return False
    return content.isdigit() and int(content) > 0


def scan_for_unrequested_menu(turn_text: str) -> list:
    hits = []
    for pattern in MENU_PATTERNS:
        if pattern.search(turn_text):
            hits.append(pattern.pattern)
    return hits


def main() -> int:
    # Stop hooks receive the turn's transcript/context on stdin as JSON
    # in this project's existing convention (matches stop_hook_validator.py).
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        log("MALFORMED_STDIN_PAYLOAD — skipping this check, not blocking")
        return 0

    turn_text = payload.get("assistant_text", "") or payload.get("output", "")
    if not turn_text:
        log("NO_TURN_TEXT_FOUND — skipping")
        return 0

    if not has_active_budget():
        log("NO_ACTIVE_BUDGET — output-shape check is opt-in per budgeted task, skipping")
        return 0

    hits = scan_for_unrequested_menu(turn_text)
    if hits:
        log(f"UNREQUESTED_MENU_DETECTED patterns={hits} — flagging for the operator, not blocking (text already generated)")
        try:
            FLAG_FILE.write_text(
                f"Unrequested menu/options output detected on a budgeted task.\n"
                f"Patterns matched: {hits}\n"
                f"Review the session transcript before continuing.\n"
            )
        except OSError:
            log("FAILED_TO_WRITE_FLAG_FILE")
    else:
        log("OUTPUT_SHAPE_CLEAN")

    return 0  # Stop hooks in this project never block turn completion here


if __name__ == "__main__":
    sys.exit(main())
