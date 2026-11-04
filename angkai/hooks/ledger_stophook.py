#!/usr/bin/env python3
""" Angkai half: blocking Stop hook that requires a FACTS block.
STAGED, NOT DEPLOYED. Blocking confirmed possible in headless -p mode on the
Angkai stack by the AC5 probe (2026-10-25: both JSON decision and exit 2 work).

Opt-in: does nothing unless the flag file ledger_enabled.txt exists next to this
script (or the path in LEDGER_FLAG). With the flag on, the final assistant message
must end with a block:
  FACTS:
  F1 | kind=FILE | source=<path> | <one-line fact>
  F2 | kind=LIVE | source=<command or system> | <one-line fact>
Checks (all mechanical): block present; every line parses; fact ids unique; a FILE
source exists and, if this session's ledger already holds that source, its sha256
is unchanged; every source was named in a tool call of this session (checked
against the transcript when readable). A violation blocks the stop with the reason
naming the failing facts. Safety: at most MAX_REJECTIONS rejections per session,
any error allows the stop (fail-open), every decision is appended to
pilot_audit.jsonl in the state dir. Not covered: whether the fact is true, or
whether Qwen follows the format (that is what the pilot measures).
A reply that relied on no fact may write FACTS: then one line NONE; that is allowed and
audited as allowed_none_declared (it grounds nothing).
Env: LEDGER_FLAG, LEDGER_STATE_DIR (default /srv/angkai/ledger_state, created and
written by the Angkai user, not inside the root-owned hooks dir).
"""
import hashlib
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FLAG = os.environ.get("LEDGER_FLAG", os.path.join(HERE, "ledger_enabled.txt"))
STATE = os.environ.get("LEDGER_STATE_DIR", "/srv/angkai/ledger_state")
MAX_REJECTIONS = 2
PATH_ROOTS = ("", "/srv/vault-drive/")
HEAD_RE = re.compile(r"^\s*[*#`_ ]*FACTS[*#`_ ]*:[*#`_ ]*$", re.IGNORECASE)
START_RE = re.compile(r"^\s*F\d+\s*\|")
FACT_RE = re.compile(
    r"^\s*F(\d+)\s*\|\s*kind=(FILE|LIVE)\s*\|\s*source=(.+?)\s*\|\s*(.+?)\s*$"
)


def parse_block(msg):
    """Return the list of fact lines after the last FACTS: header, or None."""
    lines = (msg or "").split("\n")
    idx = None
    for i, ln in enumerate(lines):
        if HEAD_RE.match(ln):
            idx = i
    if idx is None:
        return None
    out = []
    for ln in lines[idx + 1:]:
        if ln.strip() == "":
            continue
        if START_RE.match(ln):
            out.append(ln.strip())
            continue
        if ln.strip().upper() == "NONE":
            out.append("NONE")
            continue
        break
    return out


def find_file(source):
    for root in PATH_ROOTS:
        p = root + source
        if os.path.isfile(p):
            return p
    return None


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_ledger(sid):
    entries = []
    try:
        with open(os.path.join(STATE, sid + ".jsonl"), "r", encoding="utf-8") as fh:
            for ln in fh:
                if ln.strip():
                    entries.append(json.loads(ln))
    except FileNotFoundError:
        pass
    return entries


def transcript_tool_text(path):
    """Concatenated text of transcript lines that look like tool calls, or None."""
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return "\n".join(ln for ln in fh if "tool_use" in ln)
    except Exception:
        return None


def validate(msg, sid, transcript_path):
    """Return (problems, facts). facts carry kind, source, text, sha256."""
    problems = []
    facts = []
    lines = parse_block(msg)
    if lines is None:
        return ["no FACTS: block at the end of your final message"], facts
    if not lines:
        return ["the FACTS: block has no fact lines"], facts
    if lines == ["NONE"]:
        return [], facts
    if "NONE" in lines:
        return ["NONE cannot be combined with fact lines"], facts
    ledger = read_ledger(sid)
    tool_text = transcript_tool_text(transcript_path)
    seen = set()
    for raw in lines:
        m = FACT_RE.match(raw)
        if not m:
            problems.append(
                "malformed line (need: F<n> | kind=FILE or LIVE | source=<...> | <fact>): " + raw[:70]
            )
            continue
        fid, kind, source, text = "F" + m.group(1), m.group(2), m.group(3), m.group(4)
        if fid in seen:
            problems.append(fid + " is used more than once")
            continue
        seen.add(fid)
        digest = None
        if kind == "FILE":
            real = find_file(source)
            if real is None:
                problems.append("%s: the FILE source does not exist: %s" % (fid, source))
                continue
            digest = sha256_of(real)
            for e in ledger:
                if e.get("kind") == "FILE" and e.get("source") == source and e.get("sha256") != digest:
                    problems.append("%s: %s changed since it was verified this session; re-read it" % (fid, source))
                    break
        if tool_text is not None:
            needle = os.path.basename(source) if kind == "FILE" else source
            if needle and needle not in tool_text:
                problems.append("%s: no tool call in this session names the source %s" % (fid, source))
                continue
        facts.append({"fact_id": fid, "kind": kind, "source": source, "text": text, "sha256": digest})
    return problems, facts


def audit(record):
    try:
        os.makedirs(STATE, exist_ok=True)
        with open(os.path.join(STATE, "pilot_audit.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
    except Exception:
        pass


def rejections_so_far(sid):
    try:
        with open(os.path.join(STATE, sid + ".rej"), "r", encoding="utf-8") as fh:
            return int((fh.read() or "0").strip())
    except Exception:
        return 0


def main():
    if not os.path.isfile(FLAG):
        return 0
    try:
        data = json.loads(sys.stdin.read())
        if not isinstance(data, dict):
            raise ValueError("stdin is not an object")
        sid = re.sub(r"[^A-Za-z0-9_.-]", "_", str(data.get("session_id") or "nosession"))
        msg = str(data.get("last_assistant_message") or "")
        problems, facts = validate(msg, sid, data.get("transcript_path"))
        rej = rejections_so_far(sid)
        rec = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "session": sid, "facts_ok": len(facts), "problems": len(problems),
            "rejections_before": rej, "stop_hook_active": data.get("stop_hook_active"),
        }
        if not problems:
            os.makedirs(STATE, exist_ok=True)
            with open(os.path.join(STATE, sid + ".jsonl"), "a", encoding="utf-8") as fh:
                for f in facts:
                    fh.write(json.dumps(f, sort_keys=True) + "\n")
            rec["outcome"] = "allowed_none_declared" if parse_block(msg) == ["NONE"] else "allowed"
            audit(rec)
            return 0
        if rej >= MAX_REJECTIONS:
            rec["outcome"] = "allowed_cap_reached"
            rec["problem_text"] = [p[:160] for p in problems[:5]]
            audit(rec)
            return 0
        os.makedirs(STATE, exist_ok=True)
        with open(os.path.join(STATE, sid + ".rej"), "w", encoding="utf-8") as fh:
            fh.write(str(rej + 1))
        rec["outcome"] = "rejected"
        rec["problem_text"] = [p[:160] for p in problems[:5]]
        audit(rec)
        reason = "FACTS ledger check failed: " + "; ".join(problems[:6]) + (
            ". Re-send your final message ending with a corrected FACTS: block."
        )
        print(json.dumps({"decision": "block", "reason": reason}))
        return 0
    except Exception as exc:
        audit({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "outcome": "allowed_on_error", "error": type(exc).__name__ + ": " + str(exc)[:160]})
        return 0


if __name__ == "__main__":
    sys.exit(main())
