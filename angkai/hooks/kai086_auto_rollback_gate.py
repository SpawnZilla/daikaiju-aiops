#!/usr/bin/env python3
"""
kai086_auto_rollback_gate.py (, 2026-09-25) -- optional,
opt-in automatic rollback for the ONE armed command a task
runs, if its own operator-supplied health check fails afterward.

HOW IT FITS: 's `arm` optionally writes a health-check command to
task_health_check.txt (empty by default -- see kai082_authorized_command_lib.py's
 update). This hook, registered as a PostToolUse entry AFTER
's own re-baseline hook, does nothing at all unless that file is
non-empty for THIS task -- auto-rollback is opt-in per task, never a
new default behavior.

WHEN IT FIRES: after any gated call this session makes (same
production_matcher-based target resolution  already uses), if
task_health_check.txt names a real command:
  1. Run that command (a timeout, not indefinite -- a hung health check
     must not hang the whole session).
  2. Exit 0 -> health check passed. Log it, do nothing else.
  3. Exit non-zero -> for every gated FILE target this call touched,
     restore its  content backup (the state immediately before
     THIS call executed, saved by sandbox_snapshot_gate.py's own
      update) and send a real, urgent ntfy alert to the
     self-hosted kaiju-alerts channel naming exactly what was restored and
     why. A human MUST know an automatic rollback happened -- this is
     not a silent recovery.

SCOPE, restated from kai086_content_backup.py: this only meaningfully
covers FILE-CONTENT changes. If the armed command didn't touch any
file  was already tracking (e.g. it was a pure restart with no
file edit), there is nothing to restore -- the alert says so plainly
rather than pretending a rollback happened.

KNOWN LIMIT, stated again here because it matters most at the exact
moment this code runs: restoring a file's CONTENT does not restart
whatever service needs to pick up the reverted content. The alert
says this explicitly -- a human still needs to take that step.

NEVER BLOCKS: this is a PostToolUse hook: the armed command has
already executed by the time this runs. Every failure path here is
logged, never raised -- a bug in the rollback mechanism itself must
never look like a hang or a crash to the session.
"""

import datetime
import json
import os
import subprocess
import sys

sys.dont_write_bytecode = True

HOOKS_DIR = os.environ.get("KAI076_HOOKS_DIR", "/srv/angkai/.claude/hooks")
DEFAULT_CWD = os.environ.get("KAI076_DEFAULT_CWD", "/srv/angkai")
HEALTH_CHECK_FILE = os.path.join(HOOKS_DIR, "task_health_check.txt")
HEALTH_CHECK_TIMEOUT_SECONDS = int(os.environ.get("KAI086_HEALTH_CHECK_TIMEOUT", "30"))

NTFY_URL = os.environ.get("KAI086_NTFY_URL", "http://192.0.2.45:8201/kaiju-alerts")
NTFY_ENV_FILE = os.environ.get("KAI086_NTFY_ENV", "/etc/kaiju-os/ntfy.env")


