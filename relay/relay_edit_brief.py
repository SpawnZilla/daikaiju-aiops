#!/usr/bin/env python3
"""
relay_edit_brief.py -- Kaiju Relay EDIT brief type (2026-09-20, Kaiju_Relay_
Design.md section 12, option 1). Drafts a brief that MODIFIES an existing
file by exact old_text -> new_text replacements, instead of the script-shaped
MABS schema in model_relay.py. Reuses model_relay.py's tested primitives
(fetch_vault_file, call_model, JSON extraction, uncertainty + brief-id +
checkpoint checks); does not change that file or the live Pipe.

WHY (the 2026-09-19 generalization run, results JSON 20260919_162301):
  - the script-shaped schema turned an edit into 'create a new script';
  - its circularity rule emptied REFERENCES for an edit (the target is read
    AND modified);
  - Stage A's self-grounding check false-positived on every edit task, because
    the NEW content comes from the task, not from the file;
  - the model authored boilerplate (confirm line, final instruction) wrongly.
HOW THIS FIXES THEM STRUCTURALLY:
  - the model writes only title, description and the edits list; code writes
    the confirm line, steps, prohibitions, expected files (= the target),
    final instruction, the target path and the file's sha256;
  - the target is a separate field, shown under BOTH 'read first' and 'edit';
  - Stage A may only emit keys named excerpt_N (verbatim lines from the
    file); every other key is DROPPED (an allowlist, not a strip list);
  - Stage C proves mechanically that every old_text occurs EXACTLY ONCE in
    the real file, edits do not overlap, none is a no-op, none rewrites the
    whole file, and every excerpt is verbatim.
The brief carries a machine-readable EDITS_JSON block; apply_edit_brief.py
applies it deterministically (no model transcription).

RUN (on dokaisho; needs Ollama + mcpo like model_relay.py):
  python3 relay_edit_brief.py [model_tag]      runs the two 2026-09-19 cases
Offline tests: python3 test_edit_brief_suite.py
"""

import hashlib
import importlib.util
import json
import os
import re
import sys
import time

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MODEL = "qwen3-coder:30b-a3b-q4_K_M"

_EXCERPT_KEY = re.compile(r"^excerpt_\d+$")
_NOT_CONFIRMED = re.compile(r"NOT CONFIRMED", re.I)

_EDIT_BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "brief_id": {"type": "string",
                     "description": "A NEW identifier, format ANG-DRAFT-<short-topic>."},
        "title": {"type": "string", "description": "One-line title of the change."},
        "task_description": {"type": "string",
                             "description": "What is being changed and why, specific to the request."},
        "edits": {
            "type": "array", "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "old_text": {"type": "string",
                                 "description": "EXACT existing text, copied character for character from the verified excerpts. Must occur exactly once in the target file."},
                    "new_text": {"type": "string",
                                 "description": "old_text with ONLY the requested change applied; nothing else altered."},
                    "reason": {"type": "string"},
                },
                "required": ["old_text", "new_text", "reason"],
            },
        },
        "extra_hard_prohibitions": {"type": "array", "items": {"type": "string"}},
        "extra_references": {
            "type": "array",
            "items": {"type": "object",
                      "properties": {"path": {"type": "string"}, "purpose": {"type": "string"}},
                      "required": ["path", "purpose"]},
        },
    },
    "required": ["brief_id", "title", "task_description", "edits"],
}

_EDIT_VERIFY_PROMPT = (
    "You are a fact-extraction tool, not an editor. You are given a TASK "
    "(a requested change to one file) and the REFERENCE DOCUMENT, which is "
    "that file. Output ONLY a JSON object whose keys are excerpt_1, "
    "excerpt_2, ... Each value must be an EXACT, character-for-character "
    "copy of one existing line, or one contiguous block of lines, from the "
    "REFERENCE DOCUMENT that the requested change would modify or that "
    "uniquely identifies where to edit. Copy; never rephrase, never fix "
    "spelling, keep every delimiter and space. Do NOT include the requested "
    "new content. Do NOT add any other keys. If the file has nothing the "
    "change could touch, output {\"excerpt_1\": \"NOT CONFIRMED in reference "
    "document\"}. No prose outside the JSON object."
)

