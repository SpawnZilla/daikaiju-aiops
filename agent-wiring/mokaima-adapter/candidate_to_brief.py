"""
candidate_to_brief.py

Closes the "queued candidate -> real brief" gap in's
self-origination flow. bakaidah_self_origination_scan.py already queues
scan results to Health/Self_Origination_Candidates.jsonl, but nothing
turns an accepted candidate into a real dispatched task -- that hop has
been 100% manual since the scanner was built.

REAL QUEUE SCHEMA (corrected 2026-09-05, part 3, after reading the
actual live file on disk -- an earlier version of this module assumed
a flat one-record-per-candidate schema with a candidate_id field on
each record; the real file has neither):
  Each LINE in the JSONL file is one SCAN RUN, not one candidate:
    {"scan_timestamp": "...", "origin_agent": "...",
     "candidates": [{"title":..., "source_doc":..., "justification":...,
                      "cited_reference":...}, ...],
     "gate_warnings": [...], "error": ..., "raw_reply_present": ...}
  Individual candidates inside "candidates" have NO id field of their
  own. This module computes a stable candidate_id deterministically
  from (scan_timestamp, position within that scan's candidates list,
  cited_reference) via _compute_candidate_id() -- never stored
  separately, always re-derivable from the same scan record, so two
  runs of this module against the same on-disk data always agree on
  the same ids without needing a migration step.

This module does exactly one thing: given a candidate_id that Step 3
review has ALREADY ACCEPTED (this never runs on unreviewed or rejected
candidates -- that would bypass the checkpoint's own design
requires), it:

  1. Locates the candidate's (scan-line, position) inside the JSONL
     queue by its computed candidate_id.
  2. Builds a brief document in the project's existing brief format,
     from the REAL fields the scanner actually produces (title,
     source_doc, justification, cited_reference -- not the
     description/proposed_action fields an earlier draft of this
     module assumed).
  3. Stamps origin_candidate_id onto the brief for traceability, and
     calls record_origination_outcome(True) itself right here at the
     Step 3 accept decision -- see the correction note further down in
     this docstring for why that's Step 3, not Step 5.
  4. Writes the brief to VAULT's briefs directory (via the same VAULT
     write path Mokaima already uses -- vault_write_fn is injected so
     this module has no hard dependency on any specific MCP client).
  5. Marks that specific candidate (in place, inside its scan record)
     as dispatched -- the scan record itself, and every OTHER
     candidate in it, are preserved byte-for-byte; only the one
     matched candidate dict gains dispatched_brief_id/dispatched_at
     fields. The file is never truncated or re-ordered.

Explicitly OUT of scope for this module, by design:
  - It does not decide accept/reject on ITS OWN authority. The caller
    (Mokaima's Step 3 review flow) has already made that decision before
    either dispatch_accepted_candidate() or reject_candidate() is
    called -- this module records the consequence of that decision, it
    does not make it.
  - It does not talk to autonomy_scope_gate.py or Step 5 at all. This
    only produces the brief; Step 5 reviews it exactly like any other
    brief, autonomy-scope-gated exactly the same way.

record_origination_outcome() WIRING (2026-09-05, part 3): originally
planned to be wired into kaiju_mokaima_step5_review.py, keyed on an
origin_candidate_id field threaded through the task schema. Reading the
real record_origination_outcome() (bakaidah_self_origination_scan.py)
showed that plan was wrong -- its actual signature is
record_origination_outcome(accepted: bool), a plain global counter
bump, and its own docstring says explicitly it's for Mokaima's STEP 3
review flow to call, not Step 5. Step 5 reviews Bakaidah's already-
produced output for an existing task (a different pipeline stage,
different cardinality -- one task can pass through Step 5 multiple
times); calling the outcome recorder from there would risk miscounting
against what the track record is actually supposed to mean. So the
call lives here instead, at the actual Step 3 accept/reject decision
point, with no schema changes to ExecutionContract or KaijuA2ATask
needed anywhere.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Tuple


def _load_record_origination_outcome():
    """
    record_origination_outcome() lives in bakaidah_self_origination_scan.py,
    a sibling module in a DIFFERENT directory
    (/srv/data) than this file
    (/srv/adapters/mokaima-a2a-adapter/) -- same host, per
    that module's own docstring ("this script runs on intake-host, the
    same host the VAULT mount lives on"), just a different project
    directory. Loaded via importlib from an explicit path rather than a
    package-relative import, matching the project's existing
    cross-directory pattern (bakaidah_self_origination_scan.py itself
    does the equivalent sys.path.insert() trick to reach
    bakaidah_filter_check.py in its own directory) -- here the target
    directory is different from this file's own, so importlib's
    spec-from-file-location form is used instead of a bare sys.path
    insert, to avoid silently shadowing an unrelated same-named module
    if one ever exists on this host's default path.

    The directory is configurable via the BAKAIDAH_A2A_DIR environment
    variable so this module stays testable without touching the real
    path, and so a real path change on intake-host doesn't require an
    edit to this file.
    """
    bakaidah_a2a_dir = os.environ.get(
        "BAKAIDAH_A2A_DIR", "/srv/data"
    )
    module_path = os.path.join(bakaidah_a2a_dir, "bakaidah_self_origination_scan.py")
    spec = importlib.util.spec_from_file_location(
        "bakaidah_self_origination_scan", module_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(
            f"Could not load bakaidah_self_origination_scan.py from {module_path}"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.record_origination_outcome


class CandidateNotFoundError(Exception):
    pass


class CandidateAlreadyDispatchedError(Exception):
    pass


class CandidateAlreadyRejectedError(Exception):
    pass


@dataclass
class DispatchedBrief:
    brief_id: str
    origin_candidate_id: str
    title: str
    body: str
    created_at: str
    brief_path: str


@dataclass
class RejectedCandidate:
    candidate_id: str
    reason: str
    rejected_at: str


def _compute_candidate_id(scan_timestamp: str, position: int, cited_reference: str) -> str:
    """
    Deterministic id for one candidate inside one scan record. Never
    stored separately from the scan record itself -- re-derived the
    same way every time from (scan_timestamp, position, cited_reference),
    so this module never needs a migration step for scan records written
    before this module existed (every historical record already has all
    three inputs).
    """
    key = f"{scan_timestamp}|{position}|{cited_reference}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def _load_scan_records(queue_path: Path) -> list[dict]:
    """Read the JSONL queue. Each line is one SCAN RUN (with a nested
    'candidates' list), not one candidate -- see module docstring."""
    if not queue_path.exists():
        raise CandidateNotFoundError(
            f"Candidate queue not found at {queue_path}"
        )
    records = []
    with queue_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Malformed JSONL at {queue_path}:{line_no}: {exc}"
                ) from exc
    return records


def _find_candidate(
    records: list[dict], candidate_id: str
) -> Tuple[int, int, dict]:
    """
    Search every scan record's nested candidates for a matching computed
    candidate_id. Returns (scan_record_index, candidate_index, candidate_dict).
    """
    for rec_idx, rec in enumerate(records):
        for pos, cand in enumerate(rec.get("candidates", [])):
            cid = _compute_candidate_id(
                rec.get("scan_timestamp", ""), pos, cand.get("cited_reference", "")
            )
            if cid == candidate_id:
                return rec_idx, pos, cand
    raise CandidateNotFoundError(
        f"candidate_id {candidate_id!r} not present in queue"
    )


def _rewrite_queue_with_mark(
    queue_path: Path, records: list[dict], rec_idx: int, pos: int, mark: dict
) -> None:
    """
    Mutates exactly ONE candidate dict, inside exactly one scan record,
    adding the fields in `mark` -- every other scan record, and every
    other candidate within the matched scan record, is preserved
    byte-for-byte. The file is rewritten with the same one-scan-per-line
    structure the scanner itself uses, never truncated or reordered.
    """
    updated = list(records)  # shallow copy of the outer list is enough;
    rec = dict(updated[rec_idx])  # deep-ish copy of the one record we touch
    candidates = list(rec.get("candidates", []))
    cand = dict(candidates[pos])
    cand.update(mark)
    candidates[pos] = cand
    rec["candidates"] = candidates
    updated[rec_idx] = rec

    tmp_path = queue_path.with_suffix(queue_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        for r in updated:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp_path.replace(queue_path)


def _render_brief_body(candidate: dict, candidate_id: str, brief_id: str) -> str:
    """
    Matches the project's existing plain-text brief convention (the
    format Angkai is already handed via the standard handoff path).
    Built from the scanner's REAL field names (title, source_doc,
    justification, cited_reference) -- not description/proposed_action,
    which an earlier draft of this module incorrectly assumed.
    """
    title = candidate.get("title", "(untitled candidate)")
    source_doc = candidate.get("source_doc", "unknown")
    justification = candidate.get("justification", "")
    cited_reference = candidate.get("cited_reference", "unknown")

    lines = [
        f"BRIEF {brief_id}",
        f"ORIGIN: self-origination scan, candidate {candidate_id}",
        f"SOURCE DOCUMENT: {source_doc}",
        f"CITED REFERENCE: {cited_reference}",
        "",
        f"TITLE: {title}",
        "",
        "JUSTIFICATION (as proposed by the scan):",
        justification,
        "",
        "NOTE: This brief originated from Bakaidah's self-origination scan "
        "and was accepted at the normal Step 3 checkpoint before this "
        "brief was generated. It is subject to the same autonomy_scope_gate "
        "and Step 5 review as any other brief -- self-origination does not "
        "grant it any elevated trust. The cited reference above should be "
        "independently reverified before acting on this brief -- the "
        "scan's own gate-check can produce false-positive fabrication "
        "warnings on legitimate references (confirmed 2026-09-05, a "
        "numeral-format mismatch on incident vs #48), so a "
        "gate_warning on the source scan record is not itself proof the "
        "citation is fabricated.",
    ]
    return "\n".join(lines)


def dispatch_accepted_candidate(
    candidate_id: str,
    queue_path: Path,
    briefs_dir: str,
    vault_write_fn: Callable[[str, str], None],
    record_outcome_fn: Optional[Callable[[bool], dict]] = None,
) -> DispatchedBrief:
    """
    Turn one ALREADY-ACCEPTED candidate into a real brief. This IS the
    Step 3 accept decision taking effect -- calling this function is
    what "accepted" means for a self-origination candidate, so the
    origination track record gets its record_origination_outcome(True)
    call right here, not in some separate step the caller has to
    remember.

    Args:
        candidate_id: the computed id (see _compute_candidate_id) of the
            candidate to dispatch.
        queue_path: local path to Self_Origination_Candidates.jsonl
            (the staging copy Mokaima reads/writes directly).
        briefs_dir: VAULT path where briefs live, e.g.
            "/angkai/briefs/".
        vault_write_fn: injected callable(path, content) -> None that
            performs the actual VAULT write (e.g. the existing
            mcp__vault__write_file tool). Kept injected so this module
            has no hard import on any specific MCP client and can be
            unit-tested with a fake.
        record_outcome_fn: injected callable(accepted: bool) -> dict,
            defaults to the real record_origination_outcome() loaded
            via _load_record_origination_outcome() when not provided.
            Injectable so tests never touch the real track record file.

    Returns:
        DispatchedBrief describing what was written and where.

    Raises:
        CandidateNotFoundError: candidate_id not present in the queue.
        CandidateAlreadyDispatchedError: candidate was already dispatched
            (idempotency guard -- calling this twice for the same
            candidate never creates two briefs, and never double-counts
            the track record either).
        CandidateAlreadyRejectedError: candidate was already rejected --
            a rejected candidate cannot later be silently dispatched;
            that would need to go through a deliberate re-accept path,
            which does not exist here by design (keeps the track record
            counters meaning what they say).
    """
    if record_outcome_fn is None:
        record_outcome_fn = _load_record_origination_outcome()

    records = _load_scan_records(queue_path)
    rec_idx, pos, candidate = _find_candidate(records, candidate_id)

    if candidate.get("dispatched_brief_id"):
        raise CandidateAlreadyDispatchedError(
            f"candidate_id {candidate_id!r} already dispatched as brief "
            f"{candidate['dispatched_brief_id']!r}"
        )
    if candidate.get("rejected_at"):
        raise CandidateAlreadyRejectedError(
            f"candidate_id {candidate_id!r} was already rejected at "
            f"{candidate['rejected_at']} ({candidate.get('rejection_reason')})"
        )

    brief_id = f"brief-{uuid.uuid4().hex[:12]}"
    created_at = datetime.now(timezone.utc).isoformat()
    body = _render_brief_body(candidate, candidate_id, brief_id)

    brief_filename = f"{brief_id}.txt"
    brief_path = briefs_dir.rstrip("/") + "/" + brief_filename

    # Write the brief itself to VAULT. This IS a normal VAULT content write,
    # not one of the three NEVER-DIRECT-WRITE hook files, so Mokaima writing
    # it directly is within the existing rules.
    vault_write_fn(brief_path, body)

    # Mark this one candidate as dispatched, in place, inside its scan
    # record. Every other candidate/scan record is untouched.
    _rewrite_queue_with_mark(
        queue_path, records, rec_idx, pos,
        {"dispatched_brief_id": brief_id, "dispatched_at": created_at},
    )

    # Record the outcome LAST, only after both the brief write and the
    # queue mark have actually succeeded -- if either of those raised,
    # execution never reaches here, so the track record can't count an
    # acceptance that didn't really go through.
    record_outcome_fn(True)

    return DispatchedBrief(
        brief_id=brief_id,
        origin_candidate_id=candidate_id,
        title=candidate.get("title", "(untitled candidate)"),
        body=body,
        created_at=created_at,
        brief_path=brief_path,
    )


def reject_candidate(
    candidate_id: str,
    queue_path: Path,
    reason: str,
    record_outcome_fn: Optional[Callable[[bool], dict]] = None,
) -> RejectedCandidate:
    """
    Record a Step 3 REJECTION of a queued candidate. This is the
    symmetric counterpart to dispatch_accepted_candidate() -- before
    this function existed, rejections (the first live scan had 3 of
    them) were tracked only narratively, by hand, with no code path
    calling record_origination_outcome(False) at all. This closes that
    gap the same way the accept side was closed: the track record call
    lives at the actual decision point, not a separate step to remember.

    Args:
        candidate_id: the computed id (see _compute_candidate_id) of the
            candidate to reject.
        queue_path: local path to Self_Origination_Candidates.jsonl.
        reason: short human-readable reason for the rejection (e.g.
            "stale-doc false positive -- already resolved" or
            "genuinely open but standing policy is chase only if it
            recurs"). Stored on the candidate's own entry, never
            discarded -- matches the project's existing correction-note
            convention.
        record_outcome_fn: injected callable(accepted: bool) -> dict,
            defaults to the real record_origination_outcome() when not
            provided. Injectable for testing, same as the accept path.

    Returns:
        RejectedCandidate describing what was recorded.

    Raises:
        CandidateNotFoundError: candidate_id not present in the queue.
        CandidateAlreadyDispatchedError: candidate was already dispatched
            -- a dispatched candidate cannot retroactively be rejected;
            that would leave a real brief in flight with no matching
            acceptance in the track record.
        CandidateAlreadyRejectedError: candidate was already rejected
            (idempotency guard, same principle as the accept side --
            calling this twice must never double-count a rejection).
    """
    if record_outcome_fn is None:
        record_outcome_fn = _load_record_origination_outcome()

    records = _load_scan_records(queue_path)
    rec_idx, pos, candidate = _find_candidate(records, candidate_id)

    if candidate.get("dispatched_brief_id"):
        raise CandidateAlreadyDispatchedError(
            f"candidate_id {candidate_id!r} was already dispatched as brief "
            f"{candidate['dispatched_brief_id']!r} -- cannot reject a "
            f"candidate that already became a real brief"
        )
    if candidate.get("rejected_at"):
        raise CandidateAlreadyRejectedError(
            f"candidate_id {candidate_id!r} already rejected at "
            f"{candidate['rejected_at']}"
        )

    rejected_at = datetime.now(timezone.utc).isoformat()
    _rewrite_queue_with_mark(
        queue_path, records, rec_idx, pos,
        {"rejected_at": rejected_at, "rejection_reason": reason},
    )

    # Same ordering principle as the accept path: record the outcome
    # only after the queue mark has actually succeeded.
    record_outcome_fn(False)

    return RejectedCandidate(
        candidate_id=candidate_id,
        reason=reason,
        rejected_at=rejected_at,
    )


def list_pending_candidates(queue_path: Path) -> list[dict]:
    """
    Convenience for Mokaima's Step 3 review flow: returns every candidate
    across every scan record that has NEITHER been dispatched nor
    rejected yet, each annotated with its computed candidate_id so the
    caller can pass it straight to dispatch_accepted_candidate() or
    reject_candidate(). Read-only -- makes no queue modifications.
    """
    records = _load_scan_records(queue_path)
    pending = []
    for rec in records:
        scan_timestamp = rec.get("scan_timestamp", "")
        for pos, cand in enumerate(rec.get("candidates", [])):
            if cand.get("dispatched_brief_id") or cand.get("rejected_at"):
                continue
            cid = _compute_candidate_id(
                scan_timestamp, pos, cand.get("cited_reference", "")
            )
            entry = dict(cand)
            entry["candidate_id"] = cid
            entry["scan_timestamp"] = scan_timestamp
            pending.append(entry)
    return pending