def _ntfy_credential():
    """Read KAIJU_NTFY_USER / KAIJU_NTFY_PASS from the env file (KEY=VALUE lines).
    Returns "user:pass" or "" when the file is missing or unreadable; the caller then
    sends without credentials, the request fails and NOTIFY_FAILED is logged."""
    user = pw = ""
    try:
        with open(NTFY_ENV_FILE, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("export "):
                    line = line[7:]
                k, sep, v = line.partition("=")
                if sep and k.strip() == "KAIJU_NTFY_USER":
                    user = v.strip().strip("'\"")
                elif sep and k.strip() == "KAIJU_NTFY_PASS":
                    pw = v.strip().strip("'\"")
    except OSError:
        return ""
    return "%s:%s" % (user, pw) if user and pw else ""

sys.path.insert(0, HOOKS_DIR)


def _log(line):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with open(os.path.join(HOOKS_DIR, "kai086_auto_rollback.log"), "a", encoding="utf-8") as fh:
            fh.write("%s %s\n" % (stamp, line))
    except OSError:
        pass


def _notify(title, message, priority):
    try:
        cred = _ntfy_credential()
        result = subprocess.run(
            [
                "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
            ] + (["-u", cred] if cred else []) + [
                "-H", "Title: %s" % title,
                "-H", "Priority: %s" % priority,
                "-d", message,
                NTFY_URL,
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.stdout.strip() != "200":
            _log("NOTIFY_FAILED http_code=%s" % result.stdout.strip())
    except Exception as exc:  # noqa: BLE001 -- notification failure must never propagate
        _log("NOTIFY_EXCEPTION error=%s" % exc)


def _current_task_id():
    try:
        with open(os.path.join(HOOKS_DIR, "task_released.json"), "r", encoding="utf-8") as fh:
            value = json.load(fh).get("task_id", "")
    except (OSError, ValueError, AttributeError):
        return ""
    return value if isinstance(value, str) else ""


def _resolve_targets(call):
    """Same target-resolution logic as sandbox_snapshot_gate.py's _post()
    -- deliberately duplicated rather than imported, so a bug in 's
    own module can never silently disable 's rollback path too."""
    import production_matcher
    sigs, options = production_matcher.load_signatures(os.path.join(HOOKS_DIR, "production_signatures.conf"))
    match = production_matcher.match_tool_call(call, sigs, options, DEFAULT_CWD)
    if not match["gated"]:
        return set()

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
    return targets


def main():
    try:
        call = json.loads(sys.stdin.read())
        if not isinstance(call, dict):
            raise ValueError("not a JSON object")
    except ValueError:
        sys.exit(0)  # PostToolUse never blocks; nothing sensible to do with unparseable input

    try:
        health_check = open(HEALTH_CHECK_FILE, encoding="utf-8").read().strip()
    except OSError:
        health_check = ""

    if not health_check:
        sys.exit(0)  # opt-in feature, not armed for this task -- silent no-op by design

    task_id = _current_task_id()

    try:
        targets = _resolve_targets(call)
    except Exception as exc:  # noqa: BLE001
        _log("TARGET_RESOLUTION_FAILED task=%s error=%s" % (task_id, exc))
        sys.exit(0)

    if not targets:
        sys.exit(0)  # this call didn't touch a gated file target -- nothing for this hook to do

    try:
        result = subprocess.run(
            health_check, shell=True, capture_output=True, text=True,
            timeout=HEALTH_CHECK_TIMEOUT_SECONDS,
        )
        check_exit = result.returncode
        check_output = (result.stdout or "") + (result.stderr or "")
    except subprocess.TimeoutExpired:
        check_exit = -1
        check_output = "(health check timed out after %ds)" % HEALTH_CHECK_TIMEOUT_SECONDS
    except Exception as exc:  # noqa: BLE001
        check_exit = -1
        check_output = "(health check itself failed to run: %s)" % exc

    if check_exit == 0:
        _log("HEALTH_CHECK_PASS task=%s targets=%s" % (task_id, ",".join(sorted(targets))))
        sys.exit(0)

    _log("HEALTH_CHECK_FAILED task=%s exit=%s output=%s" % (task_id, check_exit, check_output[:500]))

    import kai086_content_backup
    restored = []
    not_restored = []
    for target in sorted(targets):
        if kai086_content_backup.restore_backup(task_id, target):
            restored.append(target)
            _log("ROLLBACK_RESTORED task=%s target=%s" % (task_id, target))
        else:
            not_restored.append(target)
            _log("ROLLBACK_NO_BACKUP task=%s target=%s" % (task_id, target))

    lines = ["Health check FAILED (exit %s) after task %s's armed command ran." % (check_exit, task_id)]
    if restored:
        lines.append("RESTORED from backup: " + ", ".join(restored))
    if not_restored:
        lines.append("NO BACKUP FOUND, NOT restored: " + ", ".join(not_restored))
    lines.append("REMINDER: content was restored, but nothing was automatically restarted -- "
                 "a restart may still be needed for the reverted content to take effect.")
    lines.append("Health check output (truncated): " + check_output[:300])
    _notify(" AUTO-ROLLBACK FIRED", "\n".join(lines), "urgent")


if __name__ == "__main__":
    main()
