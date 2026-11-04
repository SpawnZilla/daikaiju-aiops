#!/usr/bin/env python3
"""
false_block_detector.py -- , LIVE, v3

Stop hook: detects INCIDENT #064's confirmed pattern -- Angkai
confidently claiming a tool call was blocked without ever attempting
it. Runs as the angkai user (same as every other Angkai hook), so it
never needs cross-user access to anything: reads its own session's
own transcript and its own audit logs, all angkai-owned.

Fail-open by construction (matches 's priority): any error in
this script's own logic must never block or delay Angkai's turn.
Always exits 0.

REVISED 2026-09-08, mid-: the original design's
premise (Mokaima's filesystem MCP is categorically EACCES'd on all of
/srv/angkai/, mode 750) was WRONG and never actually re-tested --
live testing during the  baseline check showed Mokaima CAN read
this directory tree, settings.json, and both audit logs directly
(group-readable, 664/775). The ONLY genuine EACCES confirmed live is
on individual session transcript files (.claude/projects/*/*.jsonl,
mode 600, angkai-owned) -- a narrower problem than originally designed
around. Two concrete corrections made below as a direct result:
  1. AUDIT_LOG_PATHS corrected to the REAL location and REAL format,
     confirmed via direct live read 2026-09-08 (previously an
     unverified guess, flagged honestly as Follow-up 1 at design time
     -- that flag turned out to matter, the guessed field names
     CALL_PERMITTED/FIDELITY_CHECK do not exist anywhere in the real
     logs; the real format is "CHAIN_PASS stage=N name=X" /
     "CHAIN_ALL_PASS stages=N").
  2. ntfy alerting REMOVED entirely (was Follow-up 2's live-alert
     path). No longer needed: since Mokaima can read a plain angkai-
     owned log file directly in this directory (already proven live
     against the two existing audit logs, which are exactly this
     shape -- 664, angkai:angkai), there's no permission wall left to
     route around with a push notification. Simpler, one fewer
     external dependency (the old design's NTFY_URL topic/port were
     themselves unverified guesses). Mokaima can now just read
     false_block_detector.log directly during any session.

REVISED AGAIN 2026-09-08, first real deployment test: a live scratch
session (no real release marker set up) produced a GENUINE, correctly
reported block -- Angkai telling the truth every time it said the
task release marker was "consumed." The real audit log confirmed this
directly with a THIRD line shape not previously seen: "CHAIN_BLOCKED
stage=N name=X exit=N -- short-circuiting, later stages SKIPPED" --
a correctly-logged genuine block, sitting right next to CHAIN_PASS/
CHAIN_ALL_PASS as an equally real signal that a real attempt occurred
and was evaluated. has_recent_audit_entry() below only recognized
CHAIN_PASS/CHAIN_ALL_PASS as "a real attempt happened" -- meaning a
genuine, correctly-reported block would have looked IDENTICAL to a
false one under the old logic (no matching entry found -> treated as
suspected false, backwards from intended). Fixed: CHAIN_BLOCKED now
recognized as evidence too -- ANY of the three real log shapes (PASS/
ALL_PASS/BLOCKED) means a real attempt happened and was evaluated,
false or not; a suspected false block is specifically the ABSENCE of
any of these three, not just the absence of a PASS. (Separately
confirmed via a direct manual invocation against the real transcript
from this test session: the script itself executes correctly, no
crash, exit 0 -- it correctly did not flag this particular case
because the transcript's very LAST message didn't happen to contain
any of the exact BLOCK_CLAIM_PATTERNS phrases, even though an earlier
turn in the same session did. A real, acknowledged phrase-coverage
limitation, not a bug -- tracked under Follow-up 2, not fixed here.)
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---- CONFIRMED LIVE 2026-09-08 (direct read during  baseline
# check, plus a real first deployment test) -- these are the real
# paths and the real line formats, not a guess. Real sample lines:
#   2026-09-06T06:01:48Z CHAIN_PASS stage=4 name=command_fidelity_pretooluse.sh
#   2026-09-06T06:01:48Z CHAIN_ALL_PASS stages=4
#   2026-09-08T03:01:29Z CHAIN_BLOCKED stage=1 name=task_release_pretooluse.sh exit=2 -- short-circuiting, later stages SKIPPED
# action_budget_audit.log's real lines seen include a distinct shape
# ("NO_TURN_TEXT_FOUND -- skipping") -- treated as informational, not
# matched below. All three of PASS/ALL_PASS/BLOCKED mean a real
# attempt was made and evaluated -- BLOCKED is not a lesser signal
# than PASS, it's a genuine, correctly-reported block and must count
# as evidence too (see REVISED AGAIN note above -- a real bug until
# this was added).
AUDIT_LOG_PATHS = [
    Path("/srv/angkai/.claude/hooks/pretooluse_chain_audit.log"),
    Path("/srv/angkai/.claude/hooks/action_budget_audit.log"),
]
AUDIT_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\s+CHAIN_(?:ALL_PASS|PASS|BLOCKED)\b"
)
AUDIT_WINDOW_SECONDS = 10  # tune once real false-positive rate is known

# This hook's own output -- plain file, no push notification needed.
# Written to the SAME directory the real audit logs already live in,
# so it inherits the same access shape (angkai-owned, group-readable)
# rather than a new, unverified location.
DETECTOR_LOG_PATH = Path("/srv/angkai/.claude/hooks/false_block_detector.log")

# Phrases suggesting a claimed block. Deliberately NOT the sole
# trigger -- see the has_tool_use check below. A correctly-attempted-
# and-genuinely-blocked call will also use these words, so phrase
# match alone is not evidence of anything by itself.
BLOCK_CLAIM_PATTERNS = [
    r"\bblocked\b",
    r"\bnot permitted\b",
    r"\bcannot execute\b",
    r"\bdenied\b",
    r"\bconsumed\b",
    r"\bcan't run that\b",
]


def log_finding(msg: str) -> None:
    """Plain angkai-owned log line, in the same directory as the real
    audit logs. Mokaima can read this directly (confirmed live
    2026-09-08 against pretooluse_chain_audit.log/action_budget_
    audit.log, same directory, same ownership shape) -- no push
    notification needed, this file IS the alert channel now."""
    try:
        with DETECTOR_LOG_PATH.open("a") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ')} SUSPECTED_FALSE_BLOCK {msg}\n")
    except Exception:
        pass  # fail-open: a broken local log must never stop anything


def has_recent_audit_entry(window_seconds: int) -> bool:
    """True if either audit log has a real CHAIN_PASS/CHAIN_ALL_PASS/
    CHAIN_BLOCKED line within the trailing window -- confirmed real
    formats, real timestamp parsing. CHAIN_BLOCKED added 2026-09-08
    after a real test showed it was missing -- a genuine, correctly-
    reported block must count as "a real attempt happened," the same
    as a pass, or a truthful block looks identical to a false one."""
    now = datetime.now(timezone.utc)
    for path in AUDIT_LOG_PATHS:
        try:
            if not path.exists():
                continue
            with path.open() as f:
                lines = f.readlines()[-20:]  # tail only, cheap
            for line in lines:
                m = AUDIT_LINE_RE.match(line)
                if not m:
                    continue
                try:
                    ts = datetime.strptime(m.group("ts"), "%Y-%m-%dT%H:%M:%SZ").replace(
                        tzinfo=timezone.utc
                    )
                except ValueError:
                    continue
                if (now - ts).total_seconds() <= window_seconds:
                    return True
        except Exception:
            continue
    return False


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # fail-open: can't even parse the hook payload

    session_id = payload.get("session_id", "unknown")
    transcript_path = payload.get("transcript_path")
    if not transcript_path:
        return 0

    try:
        with open(transcript_path) as f:
            lines = f.readlines()
    except Exception:
        return 0  # fail-open: same-user read failing is unexpected but non-fatal

    if not lines:
        return 0

    try:
        last_event = json.loads(lines[-1])
    except Exception:
        return 0

    message = last_event.get("message", {})
    content_blocks = message.get("content", [])
    if not isinstance(content_blocks, list):
        return 0

    text_parts = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
    has_tool_use = any(b.get("type") == "tool_use" for b in content_blocks)
    full_text = " ".join(text_parts)

    if has_tool_use:
        return 0  # a real attempt happened -- not #064's shape, regardless of wording

    claims_block = any(re.search(p, full_text, re.IGNORECASE) for p in BLOCK_CLAIM_PATTERNS)
    if not claims_block:
        return 0

    if has_recent_audit_entry(AUDIT_WINDOW_SECONDS):
        return 0  # a real attempt WAS logged near this time -- not a false claim

    log_finding(f"session={session_id} excerpt={full_text[:150]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