_EDIT_DRAFT_PROMPT = (
    "You draft a structured EDIT brief for the DoSho Daikaiju homelab. "
    "Your only source of truth is the VERIFIED EXCERPTS JSON (verbatim "
    "lines from the target file). Fill the schema:\n"
    "1. brief_id: ANG-DRAFT-<short-topic>.\n"
    "2. title and task_description: specific to the request.\n"
    "3. edits: each old_text MUST be copied CHARACTER FOR CHARACTER from one "
    "excerpt (or a contiguous part of it that is unique in the file). "
    "new_text is that old_text with ONLY the requested change applied -- "
    "keep every delimiter, quote and space that was not asked to change. "
    "Never rewrite a whole file, never add unrelated edits, never invent "
    "text that is not in an excerpt. If an excerpt says NOT CONFIRMED, put "
    "old_text 'NOT CONFIRMED' and say so in reason -- do not guess.\n"
    "4. extra_hard_prohibitions and extra_references: leave empty unless "
    "truly needed; never list the target file as a reference (it is added "
    "for you)."
)

_BASE_PROHIBITIONS = [
    "Edit ONLY the target file named below, and ONLY by applying the edits listed under EDITS exactly. Do not change any other line.",
    "Every OLD text must occur EXACTLY ONCE in the target file. If it occurs 0 or more than 1 times, STOP and report the count -- do not guess, do not pick one, do not edit anything.",
    "Do not create any file. The target file already exists.",
    "Do not deploy, restart, run or test anything. Apply the edits, then stop.",
    "Report every tool result exactly as returned; never claim a step happened if it did not.",
]


