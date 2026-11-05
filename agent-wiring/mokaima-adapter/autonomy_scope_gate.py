"""
autonomy_scope_gate.py -- AUTONOMY SCOPE DECISION runtime
enforcement (decided 2026-08-29, part 10 continuation; explicitly
flagged as "no automation currently checks this policy at run time"
in AIOPS_PENDING.md -- this is that automation, built 2026-09-05,
"Mokaima help 1.1 Full Auto Angkai" part 2, as the accepted result
of that same session's self-origination scan Step 3 review).

Enforces two things, both from the decision text directly:
  1. TASK CATEGORY ELIGIBILITY: classifies an ExecutionContract into
     one of the 3 decided-eligible categories (VAULT ticket/
     documentation writes; Angkai single-command brief dispatch;
     Bakaidah read-only triage/diagnosis) or "out_of_scope" if it fits
     none of them. Only the 3 named categories get FULLY AUTONOMOUS
     EXECUTION WITH MANDATORY POST-HOC REVIEW -- everything else
     requires live human confirmation regardless of checkpoint state.
  2. HARD-MANUAL EXCLUSIONS: the decision's own explicit list, true
     "at every autonomy level" -- credentials, direct installs,
     production-affecting changes (service restarts, live config
     touching running infra), SSH/docker/systemctl/sudo commands.

BUILD-FROM-EXISTING: hard_stop_credentials_installpath_filter.py
already catches credentials and install-path/install-style commands
(section 6.1's own scope: sudo, apt/pip install, curl|bash,
make install, systemctl enable/start specifically, dpkg -i, snap
install, plus credential-shaped strings). This module does NOT
re-implement that overlap -- it only adds the patterns the AUTONOMY
SCOPE DECISION names that section 6.1 does not already cover: generic
SSH usage, generic docker usage, systemctl as a whole command family
(not just enable/start), and a broader production-affecting keyword
set (restart/reload/redeploy/rollback/migrate/prune/rm -rf). Both
modules are called independently in kaiju_mokaima_step5_review.py's
review(), and either firing forces the same escalate_to_operator route
-- this module's job is the task-category/scope question specifically,
not a second credentials scanner.

DESIGN NOTE ON CLASSIFICATION, stated plainly rather than silently
assumed: an ExecutionContract (section 12.1's own structured shape)
carries target_path/command_type/command/justification/
evidence_references -- there is no explicit "task category" field
anywhere upstream of this call. The mapping below is therefore
NECESSARILY heuristic, built from what IS available:
  command_type == "write" AND target_path under the VAULT root  ->
    vault_write (category 1: VAULT ticket/documentation writes)
  command_type in ("read", "diagnostic")                        ->
    bakaidah_readonly_triage (category 3: read-only analysis/
    root-causing that doesn't touch live infra). "diagnostic" is
    an alias Bakaidah naturally uses for read-only inspection tasks
    and is treated as equivalent to "read" for classification
    purposes (added 2026-09-12, graduation session).
  command_type == "execute"                                     ->
    angkai_brief_dispatch (category 2: single-command, low-stakes
    Angkai dispatch -- Section 13's own hooks separately enforce
    the single-command/low-stakes requirement at execution time on
    Angkai's side; this classification recognizes the CATEGORY for
    the autonomy-scope question, it does not re-implement Section 13)
  command_type == "install"                                     ->
    out_of_scope (installs are excluded outright by the decision's
    own hard-manual list, independent of this module's own
    install-command pattern checks, which live in the sibling
    hard-stop filter instead)
  command_type == "write" outside the VAULT root                 ->
    out_of_scope (category 1 is specifically VAULT documentation
    writes, not writes in general -- a write to, say,
    /srv/data is a different, uncategorized kind of action)
A hard-manual exclusion pattern firing ALWAYS overrides an otherwise-
eligible category classification -- an VAULT write that happens to
embed a systemctl command in its own command string is still
out_of_scope, not vault_write.
"""

import os
import re
from dataclasses import dataclass, field
from typing import List


VAULT_ROOT_PREFIX = "/srv/vault"

CATEGORY_VAULT_WRITE = "vault_write"
CATEGORY_ANGKAI_BRIEF_DISPATCH = "angkai_brief_dispatch"
CATEGORY_BAKAIDAH_READONLY_TRIAGE = "bakaidah_readonly_triage"
CATEGORY_OUT_OF_SCOPE = "out_of_scope"
CATEGORY_KNOWN_FIX_SCRIPT_RUN = "known_fix_script_run"

ELIGIBLE_CATEGORIES = {
    CATEGORY_VAULT_WRITE,
    CATEGORY_ANGKAI_BRIEF_DISPATCH,
    CATEGORY_BAKAIDAH_READONLY_TRIAGE,
    CATEGORY_KNOWN_FIX_SCRIPT_RUN,
}


@dataclass
class AutonomyScopeVerdict:
    """Read-only verdict, same section 12.2 boundary as
    HardStopVerdict in the sibling module -- inspects and flags only,
    never mutates or blocks by itself. Routing is the caller's job."""
    eligible: bool
    category: str
    reasons: List[str] = field(default_factory=list)


