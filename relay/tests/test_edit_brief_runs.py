#!/usr/bin/env python3
"""test_edit_brief_runs.py -- offline tests for relay_edit_brief_runs.py scoring (2026-09-20)."""

import json
import sys

import relay_edit_brief as E
import relay_edit_brief_runs as R
import test_edit_brief_suite as T

RESULTS = []


def check(name, condition):
    RESULTS.append(bool(condition))
    print("%s  %s" % ("PASS" if condition else "FAIL", name))


def main():
    files = {T.TARGET: T.FEEDS}
    good_a = json.dumps({"excerpt_1": T.OLD})
    one = E.run_edit_pipeline("m", "t", T.TARGET, call_fn=T.scripted_call(good_a, T.draft()), relay=T.make_stub(files))
    c1 = {"id": "E1", "pairs": [(T.OLD, T.NEW)]}
    s = R.score_case(c1, one, T.FEEDS)
    check("one edit matching one intended change is OK", s["ok"] and s["result_matches_intent"])
    c2 = {"id": "E3", "pairs": [(T.OLD, T.NEW), ("homelab|ServeTheHome|", "hardware|ServeTheHome|")]}
    s = R.score_case(c2, one, T.FEEDS)
    check("a MISSING second intended edit is not OK", s["ok"] is False and s["result_matches_intent"] is False)
    two = json.loads(T.draft())
    two["edits"].append({"old_text": "homelab|ServeTheHome|", "new_text": "hardware|ServeTheHome|", "reason": "r"})
    res2 = E.run_edit_pipeline("m", "t", T.TARGET, call_fn=T.scripted_call(good_a, json.dumps(two)), relay=T.make_stub(files))
    check("two edits matching a two-edit intent is OK", res2["stage_c_verdict"] == "PASS" and R.score_case(c2, res2, T.FEEDS)["ok"])
    extra = json.loads(T.draft())
    extra["edits"].append({"old_text": "# feeds\n", "new_text": "# feeds v2\n", "reason": "unrequested"})
    res3 = E.run_edit_pipeline("m", "t", T.TARGET, call_fn=T.scripted_call(good_a, json.dumps(extra)), relay=T.make_stub(files))
    check("an UNREQUESTED extra edit is not OK (result differs from the intended file)", R.score_case(c1, res3, T.FEEDS)["ok"] is False)
    neg = {"id": "E5", "negative": True}
    check("negative case: a PASS brief is a FAIL", R.score_case(neg, one, T.FEEDS)["ok"] is False)
    check("negative case: a BLOCK is OK", R.score_case(neg, dict(one, stage_c_verdict="BLOCK"), T.FEEDS)["ok"] is True)
    check("negative case: a pipeline error is OK", R.score_case(neg, {"error": "x"}, T.FEEDS)["ok"] is True)
    fab = E.run_edit_pipeline("m", "t", T.TARGET, call_fn=T.scripted_call(good_a, T.draft(old="homelab|r/homelab|nope")), relay=T.make_stub(files))
    check("normal case with a fabricated old_text is not OK and does not apply",
          R.score_case(c1, fab, T.FEEDS)["ok"] is False and R.score_case(c1, fab, T.FEEDS)["applies_cleanly"] is False)
    check("the five cases are present, one of them negative",
          len(R.CASES) == 5 and sum(1 for c in R.CASES if c.get("negative")) == 1)
    failed = RESULTS.count(False)
    print("\n%d cases, %d passed, %d FAILED" % (len(RESULTS), RESULTS.count(True), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
