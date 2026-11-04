#!/usr/bin/env python3
"""
test_edit_brief_suite.py -- offline tests for relay_edit_brief.py and
apply_edit_brief.py (2026-09-20). Stdlib only. Models and mcpo are replaced by
scripted stubs, so this proves the MECHANICS (schema handling, allowlist,
exactly-once checks, rendering, applier, refusals), not model quality -- that
needs a real run (python3 relay_edit_brief.py on dokaisho).
  python3 test_edit_brief_suite.py     (exit 1 on any FAIL)
"""

import json
import os
import re
import stat
import sys
import tempfile
import types

import apply_edit_brief as A
import relay_edit_brief as E

RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append(bool(condition))
    print("%s  %s%s" % ("PASS" if condition else "FAIL", name, ("  -- " + detail) if (detail and not condition) else ""))


FEEDS = ("# feeds\nhomelab|r/selfhosted|https://www.reddit.com/r/selfhosted/.rss\n"
         "homelab|r/homelab|https://www.reddit.com/r/homelab/.rss\n"
         "homelab|ServeTheHome|https://www.servethehome.com/feed/\n")
OLD = "homelab|r/homelab|https://www.reddit.com/r/homelab/.rss"
NEW = "homelab|r/homelab|https://www.reddit.com/r/homelab/top/.rss?t=day"
TARGET = "/fake/vault/Content_Curation/content_feeds.txt"


def make_stub(files, used_ids=(), uncertain=False):
    relay = types.SimpleNamespace()
    relay.fetch_vault_file = lambda path, timeout=15: files.get(path)

    def trailing(raw):
        text = (raw or "").strip()
        try:
            json.loads(text)
            return text
        except ValueError:
            pass
        dec = json.JSONDecoder()
        for i in reversed([k for k, c in enumerate(text) if c == "{"]):
            try:
                obj, _ = dec.raw_decode(text, i)
                return json.dumps(obj)
            except ValueError:
                continue
        return None
    relay.extract_trailing_json_object = trailing
    relay.extract_leading_json_object = trailing
    relay.uncertainty_preservation_check = lambda raw, data: (
        ["UNCERTAINTY MAY NOT BE PRESERVED"] if ("NOT CONFIRMED" in raw and uncertain) else [])
    relay.fetch_used_brief_ids = lambda: set(used_ids)
    relay._brief_id_check = types.SimpleNamespace(
        check_brief_id_collision=lambda pid, used: ("BRIEF ID COLLISION: " + pid) if pid in used else None)
    relay._checkpoint_gate = types.SimpleNamespace(
        should_checkpoint=lambda stage, w: (bool(w), "warnings present" if w else "clean"))
    return relay


def scripted_call(stage_a_out, stage_b_out):
    def call(model_tag, system_prompt, user_msg, **kwargs):
        if "fact-extraction tool" in system_prompt:
            return stage_a_out, 1.0
        return stage_b_out, 2.0
    return call


def draft(old=OLD, new=NEW, brief_id="ANG-DRAFT-homelab-feed", extra=None):
    body = {"brief_id": brief_id, "title": "Point r/homelab at the top-of-day feed",
            "task_description": "Change the r/homelab feed URL.",
            "edits": [{"old_text": old, "new_text": new, "reason": "requested URL change"}]}
    body.update(extra or {})
    return json.dumps(body)


