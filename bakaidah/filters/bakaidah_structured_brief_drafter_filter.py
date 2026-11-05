"""
title: Bakaidah Structured Brief Drafter Filter
author: the operator / Mokaima
author_url: N/A
funding_url: N/A
version: 0.3
description: v0.3 (2026-10-25): inlet() now appends a REAL FILE LISTING (read
  from the vault through mcpo directory_tree for the folders in valve
  listing_folders, default kaiju-gais-package/fashsd and the two
  angkai/staging fix-script folders) and the highest fmNN number seen, so
  the model copies real file names instead of recalling them. Fails open:
  if mcpo does not answer within listing_timeout_seconds the listing is
  skipped and v0.2 behavior applies. This adds up to 3 short network calls
  on brief requests only (the 'zero network calls' note further down
  refers to v0.1/v0.2). Valve inject_real_file_listing turns it off.
  v0.2 (2026-10-25): inlet() steering rules 6-8 added after the
  10-24 P2 regression runs (header date 2025-05-22 and 'Written by: AI
  Assistant' in all 3 drafts; wrong REFERENCES folder names; one draft
  banning public domains for a DNS test). The outlet() log string below
  still says v0.1 on purpose, so existing log greps keep working.
   Phase 2 (item 3 of 4) -- Filter (inlet/outlet),
  NOT a Pipe. Always-on, attached directly to Bakaidah (General).

  ARCHITECTURE NOTE, why this is a SHARPER scope-narrowing than the
  citation grounding Filter (2026-08-22, To do and pending 2.8 Phase 2
  ): the Pipe's mechanical guarantee (every MABS section field
  MUST exist and be non-empty, or generation is invalid at the
  grammar level) comes from calling Ollama's native /api/chat directly
  with a "format" JSON-Schema parameter, which Ollama converts into a
  GBNF grammar enforced at token-sampling time. The Pipe's OWN
  docstring documents a confirmed, already-researched Open WebUI
  limitation: Open WebUI's normal /api/chat/completions path SILENTLY
  DROPS response_format/json_schema parameters before relaying to
  Ollama. This means even inlet() injecting a schema into body before
  generation would be stripped before Bakaidah's real turn ever saw
  it -- the mechanical guarantee is Ollama-native-API-only, not
  something any Filter operating inside Open WebUI's normal
  completion flow can replicate. Same structural ceiling as the
  citation grounding Filter, for a documented reason this time rather
  than an inferred one.

  DOWNGRADE, EXPLICIT: "mechanically impossible to omit a section" is
  NOT achievable here. What this Filter delivers instead is
  "mechanically DETECTED if a section is missing or a known content
  bug is present" -- weaker, but still catches the exact failure
  modes (a section silently dropped, a REFERENCES/EXPECTED_FILES
  circularity, an unflagged IP:port, a sed single-quote variable bug,
  a deliverable path inconsistent with its own EXPECTED FILES list)
  that originally justified building the Pipe. the operator's explicit
  choice, this session, to proceed on this basis rather than skip the
  port.

  DESIGN:
    inlet(): detects a brief-drafting request via the Pipe's own
      _brief_request_pattern regex (reused verbatim), and if matched,
      injects the Pipe's five Kaidosho-specific fact rules (BRIEF ID format,
      INSTALL PATH RULE, self-hosted-not-public-cloud, write-only/
      no-deploy, REFERENCES-can't-overlap-EXPECTED_FILES) as a
      steering instruction. Soft, not enforced -- same class of
      instruction-only rule this project has repeatedly found
      insufficient alone (hence outlet() below).
    outlet(): only runs its checks when the TRIGGERING user message
      (not the response) matched _brief_request_pattern -- same
      trigger-on-the-user-message convention as  Phase 1's
      REFERENCE:/STATE:/HISTORY:/RULES: detection, avoiding wasted
      work and false positives on ordinary non-brief chats. Two
      layers of check against the FINISHED FREE-TEXT response (no
      schema, no JSON -- Bakaidah's real output through this path is
      markdown prose, not schema-validated data):
        1. STRUCTURAL COMPLETENESS: regex-detects presence/absence of
           each of the 6 required MABS section headers (HARD
           PROHIBITIONS, CONFIRM BRIEF LOADED, TASK, REFERENCES,
           EXPECTED FILES, FINAL INSTRUCTION) plus a boolean check for
           code-block content (```) standing in for OUTPUT FORMAT.
           Flags whichever are missing.
        2. CONTENT-LEVEL CHECKS, re-derived (not copy-pasted -- there
           is no dict to walk) from _mechanical_postcheck()'s four
           checks in the Pipe: REFERENCES/EXPECTED_FILES path overlap
           (circularity), IP:port address scan (_IP_PORT_PATTERN,
           REUSED VERBATIM), sed-single-quote-shell-variable bug
           (_SED_SINGLEQUOTE_VAR_PATTERN, REUSED VERBATIM), and a
           FINAL-INSTRUCTION-path-vs-EXPECTED-FILES mismatch check
           (_DELIVERABLE_PATH_PATTERN, REUSED VERBATIM). REFERENCES/
           EXPECTED FILES/FINAL INSTRUCTION section BLOCKS are located
           via a shared _build_section_map() helper (first occurrence
           of each header, sliced to the next header's start) rather
           than a schema-guaranteed field -- a real, honest
           approximation, not the Pipe's guaranteed structure.

  NOT YET LIVE-TESTED. Reuses Phase 1's proven dual-write helpers
  (_get_real_response_text/_write_response_text) verbatim -- same
  Native Mode structured-output-field requirement applies to any
  Filter mutating an assistant message, not just Phase 1's own.
  Zero network calls (unlike the citation grounding Filter) -- all
  checks are pure text/regex against the finished response, no
  latency cost, no fetch-failure edge case to handle.
  Syntax-checked (py_compile, escape-sequence grep) in Mokaima's
  sandbox before this write, per the syntax-self-check skill.
required_open_webui_version: 0.5.0
"""

