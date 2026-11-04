"""
title: Bakaidah Grounded Drafting Filter
author: the operator / Mokaima
author_url: N/A
funding_url: N/A
version: 0.10
description:  Phase 1 -- Filter (inlet/outlet), NOT a Pipe.
  Always-on, attached directly to Bakaidah (General).

  v0.9-instrumented -> v0.10 (2026-08-21, same session): FIRST GENUINE
  END-TO-END LIVE CONFIRMATION of the entire fabrication-detection
  mechanism -- trigger detection, identifier extraction, basename path
  resolution, mcpo fetch, and the fabrication check all worked
  correctly together on a real live message: Bakaidah answered with all
  15 real function names plus one deliberately fake one
  (`kaiju_test_marker_12345`), and the Filter correctly flagged ONLY
  the fake one, with zero false positives among the 16 real
  identifiers it also checked. The real answer survived intact
  underneath the banner, confirming v0.9's field-read/write fix.
  This version removes the temporary always-on instrumentation (state
  report banner) added for v0.8/v0.9 debugging and restores the
  intended warn-only-on-real-problems behavior: outlet() is now
  silent on every ordinary, non-fabricated response, same as the
  original v0.6 design intent -- but now with the two real fixes v0.6
  never actually had working (basename-first path resolution, correct
  Native Mode field read/write) live-proven underneath.
  ALSO: excludes the trigger file's own basename from the identifier
  check -- confirmed live that a response naming the file itself in
  backticks (e.g. "functions in `fashsd_config_lib.sh` are:") gets
  swept into claimed_identifiers, which is a path reference, not a
  code identifier being asserted. That case happened to pass by
  coincidence (the real file's own header comment mentions its
  filename), but would false-positive on a file without a
  self-referential header -- excluded outright rather than relying on
  that coincidence.

  v0.8-instrumented -> v0.9-instrumented (2026-08-21, same session):
  CRITICAL BUG FOUND AND FIXED -- v0.8's always-on banner, live-tested,
  visibly REPLACED Bakaidah's real answer instead of appending to it.
  Confirmed via Bakaidah's own auto-generated follow-up prompts asking
  "why did it replace the actual answer?" ROOT CAUSE, and simultaneously
  the answer to this entire session's mystery: v0.4 through v0.8 all
  read message["content"] as "the response text" -- but in Native
  Mode, that flat field is empty/stale. The REAL rendered answer lives
  in the structured output[type=message].content[type=output_text].text
  field (the same field Reference Existence Gate's v0.6 fix identified
  as what the UI renders FROM -- but this Filter only ever WROTE to
  that field, never READ from it). Reading an always-empty string
  explains every prior "claimed identifiers extracted: NONE" and every
  silent no-op since v0.4 -- not a fabrication-detection failure, a
  wrong-field-read failure the whole time. v0.8's dual-write then made
  this actively destructive: (empty content + banner) got written into
  BOTH fields, overwriting the real answer that had been sitting
  correctly in the structured field the whole time.
  FIX: new _get_real_response_text() reads the structured output_text
  field FIRST, falling back to flat content only if no structured
  output exists -- a dual-READ mirroring the existing dual-WRITE. New
  _write_response_text() centralizes the write side so both fields
  always receive the SAME complete text (real answer + banner), never
  a banner-only string. Every read/write site in outlet() now goes
  through these two helpers instead of touching the fields directly.
  Still instrumented (always-on state-report banner) for one more
  confirming live pass -- once this correctly appends after the real
  answer AND correctly detects a real fabricated marker, revert to
  v0.6's gated (warn-only-on-real-problems) behavior for v0.10.

  v0.6 -> v0.8-instrumented (2026-08-21, same session): CONCLUSIVE
  RESULT from a stripped-down diagnostic build (v0.7-diagnostic,
  unconditional banner + dual-write, zero trigger logic, zero
  logging): the marker appeared LIVE on every message. This
  conclusively proves outlet()-based content mutation and the
  dual-write pattern genuinely work on this deployment -- the
  2026-08-13 open question from Reference Existence Gate's own
  changelog is now definitively answered (not a platform-wide
  rendering limitation). It also proves neither print() nor the
  standard logging module's absence from docker logs across v0.5/v0.6
  was ever a delivery-mechanism problem.

  This narrows the real question to: why does v0.6's actual trigger
  detection / identifier extraction logic, unlike the diagnostic
  build, never reach the point of writing a banner at all when run
  against REAL live Bakaidah message data -- despite passing every
  mocked unit test in Mokaima's sandbox. Since logging visibility is
  unconfirmed and now unnecessary (the banner mechanism is proven),
  this build stops depending on docker logs entirely and instead
  reports v0.6's exact internal decision state DIRECTLY IN THE VISIBLE
  BANNER, using the exact delivery path just proven to work.

  TEMPORARY INSTRUMENTATION: outlet() now ALWAYS writes a state-report
  banner (not gated behind "if warnings:") showing: whether a trigger
  was detected and what raw path it captured, what claimed identifiers
  were extracted (if any), what path was resolved, and what the mcpo
  fetch returned. All the REAL v0.6 logic (trigger regex, basename
  resolution, mcpo fetch, fabrication check) is UNCHANGED underneath --
  this only makes the outcome of each step visible instead of silent.
  Once we see what's actually happening against real data, revert to
  v0.6's original gated-banner behavior (only warn when something's
  actually wrong) with whatever fix this reveals.

  v0.5 -> v0.6 (2026-08-21, same session): v0.5's config was fully
  confirmed correct in the live Open WebUI Admin panel -- Type=filter,
  Active toggle ON, attached under Bakaidah (General)'s per-model
  Filters list, Global correctly OFF (intentionally scoped, not a
  bug) -- yet outlet() STILL produced zero log lines across a real
  live test, not even the unconditional entry log that fires on every
  message regardless of trigger. With every config point ruled out,
  the leading remaining hypothesis is the logging mechanism itself:
  v0.5 used bare print(), but every log line that DID appear in
  docker logs this whole investigation used a structured logger
  (loguru-style "module:function:line - LEVEL - message" format, e.g.
  open_webui.utils.tools:execute_tool_server). If Open WebUI executes
  Function code in a way that doesn't pipe raw stdout into that same
  captured stream (plausible for dynamically exec'd plugin code),
  v0.5's logging would have been silently useless regardless of
  whether outlet() ran -- reintroducing the exact "can't tell if it
  ran" ambiguity v0.5 was built to eliminate.
  FIX: replaced every print() call with Python's standard logging
  module (logger.warning(), module-level `logger = logging.
  getLogger(__name__)`), on the theory that a loguru-based setup
  typically intercepts the standard logging module via a compatibility
  handler even when it doesn't capture raw stdout. Used .warning()
  specifically to match the level of the one confirmed-visible
  Filter-adjacent log line seen this session (the tool_server 500).
  NO LOGIC CHANGE from v0.5 otherwise -- same trigger detection, same
  basename-first path resolution, same fabrication check, same
  dual-write. If this version's logs still show nothing, the logging
  mechanism itself is ruled out too, and the next step is checking
  whether ANY outlet()-based Filter's debug output has ever been
  confirmed to reach docker logs on this deployment -- a genuinely
  open question predating this ticket (see v0.5's docstring, FIX 2).

  v0.4 -> v0.5 (2026-08-21, same session): TWO real fixes, both from
  live docker logs evidence (docker logs open-webui, grepped for
  errors right after a live v0.4 test), not guesses.

  FIX 1 -- WRONG PATH, ROOT CAUSE OF EVERY v0.4 SILENT FAILURE: logs
  showed Bakaidah's OWN native tool call failing with "API Request
  Error: HTTP error 500: ... Parent directory does not exist:
  /srv/kaiju-vault/kaiju-gais-package/fashsd" -- on the
  EXACT path this whole ticket's test messages have used since v0.1
  ("kaiju-gais-package/fashsd/fashsd_config_lib.sh"). The real path is
  "kaiju-gais-package/fashsd/fashsd_config_lib.sh" --
  confirmed via direct list_directory. Bakaidah's native tool silently
  recovers via its own search_files fallback every time (visible in
  every prior transcript as 2 tool calls, never explained until now).
  This Filter had no equivalent fallback -- _fetch_file() got the same
  500 on every v0.4 live test and returned None every time.
  FIX: _resolve_path() now resolves by BASENAME via the cached
  directory_tree index UNCONDITIONALLY, even when the candidate
  already contains '/' (v0.4 only did this for bare filenames,
  wrongly trusting any path containing a slash as already-correct).

  FIX 2 -- NO OBSERVABILITY: v0.4 had zero logging. Every prior
  version's silence was ambiguous between "outlet() didn't run,"
  "ran but the fetch failed silently," and "ran, warned, but the
  banner is invisible in the UI" -- three completely different
  problems with identical symptoms from the chat window alone.
  FIX: added print()-based logging at every decision point in
  outlet() (invocation, trigger detection, resolved path, fetch
  result, warning count, dual-write field presence). print() output
  from an Open WebUI Function reaches `docker logs open-webui` --
  confirmed as a real, working diagnostic channel this same session
  (that's how Fix 1 was found at all). This makes the three failure
  modes above directly distinguishable from server logs, independent
  of whatever the chat UI does or doesn't render.

  v0.3 -> v0.4 (2026-08-21, To do and pending 2.8 part 3 ):
  FULL SCOPE REDIRECT, not an incremental fix. Root finding: Bakaidah
  (General) already has native, independently-configured tool access
  to vault via mcpo (confirmed in bakaidah_system_prompt.txt's WHAT
  BAKAIDAH CAN DO section -- "Read vault files for specific content,
  credentials, configs"), completely separate from this Filter and
  from the  Pipe. Live-tested directly: Test 2 (REFERENCE:
  fashsd_config_lib.sh) got a CORRECT, SPECIFIC answer (real function
  names) from Bakaidah's own native tool_read_text_file_post call --
  with zero involvement from this Filter's v0.1-v0.3 fetch-free
  inlet()-only design. That design's entire premise (get Bakaidah to
  read a file) was solving an already-solved problem.

  v0.1-v0.3's OTHER premise -- force a detectable, observable trigger
  marker via an inlet() system-message instruction -- also broke on
  its own terms: Test 3 (v0.3 live) showed the marker instruction
  competing with and partially overriding Bakaidah's actual task
  compliance (opened with the marker, then answered "I'm ready. What
  do you need?" instead of the real question). Generation-time
  instruction-injection is not a reliable place to build a mechanical
  check.

  v0.4 abandons BOTH premises. This Filter is now outlet()-ONLY,
  following the exact proven architecture already used successfully
  three times on this deployment (bakaidah_incident_fabrication_
  filter.py, bakaidah_reference_existence_filter.py, bakaidah_
  enforcement_gate_filter.py): treat body["messages"] purely as text,
  never assume tool-call trace data is present in body (confirmed --
  none of the 3 existing outlet()-based Filters read one; all three
  independently RE-FETCH ground truth via their own direct mcpo HTTP
  calls, decoupled from whatever tool Bakaidah itself used to answer).

  WHAT THIS FILTER UNIQUELY ADDS, not redundant with the existing 3:
  bakaidah_reference_existence_filter.py already checks that a claimed
  file PATH exists. Nothing existing checks whether specific facts
  Bakaidah states about a file's CONTENT (e.g. function/identifier
  names) are actually IN that file -- this is OUTPUT CONSTRAINT 8's
  job per the system prompt, but nothing mechanically enforces it.
  This Filter closes that specific gap: when the triggering user
  message contains a REFERENCE:/STATE:/HISTORY:/RULES: line, fetch
  the real referenced file via mcpo (reusing Reference Existence
  Gate's proven bare-filename resolution via a cached directory_tree
  index -- the exact fix that closed the fashsd_config_lib.sh
  false-negative), extract every backtick-quoted identifier-shaped
  token Bakaidah's response claims, and flag any that do not appear
  verbatim in the real file content.

  REUSED, NOT REINVENTED, from bakaidah_reference_existence_filter.py
  v0.5/v0.6 (confirmed-working patterns, same mcpo endpoints/timeouts):
    - _get_file_index() / _resolve_candidate(): bare-filename ->
      real full path resolution via a cached directory_tree walk.
    - Dual-write fix (v0.6): a warning banner written only to the
      flat body["messages"][i]["content"] field is silently INVISIBLE
      in Open WebUI's Native Mode chat UI (GitHub open-webui/open-webui
      issue #27017) -- must also write to the structured
      output[type=message].content[type=output_text].text field when
      present. Applied here from the start, not discovered live again.

  TRIGGER SYNTAX, unchanged from v0.1-v0.3: a message containing one
  or more lines of the form REFERENCE: <path> or STATE:/HISTORY:/
  RULES: <path> triggers this check. No trigger line present -> this
  Filter does nothing (true no-op, same as Test 1's confirmed-clean
  path).

  NOT YET LIVE-TESTED. Syntax-checked (py_compile, escape-sequence
  grep) AND logic-tested in Mokaima's sandbox before this write, per
  the syntax-self-check skill. v0.5's mocked tree/read fixture was
  rebuilt to mirror the REAL vault structure this time (the wrong-path
  bug this version fixes, reproduced deliberately: no-op path, wrong
  partial path + real identifiers claimed [resolves via basename, no
  warning], wrong partial path + one fabricated identifier claimed
  [resolves via basename, warning correctly fires -- the exact live
  failure scenario], correct full path used directly -- all 4 passed)
  -- not a lenient substring-matching mock, per the documented lesson
  from Reference Existence Gate v0.4/v0.5's own mock-fidelity bug.

  PHASE PLAN (, this file's own build history):
    v0.1 (2026-08-20) -- async/event-emitter trigger detection.
      DEPLOYED, TESTED, NO VISIBLE TRACE. Superseded by v0.2.
    v0.2 (2026-08-20) -- sync rewrite, passive system-message marker.
      DEPLOYED, TESTED, NO VISIBLE TRACE (unfalsifiable test design).
      Superseded by v0.3.
    v0.3 (2026-08-20/21) -- sync execution, instruction-based visible
      marker. DEPLOYED, TESTED. Marker fired correctly on multi-lens
      (STATE:) but not on single-lens (REFERENCE:) -- asymmetry never
      root-caused, moot after this redirect. Marker-firing also
      measurably hijacked task compliance once (Test 3). Superseded
      by v0.4's full scope redirect.
    v0.4 (2026-08-21) -- outlet()-only content-fabrication check,
      reusing Reference Existence Gate's proven re-fetch/dual-write
      architecture instead of inlet()-based generation-time control.
      DEPLOYED, TESTED. No warning ever appeared, including on a
      deliberately-planted guaranteed-fake identifier
      (`kaiju_test_marker_12345`) -- root-caused via docker logs to
      the wrong-path bug fixed in v0.5, not a dual-write/UI-rendering
      issue (that deeper question remains genuinely open, but is no
      longer the leading suspect).
    v0.5 (2026-08-21) -- basename-first path resolution (fixes the
      confirmed wrong-path bug) + full print()-based observability.
      DEPLOYED, TESTED. Config independently confirmed fully correct
      in Admin panel (Active, attached, correctly-scoped Global=off)
      -- yet outlet() produced ZERO log output, including the
      unconditional entry line. Root-caused to bare print() likely
      not reaching the captured log stream, not a config or logic
      problem. Superseded by v0.6.
    v0.6 (2026-08-21) -- same logic as v0.5, print() replaced with
      Python's standard logging module throughout. DEPLOYED, TESTED.
      Still ZERO log output, even with confirmed correct config on
      every point. Superseded by a stripped-down diagnostic build
      (v0.7-diagnostic, not saved as this file's history -- a
      throwaway unconditional-banner test), which DID render live on
      every message -- proving the banner/dual-write mechanism itself
      works. Superseded by v0.8-instrumented.
    v0.8-instrumented (2026-08-21) -- same real v0.6 logic underneath,
      but ALWAYS writes a visible state-report banner. DEPLOYED,
      LIVE-TESTED. Correctly revealed trigger detection working, but
      also revealed a critical bug: the banner REPLACED Bakaidah's real
      answer instead of appending to it, because it read/wrote the
      wrong field (flat "content", empty in Native Mode) instead of
      the real structured output field. Superseded by v0.9.
    v0.9-instrumented (2026-08-21) -- fixes the field-read/write bug
      via new _get_real_response_text()/_write_response_text() helpers.
      DEPLOYED, LIVE-TESTED, FIRST GENUINE SUCCESS: real answer
      preserved correctly, trigger/extraction/resolution/fetch all
      worked, fabrication check correctly flagged exactly the planted
      fake identifier with zero false positives among 16 real ones.
      Superseded by v0.10.
    v0.10 (this version) -- instrumentation removed, restored to
      warn-only-on-real-problems (silent on ordinary responses).
      Excludes the trigger file's own basename from identifier checks
      (a path-reference false-positive risk found in the v0.9 live
      test). NOT YET LIVE-TESTED in this exact (non-instrumented)
      form -- the underlying logic is the same code proven working in
      v0.9's live test, only the always-on reporting wrapper changed.
    v0.11+ (planned) -- broaden claimed-fact extraction beyond
      backtick-quoted identifiers (bare snake_case tokens in list
      items, matching some of Bakaidah's observed response formats).
"""

