"""
title: Bakaidah Incident Fabrication Gate
author: the operator / Mokaima
author_url: N/A
funding_url: N/A
version: 0.2
description: Deterministic post-response gate. Cannot force a retry --
  only warns after generation completes, same limitation as Bakaidah
  Enforcement Gate. Added after a Vaultwarden MABS-brief request drew
  a response containing TWO complete incident records ("Vaultwarden
  Restarting Issue (2026-07-22)", "Health Check Automation
  (2026-07-22)") -- with root causes and fixes stated -- that do not
  exist anywhere in the real Troubleshooting_Journal.md. This is a
  distinct failure mode from prior task-substitution failures: it's
  fabrication of specific, plausible-looking facts WHILE appearing to
  stay on-task, not drifting to a different task. This filter fetches
  the real journal via mcpo (same confirmed endpoint as the Diagnostic
  History filter) and checks two things: (1) any explicit "INCIDENT
  #NNN" citation actually exists at that number in the real journal,
  and (2) any incident-shaped claim ("<Title> (YYYY-MM-Kaidosho):") whose
  claimed subject actually overlaps with what the real journal records
  for THAT SPECIFIC DATE -- not merely whether the date exists anywhere
  in the journal.

VERIFIED 2026-07-25: mcpo endpoint (http://localhost:8200/vault/read_text_file,
  body key "path", raw JSON string response) confirmed live -- same
  endpoint used successfully by the Diagnostic History filter.

IMPORTANT DESIGN NOTE (v0.1 -> v0.2): the first version only checked
  whether a claimed date existed ANYWHERE in the real journal. Tested
  against the actual fabricated response and it caught NOTHING -- every
  one of Bakaidah's 4 fabricated/paraphrased claims happened to reuse a
  genuine date that belonged to a real but UNRELATED incident (e.g. a
  fake "Vaultwarden" incident dated 2026-07-22, which IS a real incident
  date, just for an unrelated filesystem-MCP incident). v0.2 fixes this
  by checking whether the claimed title's own keywords overlap with what
  the real incident on that date actually concerns (service + category
  fields), not just date existence. Retested: correctly flagged the 2
  genuinely fabricated claims and correctly left 2 claims alone that
  turned out to be reasonably accurate (if oddly titled) paraphrases of
  real incidents (#013, #017).
"""
# CONFIG NOTE: set mcpo_base_url and the journal path in the Valves below to match your install.
# The journal is a markdown file with one header per incident in the form "INCIDENT #NNN ..." (a roster block
# between <<<ROSTER-BEGIN and ROSTER-END>>> is used when present). Served to this filter through an MCP file server behind mcpo.

import re
from pydantic import BaseModel, Field
from typing import Optional, List, Set

try:
    import requests
except ImportError:
    requests = None


