"""
kaiju_mokaima_step5_review.py -- brief section 4's Mokaima role
("the funnel and Step 5 verification checkpoint") and section 6/6.1/7's
combined review logic, wired together for the first time.

Written 2026-08-27 (Daikaiju AIOps/ part 7 continuation),
logic-tested in Mokaima's sandbox, 5/5 cases pass (test_step5_review.py,
also in kaiju-relay/). This is the DECISION LOGIC for Mokaima's Step 5
review -- it is now wrapped by kaiju_mokaima_a2a_adapter.py, the real MCP
server for brief section 8.2's "Mokaima adapter" ("MCP tool letting
Mokaima emit A2A task objects to Bakaidah directly, receive Bakaidah's
output, run verification (section 6), and either hold for check-in or
release per checkpoint state."), built 2026-08-27 (part 7 continuation
3) with the operator's explicit go-ahead. This module remains the reusable
business logic that server's review_bakaidah_output tool calls -- kept
as its own file rather than inlined, so it stays independently
testable (5/5 tests) apart from the MCP protocol layer.

Combines, in one place:
  - hard_stop_credentials_installpath_filter.evaluate() -- section 6.1
  - autonomy_scope_gate.evaluate_autonomy_scope() -- the
    AUTONOMY SCOPE DECISION's own runtime enforcement (see below)
  - kaiju_a2a_task_schema.evaluate_run_clean() -- section 7's "clean run"
    definition, itself wrapping checkpoint_gate.should_checkpoint()
  - kaiju_a2a_task_schema.CheckpointState.record_run() -- section 7's
    graduation/reset state machine
  - kaiju_a2a_task_schema.record_governance_verdicts() -- section 12.4

Section 6's five EXISTING live Bakaidah filters (Reference Existence,
Citation Grounding, Incident Fabrication, Diagnostic History, Enforcement
Gate, 2 MABS filters) are NOT reimplemented here -- per the brief, Mokaima's
job is to READ their already-fired results, not re-derive them. This
module's `section6_warnings` parameter is where those real results get
fed in; this module has no way to call those filters itself (they run
inside Bakaidah's own Open WebUI Filter chain, a different system this
module doesn't reach into). UPDATE (design locked, build this session -- "Mokaima help 1.1
Full Auto Angkai" part 2): the release-without-checkpoint branch below
now matches BOTH graduated_window and the new fully_autonomous terminal
state (see kaiju_a2a_task_schema.py's own docstring section for
the full state-machine change) -- both states release a clean, non-hard-
stopped run without a Mokaima check-in, per section 7's original
graduated_window rule. AUTONOMY SCOPE GATE UPDATE (same session, "Mokaima help 1.1 Full
Auto Angkai" part 2, built as the accepted result of this session's
Bakaidah self-origination scan Step 3 review): the AUTONOMY SCOPE
DECISION (2026-08-29) was flagged in AIOPS_PENDING.md as "no automation
currently checks this policy at run time" -- autonomy_scope_gate.py is
that automation. evaluate_autonomy_scope() runs alongside
evaluate_hard_stop() below (same priority level, same
escalate-to-the operator consequence when it fires) -- a task whose category
isn't one of the 3 decided-eligible categories (VAULT writes, Angkai
single-command dispatch, Bakaidah read-only triage), OR whose command
touches SSH/docker/systemctl/production-affecting keywords regardless of
category, is treated exactly like a hard-stop firing: never masked by an
otherwise-clean section 6 result, never graduates away, always routes to
the operator specifically. This is intentionally analogous to (not a duplicate
of) the existing hard-stop check -- see autonomy_scope_gate.py's own
BUILD-FROM-EXISTING note for which patterns each module owns. UPDATE (2026-09-24): record_run()'s transition string has always
CLAIMED "ntfy alert fires per section 10 pending_checkin case" but no
notification dispatch code existed anywhere in this file or its
dependencies -- confirmed by direct read of this file, checkpoint_gate.py,
and kaiju_a2a_task_schema.py, none of which contain any network call.
checkpoint_ntfy.notify_checkpoint_event() is the real
implementation, called here right after record_run() returns. It is a
best-effort side effect: wrapped so a notification failure can never
alter or block the governance decision already made above it. NEUTRAL-ESCALATION UPDATE (2026-09-26, the operator's decision, Full
Auto part 13): a CORRECT escalation -- the hard-stop filter or autonomy
scope gate routing a request to the operator, with no section 6 warning and no
stage error -- no longer calls record_run() and therefore no longer
resets the ladder to stage_0. It is not counted as a clean run either:
the checkpoint is left exactly as it was. Three prior resets (2026-09-17,
09-24, 09-26) were all correct escalations punished as failures. The
route is unchanged (still escalate_to_operator), and the escalation still
notifies the operator via 's "NEUTRAL:" branch, because before this change
the RESET alert was the only out-of-band signal an escalation produced.
An escalation that coincides with a real section 6 warning or a stage
error still resets, exactly as before. Tested 9/9 on intake-host
2026-09-26 against the real filter/gate/state machine (staging:
angkai/staging/-neutral-escalation/). Previous version:
kaiju_mokaima_step5_review.py.bak-kai054neutral-20260926.

MANUAL-REVIEW-OVERRIDE UPDATE (2026-09-30, Full Auto part 15): before
this change, the only inputs that could make a run non-clean were
section6_warnings (Bakaidah's own live filters) and stage_errored (the
call itself failing) -- there was no way for Mokaima's OWN independent
line-by-line check of a Bakaidah reply against its source to affect the
result at all. Found live: a real cross-date value misattribution (a
genuine string, attached to the wrong report) that no existing filter
was built to catch passed as clean_run_count 2/4, even though Mokaima's
manual check had already flagged it as a defect in the same call's own
justification text -- the justification was logged for the record but
never reached the actual is_clean/checkpoint computation below.

Fix: a new `manual_review_findings` parameter, same shape as
section6_warnings (a list of finding strings) but a DISTINCT provenance
-- tagged in governance_checks as filter_name="mokaima_manual_review",
never conflated with "section6_existing_filter" entries, so the audit
trail always shows whether a given call's non-clean verdict came from
Bakaidah's own filters or from Mokaima's independent check. Functionally,
the two lists are combined (`all_warnings`) before feeding is_clean/
checkpoint/correctly-escalated logic -- a manual finding forces exactly
the same non-clean, ladder-resetting consequence a section6 warning
always has, no new code path, no special case in the state machine
itself. A manual finding also correctly prevents the NEUTRAL-ESCALATION
branch above from firing in the (rare) case both conditions coincide --
correctly_escalated requires `not all_warnings`, not just `not
section6_warnings`, so a real defect is never silently absorbed into a
neutral, checkpoint-unchanged escalation.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from hard_stop_credentials_installpath_filter import ExecutionContract, evaluate as evaluate_hard_stop
from autonomy_scope_gate import evaluate_autonomy_scope
from kaiju_a2a_task_schema import (
    CheckpointState, GovernanceVerdict, evaluate_run_clean,
    record_governance_verdicts, GRADUATED_WINDOW, FULLY_AUTONOMOUS,
)
from checkpoint_ntfy import notify_checkpoint_event


ROUTE_RELEASE_TO_ANGKAI = "release_to_angkai"
ROUTE_HOLD_FOR_CHECKIN = "hold_for_checkin"
ROUTE_ESCALATE_TO_OPERATOR = "escalate_to_operator"

_RELEASE_STATES = (GRADUATED_WINDOW, FULLY_AUTONOMOUS)

ACTIVITY_LOG_PATH = "Health/A2A_Activity_Log.jsonl"  # relative to VAULT root


@dataclass
class Step5ReviewResult:
    route: str
    governance_checks: list
    checkpoint_transition: str
    is_clean_run: bool
    reasons: list


def append_activity_log(vault_root: str, task_id: Optional[str],
                         contract: ExecutionContract,
                         result: "Step5ReviewResult") -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task_id": task_id,
        "target_path": contract.target_path,
        "command_type": contract.command_type,
        "route": result.route,
        "is_clean_run": result.is_clean_run,
        "checkpoint_transition": result.checkpoint_transition,
        "reasons": result.reasons,
        "governance_checks": [
            {"filter_name": v.filter_name, "passed": v.passed, "detail": v.detail}
            for v in result.governance_checks
        ],
    }
    try:
        path = os.path.join(vault_root, ACTIVITY_LOG_PATH)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def review(contract: ExecutionContract, section6_warnings: list,
           checkpoint: CheckpointState, stage_errored: bool = False,
           task_id: Optional[str] = None,
           vault_root: Optional[str] = None,
           manual_review_findings: Optional[list] = None) -> Step5ReviewResult:
    hard_stop_verdict = evaluate_hard_stop(contract)
    autonomy_verdict = evaluate_autonomy_scope(contract)

    governance_checks = [
        GovernanceVerdict(
            filter_name="hard_stop_credentials_installpath_filter",
            passed=hard_stop_verdict.passed,
            detail="; ".join(hard_stop_verdict.reasons) if hard_stop_verdict.reasons else "clean",
        ),
        GovernanceVerdict(
            filter_name="autonomy_scope_gate",
            passed=autonomy_verdict.eligible,
            detail=(
                "; ".join(autonomy_verdict.reasons) if autonomy_verdict.reasons
                else f"category={autonomy_verdict.category}, eligible"
            ),
        ),
    ]
    for w in section6_warnings:
        governance_checks.append(GovernanceVerdict(
            filter_name="section6_existing_filter", passed=False, detail=w,
        ))
    # MANUAL-REVIEW-OVERRIDE (2026-09-30): tagged separately from the loop
    # above so the audit trail always shows provenance -- a manual finding
    # is Mokaima's own line-by-line check, never a live Bakaidah filter, and
    # the two must never be conflated under the same filter_name.
    for w in (manual_review_findings or []):
        governance_checks.append(GovernanceVerdict(
            filter_name="mokaima_manual_review", passed=False, detail=w,
        ))

    # Combined warning set feeding every downstream clean/checkpoint
    # decision below -- a manual finding has exactly the same consequence
    # as a section6 warning, just a different origin.
    all_warnings = list(section6_warnings) + list(manual_review_findings or [])

    scope_blocked = not autonomy_verdict.eligible
    escalated = (not hard_stop_verdict.passed) or scope_blocked

    # NEUTRAL-ESCALATION DECISION (the operator, 2026-09-26): a request
    # that the hard-stop filter or the autonomy scope gate CORRECTLY routes
    # to the operator is the system working as designed, not a failed run -- it
    # must not reset the ladder. It also does not count as clean. Scope is
    # deliberately narrow: only when NOTHING else went wrong (no section 6
    # warning, no manual-review finding, no stage error). An escalation
    # that coincides with a real section 6 warning, a manual finding, or a
    # stage error still goes through record_run() and resets, exactly as
    # before. The escalation still notifies the operator ( "NEUTRAL:"
    # branch) -- before this change the RESET alert was the only
    # out-of-band signal an escalation produced.
    correctly_escalated = escalated and not all_warnings and not stage_errored

    if correctly_escalated:
        is_clean = False
        transition = (
            "NEUTRAL: correctly escalated to the operator (hard-manual per the "
            "hard-stop filter / autonomy scope gate) -- not counted as a run, "
            "checkpoint unchanged: " + json.dumps(checkpoint.to_dict())
            + ". Per the operator's neutral-escalation decision 2026-09-26."
        )
    else:
        is_clean, clean_reason = evaluate_run_clean(
            stage_name="bakaidah_output_review",
            check_warnings=all_warnings,
            hard_stop_fired=escalated,
            stage_errored=stage_errored,
        )
        transition = checkpoint.record_run(is_clean, reason=clean_reason)

    #: best-effort only -- never let this affect the route/result below.
    try:
        notify_checkpoint_event(transition)
    except Exception:  # noqa: BLE001
        pass

    if not hard_stop_verdict.passed:
        route = ROUTE_ESCALATE_TO_OPERATOR
        reasons = list(hard_stop_verdict.reasons)
    elif scope_blocked:
        route = ROUTE_ESCALATE_TO_OPERATOR
        reasons = list(autonomy_verdict.reasons)
    elif not is_clean:
        route = ROUTE_HOLD_FOR_CHECKIN
        reasons = list(all_warnings)
    elif checkpoint.checkpoint_state in _RELEASE_STATES:
        route = ROUTE_RELEASE_TO_ANGKAI
        reasons = []
    else:
        route = ROUTE_HOLD_FOR_CHECKIN
        reasons = []

    result = Step5ReviewResult(
        route=route,
        governance_checks=governance_checks,
        checkpoint_transition=transition,
        is_clean_run=is_clean,
        reasons=reasons,
    )

    if vault_root is not None:
        append_activity_log(vault_root, task_id, contract, result)

    return result
