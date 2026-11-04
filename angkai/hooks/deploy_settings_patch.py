#!/usr/bin/env python3
"""
deploy_settings_patch.py --  settings.json PreToolUse collapse

Collapses the 3 independent PreToolUse hook entries (validate-kaiju-
relay-path.sh, action_budget_pretooluse.sh, command_fidelity_
pretooluse.sh) into ONE entry pointing at pretooluse_chain.sh.

SAFETY DESIGN (per  v2 lesson -- never blind-mutate structural
config): this script REFUSES to write anything unless it first
confirms, by direct substring search, that all three known hook
script paths are actually present somewhere in the current PreToolUse
section. If the live file doesn't look like what we expect, it prints
what it found and exits without touching the file -- that mismatch
needs a human to look at it, not a script guessing.

Usage:
  python3 deploy_settings_patch.py --check   settings.json   # read-only, prints current PreToolUse block + verdict
  python3 deploy_settings_patch.py --apply   settings.json   # backs up, writes the collapsed version, prints a diff
"""
import json
import sys
import shutil
import datetime

REQUIRED_SUBSTRINGS = [
    "validate-kaiju-relay-path.sh",
    "action_budget_pretooluse.sh",
    "command_fidelity_pretooluse.sh",
]

WRAPPER_PATH = "/srv/angkai/.claude/hooks/pretooluse_chain.sh"


def load(path):
    with open(path, "r") as f:
        return json.load(f)


def find_pretooluse_matcher(data):
    """Return the matcher string used by the existing PreToolUse
    entries, so the new single entry keeps the same matcher rather
    than us inventing one. Returns None if PreToolUse key is missing
    or empty."""
    hooks = data.get("hooks", {})
    pretool = hooks.get("PreToolUse", [])
    if not pretool:
        return None, pretool
    # Prefer the first entry's matcher; note if entries disagree.
    matchers = {entry.get("matcher") for entry in pretool if "matcher" in entry}
    return (matchers.pop() if len(matchers) == 1 else None), pretool


def blob_contains_all_required(pretool_section):
    blob = json.dumps(pretool_section)
    missing = [s for s in REQUIRED_SUBSTRINGS if s not in blob]
    return missing


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("--check", "--apply"):
        print(__doc__)
        sys.exit(1)

    mode = sys.argv[1]
    path = sys.argv[2]

    data = load(path)
    matcher, pretool = find_pretooluse_matcher(data)

    print("=== Current PreToolUse section ===")
    print(json.dumps(pretool, indent=2))
    print()

    if not pretool:
        print("REFUSING: no PreToolUse hooks found at all in this file. "
              "Expected the 3 known Section 13 entries -- this doesn't "
              "match. Not touching anything.")
        sys.exit(2)

    missing = blob_contains_all_required(pretool)
    if missing:
        print(f"REFUSING: expected all 3 known hook scripts present, "
              f"missing: {missing}. Live file doesn't match assumed "
              f"structure -- not touching anything. A human needs to "
              f"look at this before proceeding.")
        sys.exit(2)

    if matcher is None:
        print("NOTE: existing PreToolUse entries have differing or "
              "missing 'matcher' values -- cannot safely infer a single "
              "matcher to reuse. Not touching anything; specify the "
              "correct matcher manually.")
        sys.exit(2)

    print(f"VERIFIED: all 3 known hook scripts found, consistent matcher: {matcher!r}")

    new_pretool = [
        {
            "matcher": matcher,
            "hooks": [
                {"type": "command", "command": WRAPPER_PATH}
            ],
        }
    ]

    if mode == "--check":
        print()
        print("=== Proposed replacement (not written, --check mode) ===")
        print(json.dumps(new_pretool, indent=2))
        sys.exit(0)

    # --apply mode: backup first, then write.
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_path = f"{path}.bak-kai056-{ts}"
    shutil.copy2(path, backup_path)
    print(f"Backed up original to: {backup_path}")

    data["hooks"]["PreToolUse"] = new_pretool

    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    print("Written. Re-run with --check against the same path to confirm the new shape.")


if __name__ == "__main__":
    main()
