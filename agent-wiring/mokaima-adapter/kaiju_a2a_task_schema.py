"""
kaiju_a2a_task_schema.py -- DD-specific schema wrapper for's A2A
task objects (brief section 8.3) plus the section 7 human-checkpoint
graduation state machine and the section 12.4 governance-verdict
aggregator.

Written 2026-08-27 (Daikaiju AIOps/ part 7), logic-tested
in Mokaima's sandbox against mocked run sequences (10/10 cases pass --
basic 4-in-a-row graduation, reset mid stage_0 buildup, reset inside
graduated_window, re-eval-due transition, task creation stamping
current checkpoint fields, hard-stop overriding an otherwise-clean
verdict, governance_checks recording real per-filter verdicts,
checkpoint state JSON round-trip, and invalid task_type/status
rejection). Deployed 2026-08-27 (part 7 continuation 3) as a sibling-
module dependency of kaiju_mokaima_a2a_adapter.py -- an exact copy of
the authoritative kaiju-relay/kaiju_a2a_task_schema.py, persistence
functions included.

BUILD-FROM-EXISTING: reuses checkpoint_gate.py's should_checkpoint() as
the per-run "was this clean" signal rather than reinventing per-stage
warning aggregation -- this module only adds the persistent, stateful
piece (graduation counters across runs) that checkpoint_gate.py does
not have and was never designed to have (it's a stateless, single-call
decision function).

CHECKPOINT_REEVAL_POLICY DECISION (CONFIRMED 2026-08-27, same part 7
session): brief section 7 says "after those 2 unsupervised runs, the operator
checks in on the results" but did not originally say what happens on a
SUCCESSFUL re-evaluation. the operator confirmed stay_graduated is correct --
no scenario identified where resetting to stage_0 on a clean
re-evaluation would be safer or more useful; the recurring re-eval
check-in itself (every 2 runs, forever) already preserves ongoing
oversight without re-earning graduation from scratch each time. This
was Mokaima's default going in and is now a confirmed decision, not a
guess. UPDATE (design locked, build this session -- "Mokaima help 1.1
Full Auto Angkai" part 2): adds a THIRD, terminal checkpoint_state,
fully_autonomous, reached after 5 clean runs accumulated while inside
graduated_window (AUTONOMY_THRESHOLD, tracked via the new
autonomy_progress_count field -- a running total independent of
graduated_run_count's own 2-run re-eval cadence, which keeps operating
unchanged per the operator's decision to reuse existing graduated_window
mechanics rather than build a parallel ramp). Once reached,
fully_autonomous requires no further periodic re-eval check-in on the
clean path -- that cadence was graduated_window's own mechanic and is
not carried over, per the operator's decision that this state is genuinely
terminal. The reset rule is explicitly ASYMMETRIC per the operator's decision:
any non-clean run from ANY state, fully_autonomous included, resets
straight to stage_0 in one step -- there is no intermediate "fall back
to graduated_window" state. This was already the natural shape of the
existing reset branch (it runs first, before any state-specific logic,
and does not inspect which state it came from), so implementing it
required only zeroing the new counter alongside the existing ones, not
new branching logic. GUARDRAILS NEVER LOOSEN (the operator's decision): this
state only changes checkpoint CADENCE (how often a clean run requires
a human check-in) -- it changes nothing about what counts as a clean
run in the first place. evaluate_run_clean()'s hard-stop-fired check
and checkpoint_gate.should_checkpoint()'s warning-triggered mandatory
checkpoint both still run, unmodified, on every single run regardless
of checkpoint_state, exactly as before this change.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

from checkpoint_gate import should_checkpoint


# ---------------------------------------------------------------------------
# Section 7 graduation state machine (+'s fully_autonomous extension)
# ---------------------------------------------------------------------------

STAGE_0 = "stage_0"
GRADUATED_WINDOW = "graduated_window"
FULLY_AUTONOMOUS = "fully_autonomous"  #: terminal state
RESET = "reset"  # transient marker, not a resting state -- see note below

GRADUATION_THRESHOLD = 4      # clean runs to graduate out of stage_0
UNSUPERVISED_WINDOW = 2       # runs allowed unsupervised before re-check-in
AUTONOMY_THRESHOLD = 5         #: cumulative clean runs inside
                               # graduated_window to reach fully_autonomous

# Flagged, not decided (see module docstring): what a successful
# re-evaluation after the unsupervised window does. "stay_graduated"
# implements the current default; "reset_to_stage_0" is the
# alternative reading, switch this one constant if the operator picks it.
CHECKPOINT_REEVAL_POLICY = "stay_graduated"


class CheckpointState:
    """
    Persistent checkpoint/graduation state for the autonomous pipeline.
    Section 7 does not specify per-task-type state -- read literally,
    "every task holds... before Angkai implements" describes ONE
    global checkpoint, not one per task_type. This implementation is
    global by default; if a future brief revision wants per-task-type
    graduation (e.g. git-clone-class tasks graduate independently of
    systemctl-class tasks), that's a real, separate design change, not
    an extension of this module's current fields.: autonomy_progress_count is a NEW field, separate from
    graduated_run_count. graduated_run_count keeps its original meaning
    unchanged (progress toward the next 2-run re-eval check-in, reset
    every time that window completes); autonomy_progress_count is a
    running total of clean runs accumulated while in graduated_window
    that is NEVER reset by a re-eval window completing -- only by
    reaching fully_autonomous (success) or a non-clean run (reset to
    stage_0). The two counters intentionally track different things
    from the same clean runs.
    """

    def __init__(self, checkpoint_state=STAGE_0, clean_run_count=0,
                 graduated_run_count=0, autonomy_progress_count=0):
        self.checkpoint_state = checkpoint_state
        self.clean_run_count = clean_run_count
        self.graduated_run_count = graduated_run_count
        self.autonomy_progress_count = autonomy_progress_count

    def to_dict(self):
        return {
            "checkpoint_state": self.checkpoint_state,
            "clean_run_count": self.clean_run_count,
            "graduated_run_count": self.graduated_run_count,
            "autonomy_progress_count": self.autonomy_progress_count,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            checkpoint_state=d.get("checkpoint_state", STAGE_0),
            clean_run_count=d.get("clean_run_count", 0),
            graduated_run_count=d.get("graduated_run_count", 0),
            autonomy_progress_count=d.get("autonomy_progress_count", 0),
        )

    def record_run(self, is_clean: bool, reason: str = ""):
        """
        Apply section 7's graduation/reset rule for one completed run,
        extended by for the fully_autonomous terminal state.
        Returns a short human-readable transition description for the
        audit log (section 12.5).
        """
        if not is_clean:
            #: this branch is state-agnostic by construction --
            # it runs before any state-specific logic below and does not
            # inspect which state it came from. That is exactly what
            # makes the reset ASYMMETRIC: fully_autonomous falls straight
            # to stage_0 in one step, the same as graduated_window or
            # stage_0 itself would, never pausing at an intermediate
            # state. Adding fully_autonomous therefore required zeroing
            # the one new counter here, not new branching.
            prior = self.checkpoint_state
            self.checkpoint_state = STAGE_0
            self.clean_run_count = 0
            self.graduated_run_count = 0
            self.autonomy_progress_count = 0
            return (
                f"RESET: non-clean run ({reason}) -- checkpoint_state "
                f"{prior} -> {STAGE_0}, all counters zeroed. "
                f"Non-negotiable per section 7 reset rule."
            )

        if self.checkpoint_state == STAGE_0:
            self.clean_run_count += 1
            if self.clean_run_count >= GRADUATION_THRESHOLD:
                self.checkpoint_state = GRADUATED_WINDOW
                self.clean_run_count = 0
                self.graduated_run_count = 0
                return (
                    f"GRADUATED: {GRADUATION_THRESHOLD} consecutive clean "
                    f"runs reached -- checkpoint_state stage_0 -> "
                    f"graduated_window."
                )
            return (
                f"CLEAN (stage_0): clean_run_count now "
                f"{self.clean_run_count}/{GRADUATION_THRESHOLD}."
            )

        if self.checkpoint_state == GRADUATED_WINDOW:
            self.graduated_run_count += 1
            self.autonomy_progress_count += 1

            #: promotion to fully_autonomous is checked first,
            # ahead of the existing re-eval-due check below -- reaching
            # full autonomy is the more significant milestone, and takes
            # priority in the (possible) case both thresholds land on
            # the same run.
            if self.autonomy_progress_count >= AUTONOMY_THRESHOLD:
                self.checkpoint_state = FULLY_AUTONOMOUS
                self.graduated_run_count = 0
                self.autonomy_progress_count = 0
                return (
                    f"FULLY AUTONOMOUS: {AUTONOMY_THRESHOLD} cumulative "
                    f"clean runs reached inside graduated_window -- "
                    f"checkpoint_state graduated_window -> "
                    f"fully_autonomous. Terminal on the clean path: no "
                    f"further periodic re-eval check-in required. "
                    f"Guardrails unchanged -- this only changes "
                    f"checkpoint cadence, never what counts as clean."
                )

            if self.graduated_run_count >= UNSUPERVISED_WINDOW:
                if CHECKPOINT_REEVAL_POLICY == "stay_graduated":
                    self.graduated_run_count = 0
                    return (
                        f"REEVAL DUE: {UNSUPERVISED_WINDOW} unsupervised "
                        f"runs complete, all clean -- policy="
                        f"stay_graduated, counters reset, checkpoint_state "
                        f"remains graduated_window pending the operator's "
                        f"re-evaluation check-in (per section 7; ntfy "
                        f"alert fires per section 10 pending_checkin case). "
                        f"Progress toward fully_autonomous unaffected: "
                        f"autonomy_progress_count now "
                        f"{self.autonomy_progress_count}/{AUTONOMY_THRESHOLD}."
                    )
                else:
                    self.checkpoint_state = STAGE_0
                    self.clean_run_count = 0
                    self.graduated_run_count = 0
                    self.autonomy_progress_count = 0
                    return (
                        f"REEVAL DUE: {UNSUPERVISED_WINDOW} unsupervised "
                        f"runs complete, all clean -- policy="
                        f"reset_to_stage_0, checkpoint_state reset for a "
                        f"fresh graduation buildup pending the operator's "
                        f"re-evaluation check-in."
                    )
            return (
                f"CLEAN (graduated_window): graduated_run_count now "
                f"{self.graduated_run_count}/{UNSUPERVISED_WINDOW}, "
                f"autonomy_progress_count now "
                f"{self.autonomy_progress_count}/{AUTONOMY_THRESHOLD}."
            )

        if self.checkpoint_state == FULLY_AUTONOMOUS:
            #: genuinely terminal on the clean path -- no counter
            # advances further, no periodic re-eval requirement. The
            # non-clean branch above is the ONLY way out of this state.
            return (
                "CLEAN (fully_autonomous): terminal state, no counters "
                "to advance, no periodic check-in required."
            )

        # Should be unreachable given the three states above always
        # normalize back to stage_0, graduated_window, or
        # fully_autonomous -- defensive.
        raise ValueError(f"Unknown checkpoint_state: {self.checkpoint_state}")


# ---------------------------------------------------------------------------
# Section 8.3 task object + section 13's max_tool_calls extension
# ---------------------------------------------------------------------------

TASK_TYPES = {"brief", "execute", "synthesize", "verify"}
STATUSES = {
    "queued", "claimed", "in_progress", "pending_checkin",
    "complete", "failed", "escalated",
}
PRIORITIES = {"low", "normal", "high"}


@dataclass
class GovernanceVerdict:
    """One filter's individual verdict -- section 12.4's requirement
    that governance_checks record actual per-filter results, not just
    which checks ran."""
    filter_name: str
    passed: bool
    detail: str = ""


@dataclass
class KaijuA2ATask:
    task_id: str
    origin_agent: str
    target_agent: str
    task_type: str
    payload_ref: str
    priority: str
    status: str
    checkpoint_state: str
    clean_run_count: int
    created_at: str
    governance_checks: list = field(default_factory=list)
    max_tool_calls: Optional[int] = None  # section 13 extension

    def __post_init__(self):
        if self.task_type not in TASK_TYPES:
            raise ValueError(f"invalid task_type: {self.task_type}")
        if self.status not in STATUSES:
            raise ValueError(f"invalid status: {self.status}")
        if self.priority not in PRIORITIES:
            raise ValueError(f"invalid priority: {self.priority}")

    def to_json(self):
        d = asdict(self)
        d["governance_checks"] = [asdict(v) for v in self.governance_checks]
        return json.dumps(d, indent=2)


def new_task(origin_agent, target_agent, task_type, payload_ref,
             checkpoint: CheckpointState, priority="normal",
             max_tool_calls=None):
    """
    Create a new task object, stamping it with the CURRENT checkpoint
    state (section 7's fields live on the task object per 8.3's
    schema, sourced from the persistent CheckpointState tracker at
    creation time -- not independently tracked per-task).
    """
    return KaijuA2ATask(
        task_id=str(uuid.uuid4()),
        origin_agent=origin_agent,
        target_agent=target_agent,
        task_type=task_type,
        payload_ref=payload_ref,
        priority=priority,
        status="queued",
        checkpoint_state=checkpoint.checkpoint_state,
        clean_run_count=checkpoint.clean_run_count,
        created_at=datetime.now(timezone.utc).isoformat(),
        max_tool_calls=max_tool_calls,
    )


def evaluate_run_clean(stage_name, check_warnings, hard_stop_fired=False,
                        stage_errored=False):
    """
    Determine whether a completed run counts as "clean" per section 7's
    definition: passes all section 6 filter checks AND does not trigger
    section 6.1/13's hard-stop filters, without requiring a correction
    at check-in.

    Reuses checkpoint_gate.should_checkpoint() (build-from-existing) for
    the section-6-filter-warnings half of the definition, then ANDs in
    the section 6.1/13 hard-stop result explicitly -- should_checkpoint()
    has no notion of hard-stop filters at all (they didn't exist when it
    was written), so this is not something the reused function already
    covers on its own. note: this function is UNCHANGED by the fully_autonomous
    addition -- "clean" is defined identically regardless of
    checkpoint_state, which is exactly what "guardrails never loosen"
    means in code terms. fully_autonomous changes what CheckpointState.
    record_run() does with an is_clean result, never how is_clean
    itself gets computed.
    """
    mandatory, reason = should_checkpoint(stage_name, check_warnings, stage_errored)
    if hard_stop_fired:
        return False, f"hard-stop filter fired (permanent, non-graduating): {reason}"
    if mandatory:
        return False, reason
    return True, reason


def record_governance_verdicts(task: KaijuA2ATask, verdicts: list):
    """
    Populate governance_checks with actual per-filter verdicts (section
    12.4) -- not just a list of check names. `verdicts` is a list of
    GovernanceVerdict.
    """
    task.governance_checks = list(verdicts)
    return task


# ---------------------------------------------------------------------------
# Persistence -- checkpoint state file location (DECIDED 2026-08-27, part 7
# continuation session): VAULT Health/ directory, matching section 10's
# established convention for continuously-generated operational data
# (same directory A2A_Activity_Log.jsonl is specified to live in). A single
# small JSON object, not an append-only log -- checkpoint state changes IN
# PLACE with every run, it doesn't accumulate history (history lives in the
# activity log instead, per section 10). Logic-tested, 5/5 cases pass
# (test_kaiju_a2a_task_schema_persistence.py, kaiju-relay/): missing-file
# bootstrap, save/load round-trip, correct file path with valid JSON,
# no leftover .tmp after a successful write, and a graduation transition
# surviving a save/load cycle.
#
#: from_dict()'s .get("autonomy_progress_count", 0) default means
# an OLDER on-disk checkpoint file (written before this field existed)
# loads cleanly as autonomy_progress_count=0 -- no migration step needed,
# same pattern the existing fields already rely on.
# ---------------------------------------------------------------------------

CHECKPOINT_STATE_PATH = "Health/a2a_checkpoint_state.json"  # relative to VAULT root


def load_checkpoint_state(vault_root: str) -> "CheckpointState":
    """
    Load persisted checkpoint state from VAULT Health/a2a_checkpoint_state.json.
    Missing file = fresh Stage 0 state (first-ever run), not an error --
    matches the natural bootstrap case.
    """
    path = os.path.join(vault_root, CHECKPOINT_STATE_PATH)
    if not os.path.exists(path):
        return CheckpointState()
    with open(path, "r") as f:
        return CheckpointState.from_dict(json.load(f))


def save_checkpoint_state(vault_root: str, state: "CheckpointState") -> None:
    """
    Persist checkpoint state. Writes to a temp file then renames (atomic on
    the same filesystem) so a crash mid-write never leaves a corrupt/partial
    JSON file behind -- this file is read on every single task creation, so
    corruption would be a real, immediate pipeline-wide failure, not a
    cosmetic one.
    """
    path = os.path.join(vault_root, CHECKPOINT_STATE_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(state.to_dict(), f, indent=2)
    os.replace(tmp_path, path)
