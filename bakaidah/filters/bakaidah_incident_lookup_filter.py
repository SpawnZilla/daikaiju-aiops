"""
title: Bakaidah Incident Number Lookup
author: the operator / Mokaima
author_url: N/A
funding_url: N/A
version: 0.1
description: INCIDENT #102 fix, code side. When the user's message asks about
  "INCIDENT #N", this filter looks N up in the roster of the journal stub
  (vault/reference/Troubleshooting_Journal.md, fetched through mcpo) BEFORE the model
  answers and appends the result to the user's message: the roster header line
  if N exists, or an explicit "not in the roster" if it does not. After the
  model answers, outlet() checks the answer against the same lookup:
    - N not in the roster: if the answer does not say so, or names any other
      incident, the answer is REPLACED with "INCIDENT #N is not in the roster."
      (fixes the #999 -> #097 substitution).
    - N in the roster: if the answer cites an incident number that was not
      asked about, a warning is appended.
  It does not shrink the model's reads, so it does NOT fix the #077 context
  truncation by itself: it gives the model the header line up front so the
  model has no reason to read INDEX.md and a category file for a header-line
  question. Full incident text still needs a fresh chat.
  Stateless: outlet() recomputes the lookup from the last user message.
  Fails open: if the roster cannot be fetched, inlet() adds an UNAVAILABLE note
  and outlet() does nothing.
DEPLOYED 2026-11-01: passed the Bakaidah release gate on Bakaidah Online and
  Bakaidah Daikaiju (N1 and N2). Replaces the prompt-rule approach (v3.11
  rule 18) that failed the gate.
"""
# CONFIG NOTE: set mcpo_base_url and the journal path in the Valves below to match your install.
# The journal is a markdown file with one header per incident in the form "INCIDENT #NNN ..." (a roster block
# between <<<ROSTER-BEGIN and ROSTER-END>>> is used when present). Served to this filter through an MCP file server behind mcpo.

import re
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

MARKER = "[ROSTER LOOKUP"
HEADER_RE = re.compile(r"^INCIDENT\s+#0*(\d+)\s*\|(.*)$")
ASK_RE = re.compile(r"incident\s*#\s*0*(\d{1,4})|incident\s+0*(\d{1,4})\b", re.IGNORECASE)
CITE_RE = re.compile(r"incident\s*#\s*0*(\d{1,4})", re.IGNORECASE)
NOT_FOUND_RE = re.compile(r"not\s+in\s+the\s+roster", re.IGNORECASE)


def parse_roster(text: str) -> Dict[str, str]:
    """Map incident number (no leading zeros) -> full header line.
    Uses the block between the ROSTER markers when present, else all lines.
    A header line wrapped onto a second line keeps only its first line."""
    if not text:
        return {}
    begin = text.find("<<<ROSTER-BEGIN")
    end = text.find("ROSTER-END>>>")
    if begin != -1:
        text = text[begin:end] if end > begin else text[begin:]
    roster: Dict[str, str] = {}
    for line in text.splitlines():
        m = HEADER_RE.match(line.strip())
        if m:
            n = m.group(1).lstrip("0") or "0"
            roster.setdefault(n, line.strip())
    return roster


def asked_numbers(user_text: str, limit: int = 3) -> List[str]:
    out: List[str] = []
    for m in ASK_RE.finditer(user_text or ""):
        n = (m.group(1) or m.group(2) or "").lstrip("0") or "0"
        if n not in out:
            out.append(n)
    return out[:limit]


def strip_injection(user_text: str) -> str:
    i = (user_text or "").find(MARKER)
    return user_text[:i].rstrip() if i != -1 else (user_text or "")


