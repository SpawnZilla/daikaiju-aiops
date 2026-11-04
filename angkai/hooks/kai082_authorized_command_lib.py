#!/usr/bin/env python3
"""
kai082_authorized_command_lib.py (, Option B, 2026-09-24) -- a
REUSABLE arm/disarm mechanism so any future promotion-class task can
unlock exactly one mutating Bash command through Claude Code's OWN
permission layer, without loosening it beyond that one exact command.
Generalizes the one-off approach dryrun_kai064.sh used for 's dry
run into something any future ticket can call. Used by
arm_authorized_command.py and disarm_authorized_command.py in this same
directory -- not meant to be run directly.

BACKGROUND: command_fidelity_pretooluse.sh (chain stage 4) already
enforces that when task_authorized_command.txt is non-empty, every Bash
call this session makes must equal it EXACTLY. That is necessary but not
sufficient -- Claude Code's OWN permission layer sits in front of all five
of our PreToolUse hooks and, under the runner's -p (headless) mode with no
one to answer an approval prompt, denies any mutating Bash command that
isn't covered by an allow rule, no matter what our hooks would have
decided ('s root cause, confirmed live 2026-09-20 -- five hooks
passed a `sed -i` and Claude Code's own layer still blocked it).

THE FIX: `arm` writes the EXACT command to BOTH task_authorized_command.txt
(existing mechanism, unchanged) AND a matching Bash(<exact command>) entry
in settings.json's permissions.allow (new). Per Claude Code's documented
permission syntax (code.claude.com/docs/en/permissions, checked 2026-09-24):
`Bash(npm run build)` matches ONLY that exact command string -- no wildcard
needed or used here. So all three layers (Claude Code's own permission
check, the fidelity hook's exact-match, the sandbox gate's proof
requirement) end up checking the SAME single literal string. This widens
what the agent can execute by exactly one command per armed task, not a
pattern or a class of commands.

`disarm` reverses both: clears task_authorized_command.txt and removes
ONLY the exact allow-rule entry this arm call added (never any other
entry in permissions.allow -- Graft's own entries are untouched).

ONE ARMED COMMAND AT A TIME: `arm` refuses if something is already armed
(the state file below is the source of truth, not settings.json itself,
since something else could in principle add its own Bash(...) entry).

SESSION-RESTART CAVEAT (same subprocess-staleness pattern as every other
hook/settings.json change in this project): a settings.json change takes
effect on the NEXT `claude` process start, not inside an already-running
session. Arm BEFORE launching the session that needs the command, same as
's dry run already did -- this is not for arming mid-session.

KNOWN LIMIT, NOT VERIFIED: Claude Code's Bash(...) rule syntax was checked
against the docs' own examples, none of which contain a literal `(` or `)`
inside the command text itself. A command containing parentheses in its
own text (not this ticket's sed-shaped use case, but possible for a future
promotion command) may not round-trip through the rule parser correctly --
flagged, not solved, here.

 UPDATE (2026-09-25): `arm` now accepts an OPTIONAL 3rd argument,
a health-check command, written to task_health_check.txt alongside the
existing task_authorized_command.txt. This is what
kai086_auto_rollback_gate.py (a separate, optional PostToolUse hook)
reads to decide whether the armed command's own change should be
automatically rolled back -- if provided and it exits non-zero after the
armed command runs, the target's pre-call content backup ('s own
extension, kai086_content_backup.py) is restored and the operator is alerted.
Purely additive: arming WITHOUT a health-check works exactly as before,
no auto-rollback behavior at all -- this is opt-in per task, not a new
default.
"""

import json
import os
import sys
import datetime

HOOKS_DIR = os.environ.get("KAI082_HOOKS_DIR", "/srv/angkai/.claude/hooks")
SETTINGS_PATH = os.environ.get("KAI082_SETTINGS_PATH", "/srv/angkai/.claude/settings.json")
AUTH_CMD_FILE = os.path.join(HOOKS_DIR, "task_authorized_command.txt")
HEALTH_CHECK_FILE = os.path.join(HOOKS_DIR, "task_health_check.txt")  #
STATE_FILE = os.path.join(HOOKS_DIR, "kai082_armed_state.json")