class Filter:
    class Valves(BaseModel):
        enabled: bool = Field(
            default=True, description="Master on/off switch for this filter."
        )
        mcpo_base_url: str = Field(
            default="http://localhost:8200",
            description="Base URL for the mcpo server on dokaisho. "
            "Confirmed correct 2026-07-25 (same as Diagnostic History filter).",
        )
        mcpo_read_endpoint_path: str = Field(
            default="/vault/read_text_file",
            description="Endpoint path for read_text_file via mcpo. "
            "Confirmed correct 2026-07-25.",
        )
        mcpo_request_body_key: str = Field(
            default="path",
            description="JSON body key for the file path argument. "
            "Confirmed correct 2026-07-25.",
        )
        journal_path: str = Field(
            default="/home/USER/.kaiju-spine/Troubleshooting_Journal.md",
            description="Absolute path to Troubleshooting_Journal.md as seen "
            "by the mcpo/vault MCP server. Confirmed correct 2026-07-25.",
        )
        request_timeout_seconds: int = Field(
            default=8,
            description="HTTP request timeout for the mcpo fetch.",
        )
        priority: int = Field(
            default=0, description="Filter execution priority. Lower runs first."
        )

    def __init__(self):
        self.valves = self.Valves()

        # Explicit incident citation: "INCIDENT #016" or "incident #16" etc.
        self._incident_citation_pattern = re.compile(
            r"INCIDENT\s+#0*(\d+)", re.IGNORECASE
        )

        # Real incident headers in the journal, to build the ground-truth set.
        # Captures all 4 pipe-delimited fields: number, date, service, category.
        self._incident_header_pattern = re.compile(
            r"^INCIDENT\s+#(\d+)\s*\|\s*([^\|]+)\|\s*([^\|]+)\|\s*(.+)$",
            re.MULTILINE,
        )

        # Incident-shaped claims in Bakaidah's own prose, even without an
        # explicit "INCIDENT #" citation -- matches the exact shape of the
        # confirmed fabrication: "<Title> Issue (YYYY-MM-Kaidosho):" or
        # "<Title> (YYYY-MM-Kaidosho):" as a bulleted/numbered claim.
        self._incident_shaped_claim_pattern = re.compile(
            r"([A-Z][A-Za-z0-9 /_-]{3,60}?)\s*\((\d{4}-\d{2}-\d{2})\)\s*:",
        )

    def _fetch_journal(self) -> Optional[str]:
        if requests is None:
            return None
        url = self.valves.mcpo_base_url.rstrip("/") + self.valves.mcpo_read_endpoint_path
        try:
            resp = requests.post(
                url,
                json={self.valves.mcpo_request_body_key: self.valves.journal_path},
                timeout=self.valves.request_timeout_seconds,
            )
            resp.raise_for_status()
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

    def _real_incident_numbers(self, journal_text: str) -> Set[str]:
        return {m.group(1).lstrip("0") or "0" for m in self._incident_header_pattern.finditer(journal_text)}

    def _real_incidents_by_date(self, journal_text: str) -> dict:
        """Maps each real incident date -> list of (service_field, category_field)
        text, so a claimed title can be checked against what ACTUALLY happened
        on that date, not just whether the date exists anywhere in the journal.
        This matters because the confirmed fabrication reused genuine dates
        from unrelated real incidents (e.g. claiming a fake "Vaultwarden"
        incident on 2026-07-22, a date that IS real but belongs to an
        unrelated filesystem-MCP incident)."""
        by_date: dict = {}
        for m in self._incident_header_pattern.finditer(journal_text):
            date_field = m.group(2).strip()
            service_field = m.group(3).strip()
            category_field = m.group(4).strip()
            date_match = re.search(r"\d{4}-\d{2}-\d{2}", date_field)
            if date_match:
                d = date_match.group(0)
                by_date.setdefault(d, []).append((service_field, category_field))
        return by_date

    @staticmethod
    def _words(text: str) -> Set[str]:
        return set(re.findall(r"[a-z0-9]{4,}", text.lower()))

    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        return body

    def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
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

        response_text = messages[last_assistant_idx].get("content", "") or ""

        cited_numbers = set(self._incident_citation_pattern.findall(response_text))
        claimed_dated_items = self._incident_shaped_claim_pattern.findall(response_text)

        if not cited_numbers and not claimed_dated_items:
            return body

        journal_text = self._fetch_journal()
        warnings = []

        if journal_text is None:
            if cited_numbers or claimed_dated_items:
                warnings.append(
                    "warning: This response cites specific incident(s) or "
                    "incident-shaped claims, but Troubleshooting_Journal.md "
                    "could not be fetched to verify them (mcpo request "
                    "failed). Treat any INCIDENT # citations and dated claims "
                    "in this response as UNVERIFIED until checked manually."
                )
        else:
            real_numbers = self._real_incident_numbers(journal_text)
            real_by_date = self._real_incidents_by_date(journal_text)

            fake_citations = [n for n in cited_numbers if n.lstrip("0") not in real_numbers and n not in real_numbers]
            if fake_citations:
                warnings.append(
                    f"warning: FABRICATED INCIDENT CITATION -- this response "
                    f"cites INCIDENT #{', #'.join(fake_citations)}, but no "
                    f"such incident number exists in the real "
                    "Troubleshooting_Journal.md. Do not trust this claim -- "
                    "verify against the actual journal before acting on it."
                )

            # Cross-check title against what ACTUALLY happened on that date,
            # not just whether the date exists anywhere -- a claim can reuse
            # a genuine date from a totally unrelated real incident, which a
            # date-existence-only check would miss entirely (confirmed via
            # live test against the actual fabricated Vaultwarden response).
            mismatched_claims = []
            no_date_match_claims = []
            for title, date in claimed_dated_items:
                title_words = self._words(title)
                if date not in real_by_date:
                    no_date_match_claims.append((title.strip(), date))
                    continue
                real_entries = real_by_date[date]
                overlap_found = any(
                    title_words & self._words(f"{svc} {cat}")
                    for svc, cat in real_entries
                )
                if not overlap_found:
                    real_summary = "; ".join(f"{svc} ({cat})" for svc, cat in real_entries)
                    mismatched_claims.append((title.strip(), date, real_summary))

            if mismatched_claims:
                detail = "; ".join(
                    f'"{t}" ({d}) -- real incident(s) on that date: {r}'
                    for t, d, r in mismatched_claims[:5]
                )
                warnings.append(
                    "warning: LIKELY FABRICATED INCIDENT -- this response "
                    f"states {detail}, but the claimed subject shares no "
                    "overlap with what the real journal actually records for "
                    "that date. This matches the shape of a confirmed prior "
                    "fabrication (inventing a plausible incident and "
                    "attaching it to a genuine date from an unrelated real "
                    "incident). Do not trust this content -- verify against "
                    "the real journal yourself."
                )

            if no_date_match_claims:
                claim_list = "; ".join(f'"{t}" ({d})' for t, d in no_date_match_claims[:5])
                warnings.append(
                    "warning: UNVERIFIED INCIDENT-SHAPED CLAIM -- this "
                    f"response states {claim_list} as if describing a "
                    "documented incident, but no real incident in "
                    "Troubleshooting_Journal.md is dated that way at all. "
                    "Do not trust this content without checking the real "
                    "journal yourself."
                )

        if warnings:
            banner = "\n\n---\n" + "\n".join(warnings)
            messages[last_assistant_idx]["content"] = response_text + banner
            body["messages"] = messages

        return body