def main():
    # ---------------------------------------------------------------- applier
    print("== applier: plan_edits ==")
    check("single edit applies", A.plan_edits(FEEDS, [{"old_text": OLD, "new_text": NEW}]) == FEEDS.replace(OLD, NEW))
    for name, edits, needle in (
        ("0 matches refused", [{"old_text": "nope", "new_text": "x"}], "occurs 0 times"),
        ("2 matches refused", [{"old_text": "homelab|", "new_text": "x"}], "occurs 4 times"),
        ("no-op refused", [{"old_text": OLD, "new_text": OLD}], "no-op"),
        ("empty old_text refused", [{"old_text": "  ", "new_text": "x"}], "empty"),
        ("overlapping edits refused", [{"old_text": OLD, "new_text": "A"}, {"old_text": "r/homelab|https", "new_text": "B"}], "overlap"),
        ("non-string refused", [{"old_text": OLD, "new_text": 5}], "strings"),
    ):
        try:
            A.plan_edits(FEEDS, edits)
            check(name, False, "no error raised")
        except A.EditError as exc:
            check(name, needle in str(exc), str(exc))
    two = A.plan_edits(FEEDS, [{"old_text": "# feeds\n", "new_text": "# feeds v2\n"}, {"old_text": OLD, "new_text": NEW}])
    check("two independent edits both apply", two.startswith("# feeds v2\n") and NEW in two)

    print("== applier: extract_edits_json ==")
    for name, md in (("no block", "just text"), ("bad json", "EDITS_JSON x\n```json\n{oops\n```"),
                     ("no edits", 'EDITS_JSON x\n```json\n{"target_file":"/a","edits":[]}\n```'),
                     ("no target", 'EDITS_JSON x\n```json\n{"edits":[{"old_text":"a","new_text":"b"}]}\n```')):
        try:
            A.extract_edits_json(md)
            check("refuses: " + name, False)
        except A.EditError:
            check("refuses: " + name, True)

    print("== applier: CLI on a real temp file ==")
    tmp = tempfile.mkdtemp(prefix="editbrief_")
    path = os.path.join(tmp, "content_feeds.txt")
    with open(path, "w") as fh:
        fh.write(FEEDS)
    os.chmod(path, 0o640)
    brief = {"brief_id": "ANG-DRAFT-x", "title": "t", "confirm_brief_loaded_line": "c", "task_description": "d",
             "task_steps": ["s"], "target_file": path, "base_sha256": E.sha256_text(FEEDS),
             "references": [{"path": path, "purpose": "p"}], "expected_files": [path],
             "hard_prohibitions": ["h"], "final_instruction": "f",
             "edits": [{"old_text": OLD, "new_text": NEW, "reason": "r"}]}
    md_path = os.path.join(tmp, "brief.md")
    with open(md_path, "w") as fh:
        fh.write(E.render_edit_markdown(brief))
    check("round trip: rendered brief parses back", A.extract_edits_json(open(md_path).read())["edits"][0]["new_text"] == NEW)
    check("CHECK mode changes nothing", A.main([md_path]) == 0 and open(path).read() == FEEDS)
    check("--apply changes the file exactly", A.main([md_path, "--apply"]) == 0 and open(path).read() == FEEDS.replace(OLD, NEW))
    baks = [f for f in os.listdir(tmp) if ".bak-edit-" in f]
    check("backup written with the ORIGINAL content", len(baks) == 1 and open(os.path.join(tmp, baks[0])).read() == FEEDS)
    check("file mode preserved (0640)", stat.S_IMODE(os.stat(path).st_mode) == 0o640)
    check("re-apply refused (file drifted since drafting)", A.main([md_path, "--apply"]) == 1)
    check("--allow-drift still refuses (old_text now gone)", A.main([md_path, "--apply", "--allow-drift"]) == 1)
    check("missing target refused", A.main([md_path, "--target", os.path.join(tmp, "nope.txt")]) == 1)

    # ------------------------------------------------------------ module: A
    print("== Stage A allowlist ==")
    raw = json.dumps({"excerpt_1": OLD, "replacement_line": NEW, "modification_type": "URL replacement",
                      "change_description": "x", "excerpt_2": "b", "script_name": "s", "excerpt_x": "bad key"})
    clean, kept, dropped = E.filter_excerpt_facts(raw)
    check("keeps only excerpt_N keys", kept == ["excerpt_1", "excerpt_2"])
    check("drops every task-derived key (allowlist, not a strip list)",
          set(dropped) == {"replacement_line", "modification_type", "change_description", "script_name", "excerpt_x"})
    check("non-JSON Stage A output is flagged, not crashed", E.filter_excerpt_facts("prose only")[1:] == ([], None))
    check("non-string excerpt value dropped", E.filter_excerpt_facts('{"excerpt_1": 5}')[1] == [])
    check("verbatim excerpt passes", E.check_excerpts_verbatim(json.dumps({"excerpt_1": OLD}), FEEDS) == [])
    check("altered excerpt is caught", len(E.check_excerpts_verbatim(json.dumps({"excerpt_1": OLD.replace("homelab|", "homelab |", 1)}), FEEDS)) == 1)
    check("NOT CONFIRMED excerpt is exempt", E.check_excerpts_verbatim(json.dumps({"excerpt_1": "NOT CONFIRMED in reference document"}), FEEDS) == [])

    # ------------------------------------------------------------ module: C
    print("== Stage C mechanical checks ==")
    edit = lambda o, n: [{"old_text": o, "new_text": n, "reason": "r"}]  # noqa: E731
    check("good edit: no warnings", E.edit_postcheck(edit(OLD, NEW), FEEDS) == [])
    w = E.edit_postcheck(edit("homelab|r/homelab|https://www.reddit.com/r/homelab/OLD.rss", NEW), FEEDS)
    check("fabricated old_text -> FABRICATED", len(w) == 1 and "FABRICATED" in w[0])
    w = E.edit_postcheck(edit("homelab|", "x|"), FEEDS)
    check("ambiguous old_text -> AMBIGUOUS", len(w) == 1 and "AMBIGUOUS" in w[0] and "4 times" in w[0])
    w = E.edit_postcheck(edit(OLD.replace("|", " | "), NEW), FEEDS)
    check("whitespace-only mismatch named as such", any("NOT an exact match" in x for x in w) or any("FABRICATED" in x for x in w))
    w = E.edit_postcheck(edit("URL  ", "x"), "abc URL  def URL  ghi")
    check("ambiguous with trailing spaces", any("AMBIGUOUS" in x for x in w))
    check("no-op flagged", any("NO-OP" in x for x in E.edit_postcheck(edit(OLD, OLD), FEEDS)))
    check("overlap flagged", any("OVERLAP" in x for x in E.edit_postcheck(
        [{"old_text": OLD, "new_text": "A", "reason": ""}, {"old_text": "r/homelab|https", "new_text": "B", "reason": ""}], FEEDS)))
    big = "line %d\n" % 1 * 1 + "".join("filler line number %d\n" % i for i in range(40))
    check("whole-file rewrite flagged", any("WHOLE-FILE" in x for x in E.edit_postcheck(edit(big, "short"), big)))
    check("triple backtick flagged", any("backtick" in x for x in E.edit_postcheck(edit(OLD, "a ``` b"), FEEDS)))
    check("empty old_text flagged", any("empty" in x for x in E.edit_postcheck(edit("  ", "x"), FEEDS)))

    # -------------------------------------------------- module: build/render
    print("== mechanical brief fields ==")
    full = E.build_edit_brief(json.loads(draft(extra={"extra_references": [{"path": TARGET, "purpose": "dup"},
                                                                          {"path": "/fake/other.md", "purpose": "context"}],
                                                       "extra_hard_prohibitions": ["No extra."]})),
                              TARGET, E.sha256_text(FEEDS), "task")
    check("expected_files is exactly [target] (code-decided)", full["expected_files"] == [TARGET])
    check("target is FIRST in references and not duplicated", [r["path"] for r in full["references"]] == [TARGET, "/fake/other.md"])
    check("confirm line generated by code", full["confirm_brief_loaded_line"].startswith("ANG-DRAFT-homelab-feed loaded:") and "1 edit(s)" in full["confirm_brief_loaded_line"])
    check("prohibitions = 5 base + the model's extra", len(full["hard_prohibitions"]) == 6 and "No extra." in full["hard_prohibitions"])
    check("final instruction is edit-shaped (not 'script written')", "edit(s) applied" in full["final_instruction"] and "script" not in full["final_instruction"].lower())
    check("no create-a-file language anywhere in the steps", not re.search(r"\bcreate\b", " ".join(full["task_steps"]), re.I))
    check("sha256 of the file recorded", full["base_sha256"] == E.sha256_text(FEEDS))

    # --------------------------------------------------------- full pipeline
    print("== full pipeline with scripted models ==")
    files = {TARGET: FEEDS, "/fake/other.md": "context"}
    good_a = json.dumps({"excerpt_1": OLD})
    res = E.run_edit_pipeline("m", "task", TARGET, call_fn=scripted_call(good_a, draft()), relay=make_stub(files))
    check("good run: Stage C PASS, no warnings", res.get("stage_c_verdict") == "PASS" and res["stage_c_warnings"] == [], str(res.get("stage_c_warnings")))
    check("good run: target in BOTH references and expected files", res["draft_data"]["references"][0]["path"] == TARGET and res["draft_data"]["expected_files"] == [TARGET])
    check("good run: rendered brief contains OLD, NEW and EDITS_JSON", all(x in res["rendered"] for x in (OLD, NEW, "EDITS_JSON")))
    payload = A.extract_edits_json(res["rendered"])
    check("good run: the rendered brief applies to the real text and gives the intended file",
          A.plan_edits(FEEDS, payload["edits"]) == FEEDS.replace(OLD, NEW))
    sc = E.score_case({"id": "E1", "old_expected": OLD, "new_expected": NEW}, res, FEEDS)
    check("scorer: result matches intent", sc["result_matches_intent"] and sc["summary"].startswith("OK"))

    noisy = json.dumps({"excerpt_1": OLD, "replacement_line": NEW, "modification_type": "URL replacement"})
    res = E.run_edit_pipeline("m", "task", TARGET, call_fn=scripted_call(noisy, draft()), relay=make_stub(files))
    check("task-derived Stage A keys dropped, run still PASSES (the E1/E2 false-positive fix)",
          res["stage_c_verdict"] == "PASS" and set(res["dropped_keys"]) == {"replacement_line", "modification_type"})

    res = E.run_edit_pipeline("m", "task", TARGET, call_fn=scripted_call(good_a, draft(old=OLD.replace("homelab/.rss", "homelab/old.rss"))), relay=make_stub(files))
    check("fabricated old_text -> BLOCK naming it", res["stage_c_verdict"] == "BLOCK" and any("FABRICATED" in x for x in res["stage_c_warnings"]))
    check("...and the scorer says it does not apply", E.score_case({"id": "E1", "old_expected": OLD, "new_expected": NEW}, res, FEEDS)["applies_cleanly"] is False)

    res = E.run_edit_pipeline("m", "task", TARGET, call_fn=scripted_call(good_a, draft(old="homelab|", new="x|")), relay=make_stub(files))
    check("ambiguous old_text -> BLOCK", res["stage_c_verdict"] == "BLOCK" and any("AMBIGUOUS" in x for x in res["stage_c_warnings"]))

    res = E.run_edit_pipeline("m", "task", TARGET, call_fn=scripted_call(json.dumps({"excerpt_1": OLD + " EXTRA"}), draft()), relay=make_stub(files))
    check("altered Stage A excerpt -> BLOCK", any("NOT VERBATIM" in x for x in res["stage_c_warnings"]))

    res = E.run_edit_pipeline("m", "task", TARGET, call_fn=scripted_call(good_a, draft(brief_id="ANG-DRAFT-homelab-feed")), relay=make_stub(files, used_ids={"ANG-DRAFT-homelab-feed"}))
    check("brief-id collision -> BLOCK", any("COLLISION" in x for x in res["stage_c_warnings"]))

    res = E.run_edit_pipeline("m", "task", TARGET, call_fn=scripted_call(good_a, draft(extra={"extra_references": [{"path": "/fake/missing.md", "purpose": "x"}]})), relay=make_stub(files))
    check("unreadable extra reference -> BLOCK", any("extra reference" in x for x in res["stage_c_warnings"]))

    calls = []

    def call_no_draft(model_tag, system_prompt, user_msg, **kwargs):
        calls.append("B" if "fact-extraction tool" not in system_prompt else "A")
        return json.dumps({"excerpt_1": "NOT CONFIRMED in reference document"}), 1.0
    res = E.run_edit_pipeline("m", "task", TARGET, call_fn=call_no_draft, relay=make_stub(files, uncertain=True))
    check("all-NOT-CONFIRMED Stage A -> clear NOT APPLICABLE error, no draft, Stage B never called",
          "NOT APPLICABLE" in (res.get("error") or "") and res.get("not_applicable") is True and calls == ["A"] and "draft_data" not in res)
    mixed = json.dumps({"excerpt_1": OLD, "excerpt_2": "NOT CONFIRMED in reference document"})
    res = E.run_edit_pipeline("m", "task", TARGET, call_fn=scripted_call(mixed, draft()), relay=make_stub(files))
    check("a MIX of confirmed and NOT CONFIRMED excerpts still drafts", res.get("stage_c_verdict") is not None and res.get("error") is None)
    res = E.run_edit_pipeline("m", "task", TARGET, call_fn=scripted_call(json.dumps({"excerpt_1": OLD, "excerpt_2": "NOT CONFIRMED in reference document"}), draft(old="NOT CONFIRMED", new="x")), relay=make_stub(files, uncertain=True))
    check("mixed excerpts + a hallucinated NOT CONFIRMED edit -> BLOCK", res["stage_c_verdict"] == "BLOCK")

    res = E.run_edit_pipeline("m", "task", TARGET, call_fn=scripted_call("I could not find anything", draft()), relay=make_stub(files))
    check("Stage A with no usable JSON -> clean error, no crash", "no excerpt_N" in (res.get("error") or ""))
    res = E.run_edit_pipeline("m", "task", TARGET, call_fn=scripted_call(good_a, "{not json"), relay=make_stub(files))
    check("Stage B invalid JSON -> clean error, no crash", "schema forcing failed" in (res.get("error") or ""))
    res = E.run_edit_pipeline("m", "task", "/fake/missing.txt", call_fn=scripted_call(good_a, draft()), relay=make_stub(files))
    check("unreadable target -> clean error", "could not read the target" in (res.get("error") or ""))
    res = E.run_edit_pipeline("m", "task", TARGET, call_fn=scripted_call("reasoning prose first... " + good_a, "trailing junk after? " + draft()), relay=make_stub(files))
    check("reasoning-bled / prefixed JSON is still extracted", res.get("stage_c_verdict") == "PASS", str(res.get("error")))

    # ---- 2026-10-29 additions (broad run findings B2 / B8) ----
    QW3_LIKE = 'F=/x/settings.local.json\ncase "$1" in\n rollback) sudo chattr -i $F;;\nesac\n'
    t = "Rename the function restore_settings_backup() to rollback_settings() everywhere in this file."
    check("B8: renaming a function that is not in the file is flagged",
          any("TASK IDENTIFIER NOT IN FILE" in w for w in E.task_identifier_check(t, QW3_LIKE)))
    check("B8: same task, identifier present -> no warning",
          E.task_identifier_check(t, "def restore_settings_backup():\n  pass\n") == [])
    check("B8: quoted 'replace all occurrences of' wording is caught",
          any("NOT IN FILE" in w for w in E.task_identifier_check(
              "Replace all occurrences of 'restore_settings_backup()' with 'rollback_settings()' in the target file.", QW3_LIKE)))
    for ok_task in ("Change MAX_BRIEF_BYTES from 256 * 1024 to 512 * 1024 and change nothing else.",
                    "In the line that handles a missing gateway unit, change `systemctl list-units | grep -i gateway` to `systemctl list-units --all | grep -i gateway`.",
                    "Change the line that sets the port to 10001.", "Replace the first heading with a shorter one.",
                    "Directly after the line F=/x add a new line LOG=/y. Change nothing else.",
                    "In the rollback branch ONLY, add the flag --no-block to the systemctl restart command."):
        check("no false alarm: " + ok_task[:50], E.task_identifier_check(ok_task, QW3_LIKE) == [])
    PLAN = "## Later\n4. thing\n5. settings.json + hooks dir root-owned; arm/disarm via broker.\n## Second\nnext\n"
    line = "5. settings.json + hooks dir root-owned; arm/disarm via broker."
    ed, notes = E.normalize_line_deletions([{"old_text": line, "new_text": "", "reason": "r"}], PLAN)
    check("B2: whole-line deletion gets its newline", ed[0]["old_text"] == line + "\n" and len(notes) == 1)
    check("B2: after normalising, applying the edit leaves no blank line",
          PLAN.replace(ed[0]["old_text"], ed[0]["new_text"]) == "## Later\n4. thing\n## Second\nnext\n")
    ed2, n2 = E.normalize_line_deletions([{"old_text": "settings.json + hooks", "new_text": "", "reason": ""}], PLAN)
    check("mid-line deletion is NOT touched", ed2[0]["old_text"] == "settings.json + hooks" and n2 == [])
    ed3, n3 = E.normalize_line_deletions([{"old_text": line + "\n", "new_text": "", "reason": ""}], PLAN)
    check("already-complete line deletion is NOT touched", ed3[0]["old_text"] == line + "\n" and n3 == [])
    ed4, n4 = E.normalize_line_deletions([{"old_text": "4. thing", "new_text": "4. other", "reason": ""}], PLAN)
    check("replacement (non-empty new_text) is NOT touched", n4 == [])
    ed5, n5 = E.normalize_line_deletions([{"old_text": "next", "new_text": "", "reason": ""}], "a\nnext")
    check("last line without a trailing newline is NOT touched", n5 == [])
    # end to end through stage C with the real B8 edit shape: the task-identifier check must BLOCK it
    brief8 = {"brief_id": "ANG-DRAFT-x", "task_description": t, "task_steps": [], "final_instruction": "",
              "hard_prohibitions": [], "references": [{"path": "/f"}],
              "edits": [{"old_text": " rollback) sudo chattr -i $F;;", "new_text": " rollback_settings) sudo chattr -i $F;;", "reason": "r"}]}
    v, w = E.stage_c_review_edit("{}", brief8, QW3_LIKE, make_stub({}), task=t)
    check("B8 end to end: Stage C verdict is BLOCK", v == "BLOCK" and any("NOT IN FILE" in x for x in w), str(w)[:200])

    failed = RESULTS.count(False)
    print("\n%d cases, %d passed, %d FAILED" % (len(RESULTS), RESULTS.count(True), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