import re
import logging
import json as _json
import requests
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Tuple

logger = logging.getLogger(__name__)


class Filter:
    class Valves(BaseModel):
        enabled: bool = Field(
            default=True,
            description="Master on/off switch for this Filter.",
        )
        inject_dd_fact_rules: bool = Field(
            default=True,
            description="If True, inlet() appends the Pipe's five "
            "Kaidosho-specific fact rules as a steering instruction when a "
            "brief-drafting request is detected. Soft, not enforced.",
        )
        inject_real_file_listing: bool = Field(
            default=True,
            description="v0.3: append a real vault file listing (and the "
            "highest fmNN number) to the inlet steering text.",
        )
        mcpo_tree_url: str = Field(
            default="http://localhost:8200/vault/directory_tree",
            description="v0.3: mcpo endpoint for directory_tree (same one "
            "the Reference Existence Gate uses).",
        )
        listing_folders: str = Field(
            default="kaiju-gais-package/fashsd|"
            "angkai/staging/|"
            "angkai/staging/",
            description="v0.3: vault folders to list, separated by |.",
        )
        listing_timeout_seconds: int = Field(
            default=4,
            description="v0.3: per-folder timeout; on failure the listing "
            "is skipped (fail open).",
        )
        priority: int = Field(
            default=0, description="Filter execution priority. Lower runs first."
        )

    def __init__(self):
        self.valves = self.Valves()

        # Reused verbatim from bakaidah_structured_brief_drafter_pipe.py
        self._brief_request_pattern = re.compile(
            r"\b(mabs[- ]?format|mabs[- ]?brief|angkai brief|draft.*brief|"
            r"write.*brief)\b",
            re.IGNORECASE,
        )
        self._IP_PORT_PATTERN = re.compile(
            r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{2,5}\b"
        )
        self._SED_SINGLEQUOTE_VAR_PATTERN = re.compile(
            r"sed\s+[^\n]*'[^']*\$\{?[A-Za-z_][A-Za-z0-9_]*\}?[^']*'"
        )
        self._DELIVERABLE_PATH_PATTERN = re.compile(
            r"(?:/srv|/mnt/hola\d+)[\w\-./]*\.\w+"
        )

        # Section headers used for BOTH structural presence-check and
        # block-splitting (REFERENCES/EXPECTED FILES/FINAL INSTRUCTION
        # blocks are needed for the content-level checks below). Code
        # block presence ("```") is checked separately as a standalone
        # boolean -- it can appear many times, so it isn't reliable as
        # a section-splitting boundary the way a single header is.
        self._section_patterns: List[Tuple[str, "re.Pattern"]] = [
            ("HARD PROHIBITIONS", re.compile(r"hard\s+prohibitions", re.IGNORECASE)),
            ("CONFIRM BRIEF LOADED", re.compile(r"confirm\s+brief\s+loaded", re.IGNORECASE)),
            ("TASK", re.compile(r"\btask\b", re.IGNORECASE)),
            ("REFERENCES", re.compile(r"\breferences\b", re.IGNORECASE)),
            ("EXPECTED FILES", re.compile(r"expected\s+files", re.IGNORECASE)),
            ("FINAL INSTRUCTION", re.compile(r"final\s+instruction", re.IGNORECASE)),
        ]
        self._code_block_pattern = re.compile(r"```")

    @staticmethod
    def _today() -> str:
        """Today's date in the operator's time zone (UTC if zoneinfo fails)."""
        try:
            from zoneinfo import ZoneInfo
            return datetime.now(ZoneInfo("America/Detroit")).strftime("%Y-%m-%d")
        except Exception:
            return datetime.utcnow().strftime("%Y-%m-%d")

    def _list_folder(self, folder: str) -> Optional[List[str]]:
        """v0.3: names of the files directly inside one vault folder, read
        through mcpo directory_tree. None on any failure (fail open)."""
        try:
            resp = requests.post(
                self.valves.mcpo_tree_url,
                json={"path": folder, "excludePatterns": [".git", "__pycache__"]},
                timeout=self.valves.listing_timeout_seconds,
            )
            if resp.status_code != 200:
                return None
            tree = resp.json()
            if isinstance(tree, dict) and "content" in tree:
                tree = _json.loads(tree["content"])
            if not isinstance(tree, list):
                return None
            return sorted(
                e.get("name", "") for e in tree
                if e.get("type") == "file" and e.get("name")
            )
        except Exception:
            return None

    def _real_listing_text(self) -> str:
        """v0.3: ground-truth file listing for the folders briefs usually
        cite, plus the highest fmNN number seen. Empty string when
        disabled or when nothing could be read."""
        if not self.valves.inject_real_file_listing:
            return ""
        folders = [f.strip() for f in self.valves.listing_folders.split("|") if f.strip()]
        lines = []
        highest = -1
        for folder in folders:
            names = self._list_folder(folder)
            if not names:
                continue
            lines.append("vault/" + folder + "/ contains: " + ", ".join(names))
            for n in names:
                m = re.match(r"fm(\d+)_", n)
                if m:
                    highest = max(highest, int(m.group(1)))
        if not lines:
            return ""
        text = (
            "REAL FILE LISTINGS (read from the vault just now; ground "
            "truth, overrides anything you remember): "
            + " || ".join(lines)
            + ". A REFERENCES file name must be copied from these lists "
            "or from a file you read this response, together with its "
            "real folder; never combine a name with a different folder. "
            "A new file in EXPECTED FILES must not reuse a name above"
        )
        if highest >= 0:
            text += (
                " and, for a failure-mode script (fmNN_...), must take a "
                "number above fm%02d" % highest
            )
        return text + "."

    # -- inlet(): soft steering instruction, not mechanically enforced --

    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        if not self.valves.enabled or not self.valves.inject_dd_fact_rules:
            return body

        messages = body.get("messages", [])
        last_user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_msg = m.get("content", "") or ""
                break

        if not self._brief_request_pattern.search(last_user_msg):
            return body

        instruction = (
            "This looks like a request to draft a MABS-format Angkai "
            "brief. Follow these Kaidosho-specific facts exactly: (1) BRIEF ID "
            "format is always ANG-DRAFT-<short-topic>, never a different "
            "format. (2) INSTALL PATH RULE: every file this brief creates "
            "deploys to /srv or /mnt/drive1-drive3 ONLY -- never /etc, "
            "/usr/local/bin, /opt, or /home, including config files. "
            "(3) Kaidosho services are self-hosted on dokaisho (192.0.2.45) or "
            "the pi-node (192.0.2.21), never a public SaaS URL. (4) Angkai "
            "writes files only, never deploys/starts/executes them -- say "
            "so explicitly in the final instruction. (5) REFERENCES must "
            "be files to read beforehand -- never list a file that also "
            "appears in this brief's own EXPECTED FILES. "
            "(6) The brief's header line must read 'Written by: Mokaima "
            "(drafted by Bakaidah, pending Mokaima review) | "
            f"{self._today()}' -- use exactly that date, never another, "
            "and never 'AI Assistant'. "
            "(7) Folder names in REFERENCES and EXPECTED FILES must be "
            "copied exactly from files you read this response or from the "
            "vault file tree in your instructions, never shortened or "
            "guessed (real examples: angkai/staging//, "
            "angkai/staging//; the Kaiju package folder is "
            "kaiju-gais-package/ and there is no kaiju-gais-package/ folder). "
            "(8) Point (3) is about Kaidosho's own services; do not add a HARD "
            "PROHIBITION that bans public domains (for example "
            "example.com or google.com) in a DNS or connectivity test "
            "unless the request itself says so."
        )
        listing = self._real_listing_text()
        if listing:
            instruction = instruction + " " + listing

        for msg in messages:
            if msg.get("role") == "system":
                existing = msg.get("content", "") or ""
                if instruction not in existing:
                    msg["content"] = existing.rstrip() + "\n\n" + instruction
                body["messages"] = messages
                return body

        messages.insert(0, {"role": "system", "content": instruction})
        body["messages"] = messages
        return body

    # -- outlet(): the actual mechanical check --------------------------

    @staticmethod
    def _get_real_response_text(message: dict) -> str:
        """Reused verbatim from  Phase 1."""
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
        """Reused verbatim from  Phase 1."""
        message["content"] = new_text
        for _output_item in message.get("output", []) or []:
            if _output_item.get("type") != "message":
                continue
            for _content_part in _output_item.get("content", []) or []:
                if _content_part.get("type") == "output_text":
                    _content_part["text"] = new_text

    def _build_section_map(self, text: str) -> Tuple[Dict[str, str], set]:
        """Finds the first occurrence of each required section header,
        sorts by position, and slices the text between consecutive
        headers into blocks. Returns (blocks, found_labels) -- blocks
        only contains entries for headers actually found; found_labels
        is used by the structural completeness check to determine what's
        missing. This is a real, honest APPROXIMATION of the Pipe's
        schema-guaranteed structure, not a guarantee itself -- free text
        has no enforced field boundaries."""
        matches = []
        for label, pattern in self._section_patterns:
            m = pattern.search(text)
            if m:
                matches.append((m.start(), m.end(), label))
        matches.sort(key=lambda t: t[0])

        blocks: Dict[str, str] = {}
        for i, (start, end, label) in enumerate(matches):
            next_start = matches[i + 1][0] if i + 1 < len(matches) else len(text)
            blocks[label] = text[end:next_start]

        found_labels = {label for _, _, label in matches}
        return blocks, found_labels

    def _check_structural_completeness(self, text: str, found_labels: set) -> List[str]:
        warnings = []
        required_labels = {label for label, _ in self._section_patterns}
        missing = sorted(required_labels - found_labels)
        if missing:
            warnings.append(
                "STRUCTURAL WARNING: this looks like a MABS brief draft "
                "but appears to be missing expected section(s): "
                + ", ".join(missing)
                + ". A real MABS brief needs all of these -- verify "
                "before treating this as complete."
            )
        if not self._code_block_pattern.search(text):
            warnings.append(
                "STRUCTURAL WARNING: no code block (```) found in this "
                "draft -- a MABS brief's OUTPUT FORMAT section should "
                "contain the actual deliverable content."
            )
        return warnings

    def _check_content_bugs(self, text: str, blocks: Dict[str, str]) -> List[str]:
        warnings = []

        # Re-derived from Pipe Bug 1 (REFERENCES/EXPECTED_FILES
        # circularity) -- operates on Kaidosho-path-shaped tokens found in
        # each block, not a schema-guaranteed path list.
        references_block = blocks.get("REFERENCES", "")
        expected_block = blocks.get("EXPECTED FILES", "")
        if references_block and expected_block:
            ref_paths = set(self._DELIVERABLE_PATH_PATTERN.findall(references_block))
            expected_paths = set(self._DELIVERABLE_PATH_PATTERN.findall(expected_block))
            overlap = sorted(ref_paths & expected_paths)
            for path in overlap:
                warnings.append(
                    f"REFERENCES circularity: '{path}' appears in both "
                    "the REFERENCES section and the EXPECTED FILES "
                    "section -- a file can't be both an output being "
                    "created and an input read beforehand."
                )

        # Reused verbatim from Pipe Bug 2 (unconfirmed IP:port address).
        for addr in sorted(set(self._IP_PORT_PATTERN.findall(text))):
            warnings.append(
                f"UNCONFIRMED ADDRESS: '{addr}' appears in this draft. "
                "Bakaidah has no live system access and cannot confirm "
                "real addresses/ports -- verify against "
                "DD_Services_Index.md before trusting this value."
            )

        # Reused verbatim from Pipe Bug 3 (sed single-quote shell var).
        for m in self._SED_SINGLEQUOTE_VAR_PATTERN.findall(text):
            warnings.append(
                "SHELL QUOTING BUG: a sed expression has a shell "
                "variable reference inside single quotes -- it will "
                f"NOT expand and will write the literal text into the "
                f"target file instead of its real value. Snippet: {m[:80]}"
            )

        # Re-derived from Pipe Bug 4 (deliverable path vs EXPECTED
        # FILES mismatch) -- checked against the FINAL INSTRUCTION
        # block specifically, matching the Pipe's own narrower scope
        # (final_instruction + code_sections labels, not the whole
        # response) rather than the whole text, to avoid false
        # positives on paths correctly reused in TASK/REFERENCES.
        final_block = blocks.get("FINAL INSTRUCTION", "")
        if final_block and expected_block:
            mentioned = set(self._DELIVERABLE_PATH_PATTERN.findall(final_block))
            expected_paths = set(self._DELIVERABLE_PATH_PATTERN.findall(expected_block))
            mismatched = sorted(mentioned - expected_paths)
            for path in mismatched:
                warnings.append(
                    f"DELIVERABLE PATH MISMATCH: '{path}' is named in "
                    "the FINAL INSTRUCTION section but does NOT appear "
                    "in this brief's own EXPECTED FILES list -- the "
                    "real deliverable may be missing from, or "
                    "inconsistently named against, its own closed list."
                )

        return warnings

    def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        logger.warning(
            "[ Phase 2, structured brief drafter v0.1] outlet() invoked"
        )

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

        if not self._brief_request_pattern.search(triggering_msg):
            # True no-op: not a brief-drafting request at all.
            return body

        response_text = self._get_real_response_text(messages[last_assistant_idx])
        if not response_text:
            return body

        blocks, found_labels = self._build_section_map(response_text)
        warnings = self._check_structural_completeness(response_text, found_labels)
        warnings += self._check_content_bugs(response_text, blocks)

        if not warnings:
            # Warn-only-on-real-problems: silent when structurally
            # complete and no known content bugs found.
            return body

        lines = ["warning: MABS brief draft issues found (mechanical check, not model self-report):"]
        for w in warnings:
            lines.append(f"- {w}")
        banner = "\n\n---\n" + "\n".join(lines)
        new_text = response_text + banner
        self._write_response_text(messages[last_assistant_idx], new_text)
        body["messages"] = messages

        return body
