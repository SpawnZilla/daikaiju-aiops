#!/usr/bin/env python3
"""
kai084_sessionend_idle.py (, 2026-09-25) -- SessionEnd hook that
moves task_released.json from "consumed" to an explicit "idle" state when
an Angkai session ends, so a consumed marker no longer sits there
indefinitely looking like live state.

RULES (the whole point is to never clobber a real release):
  - status == "consumed"  -> rewrite status to "idle", keep task_id /
    target_agent / payload_ref unchanged ( and the audit trail
    still read task_id), add idled_at + idled_by_session.
  - status == "released"  -> NEVER touched. A fresh release waiting for
    the next session must survive this session's exit.
  - anything else / missing / unparseable -> no-op, logged.
  - Re-reads the file immediately before the atomic replace and aborts if
    status or task_id changed in between (narrows, does not eliminate,
    the race with a concurrent release_task.sh write -- release_task.sh
    takes no lock, so neither can this).

SAFE WITH THE LAUNCH RUNNER: angkai_launch_runner.py launches only on
status == "released" and task_release_pretooluse.sh authorizes only on
status == "released"; "idle" is treated exactly like "consumed" by both.

NEVER BLOCKS / NEVER RAISES: SessionEnd cannot block; every failure path
logs and exits 0. SessionEnd may not run at all if the process is killed
by a signal (SIGKILL/OOM) -- a known limit, see the deployment guide.

Stdlib only. TEST-ONLY env override: KAI084_HOOKS_DIR.
"""

import datetime
import json
import os
import sys

sys.dont_write_bytecode = True

HOOKS_DIR = os.environ.get("KAI084_HOOKS_DIR", "/srv/angkai/.claude/hooks")
RELEASE_FILE = os.path.join(HOOKS_DIR, "task_released.json")
LOG_FILE = os.path.join(HOOKS_DIR, "kai084_sessionend.log")


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(line):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write("%s %s\n" % (_now(), line))
    except OSError:
        pass


def _read_release():
    try:
        with open(RELEASE_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def main():
    try:
        event = json.loads(sys.stdin.read() or "{}")
        if not isinstance(event, dict):
            event = {}
    except ValueError:
        event = {}
    session_id = str(event.get("session_id", "unknown"))
    reason = str(event.get("reason", "unknown"))

    release = _read_release()
    if release is None:
        _log("NOOP session=%s reason=%s release_file=missing_or_invalid" % (session_id, reason))
        return

    status = release.get("status")
    task_id = release.get("task_id")
    if status != "consumed":
        _log("NOOP session=%s reason=%s status=%s task=%s" % (session_id, reason, status, task_id))
        return

    updated = dict(release)
    updated["status"] = "idle"
    updated["idled_at"] = _now()
    updated["idled_by_session"] = session_id

    tmp_path = RELEASE_FILE + ".kai084.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(updated, fh, indent=2)
            fh.write("\n")
        latest = _read_release()
        if latest is None or latest.get("status") != "consumed" or latest.get("task_id") != task_id:
            os.remove(tmp_path)
            _log("ABORT_RACE session=%s task=%s -- file changed before replace" % (session_id, task_id))
            return
        os.replace(tmp_path, RELEASE_FILE)
        try:
            os.chmod(RELEASE_FILE, 0o664)
        except OSError:
            pass  # chmod needs ownership; best-effort, same as release_task.sh
        _log("IDLED session=%s reason=%s task=%s" % (session_id, reason, task_id))
    except OSError as exc:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        _log("WRITE_FAILED session=%s task=%s error=%s" % (session_id, task_id, exc))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 -- SessionEnd must never surface a crash
        _log("UNEXPECTED_ERROR %s" % exc)
    sys.exit(0)
