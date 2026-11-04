#!/usr/bin/env python3
"""
sandbox_snapshot_gate.py -- decision logic for  (2026-09-20), the
event-adjacency snapshot gate. Stdlib only. Registered as a SEPARATE sibling
hook to 's sandbox_proof_gate.py -- both share production_matcher.py
and production_signatures.conf (per the operator's 2026-09-19 decision, already
noted in production_signatures.conf's own header).

PURPOSE:  proves a change was tested in the sandbox twin.
answers a DIFFERENT question: has the production target changed since the
last time THIS agent/task looked at (or touched) it? A stale read is
dangerous even when the sandbox proof is real -- the proof was validated
against a state that may no longer be current.

DESIGN (chain-of-custody, not a time window):
  - First gated touch to a (task_id, resolved target path) pair in this
    task: no prior snapshot exists -> record the target's CURRENT state
    (mtime, sha256, exists/not-exists) as the baseline and ALLOW. There is
    nothing to compare against yet; the operator already reviewed the
    brief before release.
  - Any LATER gated touch to the SAME (task_id, path) pair: re-read the
    target's CURRENT on-disk state right now, BEFORE this call executes,
    and compare it to the recorded baseline.
      * Mismatch (mtime or hash differs, or existence flipped) -> BLOCK.
        Something changed this path outside this task's own action chain
        since the last time this task touched it.
      * Match, but the baseline is older than SNAPSHOT_MAX_AGE_SECONDS ->
        BLOCK (loose time-ceiling backstop -- catches an orphaned/leftover
        snapshot from an aborted earlier run; NOT the primary check).
      * Match and within the ceiling -> ALLOW.
  - A companion PostToolUse hook (sandbox_snapshot_posttooluse.sh, mode
    "post") re-reads the target AFTER the call executes and overwrites the
    snapshot with the new state -- this becomes the baseline for the NEXT
    gated touch. If the PostToolUse hook never runs (crash, non-Claude-Code
    write path), the NEXT PreToolUse check will correctly see a mismatch
    (the pre-call baseline vs. the now-different on-disk state) and block,
    which is the safe failure direction.

FAIL-CLOSED: same stance as sandbox_proof_gate.py -- unparseable input,
a missing/invalid production_signatures.conf, or any internal error blocks
the call. Calls that don't match a `path` signature (or match only a
unit/port signature, which has no filesystem target to snapshot) are not
this gate's concern and pass through untouched.

KNOWN LIMIT (same class as 's): the snapshot store lives under this
same agent's write access (SNAPSHOT_DIR below), so this gate stops
accidents and external interference, not an agent that deliberately
tampers with its own snapshot files to unblock itself -- that requires
 layer A (guardrail self-protection), same as 's own
documented limit. This gate's real value is catching a stale read against
external changes (another session, the watchdog, a human editing the file
directly), which is the failure mode it was written for.

KNOWN LIMIT (directories): a `path` signature that names a directory is
snapshotted by the directory's own mtime only, not a recursive content
hash (too expensive to run on every gated call for large directories). A
change to a file inside the directory that doesn't touch the directory's
own mtime (e.g. an in-place edit via an open file descriptor) will not be
caught. File-level signatures get full mtime+sha256 tracking.

 UPDATE (2026-09-25): _pre() now ALSO saves a real content backup
(kai086_content_backup.save_backup) for every real file target, right at
the moment it's about to ALLOW (both the baseline case and the match
case) -- this is the "state immediately before this specific call
executes" restore point kai086_auto_rollback_gate.py (a separate,
optional PostToolUse hook) uses if that call's own health check later
fails. This is a pure addition: the existing hash-based drift detection
above is completely unchanged, backup-saving failures never block a call
(best-effort, logged only) so 's own core purpose can't regress
because of a  problem (e.g. the backup disk being full).

TEST-ONLY ENV OVERRIDES: KAI076_HOOKS_DIR, KAI076_SNAPSHOT_DIR,
KAI076_DEFAULT_CWD, KAI076_MAX_AGE_SECONDS (see also KAI064_* which this
file does not use directly but production_matcher.py's config path does
follow KAI076_HOOKS_DIR here, not KAI064_HOOKS_DIR).
"""

import datetime
import hashlib
import json
import os
import re
import sys

sys.dont_write_bytecode = True

HOOKS_DIR = os.environ.get("KAI076_HOOKS_DIR", "/srv/angkai/.claude/hooks")
SNAPSHOT_DIR = os.environ.get("KAI076_SNAPSHOT_DIR", "/srv/angkai/sandbox_snapshots")
DEFAULT_CWD = os.environ.get("KAI076_DEFAULT_CWD", "/srv/angkai")
MAX_AGE_SECONDS = int(os.environ.get("KAI076_MAX_AGE_SECONDS", str(6 * 3600)))  # loose backstop, default 6h
sys.path.insert(0, HOOKS_DIR)