import re
import time
import json as _json
import logging
import requests
from pydantic import BaseModel, Field
from typing import Optional, List

logger = logging.getLogger(__name__)


class Filter:
    class Valves(BaseModel):
        enabled: bool = Field(
            default=True,
            description="Master on/off switch for this Filter.",
        )
        mcpo_read_url: str = Field(
            default="http://localhost:8200/vault/read_text_file",
            description="mcpo endpoint for reading vault files. Same "
            "confirmed-live endpoint used by bakaidah_reference_"
            "existence_filter.py and bakaidah_incident_fabrication_"
            "filter.py.",
        )
        mcpo_tree_url: str = Field(
            default="http://localhost:8200/vault/directory_tree",
            description="mcpo endpoint for directory_tree, used to "
            "build a basename -> full path index for resolving a "
            "bare filename the triggering REFERENCE:/STATE: line "
            "names without its directory. Same endpoint/approach as "
            "bakaidah_reference_existence_filter.py v0.5.",
        )
        request_timeout_seconds: int = Field(
            default=10,
            description="Timeout for the single referenced-file fetch.",
        )
        tree_timeout_seconds: int = Field(
            default=20,
            description="Timeout for the directory_tree call used to "
            "build the file index -- longer than a single read, since "
            "it walks the whole vault tree.",
        )
        index_cache_seconds: int = Field(
            default=300,
            description="How long the file index is cached before "
            "re-walking the tree. vault doesn't change fast enough to "
            "need a fresh walk on every single check.",
        )
        max_identifiers_checked: int = Field(
            default=25,
            description="Safety cap on how many claimed identifiers "
            "to verify in one response.",
        )
        priority: int = Field(
            default=0, description="Filter execution priority. Lower runs first."
        )

    def __init__(self):
        self.valves = self.Valves()
        self._file_index_cache: dict = {}
        self._file_index_cache_time: float = 0

        # Trigger detection -- unchanged syntax from v0.1-v0.3.
        self._reference_line_pattern = re.compile(
            r"^\s*REFERENCE:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE
        )
        self._lens_line_pattern = re.compile(
            r"^\s*(STATE|HISTORY|RULES):\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE
        )

        # Claimed-identifier extractor: backtick-quoted tokens shaped
        # like a function/variable/config name (word chars, underscore,
        # dot, hyphen -- covers snake_case, dotted, and kebab-case
        # identifiers). Deliberately does NOT try to catch bare
        # (non-backtick) identifiers in this version -- see v0.5+ note
        # in the module docstring.
        self._identifier_pattern = re.compile(r"`([A-Za-z_][A-Za-z0-9_.\-]{1,80})`")

    # -- Trigger detection (unchanged logic from v0.1-v0.3) ------------

    def _detect_trigger_path(self, text: str) -> Optional[str]:
        """Returns the first referenced path from a STATE:/HISTORY:/
        RULES: or REFERENCE: line in the given text, or None if no
        trigger line is present. Lens lines win over REFERENCE: if
        both present, same precedence as the  Pipe."""
        lens_match = self._lens_line_pattern.search(text)
        if lens_match:
            return lens_match.group(2).strip()
        ref_match = self._reference_line_pattern.search(text)
        if ref_match:
            return ref_match.group(1).strip()
        return None

    # -- File resolution (reused pattern from Reference Existence Gate) -

    def _get_file_index(self) -> dict:
        """Builds/caches a basename -> [full relative paths] index via
        ONE directory_tree call, refreshed after index_cache_seconds.
        Reused, not reinvented, from bakaidah_reference_existence_
        filter.py v0.5 -- same reasoning: a bare filename can never
        resolve via a literal mcpo read_text_file call, which requires
        an exact relative path. Degrades gracefully: returns the last
        good cache (possibly empty) on failure, rather than raising."""
        now = time.time()
        if (
            self._file_index_cache
            and (now - self._file_index_cache_time) < self.valves.index_cache_seconds
        ):
            return self._file_index_cache
        try:
            resp = requests.post(
                self.valves.mcpo_tree_url,
                json={"path": "", "excludePatterns": [".git"]},
                timeout=self.valves.tree_timeout_seconds,
            )
            if resp.status_code != 200:
                return self._file_index_cache
            tree = resp.json()
            if isinstance(tree, dict) and "content" in tree:
                tree = _json.loads(tree["content"])
            index: dict = {}

            def walk(entries, prefix):
                for entry in entries:
                    name = entry.get("name", "")
                    full = f"{prefix}/{name}" if prefix else name
                    if entry.get("type") == "file":
                        index.setdefault(name, []).append(full)
                    elif entry.get("type") == "directory":
                        walk(entry.get("children", []), full)

            walk(tree, "")
            self._file_index_cache = index
            self._file_index_cache_time = now
            return index
        except Exception:
            return self._file_index_cache

    def _resolve_path(self, candidate: str) -> str:
        """v0.5 FIX: a candidate containing '/' is NO LONGER assumed
        correct as-is. Proven wrong live (2026-08-21): every REFERENCE:
        test message across v0.1-v0.4 used a PARTIAL path
        ("kaiju-gais-package/fashsd/fashsd_config_lib.sh") missing a real
        directory segment ("") -- confirmed via
        docker logs showing Bakaidah's OWN native tool call fail with
        an identical 500 "Parent directory does not exist" error on
        its first attempt, before silently recovering via its own
        search_files fallback (2 tool calls every time, not 1 -- a
        pattern visible in every prior test transcript, never
        previously explained). This Filter had no equivalent fallback,
        so _fetch_file() silently got the same 500 every time and
        returned None.
        Fixed: resolve by BASENAME via the cached directory_tree index
        regardless of whether the candidate contains '/' -- if the
        basename resolves to exactly one real file, use that real full
        path instead of trusting the candidate's own directory
        portion. Falls back to the literal candidate only if the
        basename index lookup finds zero or multiple matches."""
        basename = candidate.rsplit("/", 1)[-1]
        index = self._get_file_index()
        matches = index.get(basename, [])
        if len(matches) == 1:
            return matches[0]
        return candidate

    def _fetch_file(self, path: str) -> Optional[str]:
        """Real read via mcpo. Read-only. Returns None on any failure
        (network, timeout, non-200, missing file) -- None must be
        treated as 'unable to verify', never as 'claim is fabricated'."""
        try:
            resp = requests.post(
                self.valves.mcpo_read_url,
                json={"path": path},
                timeout=self.valves.request_timeout_seconds,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if isinstance(data, str):
                return data
            if isinstance(data, dict):
                for key_path in (("content",), ("text",), ("result", "content")):
                    val = data
                    try:
                        for k in key_path:
                            val = val[k]
                        if isinstance(val, str):
                            return val
                    except (KeyError, IndexError, TypeError):
                        continue
            return None
        except Exception:
            return None

    # -- Content-fabrication check (the new, non-redundant part) -------

    @staticmethod
    def _get_real_response_text(message: dict) -> str:
        """v0.9 FIX, ROOT CAUSE OF THE ENTIRE SESSION'S MYSTERY: in
        Native Mode, the flat message["content"] field is empty/stale
        -- the REAL rendered answer lives in the structured
        output[type=message].content[type=output_text].text field
        instead (the same field Reference Existence Gate's v0.6 fix
        identified as what the UI actually renders FROM, but this
        Filter never READ from -- only ever wrote to it). Every
        version through v0.8 read message["content"] as "the response
        text" and got an empty string every time, which explains every
        prior "claimed identifiers extracted: NONE" and every silent
        no-op since v0.4 -- not because Bakaidah's answers lacked
        backtick-quoted content, but because this Filter was checking
        the wrong field entirely.
        CONFIRMED LIVE (2026-08-21): v0.8's always-on banner, written
        via content=response_text+banner where response_text was "",
        then dual-written into the structured output_text field,
        VISIBLY REPLACED Bakaidah's real answer in the chat -- Bakaidah's
        own generated follow-up prompts asked "why did it replace the
        actual answer?", directly confirming the structured field held
        the real text that got overwritten.
        Prefers the structured output_text field; falls back to flat
        content only if no structured output exists (Legacy Mode, or a
        model that didn't return one) -- mirrors the fallback direction
        of the existing dual-WRITE logic, just for reading."""
        for _output_item in message.get("output", []) or []:
            if _output_item.get("type") != "message":
                continue
            for _content_part in _output_item.get("content", []) or []:
                if _content_part.get("type") == "output_text":
                    text = _content_part.get("text")
                    if text:
                        return text
        return message.get("content", "") or ""

    @staticmethod
    def _write_response_text(message: dict, new_text: str) -> None:
        """v0.9 companion to _get_real_response_text -- writes the
        FULL final text (real answer + banner, already combined by the
        caller) to both fields. This is the corrected dual-write: v0.8
        wrote (empty content + banner) into BOTH fields, which is what
        destroyed the real answer -- the caller must pass the complete
        text (real content included), not just the banner."""
        message["content"] = new_text
        for _output_item in message.get("output", []) or []:
            if _output_item.get("type") != "message":
                continue
            for _content_part in _output_item.get("content", []) or []:
                if _content_part.get("type") == "output_text":
                    _content_part["text"] = new_text

    def _extract_claimed_identifiers(self, response_text: str) -> List[str]:
        found = self._identifier_pattern.findall(response_text)
        seen = set()
        result = []
        for ident in found:
            if ident not in seen:
                seen.add(ident)
                result.append(ident)
        return result[: self.valves.max_identifiers_checked]

    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        # v0.4: true no-op. All logic moved to outlet() -- see module
        # docstring for why inlet()-based generation-time control was
        # abandoned in this version.
        return body

    def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        logger.warning("[ v0.10] outlet() invoked")

        if not self.valves.enabled:
            return body

        messages = body.get("messages", [])
        if not messages:
            return body

        last_assistant_idx = None
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "assistant":
                last_assistant_idx = i
                break
        if last_assistant_idx is None:
            return body

        triggering_msg = ""
        for i in range(last_assistant_idx - 1, -1, -1):
            if messages[i].get("role") == "user":
                triggering_msg = messages[i].get("content", "") or ""
                break

        trigger_path = self._detect_trigger_path(triggering_msg)
        if trigger_path is None:
            # TRUE NO-OP: no REFERENCE:/STATE:/HISTORY:/RULES: line in
            # the triggering message. No body mutation, no mcpo calls.
            # v0.9 confirmed live: the real answer correctly survives
            # untouched on this path, since it's never read or written.
            return body

        response_text = self._get_real_response_text(messages[last_assistant_idx])
        claimed_identifiers = self._extract_claimed_identifiers(response_text)
        # v0.10: exclude the trigger file's own basename from the
        # claims to check -- confirmed live (2026-08-21) that a
        # response mentioning the filename itself in backticks (e.g.
        # "The functions in `fashsd_config_lib.sh` are:") gets swept
        # into claimed_identifiers by the regex, which is a path
        # reference, not a code identifier being asserted. That case
        # happened to pass by coincidence (the file's own header
        # comment mentions its filename), but is fragile for files
        # without a self-referential header -- exclude it outright.
        trigger_basename = trigger_path.rsplit("/", 1)[-1]
        claimed_identifiers = [
            i for i in claimed_identifiers if i != trigger_basename
        ]
        if not claimed_identifiers:
            return body

        resolved_path = self._resolve_path(trigger_path)
        real_content = self._fetch_file(resolved_path)

        warnings = []
        if real_content is None:
            warnings.append(
                f"note: this response makes {len(claimed_identifiers)} "
                f"specific identifier claim(s) about '{trigger_path}', "
                "but that file could not be fetched via mcpo to verify "
                "them (missing, or a connection/timeout issue). Treat "
                "these claims as UNVERIFIED until checked manually: "
                + ", ".join(f"`{i}`" for i in claimed_identifiers)
            )
        else:
            missing = [i for i in claimed_identifiers if i not in real_content]
            if missing:
                warnings.append(
                    "warning: LIKELY FABRICATED IDENTIFIER CLAIM -- this "
                    f"response states the following as if present in "
                    f"'{trigger_path}', but they do not appear anywhere "
                    "in the real file content (fetched via mcpo): "
                    + ", ".join(f"`{i}`" for i in missing)
                    + ". Do not trust these without verifying against the "
                    "real file yourself."
                )

        if not warnings:
            # v0.10: genuinely clean, real warn-only-on-real-problems
            # behavior restored -- no banner, real answer untouched.
            return body

        banner = "\n\n---\n" + "\n".join(warnings)
        new_text = response_text + banner
        self._write_response_text(messages[last_assistant_idx], new_text)
        body["messages"] = messages

        return body
