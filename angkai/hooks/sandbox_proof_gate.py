#!/usr/bin/env python3
"""
sandbox_proof_gate.py -- the decision logic behind sandbox_proof_pretooluse.sh
(, 2026-09-19). Stdlib only.

Chain contract (same as the other hooks): one JSON object on stdin
(tool_name, tool_input, cwd, session_id ...); exit 0 = allow; exit 2 = block
with the reason on stderr. Registered as STAGE 5 of pretooluse_chain.sh.

WHAT IT BLOCKS: a call that touches a production signature
(production_signatures.conf: paths, systemd units, ports) -- via Bash OR via
a write tool (Write/Edit, mcp vault write_file/create_directory, ...) --
unless sandbox_proof_<task_id>.json exists in the hooks dir with
result == "pass" for the CURRENT task (task id from task_released.json).
A denypath signature is always blocked; no proof unlocks it.

FAIL-CLOSED: unparseable hook input, a missing/invalid config, or any
internal error blocks the call (like the chain itself does for a missing
hook). Calls to tools that can never write (reads, listings) skip the config
entirely, so a missing or invalid CONFIG only blocks relevant calls. A
missing production_matcher.py blocks EVERY call (it fails at import, before
the tool is classified) -- the same stance as the chain's missing-hook rule.

KNOWN LIMIT ( design, not solved here): the proof file is written by
the same agent the gate constrains, so it stops accidents and substituted
commands, not a deliberately forging agent. See  long-term direction.

PROOF STORE (hardening 2026-09-19): proofs are read from PROOF_DIR
(/srv/angkai/sandbox_proofs), NOT from the hooks dir the agent can write.
The gate refuses to trust a proof unless the store is a real directory (not a
symlink) owned by someone other than the agent user and with no group/other
write, and the proof is a regular file (not a symlink) likewise owned by
someone else with no group/other write. A mis-set permission therefore fails
CLOSED instead of silently reopening the hole. STILL a known limit: the agent
owns the hooks dir, so it could edit the gate itself, and its docker-group
membership is root-equivalent -- this raises the bar from "one stray write" to
"deliberate tampering"; real protection is  layer A.

TEST-ONLY ENV OVERRIDES: KAI064_HOOKS_DIR, KAI064_PROOF_DIR, KAI064_DEFAULT_CWD,
KAI064_TEST_AGENT_UID (the agent cannot set the environment of its own hook).
"""

import datetime
import json
import os
import re
import stat
import sys

sys.dont_write_bytecode = True

HOOKS_DIR = os.environ.get("KAI064_HOOKS_DIR", "/srv/angkai/.claude/hooks")
PROOF_DIR = os.environ.get("KAI064_PROOF_DIR", "/srv/angkai/sandbox_proofs")
DEFAULT_CWD = os.environ.get("KAI064_DEFAULT_CWD", "/srv/angkai")
sys.path.insert(0, HOOKS_DIR)

_SAFE_TASK_ID = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


def _agent_uid():
    try:
        return int(os.environ["KAI064_TEST_AGENT_UID"])
    except (KeyError, ValueError):
        return os.getuid()


def _log(line):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with open(os.path.join(HOOKS_DIR, "sandbox_proof_audit.log"), "a", encoding="utf-8") as fh:
            fh.write("%s %s\n" % (stamp, line))
    except OSError:
        pass


def _block(reason, log_line):
    _log("SANDBOX_GATE_BLOCKED " + log_line)
    sys.stderr.write("BLOCKED: sandbox-proof gate. " + reason + "\n")
    sys.stderr.write("Prove the change in the -sandbox twin first. A proof file may only come from a "
                     "real sandbox run -- do NOT create or edit it yourself. STOP and report to "
                     "Mokaima/the operator.\n")
    sys.exit(2)


def _current_task_id():
    try:
        with open(os.path.join(HOOKS_DIR, "task_released.json"), "r", encoding="utf-8") as fh:
            value = json.load(fh).get("task_id", "")
    except (OSError, ValueError, AttributeError):
        return ""
    return value if isinstance(value, str) else ""


