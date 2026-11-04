#!/usr/bin/env python3
"""
apply_edit_brief.py -- deterministic executor for a Kaiju Relay EDIT brief
(2026-09-20). Stdlib only. NO language model: it applies the brief's
machine-readable EDITS_JSON block by exact string replacement, so nobody has
to transcribe old/new text by hand.

  python3 apply_edit_brief.py <brief.md>                  CHECK only (default): prints what it would do
  python3 apply_edit_brief.py <brief.md> --apply           apply, after a backup
  options: --target PATH   override the target file named in the brief
           --allow-drift   apply even if the file's sha256 differs from the one
                           recorded when the brief was drafted (every old_text
                           must STILL occur exactly once)

It REFUSES (exit 1, nothing written) when: the brief has no EDITS_JSON block;
the file changed since drafting (unless --allow-drift); any old_text occurs 0
or more than 1 times; two edits overlap; an edit is a no-op or empty.
On --apply it writes <target>.bak-edit-<timestamp> first, replaces the file
atomically (temp file in the same directory, mode preserved), prints a unified
diff, and re-reads the result to confirm every new_text is present.
The operator runs this (the target may be owned by another user: use sudo -u).
"""

import argparse
import difflib
import hashlib
import json
import os
import re
import sys
import tempfile
import time

_BLOCK = re.compile(r"EDITS_JSON[^\n]*\n```json\n(.*?)\n```", re.DOTALL)


class EditError(Exception):
    pass


def extract_edits_json(markdown_text):
    match = _BLOCK.search(markdown_text)
    if not match:
        raise EditError("no EDITS_JSON block found in the brief")
    try:
        payload = json.loads(match.group(1))
    except ValueError as exc:
        raise EditError("EDITS_JSON is not valid JSON: %s" % exc)
    if not isinstance(payload, dict) or not isinstance(payload.get("edits"), list) or not payload["edits"]:
        raise EditError("EDITS_JSON has no non-empty 'edits' list")
    if not isinstance(payload.get("target_file"), str) or not payload["target_file"]:
        raise EditError("EDITS_JSON has no target_file")
    return payload


def plan_edits(target_text, edits):
    """Validate every edit against the ORIGINAL text; return the new text.
    Raises EditError describing the first problem found."""
    spans = []
    for i, edit in enumerate(edits, 1):
        old, new = edit.get("old_text"), edit.get("new_text")
        if not isinstance(old, str) or not isinstance(new, str):
            raise EditError("edit %d: old_text/new_text must be strings" % i)
        if not old.strip():
            raise EditError("edit %d: old_text is empty" % i)
        if old == new:
            raise EditError("edit %d: old_text equals new_text (no-op)" % i)
        count = target_text.count(old)
        if count != 1:
            raise EditError("edit %d: old_text occurs %d times (need exactly 1)" % (i, count))
        start = target_text.index(old)
        spans.append((start, start + len(old), new, i))
    spans.sort()
    for left, right in zip(spans, spans[1:]):
        if left[1] > right[0]:
            raise EditError("edits %d and %d overlap" % (left[3], right[3]))
    out, cursor = [], 0
    for start, end, new, _ in spans:
        out.append(target_text[cursor:start])
        out.append(new)
        cursor = end
    out.append(target_text[cursor:])
    return "".join(out)


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Apply a Kaiju Relay EDIT brief deterministically.")
    ap.add_argument("brief")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--target")
    ap.add_argument("--allow-drift", action="store_true")
    args = ap.parse_args(argv)

    try:
        with open(args.brief, "r", encoding="utf-8") as fh:
            payload = extract_edits_json(fh.read())
        target = args.target or payload["target_file"]
        with open(target, "r", encoding="utf-8") as fh:
            original = fh.read()
        base = payload.get("base_sha256")
        if base and sha256_text(original) != base and not args.allow_drift:
            raise EditError("the target changed since the brief was drafted (sha256 differs); "
                            "re-draft the brief, or pass --allow-drift to apply anyway")
        updated = plan_edits(original, payload["edits"])
    except (EditError, OSError) as exc:
        print("REFUSED: %s" % exc)
        return 1

    diff = "".join(difflib.unified_diff(original.splitlines(True), updated.splitlines(True),
                                        "a/" + os.path.basename(target), "b/" + os.path.basename(target)))
    print(diff if diff else "(no textual change)")
    if not args.apply:
        print("CHECK OK: %d edit(s) would apply cleanly to %s. Re-run with --apply to write." % (len(payload["edits"]), target))
        return 0

    backup = "%s.bak-edit-%s" % (target, time.strftime("%Y%m%d-%H%M%S"))
    with open(backup, "w", encoding="utf-8") as fh:
        fh.write(original)
    directory = os.path.dirname(os.path.abspath(target))
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".apply_edit_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(updated)
        os.chmod(tmp, os.stat(target).st_mode & 0o7777)
        os.replace(tmp, target)
    except OSError as exc:
        if os.path.exists(tmp):
            os.remove(tmp)
        print("FAILED while writing (original untouched, backup at %s): %s" % (backup, exc))
        return 1
    with open(target, "r", encoding="utf-8") as fh:
        check = fh.read()
    missing = [i for i, e in enumerate(payload["edits"], 1) if e["new_text"] not in check]
    if missing or check != updated:
        print("VERIFY FAILED after writing (edits missing: %s). Backup: %s" % (missing, backup))
        return 1
    print("APPLIED %d edit(s) to %s. Backup: %s. New sha256: %s" % (len(payload["edits"]), target, backup, sha256_text(check)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
