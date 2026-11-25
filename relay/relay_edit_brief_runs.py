#!/usr/bin/env python3
"""
relay_edit_brief_runs.py -- multi-run reliability runner for relay_edit_brief.py
(2026-09-20). Five cases x N runs against a real model: the two 2026-09-19
cases, a two-edit case, an AMBIGUOUS-token case (homelab| occurs on several
lines, so the model must pick unique context) and an IMPOSSIBLE change that
must NOT yield a passing brief.

  python3 relay_edit_brief_runs.py [model_tag] [runs]      (run ON dokaisho; default 1 run)

Scoring is ground truth, not model self-report: the drafted edits are applied
to the real file text and compared with the file the change SHOULD produce.
A negative case succeeds only if NO passing brief comes out. Writes
relay_edit_brief_runs_results_<timestamp>.json next to this script.
Offline tests: python3 test_edit_brief_runs.py
"""

import json
import os
import sys
import time

import apply_edit_brief
import relay_edit_brief as E

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_VAULT = "/srv/kaiju-vault"
_FEEDS = _VAULT + "/Content_Curation/content_feeds.txt"

CASES = [
    {"id": "E1_config_line", "target": _FEEDS,
     "pairs": [("homelab|r/homelab|https://www.reddit.com/r/homelab/.rss",
                "homelab|r/homelab|https://www.reddit.com/r/homelab/top/.rss?t=day")],
     "task": "On the feed line for r/homelab, replace the URL with https://www.reddit.com/r/homelab/top/.rss?t=day "
             "and change nothing else in the file."},
    {"id": "E2_code_constant", "target": _VAULT + "/angkai/staging//content_curation.py",
     "pairs": [('FEED_HOST_DELAY_SECONDS = float(os.environ.get("FEED_HOST_DELAY_SECONDS", "10"))',
                'FEED_HOST_DELAY_SECONDS = float(os.environ.get("FEED_HOST_DELAY_SECONDS", "15"))')],
     "task": "Change the default value of FEED_HOST_DELAY_SECONDS from 10 to 15 (the second argument of its "
             "os.environ.get call) and change nothing else."},
    {"id": "E3_two_edits", "target": _FEEDS,
     "pairs": [("homelab|r/homelab|https://www.reddit.com/r/homelab/.rss",
                "homelab|r/homelab|https://www.reddit.com/r/homelab/top/.rss?t=day"),
               ("homelab|r/selfhosted|https://www.reddit.com/r/selfhosted/.rss",
                "homelab|r/selfhosted|https://www.reddit.com/r/selfhosted/top/.rss?t=day")],
     "task": "Change the URL on the r/homelab feed line to https://www.reddit.com/r/homelab/top/.rss?t=day and the "
             "URL on the r/selfhosted feed line to https://www.reddit.com/r/selfhosted/top/.rss?t=day. Change "
             "nothing else."},
    {"id": "E4_ambiguous_token", "target": _FEEDS,
     "pairs": [("homelab|ServeTheHome|", "hardware|ServeTheHome|")],
     "task": "Change the category of the ServeTheHome feed from homelab to hardware (the text before the first | "
             "on that line) and change nothing else. Other feed lines also start with homelab and must NOT change."},
    {"id": "E5_impossible_change", "target": _FEEDS, "negative": True,
     "task": "Change the FEED_HOST_DELAY_SECONDS default from 10 to 15 in this file."},
]


def score_case(case, result, target_text):
    """A normal case is OK when Stage C says PASS AND applying the drafted edits
    to the real text gives exactly the intended file. A negative case is OK only
    when no passing brief was produced."""
    out = {"case": case["id"], "error": result.get("error"),
           "stage_c_verdict": result.get("stage_c_verdict"),
           "n_warnings": len(result.get("stage_c_warnings", []))}
    brief = result.get("draft_data")
    if case.get("negative"):
        produced_pass = bool(brief) and result.get("stage_c_verdict") == "PASS"
        out["ok"] = not produced_pass
        out["summary"] = ("FAIL -- a PASSING brief was produced for an impossible change" if produced_pass
                          else "OK -- no passing brief for an impossible change")
        return out
    if not brief:
        out["ok"] = False
        out["summary"] = "NO DRAFT -- %s" % result.get("error")
        return out
    out["n_edits"] = len(brief["edits"])
    expected = target_text
    for old, new in case["pairs"]:
        expected = expected.replace(old, new, 1)
    try:
        actual = apply_edit_brief.plan_edits(target_text, brief["edits"])
        out["applies_cleanly"] = True
        out["result_matches_intent"] = actual == expected
    except apply_edit_brief.EditError as exc:
        out["applies_cleanly"] = False
        out["result_matches_intent"] = False
        out["apply_error"] = str(exc)
    out["ok"] = bool(out["result_matches_intent"]) and out["stage_c_verdict"] == "PASS"
    out["summary"] = "OK -- the drafted edits produce exactly the intended file" if out["ok"] else "REVIEW"
    return out


def main():
    model_tag = sys.argv[1] if len(sys.argv) > 1 else E.DEFAULT_MODEL
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    relay = E._load_relay()
    all_results = []
    for case in CASES:
        target_text = relay.fetch_vault_file(case["target"]) or ""
        for run in range(1, runs + 1):
            print("\n" + "=" * 70 + "\n%s  (run %d of %d)\n" % (case["id"], run, runs) + "=" * 70)
            try:
                result = E.run_edit_pipeline(model_tag, case["task"], case["target"], relay=relay)
            except Exception as exc:  # noqa: BLE001
                result = {"error": "pipeline raised: %s" % exc}
            if run == 1:
                print(result.get("rendered") or ("ERROR: %s" % result.get("error")))
            score = score_case(case, result, target_text)
            print("-> %s" % score["summary"])
            all_results.append({"case": case["id"], "run": run, "score": score, "result": result})
    print("\n" + "=" * 70 + "\nSCORECARD (ground truth: drafted edits applied to the real file)\n" + "=" * 70)
    for case in CASES:
        mine = [r for r in all_results if r["case"] == case["id"]]
        print("[%s] %d of %d OK" % (case["id"], sum(1 for r in mine if r["score"]["ok"]), len(mine)))
        for r in mine:
            if not r["score"]["ok"]:
                s = r["score"]
                print("    run %d: %s | edits=%s | applies=%s | matches=%s | Stage C=%s" % (
                    r["run"], s["summary"][:58], s.get("n_edits"), s.get("applies_cleanly"),
                    s.get("result_matches_intent"), s.get("stage_c_verdict")))
                for w in r["result"].get("stage_c_warnings", [])[:3]:
                    print("        ! " + w[:150])
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(_THIS_DIR, "relay_edit_brief_runs_results_%s.json" % stamp)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"model": model_tag, "runs": runs, "timestamp": stamp, "results": all_results},
                  fh, indent=2, ensure_ascii=False)
    print("\nResults written to: " + path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
