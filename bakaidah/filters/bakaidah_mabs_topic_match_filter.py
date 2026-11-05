"""
title: Bakaidah MABS Brief Topic Match Gate
author: the operator / Mokaima
author_url: N/A
funding_url: N/A
version: 0.2
description: Deterministic post-response gate for MABS-brief-shaped
  requests. Cannot force a retry -- only warns after generation
  completes, same limitation as Bakaidah Enforcement Gate. Added after
  Bakaidah failed a "draft a MABS brief for X" request 3 consecutive
  times (v2.7-v2.9), each time in a different shape.

  v0.1 -> v0.2 (2026-07-25): a 5th failed attempt revealed the fake
  response had a title mentioning the right subject ("Vaultwarden
  Health Check Restart Script") while EVERY substantive section (TASK,
  REFERENCES, code) was actually about a completely different, real,
  unrelated task (FM-02 Docker-daemon generalization) -- just relabeled
  with a new ID and title. This slipped past v0.1 for two confirmed
  reasons, both fixed here:
    (1) The structural-marker regexes required a colon immediately
        after each section header (e.g. "REFERENCES:"), but the real
        MABS format never uses colons there -- headers sit alone under
        divider lines. This meant the structure check may have never
        actually matched the real format since v0.1 was built. Fixed:
        markers now match the header word at the start of a line, no
        colon required.
    (2) The topic-match check searched the WHOLE response text for the
        requested keyword, which the fabricated title satisfied trivially
        even though the actual task content had nothing to do with it.
        Fixed: now ALSO extracts the TASK section's own body specifically
        and requires the keyword to appear there -- a title-only mention
        no longer satisfies this check.
  Both fixes verified against the real fabricated response before
  staging: old regex matched 0/8 structural markers (should have been
  5/8), new regex correctly finds 5/8; old topic check passed (wrongly)
  because "vaultwarden" was in the title, new TASK-body check correctly
  finds no match and would flag it.
"""

import re
from pydantic import BaseModel, Field
from typing import Optional, List