# Hard-manual exclusion patterns NOT already covered by
# hard_stop_credentials_installpath_filter.py's own install-command
# patterns -- see module docstring's BUILD-FROM-EXISTING note.
_SSH_PATTERN = re.compile(r"\bssh\b")
_DOCKER_PATTERN = re.compile(r"\bdocker\b")
_SYSTEMCTL_ANY_PATTERN = re.compile(r"\bsystemctl\b")
_PRODUCTION_CHANGE_KEYWORDS = re.compile(
    r"\b(restart|reload|redeploy|rollback|migrate|prune|rm\s+-rf)\b",
    re.IGNORECASE,
)


def _check_hard_manual_exclusions(text: str) -> List[str]:
    reasons = []
    if not text:
        return reasons
    if _SSH_PATTERN.search(text):
        reasons.append(
            "contains 'ssh' -- SSH commands are explicitly hard-manual "
            "per the AUTONOMY SCOPE DECISION, regardless of "
            "checkpoint/graduation state"
        )
    if _DOCKER_PATTERN.search(text):
        reasons.append(
            "contains 'docker' -- Docker commands are explicitly "
            "hard-manual per the AUTONOMY SCOPE DECISION, "
            "regardless of checkpoint/graduation state"
        )
    if _SYSTEMCTL_ANY_PATTERN.search(text):
        reasons.append(
            "contains 'systemctl' -- systemctl commands are explicitly "
            "hard-manual per the AUTONOMY SCOPE DECISION (this "
            "check is broader than section 6.1's own systemctl "
            "enable/start pattern -- any systemctl verb qualifies here)"
        )
    m = _PRODUCTION_CHANGE_KEYWORDS.search(text)
    if m:
        reasons.append(
            f"contains production-affecting keyword '{m.group(0)}' -- "
            f"production-affecting changes are explicitly hard-manual "
            f"per the AUTONOMY SCOPE DECISION"
        )
    return reasons


# --- known_fix_script_run (S3b-2 amendment) --------------------------------
KNOWN_FIX_ALLOWLIST = os.environ.get("KAIJU_KNOWN_FIX_ALLOWLIST", "/etc/kaiju-os/known-fix-run.allow")
_KNOWN_FIX_EVIDENCE = re.compile(r"\A(incident|service):[A-Za-z0-9._-]+\Z")


def _known_fix_allowed(contract) -> bool:
    """True only on an exact allowlist line match (see module amendment note). Fail closed."""
    cmd = contract.command or ""
    parts = cmd.split(" ")
    if len(parts) != 3 or not contract.target_path or contract.target_path != parts[2]:
        return False
    for ref in (contract.evidence_references or []):
        if not isinstance(ref, str) or not _KNOWN_FIX_EVIDENCE.match(ref):
            return False
    try:
        with open(KNOWN_FIX_ALLOWLIST, "r", encoding="utf-8") as fh:
            for line in fh:
                s = line.rstrip("\n")
                if s and not s.startswith("#") and s == cmd:
                    return True
    except OSError:
        return False
    return False


def classify_task_category(contract) -> str:
    """
    Heuristic classification -- see module docstring for the mapping
    and its rationale. `contract` is an ExecutionContract (duck-typed:
    needs .command_type and .target_path).
    """
    command_type = contract.command_type
    target_path = contract.target_path or ""

    if command_type == "write":
        if target_path.startswith(VAULT_ROOT_PREFIX):
            return CATEGORY_VAULT_WRITE
        return CATEGORY_OUT_OF_SCOPE
    if command_type in ("read", "diagnostic"):
        return CATEGORY_BAKAIDAH_READONLY_TRIAGE
    if command_type == "execute":
        return CATEGORY_ANGKAI_BRIEF_DISPATCH
    if command_type == "known_fix_script_run":
        return (CATEGORY_KNOWN_FIX_SCRIPT_RUN if _known_fix_allowed(contract)
                else CATEGORY_OUT_OF_SCOPE)
    # "install" and any unrecognized command_type -> out of scope.
    return CATEGORY_OUT_OF_SCOPE


def evaluate_autonomy_scope(contract) -> AutonomyScopeVerdict:
    """
    Combines category classification with the hard-manual exclusion
    check. Eligible only if the category is one of the 3 decided
    eligible categories AND no hard-manual exclusion pattern fires
    anywhere in the command, justification, or evidence_references.
    """
    category = classify_task_category(contract)

    reasons = _check_hard_manual_exclusions(contract.command)
    if category != CATEGORY_KNOWN_FIX_SCRIPT_RUN:
        reasons += _check_hard_manual_exclusions(contract.justification)
        for ref in (contract.evidence_references or []):
            reasons += _check_hard_manual_exclusions(ref)

    if reasons:
        # A hard-manual exclusion pattern always overrides an
        # otherwise-eligible category classification.
        return AutonomyScopeVerdict(
            eligible=False, category=CATEGORY_OUT_OF_SCOPE, reasons=reasons
        )

    if category not in ELIGIBLE_CATEGORIES:
        return AutonomyScopeVerdict(
            eligible=False,
            category=category,
            reasons=[
                f"task category '{category}' is not one of the 3 "
                f"categories decided eligible for autonomous handling "
                f"under the AUTONOMY SCOPE DECISION "
                f"(vault_write, angkai_brief_dispatch, "
                f"bakaidah_readonly_triage) -- requires live human "
                f"confirmation regardless of checkpoint state"
            ],
        )

    return AutonomyScopeVerdict(eligible=True, category=category, reasons=[])