_SAFE_TASK_ID = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


def _log(line):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with open(os.path.join(HOOKS_DIR, "sandbox_snapshot_audit.log"), "a", encoding="utf-8") as fh:
            fh.write("%s %s\n" % (stamp, line))
    except OSError:
        pass


def _save_backup_best_effort(task_id, target):
    """: best-effort content backup. NEVER raises, NEVER blocks --
    a backup-save failure (e.g. disk full) must not turn into a
    outage, since backup-saving is an addition, not the gate's core job."""
    try:
        import kai086_content_backup
        saved = kai086_content_backup.save_backup(task_id, target)
        if saved:
            _log("SNAPSHOT_GATE_BACKUP_SAVED task=%s target=%s" % (task_id, target))
    except Exception as exc:  # noqa: BLE001
        _log("SNAPSHOT_GATE_BACKUP_FAILED task=%s target=%s error=%s" % (task_id, target, exc))


def _block(reason, log_line):
    _log("SNAPSHOT_GATE_BLOCKED " + log_line)
    sys.stderr.write("BLOCKED: sandbox-snapshot gate. " + reason + "\n")
    sys.stderr.write("The production target this call touches has changed since this task's last "
                      "recorded snapshot, or that snapshot is too old to trust. STOP and report to "
                      "Mokaima/the operator -- re-read the current state before deciding how to proceed.\n")
    sys.exit(2)


def _current_task_id():
    try:
        with open(os.path.join(HOOKS_DIR, "task_released.json"), "r", encoding="utf-8") as fh:
            value = json.load(fh).get("task_id", "")
    except (OSError, ValueError, AttributeError):
        return ""
    return value if isinstance(value, str) else ""


def _snapshot_path(task_id, target):
    key = hashlib.sha256(target.encode("utf-8")).hexdigest()[:32]
    return os.path.join(SNAPSHOT_DIR, "%s__%s.json" % (task_id, key))


