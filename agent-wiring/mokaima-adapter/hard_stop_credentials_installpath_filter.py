"""
hard_stop_credentials_installpath_filter.py -- brief section 6.1's
"one genuine gap": a mechanical hard-stop for credentials / install-paths /
production actions in Bakaidah's proposed action, before it can reach
Angkai. Today this protection exists only as the BAKAIDAH-FIRST rule,
applied personally by Mokaima -- not automated. This is that automation.

Written 2026-08-27 (Daikaiju AIOps/ part 7), logic-tested
in Mokaima's sandbox (12/12 cases pass, including a real bug found and
fixed mid-build -- see below). Deployed 2026-08-27 (part 7 continuation
3) as a sibling-module dependency of kaiju_mokaima_a2a_adapter.py -- an
exact copy of the authoritative kaiju-relay/hard_stop_credentials_
installpath_filter.py.

SCOPE NOTE: this is Section 6.1's FIRST filter only (credentials/
install-path). Section 6.1's SECOND filter (self-initiated Plan Mode,
CHECK 2b) is a DIFFERENT component and was already built and deployed
live 2026-08-24 (validate-kaiju-relay-path.sh CHECK 2b) -- not
duplicated here. Section 12's five refinements and Section 13's three
hooks (action_budget/command_fidelity/output_shape) were also already
built and deployed live on 2026-08-24/25 -- this filter is the one
piece of "Section 6.1/12/13" that was genuinely still missing; the
rest already exists. Section 12.1's structured-execution-contract
requirement and section 12.2's hard read-only/no-mutate boundary are
both applied directly in this module's design (see below).

REAL BUG FOUND DURING LOGIC TESTING: the first credential-pattern
regex was \b-anchored on the left (\btoken\b etc.), which does NOT
match inside a prefixed identifier like HF_TOKEN or AWS_SECRET_ACCESS_
KEY -- underscore is a word character, so no boundary exists between
"_" and "T". Caught by a test case using a realistic HF_TOKEN=...
string (this project's own real Colibri work uses exactly this env
var). Fixed by dropping the left-side \b anchor and allowing an
optional identifier-prefix instead.

BUILD-FROM-EXISTING NOTE (per section 6.1's own instruction): the
credential-pattern half of this filter is real, tested pattern-
matching, not a placeholder -- but it is deliberately NOT an
integration of an external secret-scanning library (gitleaks/
detect-secrets family) as the brief suggests checking first. Reason:
neither is installable by Mokaima directly (no intake-host shell access;
would need a full INSTALL PATH RULE dry-run/approval cycle run by
the operator/Angkai). This module ships a self-contained, dependency-free
regex-based implementation now (matches this project's existing
Filter style -- Reference Existence, Incident Fabrication, etc. are
all hand-rolled pattern checks, not library integrations) and flags
detect-secrets as a genuine future strengthening candidate, not a
blocker -- consistent with's "smallest tool that solves it"
precedent (LangGraph rejected there for the same reasoning).
"""

import re
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Section 12.1: structured execution contract (not free-form prose)
# ---------------------------------------------------------------------------

@dataclass
class ExecutionContract:
    """
    Bakaidah's proposed action, as handed to this filter. Structured per
    section 12.1 specifically so the filter can pattern-match
    mechanically rather than parsing narrative text.
    """
    target_path: str
    command_type: str          # "install" | "write" | "execute" | "read"
    command: str                # the actual proposed command string
    justification: str = ""
    evidence_references: list = field(default_factory=list)


@dataclass
class HardStopVerdict:
    """
    Section 12.2: this filter inspects and flags only -- it never
    auto-edits, auto-approves, or executes. The verdict is read-only
    output for Mokaima/the gateway to act on, never a mutation itself.
    """
    passed: bool
    reasons: list           # empty if passed
    category: str = "credentials_installpath"  # for section 12.4 traceability


# ---------------------------------------------------------------------------
# Protected-zone / install-path detection (INSTALL PATH RULE)
# ---------------------------------------------------------------------------

# Per the standing INSTALL PATH RULE: nothing installs to boot, EFI,
# swap, root (/), or home (/home) without explicit approval; all AI
# stack software goes to /srv.
_PROTECTED_PATH_PREFIXES = (
    "/boot", "/efi", "/EFI", "/swap", "/home",
)
_APPROVED_INSTALL_ROOT = "/srv"


