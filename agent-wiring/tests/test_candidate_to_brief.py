import json
import tempfile
from pathlib import Path

from candidate_to_brief import (
    dispatch_accepted_candidate,
    reject_candidate,
    list_pending_candidates,
    _compute_candidate_id,
    CandidateNotFoundError,
    CandidateAlreadyDispatchedError,
    CandidateAlreadyRejectedError,
)

SCAN_TS = "2026-09-05T15:43:32.300966+00:00"

def make_queue(tmp_path):
    """Mirrors the REAL on-disk shape: one scan record per line, nested
    candidates, no candidate_id field anywhere."""
    queue_path = tmp_path / "Self_Origination_Candidates.jsonl"
    scan_record = {
        "scan_timestamp": SCAN_TS,
        "origin_agent": "bakaidah_self_origination",
        "candidates": [
            {
                "cited_reference": "incident",
                "source_doc": "Troubleshooting_Journal.md",
                "title": "Live-verify v0.6 fix for Reference Existence Gate Filter banner",
                "justification": "A v0.6 fix has been written but not live-verified.",
            },
            {
                "cited_reference": "incident",
                "source_doc": "Troubleshooting_Journal.md",
                "title": "Deploy tool-name fix",
                "justification": "A one-line fix is staged but held for review.",
            },
        ],
        "gate_warnings": ["warning: FABRICATED INCIDENT CITATION -- #48"],
        "error": None,
        "raw_reply_present": True,
    }
    with queue_path.open("w") as f:
        f.write(json.dumps(scan_record) + "\n")
    return queue_path

def cid(position, cited_reference):
    return _compute_candidate_id(SCAN_TS, position, cited_reference)

def test_list_pending_matches_real_shape():
    with tempfile.TemporaryDirectory() as td:
        queue_path = make_queue(Path(td))
        pending = list_pending_candidates(queue_path)
        assert len(pending) == 2
        assert pending[0]["candidate_id"] == cid(0, "incident")
        assert pending[1]["candidate_id"] == cid(1, "incident")
        print("test_list_pending_matches_real_shape PASS")

def test_happy_path_calls_outcome_true_preserves_sibling():
    with tempfile.TemporaryDirectory() as td:
        queue_path = make_queue(Path(td))
        target_id = cid(1, "incident")
        written = {}
        outcome_calls = []

        result = dispatch_accepted_candidate(
            candidate_id=target_id,
            queue_path=queue_path,
            briefs_dir="/angkai/briefs/",
            vault_write_fn=lambda p, c: written.__setitem__(p, c),
            record_outcome_fn=lambda a: (outcome_calls.append(a), {})[1],
        )
        assert result.origin_candidate_id == target_id
        assert result.brief_path in written
        assert "incident" in written[result.brief_path]
        assert outcome_calls == [True]

        # sibling candidate (position 0) must be completely untouched
        raw = json.loads(queue_path.read_text().strip())
        assert raw["candidates"][0].get("dispatched_brief_id") is None
        assert raw["candidates"][1]["dispatched_brief_id"] == result.brief_id
        print("test_happy_path_calls_outcome_true_preserves_sibling PASS")

def test_not_found():
    with tempfile.TemporaryDirectory() as td:
        queue_path = make_queue(Path(td))
        try:
            dispatch_accepted_candidate(
                candidate_id="doesnotexist000",
                queue_path=queue_path, briefs_dir="/angkai/briefs/",
                vault_write_fn=lambda p, c: None, record_outcome_fn=lambda a: None,
            )
            assert False, "expected CandidateNotFoundError"
        except CandidateNotFoundError:
            print("test_not_found PASS")

def test_idempotent_double_dispatch_no_double_count():
    with tempfile.TemporaryDirectory() as td:
        queue_path = make_queue(Path(td))
        target_id = cid(0, "incident")
        writes = []
        outcome_calls = []
        kwargs = dict(
            candidate_id=target_id, queue_path=queue_path, briefs_dir="/angkai/briefs/",
            vault_write_fn=lambda p, c: writes.append(p),
            record_outcome_fn=lambda a: (outcome_calls.append(a), {})[1],
        )
        dispatch_accepted_candidate(**kwargs)
        try:
            dispatch_accepted_candidate(**kwargs)
            assert False, "expected CandidateAlreadyDispatchedError"
        except CandidateAlreadyDispatchedError:
            assert len(writes) == 1
            assert outcome_calls == [True]
            print("test_idempotent_double_dispatch_no_double_count PASS")