class Filter:
    class Valves(BaseModel):
        enable_topic_match_flag: bool = Field(
            default=True,
            description="Flag MABS-brief responses whose TASK section body "
            "doesn't actually mention the subject/service requested, even "
            "if the title does.",
        )
        enable_structure_flag: bool = Field(
            default=True,
            description="Flag MABS-brief responses missing the structural "
            "markers a real brief should have (REFERENCES, TASK, "
            "CONSTRAINTS, etc.).",
        )
        enable_partial_process_flag: bool = Field(
            default=True,
            description="Flag responses that look like a mid-process status "
            "narration ('X loaded, task: Y', 'here's a summary of current "
            "status') rather than a finished deliverable.",
        )
        min_structural_markers_required: int = Field(
            default=3,
            description="Minimum number of MABS structural markers "
            "(REFERENCES, CONTEXT, TASK, CONSTRAINTS, EXPECTED FILES, "
            "FINAL INSTRUCTION) that must appear for a response to count "
            "as a real brief attempt, not a fragment.",
        )
        priority: int = Field(
            default=0, description="Filter execution priority. Lower runs first."
        )

    def __init__(self):
        self.valves = self.Valves()

        self._brief_request_pattern = re.compile(
            r"\b(mabs[- ]?format|mabs[- ]?brief|angkai brief|draft.*brief|"
            r"write.*brief)\b",
            re.IGNORECASE,
        )

        self._known_terms = [
            "gluetun", "sonarr", "radarr", "lidarr", "prowlarr", "qbittorrent",
            "immich", "jellyfin", "nextcloud", "gitea", "vaultwarden",
            "pihole", "pi-hole", "unbound", "caddy", "ntfy", "searxng",
            "open webui", "openwebui", "portainer", "watchtower",
            "uptime kuma", "wireguard", "graphify", "angkai", "bakaidah",
            "mokaima", "drive1", "drive2", "drive3", "drive4", "drive5",
            "dokaisho", "varan", "pi-node", "pi-user",
        ]

        # FIXED (v0.2): match the header word at the start of a line -- the
        # real MABS format never puts a colon after these, it's a bare word
        # under a divider line (e.g. "REFERENCES\n----\n..."), not
        # "REFERENCES:". The old colon-requiring regex never matched real
        # briefs at all -- confirmed via test before this fix.
        self._structural_markers = [
            re.compile(r"^\s*REFERENCES\b", re.IGNORECASE | re.MULTILINE),
            re.compile(r"^\s*CONTEXT\b", re.IGNORECASE | re.MULTILINE),
            re.compile(r"^\s*TASK\s*$", re.IGNORECASE | re.MULTILINE),
            re.compile(r"^\s*CONSTRAINTS\b", re.IGNORECASE | re.MULTILINE),
            re.compile(r"^\s*EXPECTED FILES\b", re.IGNORECASE | re.MULTILINE),
            re.compile(r"^\s*FINAL INSTRUCTION\b", re.IGNORECASE | re.MULTILINE),
            re.compile(r"^\s*HARD PROHIBITIONS\b", re.IGNORECASE | re.MULTILINE),
            re.compile(r"^\s*REQUESTED TAKEAWAY\b", re.IGNORECASE | re.MULTILINE),
        ]

        # NEW (v0.2): extract the TASK section's own body specifically, so
        # keyword matching can check SUBSTANCE, not just whether the word
        # appears anywhere (including a title that can be relabeled freely
        # without changing the actual content underneath).
        self._task_section_pattern = re.compile(
            r"TASK\s*\n[─═\-=]+\n(.*?)(?=\n[─═\-=]{4,})",
            re.IGNORECASE | re.DOTALL,
        )

        self._partial_process_pattern = re.compile(
            r"(here'?s a summary of (the )?current status|"
            r"summary of current status and pending tasks|"
            r"\bloaded\.\s*task\s*:|"
            r"explored\s+\d+\s+(tool_|file)|"
            r"based on the information from .*here'?s a (summary|overview)|"
            r"key components identified|"
            r"this (appears to be|represents) a (sophisticated|comprehensive) "
            r"home ?lab)",
            re.IGNORECASE,
        )

    def _extract_subject_keywords(self, text: str) -> List[str]:
        lowered = text.lower()
        return [term for term in self._known_terms if term in lowered]

    def _count_structural_markers(self, text: str) -> int:
        return sum(1 for pat in self._structural_markers if pat.search(text))

    def _extract_task_body(self, text: str) -> str:
        m = self._task_section_pattern.search(text)
        return m.group(1).strip() if m else ""

    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        return body

    def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
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
            return body

        response_text = messages[last_assistant_idx].get("content", "") or ""
        warnings = []

        requested_keywords = self._extract_subject_keywords(triggering_msg)
        marker_count = self._count_structural_markers(response_text)

        if self.valves.enable_partial_process_flag:
            if self._partial_process_pattern.search(response_text):
                warnings.append(
                    "warning: This response looks like a MID-PROCESS STATUS "
                    "FRAGMENT (e.g. 'here's a summary of current status', "
                    "'X loaded, task: Y') rather than a completed MABS brief. "
                    "Per OUTPUT CONSTRAINT 12, a drafting request must produce "
                    "either the complete deliverable or an explicit statement "
                    "of what failed -- a status narration is neither. Do not "
                    "treat this response as the requested brief."
                )

        if self.valves.enable_structure_flag:
            if marker_count < self.valves.min_structural_markers_required:
                warnings.append(
                    f"warning: This response shows only {marker_count} of the "
                    "expected MABS brief structural markers (REFERENCES, "
                    "CONTEXT, TASK, CONSTRAINTS, EXPECTED FILES, FINAL "
                    "INSTRUCTION, HARD PROHIBITIONS, REQUESTED TAKEAWAY) -- "
                    f"below the {self.valves.min_structural_markers_required} "
                    "expected for a real brief attempt. This does not look "
                    "like a complete MABS-formatted brief."
                )

        if self.valves.enable_topic_match_flag and requested_keywords:
            task_body = self._extract_task_body(response_text)
            response_lower = response_text.lower()
            matched_anywhere = [kw for kw in requested_keywords if kw in response_lower]
            matched_in_task = (
                [kw for kw in requested_keywords if kw in task_body.lower()]
                if task_body
                else []
            )

            if not matched_anywhere:
                warnings.append(
                    "warning: TOPIC MISMATCH -- the request appears to concern "
                    f"{', '.join(requested_keywords)}, but none of those terms "
                    "appear anywhere in this response. This may be a "
                    "different, unrelated document presented as if it "
                    "answered this request."
                )
            elif not matched_in_task:
                warnings.append(
                    "warning: TITLE/BODY MISMATCH -- the request appears to "
                    f"concern {', '.join(requested_keywords)}, and that term "
                    "appears somewhere in this response (likely the title), "
                    "but NOT in the actual TASK section body. This matches a "
                    "confirmed prior fabrication pattern: a relabeled title "
                    "over an unrelated existing task's real content. Verify "
                    "the TASK section actually concerns the requested "
                    "subject before treating this as the answer."
                )

        if warnings:
            banner = "\n\n---\n" + "\n".join(warnings)
            messages[last_assistant_idx]["content"] = response_text + banner
            body["messages"] = messages

        return body