def _check_install_path(contract: ExecutionContract) -> list:
    reasons = []
    path = contract.target_path or ""
    normalized = path.rstrip("/")

    if normalized == "" or normalized == "/":
        reasons.append(f"target_path is root (/) -- protected zone, explicit approval required")
        return reasons

    for prefix in _PROTECTED_PATH_PREFIXES:
        if normalized == prefix or normalized.startswith(prefix + "/"):
            reasons.append(
                f"target_path '{path}' falls under protected zone '{prefix}' "
                f"-- INSTALL PATH RULE requires explicit approval"
            )
            return reasons

    if contract.command_type == "install" and not normalized.startswith(_APPROVED_INSTALL_ROOT):
        reasons.append(
            f"command_type='install' targeting '{path}', which is outside "
            f"the approved install root ({_APPROVED_INSTALL_ROOT}) -- "
            f"INSTALL PATH RULE requires all AI stack software under "
            f"{_APPROVED_INSTALL_ROOT}"
        )

    return reasons


# ---------------------------------------------------------------------------
# sudo / install-style command detection
# ---------------------------------------------------------------------------

_INSTALL_COMMAND_PATTERNS = [
    re.compile(r"\bsudo\b"),
    re.compile(r"\bapt(-get)?\s+install\b"),
    re.compile(r"\bpip3?\s+install\b(?!.*--target[= ]/srv)"),
    re.compile(r"curl[^|]*\|\s*(sh|bash)\b"),
    re.compile(r"wget[^|]*\|\s*(sh|bash)\b"),
    re.compile(r"\bmake\s+install\b"),
    re.compile(r"\bsystemctl\s+(enable|start)\b"),
    re.compile(r"\bdpkg\s+-i\b"),
    re.compile(r"\bsnap\s+install\b"),
]


def _check_install_style_command(contract: ExecutionContract) -> list:
    reasons = []
    cmd = contract.command or ""
    for pattern in _INSTALL_COMMAND_PATTERNS:
        m = pattern.search(cmd)
        if m:
            reasons.append(
                f"command contains install/privilege-escalation pattern "
                f"'{m.group(0)}' -- requires explicit approval per "
                f"INSTALL PATH RULE"
            )
    return reasons


# ---------------------------------------------------------------------------
# Credential-shaped string detection (self-contained regex, see module
# docstring for the build-from-existing rationale on not vendoring an
# external scanner)
# ---------------------------------------------------------------------------

_CREDENTIAL_PATTERNS = [
    ("generic_secret_assignment",
     # Not \b-anchored on the left: real credential env-var names are
     # routinely prefixed (HF_TOKEN, AWS_SECRET_ACCESS_KEY, DB_PASSWORD)
     # and \b doesn't fire between two word characters like '_' and 'T'.
     re.compile(r"(?i)[A-Za-z0-9_]*(api[_-]?key|secret|token|password|passwd|pwd|access[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9+/=_\-]{8,}")),
    ("aws_access_key_id",
     re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key_header",
     re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("bearer_token",
     re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-_.]{20,}")),
    ("slack_token",
     re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
]


def _check_credential_strings(text: str) -> list:
    reasons = []
    if not text:
        return reasons
    for name, pattern in _CREDENTIAL_PATTERNS:
        m = pattern.search(text)
        if m:
            # Never echo the actual matched secret text into a log/verdict --
            # report the category and position only.
            reasons.append(
                f"credential-shaped string detected (pattern: {name}) at "
                f"offset {m.start()} -- value redacted from this verdict"
            )
    return reasons


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def evaluate(contract: ExecutionContract) -> HardStopVerdict:
    """
    Section 6.1's mechanical hard-stop check. Read-only (section 12.2) --
    returns a verdict, never mutates the contract or takes any action
    itself. Behavior on a non-passing verdict (routing to the operator,
    never-auto-block-permanently, never-graduates-away) is the CALLER's
    responsibility (the gateway / Mokaima's Step 5 review), not this
    function's -- this function only detects and reports.
    """
    reasons = []
    reasons += _check_install_path(contract)
    reasons += _check_install_style_command(contract)
    reasons += _check_credential_strings(contract.command)
    reasons += _check_credential_strings(contract.justification)
    for ref in contract.evidence_references:
        reasons += _check_credential_strings(ref)

    return HardStopVerdict(passed=(len(reasons) == 0), reasons=reasons)
