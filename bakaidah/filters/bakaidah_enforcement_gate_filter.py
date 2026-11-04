"""
title: Bakaidah Enforcement Gate
author: the operator
author_url: N/A
funding_url: N/A
version: 0.1
description: Deterministic post-response gate for Bakaidah. Flags unrequested session summaries, risky install-path suggestions, and unverified software status claims with a visible warning banner. Cannot force a retry -- only warns after generation completes.
"""

import re
from pydantic import BaseModel, Field
from typing import Optional


class Filter:
    class Valves(BaseModel):
        enable_session_summary_gate: bool = Field(
            default=True,
            description="Block SESSION SUMMARY-shaped responses unless 'bakaidahsummary' was in the triggering message.",
        )
        enable_install_path_flag: bool = Field(
            default=True,
            description="Flag install commands targeting home/root/boot/EFI/swap with a warning banner.",
        )
        enable_software_status_flag: bool = Field(
            default=True,
            description="Flag software 'active/maintained/latest version' claims that show no evidence of a search citation.",
        )
        priority: int = Field(
            default=0, description="Filter execution priority. Lower runs first."
        )

    def __init__(self):
        self.valves = self.Valves()
        self._summary_markers = re.compile(
            r"(session summary|achievements?:|technical config|files? created|next steps?:)",
            re.IGNORECASE,
        )
        self._install_pattern = re.compile(
            r"(cd\s+~|cd\s+\$HOME|mkdir\s+~|mkdir\s+/home|sudo\s+.*\binstall\b.*\s/(boot|efi|swap)\b|>\s*/etc/fstab)",
            re.IGNORECASE,
        )
        self._status_claim_pattern = re.compile(
            r"\b(actively maintained|actively developed|current(ly)? (the )?(best|recommended)|latest (version|release)|still (maintained|supported|active))\b",
            re.IGNORECASE,
        )
        self._citation_evidence_pattern = re.compile(
            r"(\[\d+\]|\bsource[s]?\b\s*:|\bhttps?://)", re.IGNORECASE
        )

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

        response_text = messages[last_assistant_idx].get("content", "") or ""
        warnings = []

        if self.valves.enable_session_summary_gate:
            triggering_msg = ""
            for i in range(last_assistant_idx - 1, -1, -1):
                if messages[i].get("role") == "user":
                    triggering_msg = messages[i].get("content", "") or ""
                    break
            summary_shaped = len(self._summary_markers.findall(response_text)) >= 2
            keyword_present = "bakaidahsummary" in triggering_msg.lower()
            if summary_shaped and not keyword_present:
                warnings.append(
                    "warning: This response looks like a SESSION SUMMARY, but "
                    "'bakaidahsummary' wasn't in your message. Flagging per "
                    "v2.3 CONSTRAINTS -- summaries should only be produced "
                    "when explicitly requested."
                )

        if self.valves.enable_install_path_flag:
            if self._install_pattern.search(response_text):
                warnings.append(
                    "warning: INSTALL PATH RULE -- this response suggests installing "
                    "to home/root/boot/EFI/swap. Nothing installs there "
                    "without your explicit approval -- verify before running."
                )

        if self.valves.enable_software_status_flag:
            has_status_claim = self._status_claim_pattern.search(response_text)
            has_citation_evidence = self._citation_evidence_pattern.search(
                response_text
            )
            if has_status_claim and not has_citation_evidence:
                warnings.append(
                    "warning: This response makes a software status/version claim "
                    "with no visible citation. Per v2.3, this should be "
                    "search-verified -- treat the claim as unconfirmed until "
                    "you check it yourself."
                )

        if warnings:
            banner = "\n\n---\n" + "\n".join(warnings)
            messages[last_assistant_idx]["content"] = response_text + banner
            body["messages"] = messages

        return body