def _write_inplace(path, text):
    """PROTECTED_REGULAR FIX (2026-09-26): the hooks dir is sticky + group-writable
    since the lockdown and fs.protected_regular=2, so open(path, "w") (O_CREAT) of an
    angkai-owned file is refused -- even for root. Update in place without O_CREAT;
    create only when missing."""
    data = text.encode("utf-8")
    if os.path.exists(path):
        with open(path, "r+b") as fh:
            fh.seek(0)
            fh.write(data)
            fh.truncate()
    else:
        with open(path, "xb") as fh:
            fh.write(data)


def _backup(path):
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = "%s.bak-kai082-%s" % (path, stamp)
    with open(path, "r", encoding="utf-8") as src, open(backup_path, "w", encoding="utf-8") as dst:
        dst.write(src.read())
    return backup_path


def _load_settings():
    with open(SETTINGS_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_settings(data):
    tmp = SETTINGS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    # validate before replacing -- a bad write must never land as the live file
    with open(tmp, "r", encoding="utf-8") as fh:
        json.load(fh)
    os.replace(tmp, SETTINGS_PATH)


def arm(task_id, command, health_check=None):
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as fh:
            existing = json.load(fh)
        print("REFUSED: task '%s' is already armed with command %r (armed %s)."
              % (existing["task_id"], existing["command"], existing["armed_at"]))
        print("Run disarm_authorized_command.py first if that's stale.")
        sys.exit(1)

    if not command or not command.strip():
        print("REFUSED: empty command.")
        sys.exit(1)

    rule = "Bash(%s)" % command

    settings_backup = _backup(SETTINGS_PATH)
    data = _load_settings()
    allow = data.setdefault("permissions", {}).setdefault("allow", [])
    if rule in allow:
        print("NOTE: rule already present in permissions.allow (unexpected, but not an error) -- not duplicating.")
    else:
        allow.append(rule)
        _write_settings(data)

    _write_inplace(AUTH_CMD_FILE, command)

    if health_check and health_check.strip():
        _write_inplace(HEALTH_CHECK_FILE, health_check)
    else:
        # explicit empty write, not "leave whatever was there" -- a stale
        # health-check from a PREVIOUS armed task must never silently apply
        # to this one
        _write_inplace(HEALTH_CHECK_FILE, "")

    state = {
        "task_id": task_id,
        "command": command,
        "health_check": health_check or "",
        "rule": rule,
        "settings_backup": settings_backup,
        "armed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    with open(STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)

    print("ARMED task '%s'." % task_id)
    print("  task_authorized_command.txt = %r" % command)
    print("  permissions.allow += %r" % rule)
    if health_check:
        print("  task_health_check.txt = %r (auto-rollback ENABLED, )" % health_check)
    else:
        print("  task_health_check.txt = (empty -- auto-rollback NOT enabled for this task)")
    print("  settings.json backup: %s" % settings_backup)
    print("REMINDER: start the Claude Code session AFTER this arm call, not")
    print("before -- settings.json changes only take effect on next start.")


def disarm():
    if not os.path.exists(STATE_FILE):
        print("Nothing armed (no state file) -- checking for a stray authorized-command file...")
        if os.path.exists(AUTH_CMD_FILE) and open(AUTH_CMD_FILE, encoding="utf-8").read().strip():
            print("WARNING: task_authorized_command.txt is non-empty but no  state file exists.")
            print("This was likely armed by something else (e.g. the old dryrun_kai064.sh path).")
            print("Not touching settings.json (no rule recorded to remove). Truncating the auth file only.")
            _write_inplace(AUTH_CMD_FILE, "")
        else:
            print("Nothing to do.")
        return

    with open(STATE_FILE, "r", encoding="utf-8") as fh:
        state = json.load(fh)

    _backup(SETTINGS_PATH)
    data = _load_settings()
    allow = data.get("permissions", {}).get("allow", [])
    if state["rule"] in allow:
        allow.remove(state["rule"])
        _write_settings(data)
        print("Removed rule %r from permissions.allow." % state["rule"])
    else:
        print("NOTE: rule %r was not found in permissions.allow (removed by something else already?) -- nothing to remove there."
              % state["rule"])

    _write_inplace(AUTH_CMD_FILE, "")
    if os.path.exists(HEALTH_CHECK_FILE):  #
        _write_inplace(HEALTH_CHECK_FILE, "")
    os.remove(STATE_FILE)
    print("DISARMED task '%s'. task_authorized_command.txt and task_health_check.txt cleared." % state["task_id"])
