#!/usr/bin/env python3
"""
angkai_launch_runner.py

Boot-persistent polling watcher that launches a live Angkai (Claude
Code) session whenever a task_released.json release targets
"angkai" and no Angkai session is currently running.

Built for  (Daikaiju AIOps full autonomous operation). Owned
and run as angkai. Does NOT touch task_released.json/task_budget.txt
content -- those remain release_task.sh's exclusive write path per
the NEVER-DIRECT-WRITE rule. This script only READS
task_released.json and manages its own separate lock file
(angkai_session.lock), which nothing else in the pipeline reads or
writes.

Poll-cycle logic (decided 2026-09-04, , "Mokaima help 1.1 Full
Auto Angkai"):
  1. Read task_released.json -- nothing there -> no-op.
  2. target_agent != "angkai" -> skip.
  3. Lock exists, PID alive -> skip (a session is running).
  4. Lock exists, PID dead -> stale, clear it.
  5. task_id matches the lock's last-launched task_id -> skip
     (already handled).
  6. Otherwise -> launch (subprocess.Popen(), the existing
     ANG_BRIEF_BASENAME=... claude --allowedTools "..." command from
     CLAUDE.md v4.7's LAUNCH COMMAND section), write the lock
     immediately.

KNOWN LIMITATION, not in scope for this build: if a launched session
exits immediately (e.g. a hard launch-time error) before the release
marker is consumed, the lock clears fast enough that the very next
poll cycle could relaunch against the same still-unconsumed release,
producing a rapid relaunch loop rather than a single clean failure.
Not mitigated here -- flagged for a future pass if it's ever observed
live, per this project's own honest-gap-over-silent-assumption
convention.
"""


import json
import logging
import os
import signal
import subprocess
import threading
import time
import sys

sys.path.insert(0, '/srv/angkai/staging/')
import exec_agent_adapters  # noqa: E402

HOOKS_DIR = "/srv/angkai/.claude/hooks"
TASK_RELEASED_FILE = os.path.join(HOOKS_DIR, "task_released.json")
LOCK_FILE = os.path.join(HOOKS_DIR, "angkai_session.lock")
LAUNCH_CWD = "/srv/angkai"

# Matches CLAUDE.md v4.7's LAUNCH COMMAND section exactly (2026-08-27):
# mcp__vault__read_text_file, NOT the dead mcp__vault__read_file name.
ALLOWED_TOOLS = (
    "mcp__vault__read_text_file,mcp__vault__write_file,"
    "mcp__vault__list_directory,mcp__vault__create_directory"
)

# Matches angkai's own .bashrc `claude` ALIAS exactly (confirmed by direct
# read, 2026-09-04) -- Angkai never uses real Anthropic auth at all;
# every interactive launch routes to local Ollama via this exact binary
# path + these exact env vars + this exact --model flag. subprocess.Popen
# cannot rely on shell alias expansion (aliases are a login/interactive-
# shell feature, not inherited by a directly-exec'd child process), so
# this runner must replicate the alias's real effect directly rather than
# just invoking the bare "claude" command name. Confirmed live 2026-09-04:
# both this runner AND a plain `sudo -u angkai ... claude -p ...` test (a
# non-login, non-interactive shell, which also never sources .bashrc)
# failed identically with "Not logged in" until this was fixed -- same
# root cause, not two separate bugs.
CLAUDE_BINARY = "/srv/ai/npm-global/bin/claude"
CLAUDE_MODEL = "angkai-model"
CLAUDE_ENV_OVERRIDES = {
    "ANTHROPIC_AUTH_TOKEN": "ollama",
    "ANTHROPIC_BASE_URL": "http://localhost:11435",
    "ANTHROPIC_API_KEY": "",
    "TOOL_FILTER_ALLOWLIST": ALLOWED_TOOLS,
}

