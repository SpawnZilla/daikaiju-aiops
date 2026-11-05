"""
checkpoint_ntfy.py, 2026-09-24) -- the ntfy dispatch that
kaiju_a2a_task_schema.py's CheckpointState.record_run() was DESCRIBED as
doing (its own return string literally says "ntfy alert fires per section
10 pending_checkin case") but never actually did. Read in full 2026-09-24:
checkpoint_gate.py, kaiju_mokaima_step5_review.py, and
kaiju_a2a_task_schema.py contain zero notification dispatch code anywhere
-- the phrase was descriptive of what the original design brief's section
10 specifies, not something the code implements. This module is that
missing implementation.

WHY THIS MATTERS: the 2-run re-eval check-in and the reset-to-stage_0
event are the ONLY points where a human is meant to be pulled back into
an otherwise-unsupervised loop. Without an actual out-of-band signal,
that check-in depends entirely on someone reading Mokaima's tool output
live, which provides no real oversight for genuinely unattended running.

TOPIC CHOICE (the operator, 2026-09-24): the self-hosted "dd-alerts" topic (same
server, same credentials pattern as watchdog_notify.sh) -- NOT the
"Rokaidan" ntfy.sh topic, which is architecturally a different thing
entirely (a PUBLIC, unauthenticated INBOUND trigger channel for's
remote-wake feature, not an outbound alert channel; using it here would
misuse a channel scoped for something else and expose governance events
on the operator's own decision, not a Rodkai-wake trigger).

ONLY 3 OF THE POSSIBLE record_run() TRANSITIONS FIRE A NOTIFICATION:
RESET, REEVAL DUE, and FULLY AUTONOMOUS. Routine "CLEAN (stage_0):
clean_run_count now N/4" progress messages do NOT notify -- that would be
noise on every single run, defeating the point of an alert.

FAIL-OPEN BY DESIGN: a notification failure (network down, ntfy
unreachable, bad credentials) must NEVER break or alter the actual
governance decision -- record_run() has already committed its state
change by the time this is called. Wrapped in try/except, logs failure,
never raises.
"""

import subprocess
import datetime
import os

NTFY_URL = "http://192.0.2.45:<port>/dd-alerts"
NTFY_USER = "operatorpawn"
NTFY_PASS = "LillyNaya0604"  # same credential watchdog_notify.sh already uses -- the operator's call 2026-09-24 to leave as is, not rotated

LOG_PATH = os.environ.get("CHECKPOINT_LOG_PATH", "/srv/adapters/mokaima-a2a-adapter/checkpoint_ntfy.log")


def _log(line):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write("%s %s\n" % (stamp, line))
    except OSError:
        pass


def _send(title, message, priority):
    try:
        result = subprocess.run(
            [
                "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                "-u", "%s:%s" % (NTFY_USER, NTFY_PASS),
                "-H", "Title: %s" % title,
                "-H", "Priority: %s" % priority,
                "-d", message,
                NTFY_URL,
            ],
            capture_output=True, text=True, timeout=10,
        )
        code = result.stdout.strip()
        if code == "200":
            _log("SENT title=%r priority=%s" % (title, priority))
            return True
        _log("FAILED title=%r http_code=%s stderr=%s" % (title, code, result.stderr[:200]))
        return False
    except Exception as exc:  # noqa: BLE001 -- never let a notification failure propagate
        _log("EXCEPTION title=%r error=%s" % (title, exc))
        return False


def notify_checkpoint_event(transition_text):
    """
    Call this right after checkpoint.record_run() returns, passing its
    exact return string. Fires at most one ntfy notification, only for
    the 3 event types that actually need a human's attention. Returns
    True/False for whether a send was attempted and succeeded (callers
    should NOT branch governance logic on this -- log-and-move-on only).
    """
    if transition_text.startswith("RESET:"):
        return _send(
            " Guardrail Reset",
            "A non-clean run reset the autonomy checkpoint to stage_0. "
            + transition_text,
            "urgent",
        )
    if transition_text.startswith("REEVAL DUE:"):
        return _send(
            " Check-in Needed",
            "2 unsupervised clean runs complete inside graduated_window. "
            + transition_text,
            "high",
        )
    if transition_text.startswith("FULLY AUTONOMOUS:"):
        return _send(
            " Reached Full Autonomy",
            transition_text,
            "default",
        )
    # neutral-escalation (2026-09-26): a correct escalation no
    # longer resets (so no RESET alert) -- this is now its out-of-band
    # signal, so an escalation never goes silent.
    if transition_text.startswith("NEUTRAL:"):
        return _send(
            " Escalated to the operator",
            "A request was correctly escalated as hard-manual and needs "
            "your decision. Checkpoint NOT reset. " + transition_text,
            "high",
        )
    return None  # routine progress message -- no notification, by design