class Filter:
    class Valves(BaseModel):
        enabled: bool = Field(default=True, description="Master on/off switch.")
        mcpo_base_url: str = Field(default="http://localhost:8200")
        mcpo_read_endpoint_path: str = Field(default="/vault/read_text_file")
        mcpo_request_body_key: str = Field(default="path")
        stub_path: str = Field(
            default="/home/USER/.kaiju-spine/Troubleshooting_Journal.md",
            description="Journal stub that holds the generated roster.",
        )
        request_timeout_seconds: int = Field(default=8)
        max_user_chars: int = Field(
            default=600,
            description="Skip long user messages (pasted logs) that merely mention incidents.",
        )
        replace_not_found: bool = Field(
            default=True,
            description="Replace a wrong answer to a not-in-roster number. False = append a warning only.",
        )
        priority: int = Field(default=0)

    def __init__(self):
        self.valves = self.Valves()

    def _fetch_roster(self) -> Optional[Dict[str, str]]:
        if requests is None:
            return None
        url = self.valves.mcpo_base_url.rstrip("/") + self.valves.mcpo_read_endpoint_path
        try:
            resp = requests.post(
                url,
                json={self.valves.mcpo_request_body_key: self.valves.stub_path},
                timeout=self.valves.request_timeout_seconds,
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, str):
                text = data
            elif isinstance(data, dict):
                text = data.get("content") or data.get("text") or ""
            else:
                text = ""
            roster = parse_roster(text)
            return roster or None
        except Exception:
            return None

    @staticmethod
    def _last(messages: list, role: str) -> Optional[int]:
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == role:
                return i
        return None

    @staticmethod
    def _text(msg: dict) -> str:
        c = msg.get("content", "")
        return c if isinstance(c, str) else ""

    def build_injection(self, nums: List[str], roster: Optional[Dict[str, str]]) -> str:
        if roster is None:
            return (
                f"\n\n{MARKER} UNAVAILABLE] The journal roster could not be fetched. "
                "Say the roster lookup is unavailable and do not guess an incident."
            )
        lines = [f"\n\n{MARKER}, from the journal roster; authoritative, produced by a filter before you answer]"]
        for n in nums:
            if n in roster:
                lines.append(f"INCIDENT #{n} IS in the roster. Header line: {roster[n]}")
            else:
                lines.append(
                    f"INCIDENT #{n} is NOT in the roster. Your answer must be exactly: "
                    f"\"INCIDENT #{n} is not in the roster.\" Name no other incident."
                )
        lines.append(
            "For a question about an incident that IS in the roster, answer from its header line. "
            "Do not read INDEX.md or a category file in this chat; if the user wants the full text, "
            "tell them it needs a fresh chat. Never answer with a different incident number."
        )
        return "\n".join(lines)

    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        if not self.valves.enabled:
            return body
        messages = body.get("messages", [])
        i = self._last(messages, "user")
        if i is None:
            return body
        text = self._text(messages[i])
        if MARKER in text or len(text) > self.valves.max_user_chars:
            return body
        nums = asked_numbers(text)
        if not nums:
            return body
        roster = self._fetch_roster()
        messages[i]["content"] = text + self.build_injection(nums, roster)
        body["messages"] = messages
        return body

    def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        if not self.valves.enabled:
            return body
        messages = body.get("messages", [])
        ai = self._last(messages, "assistant")
        ui = self._last(messages, "user")
        if ai is None or ui is None or ui > ai:
            return body
        user_text = self._text(messages[ui])
        if MARKER not in user_text or "UNAVAILABLE]" in user_text:
            return body  # inlet did not run or roster was unavailable: fail open
        nums = asked_numbers(strip_injection(user_text))
        if not nums:
            return body
        roster = self._fetch_roster()
        if roster is None:
            return body
        answer = self._text(messages[ai])
        cited = {(m.group(1).lstrip("0") or "0") for m in CITE_RE.finditer(answer)}
        allowed = set(nums)
        for n in nums:
            allowed |= {(m.group(1).lstrip("0") or "0") for m in CITE_RE.finditer(roster.get(n, ""))}
        missing = [n for n in nums if n not in roster]
        foreign = sorted(cited - allowed, key=int)

        if missing and (foreign or not NOT_FOUND_RE.search(answer)):
            sentence = " ".join(f"INCIDENT #{n} is not in the roster." for n in missing)
            if self.valves.replace_not_found:
                messages[ai]["content"] = (
                    sentence
                    + "\n\n---\nwarning: the model's own answer was replaced because it did not say "
                    "this number is missing from the roster or it named a different incident."
                )
            else:
                messages[ai]["content"] = answer + (
                    "\n\n---\nwarning: " + sentence + " The answer above is not reliable for that number."
                )
            body["messages"] = messages
        elif foreign:
            messages[ai]["content"] = answer + (
                "\n\n---\nwarning: this answer cites INCIDENT #" + ", #".join(foreign) +
                " but you asked about #" + ", #".join(nums) +
                ". Only the roster header line for the asked number is verified."
            )
            body["messages"] = messages
        return body