def _state_of(target):
    """Returns a dict describing the target's current on-disk state.
    Directories: mtime only (see KNOWN LIMIT above). Files: mtime + sha256.
    Missing path: exists=False, nothing else."""
    try:
        st = os.stat(target)
    except OSError:
        return {"exists": False}
    if os.path.isdir(target):
        return {"exists": True, "kind": "dir", "mtime": st.st_mtime}
    h = hashlib.sha256()
    try:
        with open(target, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return {"exists": False}
    return {"exists": True, "kind": "file", "mtime": st.st_mtime, "sha256": h.hexdigest()}


def _states_match(a, b):
    if a.get("exists") != b.get("exists"):
        return False
    if not a.get("exists"):
        return True
    if a.get("kind") != b.get("kind"):
        return False
    if a.get("kind") == "dir":
        return a.get("mtime") == b.get("mtime")
    return a.get("sha256") == b.get("sha256")


def _write_snapshot(path, target, state):
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    record = dict(state)
    record["target"] = target
    record["recorded_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(record, fh)
    os.replace(tmp, path)


def _read_snapshot(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _age_seconds(record):
    try:
        recorded = datetime.datetime.fromisoformat(record["recorded_at"])
    except (KeyError, ValueError):
        return None
    now = datetime.datetime.now(datetime.timezone.utc)
    return (now - recorded).total_seconds()


def _pre(call, task_id):
    import production_matcher
    sigs, options = production_matcher.load_signatures(os.path.join(HOOKS_DIR, "production_signatures.conf"))
    match = production_matcher.match_tool_call(call, sigs, options, DEFAULT_CWD)
    if not match["gated"]:
        sys.exit(0)

    cwd = call.get("cwd") or DEFAULT_CWD
    tool_input = call.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}
    targets = set()
    if match["kind"] == "write":
        for key in ("file_path", "path", "notebook_path", "source", "destination", "dest", "target"):
            v = tool_input.get(key)
            if isinstance(v, str) and v:
                targets.add(production_matcher.resolve_path(v, cwd))
    # For Bash, production_matcher already told us it's gated but doesn't hand
    # back the specific candidate paths -- re-derive them the same way it did.
    if match["kind"] == "bash":
        command = tool_input.get("command")
        command = command if isinstance(command, str) else ""
        cands, _ = production_matcher._bash_candidates(command, cwd)  # same helper it uses internally
        # Only snapshot candidates that actually correspond to a `path` signature
        # (unit/port hits have no filesystem target).
        for sig in sigs:
            if sig["kind"] not in ("path", "denypath"):
                continue
            roots = {sig["value"], os.path.realpath(sig["value"])}
            for c in cands:
                if any(production_matcher._under(c, r) for r in roots):
                    targets.add(c)

    if not targets:
        # Gated via a unit/port signature only -- nothing to snapshot.
        _log("SNAPSHOT_GATE_NOTHING_TO_SNAPSHOT task=%s labels=%s" % (task_id or "-", ";".join(match["labels"])))
        sys.exit(0)

    if not task_id or not _SAFE_TASK_ID.match(task_id):
        _block("this call touches a production path (%s) but there is no valid active task id in "
               "task_released.json to key a snapshot against." % "; ".join(match["labels"]),
               "no-task labels=%s" % ";".join(match["labels"]))

    for target in sorted(targets):
        snap_path = _snapshot_path(task_id, target)
        current = _state_of(target)
        existing = _read_snapshot(snap_path)
        if existing is None:
            _write_snapshot(snap_path, target, current)
            _save_backup_best_effort(task_id, target)  #
            _log("SNAPSHOT_GATE_BASELINE task=%s target=%s" % (task_id, target))
            continue
        if not _states_match(existing, current):
            _block("target '%s' does not match this task's last recorded snapshot -- something changed "
                   "it outside this task's own action chain since the last touch." % target,
                   "mismatch task=%s target=%s" % (task_id, target))
        age = _age_seconds(existing)
        if age is None or age > MAX_AGE_SECONDS:
            _block("the recorded snapshot for '%s' is too old to trust (%s) -- re-baseline before "
                   "proceeding." % (target, "age unknown" if age is None else "%.0fs old" % age),
                   "stale task=%s target=%s age=%s" % (task_id, target, age))
        _save_backup_best_effort(task_id, target)  #  -- fresh pre-this-call backup
        _log("SNAPSHOT_GATE_MATCH task=%s target=%s age=%.0fs" % (task_id, target, age))
    sys.exit(0)


def _post(call, task_id):
    """Re-snapshot every gated target this call just touched, so the NEXT
    PreToolUse check has a fresh baseline. If task_id is missing/invalid we
    simply have nothing to key against -- silently no-op (PostToolUse
    failures should never block an already-completed action)."""
    if not task_id or not _SAFE_TASK_ID.match(task_id):
        sys.exit(0)
    try:
        import production_matcher
        sigs, options = production_matcher.load_signatures(os.path.join(HOOKS_DIR, "production_signatures.conf"))
        match = production_matcher.match_tool_call(call, sigs, options, DEFAULT_CWD)
    except Exception:  # noqa: BLE001 -- PostToolUse never blocks; log-only best effort
        sys.exit(0)
    if not match["gated"]:
        sys.exit(0)

    cwd = call.get("cwd") or DEFAULT_CWD
    tool_input = call.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}
    targets = set()
    if match["kind"] == "write":
        for key in ("file_path", "path", "notebook_path", "source", "destination", "dest", "target"):
            v = tool_input.get(key)
            if isinstance(v, str) and v:
                targets.add(production_matcher.resolve_path(v, cwd))
    if match["kind"] == "bash":
        command = tool_input.get("command")
        command = command if isinstance(command, str) else ""
        cands, _ = production_matcher._bash_candidates(command, cwd)
        for sig in sigs:
            if sig["kind"] not in ("path", "denypath"):
                continue
            roots = {sig["value"], os.path.realpath(sig["value"])}
            for c in cands:
                if any(production_matcher._under(c, r) for r in roots):
                    targets.add(c)

    for target in sorted(targets):
        snap_path = _snapshot_path(task_id, target)
        _write_snapshot(snap_path, target, _state_of(target))
        _log("SNAPSHOT_GATE_REBASELINE task=%s target=%s" % (task_id, target))
    sys.exit(0)


def main():
    mode = "pre"
    if len(sys.argv) > 1 and sys.argv[1] in ("pre", "post"):
        mode = sys.argv[1]
    try:
        call = json.loads(sys.stdin.read())
        if not isinstance(call, dict):
            raise ValueError("not a JSON object")
    except ValueError as exc:
        if mode == "post":
            sys.exit(0)  # PostToolUse never blocks
        _block("could not parse the hook input (%s) -- failing closed." % exc, "unparseable-input")
        return

    try:
        import production_matcher  # noqa: F401  -- import check only; used inside _pre/_post
    except Exception as exc:  # noqa: BLE001
        if mode == "post":
            sys.exit(0)
        _block("cannot load production_matcher.py (%s) -- failing closed." % exc, "matcher-load-failed")
        return

    task_id = _current_task_id()
    if mode == "post":
        _post(call, task_id)
    else:
        _pre(call, task_id)


if __name__ == "__main__":
    main()