def test_reject_calls_outcome_false_preserves_sibling():
    with tempfile.TemporaryDirectory() as td:
        queue_path = make_queue(Path(td))
        target_id = cid(1, "incident")
        outcome_calls = []
        result = reject_candidate(
            candidate_id=target_id, queue_path=queue_path,
            reason="already deployed and regression-tested -- confirmed via direct journal read",
            record_outcome_fn=lambda a: (outcome_calls.append(a), {})[1],
        )
        assert result.candidate_id == target_id
        assert outcome_calls == [False]
        raw = json.loads(queue_path.read_text().strip())
        assert raw["candidates"][1]["rejection_reason"].startswith("already deployed")
        assert raw["candidates"][0].get("rejected_at") is None
        print("test_reject_calls_outcome_false_preserves_sibling PASS")

def test_reject_idempotent_no_double_count():
    with tempfile.TemporaryDirectory() as td:
        queue_path = make_queue(Path(td))
        target_id = cid(0, "incident")
        outcome_calls = []
        reject_candidate(
            candidate_id=target_id, queue_path=queue_path, reason="first",
            record_outcome_fn=lambda a: (outcome_calls.append(a), {})[1],
        )
        try:
            reject_candidate(
                candidate_id=target_id, queue_path=queue_path, reason="second",
                record_outcome_fn=lambda a: (outcome_calls.append(a), {})[1],
            )
            assert False, "expected CandidateAlreadyRejectedError"
        except CandidateAlreadyRejectedError:
            assert outcome_calls == [False]
            print("test_reject_idempotent_no_double_count PASS")

def test_cannot_reject_already_dispatched():
    with tempfile.TemporaryDirectory() as td:
        queue_path = make_queue(Path(td))
        target_id = cid(0, "incident")
        dispatch_accepted_candidate(
            candidate_id=target_id, queue_path=queue_path, briefs_dir="/angkai/briefs/",
            vault_write_fn=lambda p, c: None, record_outcome_fn=lambda a: None,
        )
        try:
            reject_candidate(
                candidate_id=target_id, queue_path=queue_path, reason="too late",
                record_outcome_fn=lambda a: None,
            )
            assert False, "expected CandidateAlreadyDispatchedError"
        except CandidateAlreadyDispatchedError:
            print("test_cannot_reject_already_dispatched PASS")

def test_cannot_dispatch_already_rejected():
    with tempfile.TemporaryDirectory() as td:
        queue_path = make_queue(Path(td))
        target_id = cid(0, "incident")
        reject_candidate(
            candidate_id=target_id, queue_path=queue_path, reason="not worth it",
            record_outcome_fn=lambda a: None,
        )
        try:
            dispatch_accepted_candidate(
                candidate_id=target_id, queue_path=queue_path, briefs_dir="/angkai/briefs/",
                vault_write_fn=lambda p, c: None, record_outcome_fn=lambda a: None,
            )
            assert False, "expected CandidateAlreadyRejectedError"
        except CandidateAlreadyRejectedError:
            print("test_cannot_dispatch_already_rejected PASS")

def test_candidate_id_stable_across_recomputation():
    # Same inputs must always produce the same id -- no stored state needed.
    assert cid(0, "incident") == cid(0, "incident")
    assert cid(0, "incident") != cid(1, "incident")
    assert cid(0, "incident-A") != cid(0, "incident-B")
    print("test_candidate_id_stable_across_recomputation PASS")

if __name__ == "__main__":
    test_list_pending_matches_real_shape()
    test_happy_path_calls_outcome_true_preserves_sibling()
    test_not_found()
    test_idempotent_double_dispatch_no_double_count()
    test_reject_calls_outcome_false_preserves_sibling()
    test_reject_idempotent_no_double_count()
    test_cannot_reject_already_dispatched()
    test_cannot_dispatch_already_rejected()
    test_candidate_id_stable_across_recomputation()
    print("ALL TESTS PASS")