def _check_proof(task_id):
    """Returns (ok, reason for the agent, log tag). The reason NEVER names the
    proof file's path -- the agent can write that file, so we do not tell it
    where to put one. The log tag records WHY (no-task / no-proof /
    proof-invalid / proof-fail / proof-mismatch) for the audit trail."""
    if not task_id or not _SAFE_TASK_ID.match(task_id) or ".." in task_id:
        return False, "no valid active task id in task_released.json", "no-task"
    try:
        store = os.lstat(PROOF_DIR)
    except OSError:
        return False, "no sandbox proof exists for task '%s'" % task_id, "no-proof"
    if not stat.S_ISDIR(store.st_mode) or store.st_uid == _agent_uid() or store.st_mode & 0o022:
        return False, "the sandbox proof store is not trusted (wrong owner or writable by the agent)", "proof-store-unsafe"
    path = os.path.join(PROOF_DIR, "sandbox_proof_%s.json" % task_id)
    try:
        entry = os.lstat(path)
    except OSError:
        return False, "no sandbox proof exists for task '%s'" % task_id, "no-proof"
    if not stat.S_ISREG(entry.st_mode) or entry.st_uid == _agent_uid() or entry.st_mode & 0o022:
        return False, "the proof for task '%s' is not trusted (not a plain file, or owned or writable by the agent)" % task_id, "proof-untrusted"
    try:
        with open(path, "r", encoding="utf-8") as fh:
            proof = json.load(fh)
    except (OSError, ValueError):
        return False, "the proof for task '%s' is not valid JSON" % task_id, "proof-invalid"
    if not isinstance(proof, dict):
        return False, "the proof for task '%s' is not a JSON object" % task_id, "proof-invalid"
    if proof.get("result") != "pass":
        return False, "proof result for task '%s' is %r (need 'pass')" % (task_id, proof.get("result")), "proof-fail"
    if proof.get("task_id") != task_id:
        return False, "the proof names task %r, not the current task '%s'" % (proof.get("task_id"), task_id), "proof-mismatch"
    for field in ("sandbox_service", "timestamp"):
        if not isinstance(proof.get(field), str) or not proof[field].strip():
            return False, "the proof for task '%s' has no %s" % (task_id, field), "proof-invalid"
    return True, "", ""


def main():
    try:
        call = json.loads(sys.stdin.read())
        if not isinstance(call, dict):
            raise ValueError("not a JSON object")
    except ValueError as exc:
        _block("could not parse the hook input (%s) -- failing closed." % exc, "unparseable-input")

    try:
        import production_matcher
    except Exception as exc:  # noqa: BLE001 -- fail closed on any load problem
        _block("cannot load production_matcher.py (%s) -- failing closed." % exc, "matcher-load-failed")

    tool = call.get("tool_name") or ""
    if production_matcher.tool_kind(tool) == "other":
        sys.exit(0)

    try:
        sigs, options = production_matcher.load_signatures(os.path.join(HOOKS_DIR, "production_signatures.conf"))
        match = production_matcher.match_tool_call(call, sigs, options, DEFAULT_CWD)
    except production_matcher.ConfigError as exc:
        _block("signature config problem (%s) -- failing closed." % exc, "config-error")
    except Exception as exc:  # noqa: BLE001
        _block("internal error (%s) -- failing closed." % exc, "internal-error")

    task_id = _current_task_id()
    labels = "; ".join(match["labels"])
    summary = "tool=%s task=%s labels=[%s]" % (tool, task_id or "-", labels)

    if match["unverifiable"] and not match["gated"]:
        _log("SANDBOX_GATE_UNVERIFIABLE_ALLOWED " + summary)
    if not match["gated"]:
        sys.exit(0)
    if match["deny"]:
        _block("this call targets a DENIED path (%s); no proof can unlock it." % labels, "deny " + summary)

    ok, why, tag = _check_proof(task_id)
    if not ok:
        _block("this call touches production (%s) and %s." % (labels, why), tag + " " + summary)
    _log("SANDBOX_GATE_ALLOWED_WITH_PROOF " + summary)
    sys.exit(0)


if __name__ == "__main__":
    main()