def _norm(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_relay():
    spec = importlib.util.spec_from_file_location("model_relay", os.path.join(_THIS_DIR, "model_relay.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- Stage A --
def filter_excerpt_facts(raw_json):
    """Keep ONLY excerpt_N keys with string values (an allowlist). Returns
    (clean_json_str, kept_keys, dropped_keys). Non-JSON -> (raw, [], None)."""
    try:
        data = json.loads(raw_json)
    except (TypeError, ValueError):
        return raw_json, [], None
    if not isinstance(data, dict):
        return raw_json, [], None
    kept = {k: v for k, v in data.items() if _EXCERPT_KEY.match(k) and isinstance(v, str)}
    dropped = [k for k in data if k not in kept]
    return json.dumps(kept, indent=2, ensure_ascii=False), list(kept), dropped


def check_excerpts_verbatim(excerpts_json, target_text):
    """Every confirmed excerpt must appear EXACTLY in the file."""
    warnings = []
    try:
        data = json.loads(excerpts_json)
    except (TypeError, ValueError):
        return ["STAGE A OUTPUT was not valid JSON after filtering; cannot check the excerpts."]
    for key, value in data.items():
        if _NOT_CONFIRMED.search(value):
            continue
        if value not in target_text:
            warnings.append("STAGE A EXCERPT NOT VERBATIM: '%s' does not occur exactly in the target file "
                            "(fabricated or altered): %r" % (key, value[:120]))
    return warnings


# ---------------------------------------------------------------- Stage B --
def build_edit_brief(draft, target_path, base_sha, task):
    """Combine the model's small draft with everything code decides."""
    edits = [{"old_text": str(e.get("old_text", "")), "new_text": str(e.get("new_text", "")),
              "reason": str(e.get("reason", ""))} for e in draft.get("edits", []) if isinstance(e, dict)]
    base = os.path.basename(target_path)
    brief_id = str(draft.get("brief_id", "ANG-DRAFT-edit"))
    extra_refs = [r for r in draft.get("extra_references", []) if isinstance(r, dict) and r.get("path")
                  and r.get("path") != target_path]
    steps = [
        "Read the target file in full: %s" % target_path,
        "For each edit below, confirm its OLD text occurs exactly once in the file.",
        "Apply the edits exactly as written and change nothing else.",
        "Re-read the file; confirm each NEW text is present and each OLD text is gone.",
        "State the final instruction below and stop.",
    ]
    return {
        "brief_id": brief_id,
        "title": str(draft.get("title", "")),
        "confirm_brief_loaded_line": "%s loaded: %s -- %d edit(s) to %s." % (
            brief_id, str(draft.get("title", "")), len(edits), base),
        "task_description": str(draft.get("task_description", "")) or task,
        "task_steps": steps,
        "target_file": target_path,
        "base_sha256": base_sha,
        "references": [{"path": target_path, "purpose": "the file to edit -- read it first, in full"}] + extra_refs,
        "expected_files": [target_path],
        "hard_prohibitions": list(_BASE_PROHIBITIONS) + [str(p) for p in draft.get("extra_hard_prohibitions", [])],
        "edits": edits,
        "final_instruction": ("State exactly: \"%s complete: %d edit(s) applied to %s.\" Then stop. "
                              "Do not deploy, restart, run or test anything." % (brief_id, len(edits), base)),
    }


# ---------------------------------------------------------------- Stage C --
def edit_postcheck(edits, target_text):
    """Mechanical proof that the edits are applicable to the REAL file."""
    warnings, spans = [], []
    for i, edit in enumerate(edits, 1):
        old, new = edit["old_text"], edit["new_text"]
        if "```" in old or "```" in new:
            warnings.append("EDIT %d: contains a triple backtick, which breaks the brief's EDITS_JSON block." % i)
        if not old.strip():
            warnings.append("EDIT %d: old_text is empty." % i)
            continue
        count = target_text.count(old)
        if count == 0:
            if _norm(old) in _norm(target_text):
                warnings.append("EDIT %d: old_text is NOT an exact match -- it matches only after whitespace/case "
                                "normalization, and the applier matches exactly." % i)
            else:
                warnings.append("EDIT %d: FABRICATED old_text -- it does not occur anywhere in the target file: %r" % (i, old[:120]))
        elif count > 1:
            warnings.append("EDIT %d: old_text is AMBIGUOUS -- it occurs %d times in the target file; include enough "
                            "surrounding text to make it unique." % (i, count))
        else:
            start = target_text.index(old)
            spans.append((start, start + len(old), i))
        if old == new:
            warnings.append("EDIT %d: NO-OP -- old_text equals new_text." % i)
    spans.sort()
    for left, right in zip(spans, spans[1:]):
        if left[1] > right[0]:
            warnings.append("EDITS %d and %d OVERLAP." % (left[2], right[2]))
    total_old = sum(len(e["old_text"]) for e in edits)
    if len(target_text) > 200 and total_old > 0.6 * len(target_text):
        warnings.append("EDITS look like a WHOLE-FILE REWRITE (old_text covers %d of %d characters)." % (total_old, len(target_text)))
    return warnings


_RENAME_RE = re.compile(
    r"""(?:rename|replace|change)\s+(?:all\s+occurrences\s+of\s+)?"""
    r"""(?:the\s+(?:function|method|class|variable|constant|name|identifier)\s+)?"""
    r"""[`'"]?([A-Za-z_][\w.]*)(?:\(\))?[`'"]?\s+(?:to|with|into|->)\b""", re.I)


def task_identifier_check(task, target_text):
    """If the task says rename/replace/change <identifier> to ..., the OLD identifier must exist in the target file.
    Added 2026-10-29 after the broad run (B8): the model 'renamed' a function that does not exist by editing an unrelated
    branch name, and Stage C passed because every edit was mechanically valid."""
    warnings = []
    for m in _RENAME_RE.finditer(task or ""):
        name = m.group(1)
        looks_like_identifier = ("_" in name) or ("." in name) or (name != name.lower() and name != name.upper() and name[0].islower()) \
            or m.group(0).replace("`", "").replace("'", "").replace('"', "").find(name + "()") != -1
        if looks_like_identifier and name not in target_text:
            warnings.append("TASK IDENTIFIER NOT IN FILE: the task says to change %r, but that text does not occur in the target "
                            "file -- any edit would be for something else (possible hallucinated mapping); a human must confirm." % name)
    return warnings


def normalize_line_deletions(edits, target_text):
    """Deterministic fix: a model that deletes a whole line usually leaves out its newline, which leaves a blank line behind.
    If new_text is empty, old_text is exactly one whole line (starts at a line start, followed by a newline in the file) and
    occurs once, extend old_text by that newline. Returns (edits, notes)."""
    out, notes = [], []
    for i, e in enumerate(edits, 1):
        old, new = e["old_text"], e["new_text"]
        if new == "" and old and not old.endswith("\n") and "\n" not in old and target_text.count(old) == 1:
            idx = target_text.index(old)
            end = idx + len(old)
            if (idx == 0 or target_text[idx - 1] == "\n") and target_text[end:end + 1] == "\n":
                e = dict(e, old_text=old + "\n", reason=(e.get("reason", "") + " [auto: trailing newline included so no blank line is left]").strip())
                notes.append("EDIT %d: whole-line deletion extended by its newline" % i)
        out.append(e)
    return out, notes


def stage_c_review_edit(excerpts_json, brief, target_text, relay, reference_reader=None, task=None):
    """Returns (verdict, warnings). Any warning = BLOCK, like model_relay's Stage C."""
    warnings = list(edit_postcheck(brief["edits"], target_text))
    warnings.extend(check_excerpts_verbatim(excerpts_json, target_text))
    for t in {x for x in (task, brief.get("task_description")) if x}:
        warnings.extend(w for w in task_identifier_check(t, target_text) if w not in warnings)
    shim = {  # shape model_relay.uncertainty_preservation_check expects
        "task_description": brief["task_description"], "task_steps": brief["task_steps"],
        "code_sections": [{"code": e["new_text"]} for e in brief["edits"]],
        "final_instruction": brief["final_instruction"], "hard_prohibitions": brief["hard_prohibitions"],
    }
    warnings.extend(relay.uncertainty_preservation_check(excerpts_json, shim))
    reader = reference_reader or relay.fetch_vault_file
    for ref in brief["references"][1:]:
        if reader(ref["path"]) is None:
            warnings.append("POSSIBLE FABRICATED REFERENCE: extra reference '%s' could not be read." % ref["path"])
    collision = relay._brief_id_check.check_brief_id_collision(brief["brief_id"], relay.fetch_used_brief_ids())
    if collision:
        warnings.append(collision)
    return ("BLOCK" if warnings else "PASS"), warnings


# --------------------------------------------------------------- rendering --
def render_edit_markdown(brief, warnings=None):
    lines = ["# %s -- %s" % (brief["brief_id"], brief["title"]),
             "Brief for: Angkai (Claude Code / Qwen) or the operator, via apply_edit_brief.py",
             "Written by: Kaiju Relay EDIT drafter (DRAFT -- NOT YET reviewed or approved by Mokaima)",
             "Protocol version: MABS v2.20 (edit brief)", ""]
    if warnings:
        lines += ["!" * 40, "MECHANICAL CHECK WARNINGS (mechanical, not model self-report):", "!" * 40]
        lines += ["  ! %s" % w for w in warnings] + [""]
    lines += ["=" * 40, "HARD PROHIBITIONS -- no exceptions, ever:", "=" * 40]
    lines += ["  X %s" % p for p in brief["hard_prohibitions"]] + [""]
    lines += ["-" * 40, "CONFIRM BRIEF LOADED", "-" * 40, "Before doing anything else, state:",
              '  "%s"' % brief["confirm_brief_loaded_line"], "Then proceed.", ""]
    lines += ["-" * 40, "TASK", "-" * 40, brief["task_description"], ""]
    lines += ["%d. %s" % (i, s) for i, s in enumerate(brief["task_steps"], 1)] + [""]
    lines += ["-" * 40, "REFERENCES (read every one of these before writing anything)", "-" * 40]
    for i, ref in enumerate(brief["references"], 1):
        lines += ["  %d. %s" % (i, ref["path"]), "     (%s)" % ref["purpose"]]
    lines += ["", "-" * 40, "EXPECTED FILES (closed list -- the ONLY file that may change)", "-" * 40]
    lines += ["  - %s" % f for f in brief["expected_files"]] + ["Do not create any file.", ""]
    lines += ["-" * 40, "EDITS (each OLD text must occur exactly once in the target)", "-" * 40]
    for i, edit in enumerate(brief["edits"], 1):
        lines += ["", "Edit %d -- %s" % (i, edit["reason"]), "OLD:", "```", edit["old_text"], "```",
                  "NEW:", "```", edit["new_text"], "```"]
    payload = {"target_file": brief["target_file"], "base_sha256": brief["base_sha256"],
               "edits": [{"old_text": e["old_text"], "new_text": e["new_text"]} for e in brief["edits"]]}
    lines += ["", "EDITS_JSON (machine-readable; apply_edit_brief.py applies exactly this):", "```json",
              json.dumps(payload, indent=2, ensure_ascii=False), "```", ""]
    lines += ["-" * 40, "FINAL INSTRUCTION", "-" * 40, brief["final_instruction"], "", "---",
              "[NOTE: structure and boilerplate are generated by code; only the title, description and edits "
              "come from the model. Stage C proved each OLD text occurs exactly once in the real file at draft "
              "time (file sha256 recorded above). Mokaima must still review before this reaches Angkai.]"]
    return "\n".join(lines)


# --------------------------------------------------------------- pipeline --
def run_edit_pipeline(model_tag, task, target_path, timeout=180, num_ctx=None, call_fn=None, relay=None):
    relay = relay or _load_relay()
    call_fn = call_fn or relay.call_model
    result = {"model_tag": model_tag, "task": task, "target": target_path, "error": None}
    target_text = relay.fetch_vault_file(target_path)
    if target_text is None:
        result["error"] = "could not read the target file '%s'" % target_path
        return result
    base_sha = sha256_text(target_text)
    result["base_sha256"] = base_sha

    verify_input = ("TASK: %s\n\nREFERENCE DOCUMENT (the target file, the ONLY source of truth):\n"
                    "--- BEGIN %s ---\n%s\n--- END %s ---" % (task, target_path, target_text, target_path))
    raw, elapsed_a = call_fn(model_tag=model_tag, system_prompt=_EDIT_VERIFY_PROMPT, user_msg=verify_input,
                             timeout=timeout, num_ctx=num_ctx)
    extracted = relay.extract_trailing_json_object(raw)
    if extracted is not None:
        raw = extracted
    excerpts_json, kept, dropped = filter_excerpt_facts(raw)
    result.update(verify_elapsed=elapsed_a, excerpt_keys=kept, dropped_keys=dropped or [])
    if not kept:
        result["error"] = "Stage A produced no excerpt_N facts (raw output was not usable JSON or had no excerpts)"
        return result
    if all(_NOT_CONFIRMED.search(v) for v in json.loads(excerpts_json).values()):
        result["error"] = ("NOT APPLICABLE: Stage A found nothing in the target file that the requested change "
                           "would touch (every excerpt was NOT CONFIRMED) -- check the request and the target "
                           "file; no edit brief was drafted")
        result["not_applicable"] = True
        return result

    draft_msg = ("TASK: %s\nTARGET FILE: %s\n\nVERIFIED EXCERPTS (verbatim lines from the target file; your only "
                 "source of truth):\n%s\n\nDraft the edit brief now, following the schema exactly."
                 % (task, target_path, excerpts_json))
    draft_raw, elapsed_b = call_fn(model_tag=model_tag, system_prompt=_EDIT_DRAFT_PROMPT, user_msg=draft_msg,
                                   json_schema=_EDIT_BRIEF_SCHEMA, temperature=0.3, timeout=timeout, num_ctx=num_ctx)
    leading = relay.extract_leading_json_object(draft_raw)
    if leading is not None:
        draft_raw = leading
    result["draft_elapsed"] = elapsed_b
    try:
        draft = json.loads(draft_raw)
        if not isinstance(draft, dict):
            raise ValueError("draft is not a JSON object")
    except ValueError as exc:
        result["error"] = "schema forcing failed: %s" % exc
        return result

    brief = build_edit_brief(draft, target_path, base_sha, task)
    brief["edits"], _norm_notes = normalize_line_deletions(brief["edits"], target_text)
    verdict, warnings = stage_c_review_edit(excerpts_json, brief, target_text, relay, task=task)
    mandatory, reason = relay._checkpoint_gate.should_checkpoint("stage_c", warnings)
    result.update(draft_data=brief, stage_c_verdict=verdict, stage_c_warnings=warnings,
                  checkpoint_mandatory=mandatory, checkpoint_reason=reason,
                  rendered=render_edit_markdown(brief, warnings), excerpts=excerpts_json,
                  total_elapsed=elapsed_a + elapsed_b)
    return result


# ------------------------------------------------------- the two live cases --
_VAULT = "/srv/kaiju-vault"
CASES = [
    {"id": "E1_config_line", "target": _VAULT + "/Content_Curation/content_feeds.txt",
     "old_expected": "homelab|r/homelab|https://www.reddit.com/r/homelab/.rss",
     "new_expected": "homelab|r/homelab|https://www.reddit.com/r/homelab/top/.rss?t=day",
     "task": "On the feed line for r/homelab, replace the URL with https://www.reddit.com/r/homelab/top/.rss?t=day "
             "and change nothing else in the file."},
    {"id": "E2_code_constant", "target": _VAULT + "/angkai/staging//content_curation.py",
     "old_expected": 'FEED_HOST_DELAY_SECONDS = float(os.environ.get("FEED_HOST_DELAY_SECONDS", "10"))',
     "new_expected": 'FEED_HOST_DELAY_SECONDS = float(os.environ.get("FEED_HOST_DELAY_SECONDS", "15"))',
     "task": "Change the default value of FEED_HOST_DELAY_SECONDS from 10 to 15 (the second argument of its "
             "os.environ.get call) and change nothing else."},
]


def score_case(case, result, target_text):
    """Ground-truth scoring: apply the drafted edits (apply_edit_brief.plan_edits)
    to the real file text and compare with the file the change SHOULD produce."""
    import apply_edit_brief
    out = {"case": case["id"], "error": result.get("error")}
    brief = result.get("draft_data")
    if not brief:
        out["summary"] = "NO DRAFT -- %s" % result.get("error")
        return out
    edits = brief["edits"]
    out["n_edits"] = len(edits)
    out["stage_c_verdict"] = result.get("stage_c_verdict")
    out["n_warnings"] = len(result.get("stage_c_warnings", []))
    out["intended_edit_present"] = any(
        _norm(case["old_expected"]) in _norm(e["old_text"]) and _norm(case["new_expected"]) in _norm(e["new_text"])
        for e in edits)
    expected_text = target_text.replace(case["old_expected"], case["new_expected"], 1)
    try:
        actual_text = apply_edit_brief.plan_edits(target_text, edits)
        out["applies_cleanly"] = True
        out["result_matches_intent"] = actual_text == expected_text
    except apply_edit_brief.EditError as exc:
        out["applies_cleanly"] = False
        out["result_matches_intent"] = False
        out["apply_error"] = str(exc)
    ok = out["result_matches_intent"] and out["stage_c_verdict"] == "PASS"
    out["summary"] = "OK -- the drafted edits produce exactly the intended file" if ok else "REVIEW"
    return out


def main():
    model_tag = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
    relay = _load_relay()
    all_results = []
    for case in CASES:
        print("\n" + "=" * 70 + "\n" + case["id"] + "\n" + "=" * 70)
        try:
            result = run_edit_pipeline(model_tag, case["task"], case["target"], relay=relay)
        except Exception as exc:  # noqa: BLE001
            result = {"error": "pipeline raised: %s" % exc}
        print(result.get("rendered") or ("ERROR: %s" % result.get("error")))
        target_text = relay.fetch_vault_file(case["target"]) or ""
        all_results.append({"case": case["id"], "score": score_case(case, result, target_text), "result": result})
    print("\n" + "=" * 70 + "\nSCORECARD (mechanical -- read each rendered brief too)\n" + "=" * 70)
    for item in all_results:
        s = item["score"]
        print("[%s] %s | edits=%s | applies cleanly=%s | result matches intent=%s | Stage C=%s (%s warning(s))" % (
            s["case"], s["summary"], s.get("n_edits"), s.get("applies_cleanly"),
            s.get("result_matches_intent"), s.get("stage_c_verdict"), s.get("n_warnings")))
        for w in item["result"].get("stage_c_warnings", [])[:6]:
            print("    ! " + w[:170])
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(_THIS_DIR, "relay_edit_brief_results_%s.json" % stamp)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"model": model_tag, "timestamp": stamp, "results": all_results}, fh, indent=2, ensure_ascii=False)
    print("\nResults written to: " + path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
