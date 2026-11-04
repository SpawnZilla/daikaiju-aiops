#!/usr/bin/env python3
"""
 Stop Hook Validator
Runs once per Claude Code Stop event during an Angkai session.
Log-only: never blocks the turn, never prints {"decision": "block"}.
"""
import sys
import json
import re
import os

VAULT_ROOT = "/srv/kaiju-vault"
LOG_DIR = "/srv/angkai/logs"
LOG_PATH = os.path.join(LOG_DIR, "stop_hook_validator.log")


def log(lines):
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(LOG_PATH, "a") as f:
        for line in lines:
            f.write(line + "\n")


def extract_brief_path(transcript_path):
    """Read the session transcript .jsonl, find the first user message,
    extract the brief path from Kaidosho's standing handoff format:
    'Read and execute: [path]. Follow the pause points.'
    Real Claude Code transcript schema (confirmed 2026-07-29 via live
    transcript inspection, not assumed): each line's top-level object
    has "type": "user"/"assistant"/etc, and the actual role+content
    live NESTED under a "message" key -- e.g.
    {"type": "user", "message": {"role": "user", "content": "..."}}.
    The original version read msg.get("content") directly at the top
    level, which is always empty -- confirmed live via two real Stop
    hook runs, both logging "could not extract brief path" despite a
    real handoff message being present."""
    try:
        with open(transcript_path, "r") as f:
            for line in f:
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") != "user":
                    continue
                message = msg.get("message", {})
                content = message.get("content", "")
                if isinstance(content, list):
                    content = " ".join(
                        b.get("text", "") for b in content if isinstance(b, dict)
                    )
                match = re.search(r"Read and execute:\s*(\S+?)\.?\s", content)
                if match:
                    return match.group(1)
                continue
    except FileNotFoundError:
        log([f"ERROR: transcript_path not found: {transcript_path}"])
        return None
    except Exception as e:
        log([f"ERROR reading transcript: {e}"])
        return None
    return None


def resolve_vault_path(brief_path):
    """brief_path arrives with a vault/ prefix per Rule 4 - strip it
    and join to the real vault root."""
    rel = brief_path
    if rel.startswith("vault/"):
        rel = rel[len("vault/"):]
    return os.path.join(VAULT_ROOT, rel)


def check_expected_files(brief_text, ang_id):
    """RULE 17 CHECK: confirm each declared EXPECTED FILES entry actually
    exists, resolved against ITS OWN stated path -- not an assumed
    angkai/staging/<ANG-ID>/ directory."""
    findings = []
    section = re.search(
        r"^EXPECTED FILES.*?\n(.*?)\n^Do not create", brief_text,
        re.DOTALL | re.MULTILINE
    )
    if not section:
        findings.append("EXPECTED FILES section not found in brief")
        return findings

    expected_paths = []
    for m in re.finditer(r"^\s*\d+\.\s+(\S+)", section.group(1), re.MULTILINE):
        expected_paths.append(m.group(1))

    if not expected_paths:
        findings.append("EXPECTED FILES section found but no numbered entries parsed")
        return findings

    staging_dir = os.path.join(VAULT_ROOT, "angkai", "staging", ang_id)
    daikaiju_root = os.path.join(VAULT_ROOT, "")
    for path in expected_paths:
        direct = resolve_vault_path(path)
        under_daikaiju = os.path.join(daikaiju_root, path)
        fallback = os.path.join(staging_dir, os.path.basename(path))
        if os.path.isfile(direct):
            continue
        if os.path.isfile(under_daikaiju):
            continue
        if os.path.isfile(fallback):
            continue
        findings.append(
            f"expected file not found: {path} "
            f"(tried: {direct}, {under_daikaiju}, and {fallback})"
        )

    if os.path.isdir(staging_dir):
        actual = set(os.listdir(staging_dir))
        expected_basenames = {os.path.basename(p) for p in expected_paths}
        unexpected = actual - expected_basenames
        if unexpected:
            findings.append(f"unexpected files in staging: {sorted(unexpected)}")

    return findings


def check_references(brief_text):
    """RULE 19 CHECK: spot-check REFERENCES manifest paths actually
    exist in vault."""
    findings = []
    for m in re.finditer(
        r'mcp__vault__read_file with path:\s*\n?\s*"([^\"]+)"', brief_text
    ):
        ref_path = m.group(1)
        full_path = resolve_vault_path(ref_path)
        if not os.path.isfile(full_path):
            findings.append(f"REFERENCES path does not exist: {ref_path}")
    return findings


def main():
    data = json.load(sys.stdin)

    if data.get("stop_hook_active"):
        sys.exit(0)

    session_id = data.get("session_id", "unknown")
    transcript_path = data.get("transcript_path")

    findings = [f"--- validation run, session {session_id} ---"]

    if not transcript_path:
        findings.append("no transcript_path in stdin payload")
        log(findings)
        sys.exit(0)

    brief_path = extract_brief_path(transcript_path)
    if not brief_path:
        findings.append("could not extract brief path from first user message")
        log(findings)
        sys.exit(0)

    brief_full_path = resolve_vault_path(brief_path)
    if not os.path.isfile(brief_full_path):
        findings.append(f"brief file not found at resolved path: {brief_full_path}")
        log(findings)
        sys.exit(0)

    with open(brief_full_path, "r") as f:
        brief_text = f.read()

    ang_id_match = re.search(r"(ANG-\d+)", os.path.basename(brief_full_path))
    if ang_id_match:
        findings.extend(check_expected_files(brief_text, ang_id_match.group(1)))
    else:
        findings.append(f"could not determine ANG-XXX id from filename: {brief_full_path}")

    findings.extend(check_references(brief_text))

    if len(findings) == 1:
        findings.append("no issues found")

    log(findings)
    sys.exit(0)


if __name__ == "__main__":
    main()