POLL_INTERVAL_SECONDS = int(os.environ.get("ANGKAI_RUNNER_POLL_SECONDS", "45"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [angkai_launch_runner] %(message)s",
)
log = logging.getLogger("angkai_launch_runner")

_shutdown = threading.Event()


def _handle_signal(signum, frame):
    log.info("Received signal %s, shutting down.", signum)
    _shutdown.set()


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


def read_task_released():
    """Return the parsed task_released.json dict, or None if it does
    not exist, is empty, or is not valid JSON."""
    if not os.path.isfile(TASK_RELEASED_FILE):
        return None
    try:
        with open(TASK_RELEASED_FILE, "r") as f:
            content = f.read().strip()
    except OSError as exc:
        log.warning("Could not read %s: %s", TASK_RELEASED_FILE, exc)
        return None
    if not content:
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        log.warning("task_released.json is not valid JSON: %s", exc)
        return None


def read_lock():
    """Return the parsed lock-file dict, or None if it does not
    exist, is empty, or is not valid JSON."""
    if not os.path.isfile(LOCK_FILE):
        return None
    try:
        with open(LOCK_FILE, "r") as f:
            content = f.read().strip()
    except OSError as exc:
        log.warning("Could not read %s: %s", LOCK_FILE, exc)
        return None
    if not content:
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        log.warning("angkai_session.lock is not valid JSON: %s", exc)
        return None


def pid_is_alive(pid):
    """Check liveness via /proc rather than trusting the lock file's
    own claim -- same self-healing-over-trusting-state philosophy as
    /'s fixes."""
    try:
        pid_int = int(pid)
    except (TypeError, ValueError):
        return False
    return os.path.isdir("/proc/%d" % pid_int)


def write_lock(pid, task_id):
    payload = {
        "pid": pid,
        "task_id": task_id,
        "launched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    tmp_path = LOCK_FILE + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(payload, f)
    os.replace(tmp_path, LOCK_FILE)
    log.info("Wrote lock: pid=%s task_id=%s", pid, task_id)


def remove_lock(reason):
    try:
        os.remove(LOCK_FILE)
        log.info("Removed lock (%s).", reason)
    except FileNotFoundError:
        pass
    except OSError as exc:
        log.warning("Could not remove lock file: %s", exc)


def wait_and_clear_lock(proc, task_id):
    """Background thread: block on the launched session's own exit,
    then clear the lock the moment it ends -- the primary, reliable
    cleanup path decided for this runner. The PID-liveness check in
    poll_once() is the fallback path for when the runner process
    itself restarted and lost this thread."""
    proc.wait()
    log.info(
        "Angkai session for task_id=%s exited (returncode=%s).",
        task_id,
        proc.returncode,
    )
    remove_lock("session exited")


def build_prompt(basename):
    """Non-interactive Claude Code (claude -p) needs the actual task
    text passed as an argument -- ANG_BRIEF_BASENAME alone only feeds
    the PreToolUse hooks, it does not put anything in front of the
    model. Hardcodes the vault/angkai/briefs/ prefix directly
    (CLAUDE.md's own documented path convention) rather than letting
    the launched session guess a path -- this exact wrong-path-guess
    failure was observed live during this feature's own first manual
    launch attempt (2026-09-04)."""
    return (
        "Read the file at exactly this path and do nothing else "
        "first: vault/angkai/briefs/" + basename + "\n"
        "Then execute exactly what it says. Do not explore any other "
        "directory or guess any other path."
    )


def launch_angkai(task_id, payload_ref):
    adapter = exec_agent_adapters.load()
    spec = exec_agent_adapters.validate_launch(adapter.build_launch(task_id, payload_ref))
    env = os.environ.copy()
    env.update(spec["env"])
    cmd = spec["cmd"]
    log.info(
        "Launching Angkai for task_id=%s payload_ref=%s",
        task_id,
        payload_ref,
    )
    proc = subprocess.Popen(cmd, cwd=spec["cwd"], env=env)
    write_lock(proc.pid, task_id)
    watcher = threading.Thread(
        target=wait_and_clear_lock,
        args=(proc, task_id),
        daemon=True,
    )
    watcher.start()


def poll_once():
    release = read_task_released()
    if not release:
        return

    if release.get("target_agent") != "angkai":
        return

    # BUG FOUND LIVE 2026-09-04: this check was missing entirely --
    # without it, a release that's already been consumed (status
    # flipped to "consumed" by task_release_pretooluse.sh once some
    # session's first tool call reaches it) still matches target_agent
    # and gets relaunched against, every time its lock clears, forever
    # -- observed live as a second, unwanted launch against an already-
    # consumed task_id. Only a release still genuinely awaiting pickup
    # should ever trigger a launch.
    if release.get("status") != "released":
        return

    lock = read_lock()
    if lock is not None:
        if pid_is_alive(lock.get("pid")):
            return
        remove_lock("stale -- PID no longer alive")
        lock = None

    task_id = release.get("task_id")
    if lock is not None and lock.get("task_id") == task_id:
        return

    payload_ref = release.get("payload_ref")
    launch_angkai(task_id, payload_ref)


def main():
    log.info(
        "angkai_launch_runner starting. Polling %s every %ss.",
        TASK_RELEASED_FILE,
        POLL_INTERVAL_SECONDS,
    )
    while not _shutdown.is_set():
        try:
            poll_once()
        except Exception:
            log.exception("Unexpected error during poll cycle.")
        _shutdown.wait(POLL_INTERVAL_SECONDS)
    log.info("angkai_launch_runner stopped.")


if __name__ == "__main__":
    main()
