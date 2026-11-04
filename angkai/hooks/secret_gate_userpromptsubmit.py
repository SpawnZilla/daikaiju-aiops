#!/usr/bin/env python3
"""UserPromptSubmit hook: block prompts that contain credential-shaped text.

Reads the hook JSON from stdin, scans the "prompt" field, and exits 2
(block, message to stderr) on a match. Fails OPEN on any parse/IO error,
matching the other Kaidosho hooks' fail-open-on-empty convention.

The matched text is NEVER printed or logged; only the pattern label is.
Optional audit log: set SECRET_GATE_LOG to a file path (JSONL append).
"""
import json
import os
import re
import sys
import time

PATTERNS = [
    ("api-key-sk", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("github-fine-grained", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private-key-block", re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----")),
    (
        "secret-assignment",
        re.compile(
            r"(?i)\b[A-Z0-9_]*(?:API_?KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*"
            r"\s*[=:]\s*['\"]?[A-Za-z0-9_./+=-]{16,}"
        ),
    ),
]


def scan(text):
    """Return the sorted list of pattern labels that match text."""
    return sorted({label for label, rx in PATTERNS if rx.search(text)})


def log_hit(session_id, labels):
    path = os.environ.get("SECRET_GATE_LOG")
    if not path:
        return
    try:
        entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                 "session_id": session_id, "patterns": labels}
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def main():
    try:
        data = json.load(sys.stdin)
        prompt = data.get("prompt", "")
        if not isinstance(prompt, str):
            return 0
    except (ValueError, AttributeError):
        return 0
    labels = scan(prompt)
    if not labels:
        return 0
    log_hit(data.get("session_id", ""), labels)
    sys.stderr.write(
        "secret-gate: prompt blocked, credential-shaped text detected ("
        + ", ".join(labels)
        + "). Remove or redact it and resubmit.\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
