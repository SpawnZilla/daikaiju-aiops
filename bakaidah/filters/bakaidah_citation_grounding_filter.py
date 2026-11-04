"""
title: Bakaidah Citation Grounding Filter
author: the operator / Mokaima
author_url: N/A
funding_url: N/A
version: 0.5
description:  Phase 2 item 2, v0.5 (staged 2026-11-02, replaces v0.4; v0.4 added the tool-output search below, v0.5 fixes quote pairing: two short quoted words in one sentence were paired into a false quote and reported NOT found). v0.3 checked each
  quoted span in the answer only against the document strings in the assistant message's sources.
  For web answers Open WebUI keeps there the search_web snippets (cut off with "..." at a varying
  point) and only the first ~500 characters of a fetched page, so a quote taken from the page
  body was reported as NOT found about half the time even when it is on the page (2026-11-02 P3
  runs, with and without the relay tool). v0.4 also searches the full text of the fetch_url and
  search_web tool outputs stored in the message's output items. Tool outputs of other tools (file
  reads, graph queries, the relay) are NOT added, so quoted text in a drafted brief is still not
  checked against them. Result display is unchanged: Open WebUI status and notification events,
  plus a banner appended to the stored answer. Stateless, no network calls, fails open: no quotes
  or no source text means no change. The inlet() steering line is unchanged.
required_open_webui_version: 0.5.0
"""

import re
import logging
from pydantic import BaseModel, Field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# A quote must open after a non-word char and close before one, so the closing quote of one short
# quoted word and the opening quote of the next ("Upgrade" ... "websocket") never pair up (v0.5).
_QUOTE_RE = re.compile(r"(?<!\w)\"([^\"\n]{10,400})\"(?!\w)")
_SMART = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'",
                        "–": "-", "—": "-", " ": " ", "`": "'"})
_ELLIPSIS_RE = re.compile(r"\.{3,}|…")


def _norm(s: str) -> str:
    s = s.translate(_SMART)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s.strip(" .,;:!?-'\"")


def extract_quotes(text: str, min_chars: int, max_chars: int) -> List[str]:
    out: List[str] = []
    for m in _QUOTE_RE.finditer(text.translate(_SMART)):
        q = m.group(1).strip()
        if min_chars <= len(q) <= max_chars and q not in out:
            out.append(q)
    return out


def source_texts(message: dict) -> List[str]:
    """Document strings Open WebUI kept in the message's sources (search snippets, page heads)."""
    docs: List[str] = []
    sources = message.get("sources")
    for s in sources if isinstance(sources, list) else []:
        if not isinstance(s, dict):
            continue
        d = s.get("document")
        for x in d if isinstance(d, list) else []:
            if isinstance(x, str) and x.strip():
                docs.append(x)
    return docs


def _out_text(o) -> str:
    if isinstance(o, str):
        return o
    parts: List[str] = []
    for x in o if isinstance(o, list) else []:
        if isinstance(x, dict):
            t = x.get("text")
            if isinstance(t, str):
                parts.append(t)
        elif isinstance(x, str):
            parts.append(x)
    return "\n".join(parts)


def tool_output_texts(message: dict, names: List[str]) -> List[str]:
    """Full text of the outputs of tool calls whose name contains one of names (e.g. fetch_url)."""
    out = message.get("output")
    if not isinstance(out, list):
        return []
    wanted = [n.strip().lower() for n in names if isinstance(n, str) and n.strip()]
    by_call = {}
    for item in out:
        if isinstance(item, dict) and item.get("type") == "function_call":
            by_call[item.get("call_id")] = str(item.get("name", "")).lower()
    texts: List[str] = []
    for item in out:
        if isinstance(item, dict) and item.get("type") == "function_call_output":
            nm = by_call.get(item.get("call_id"), "")
            if nm and any(w in nm for w in wanted):
                t = _out_text(item.get("output"))
                if t.strip():
                    texts.append(t)
    return texts


def quote_is_grounded(quote: str, haystack: str, min_segment: int) -> bool:
    """True if the quote is in the sources. A quote containing '...' is split there and every
    segment of at least min_segment characters must appear (order not required)."""
    segs = [_norm(p) for p in _ELLIPSIS_RE.split(quote)]
    segs = [p for p in segs if len(p) >= min_segment]
    if not segs:
        return True  # nothing checkable, never call it fabricated
    return all(p in haystack for p in segs)


class Filter:
    class Valves(BaseModel):
        enabled: bool = Field(default=True, description="Master on/off switch.")
        inject_quote_instruction: bool = Field(
            default=True,
            description="inlet() asks Bakaidah to quote the exact supporting line when citing a web source.",
        )
        include_tool_output: bool = Field(
            default=True,
            description="Also search the full text of the web tool outputs (see web_tool_names) stored in the message.",
        )
        web_tool_names: str = Field(
            default="fetch_url,search_web",
            description="Comma-separated tool-name fragments whose output counts as a source.",
        )
        min_quote_chars: int = Field(default=15, description="Shortest quoted span checked.")
        max_quote_chars: int = Field(default=300, description="Longest quoted span checked.")
        min_segment_chars: int = Field(default=12, description="Shortest piece of a quote (split at ...) that must match.")
        max_quotes_checked: int = Field(default=6, description="Most quotes checked per answer.")
        append_banner: bool = Field(default=True, description="Also append the warning banner to the stored answer text.")
        emit_events: bool = Field(default=True, description="Send status/notification events to the chat window.")
        debug: bool = Field(default=True, description="One log line per call.")
        priority: int = Field(default=0, description="Filter execution priority. Lower runs first.")

    def __init__(self):
        self.valves = self.Valves()
        self._tool_docs = 0

    # inlet: unchanged from v0.2 (soft steering line)
    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        if not self.valves.enabled or not self.valves.inject_quote_instruction:
            return body
        instruction = (
            "When citing a web source in your answer, include the exact "
            "literal sentence or line from that source that supports your "
            "claim, not a paraphrase."
        )
        messages = body.get("messages", [])
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

    @staticmethod
    def _real_text_part(message: dict) -> Optional[dict]:
        for item in message.get("output", []) or []:
            if isinstance(item, dict) and item.get("type") == "message":
                for part in item.get("content", []) or []:
                    if isinstance(part, dict) and part.get("type") == "output_text" and part.get("text"):
                        return part
        return None

    @classmethod
    def _response_text(cls, message: dict) -> str:
        part = cls._real_text_part(message)
        if part:
            return part["text"]
        c = message.get("content", "")
        return c if isinstance(c, str) else ""

    @classmethod
    def _write_text(cls, message: dict, new_text: str) -> None:
        part = cls._real_text_part(message)
        if part:
            part["text"] = new_text
        if isinstance(message.get("content", ""), str):
            message["content"] = new_text

    def check(self, body: dict) -> Optional[Tuple[int, List[str], int]]:
        """Returns (quotes_checked, unverified_quotes, source_docs) or None if there is nothing to check."""
        self._tool_docs = 0
        messages = body.get("messages", [])
        idx = next((i for i in range(len(messages) - 1, -1, -1)
                    if isinstance(messages[i], dict) and messages[i].get("role") == "assistant"), None)
        if idx is None:
            return None
        msg = messages[idx]
        text = self._response_text(msg)
        docs = source_texts(msg)
        if self.valves.include_tool_output:
            extra = tool_output_texts(msg, self.valves.web_tool_names.split(","))
            self._tool_docs = len(extra)
            docs = docs + extra
        if not text.strip() or not docs:
            return None
        user_text = ""
        for m in reversed(messages[:idx]):
            if isinstance(m, dict) and m.get("role") == "user" and isinstance(m.get("content"), str):
                user_text = _norm(m["content"])
                break
        quotes = extract_quotes(text, self.valves.min_quote_chars, self.valves.max_quote_chars)
        quotes = [q for q in quotes if _norm(q) not in user_text][: self.valves.max_quotes_checked]
        if not quotes:
            return None
        hay = _norm(" ".join(docs))
        bad = [q for q in quotes if not quote_is_grounded(q, hay, self.valves.min_segment_chars)]
        return len(quotes), bad, len(docs)

    async def outlet(self, body: dict, __user__: Optional[dict] = None, __event_emitter__=None) -> dict:
        if not self.valves.enabled:
            return body
        try:
            res = self.check(body)
            if self.valves.debug:
                logger.warning("[ citation grounding v0.5] outlet() invoked checked=%s tool_docs=%d",
                               None if res is None else (res[0], len(res[1]), res[2]), self._tool_docs)
            if res is None:
                return body
            n, bad, ndocs = res
            if self.valves.emit_events and __event_emitter__:
                if bad:
                    desc = "Citation check: %d of %d quoted lines NOT found in the fetched sources" % (len(bad), n)
                else:
                    desc = "Citation check: %d of %d quoted lines found in the fetched sources" % (n, n)
                await __event_emitter__({"type": "status", "data": {"description": desc, "done": True}})
                if bad:
                    await __event_emitter__({"type": "notification", "data": {"type": "warning", "content": desc + ". Check the answer's quotes before trusting them."}})
            if bad and self.valves.append_banner:
                messages = body.get("messages", [])
                idx = next(i for i in range(len(messages) - 1, -1, -1) if messages[i].get("role") == "assistant")
                text = self._response_text(messages[idx])
                lines = ["warning: possibly fabricated citation -- these quoted lines were checked against the "
                         "pages Bakaidah actually retrieved and do not appear there:"]
                lines += ['- "%s"' % q.strip() for q in bad]
                lines.append("Do not trust these quotes without checking the real source yourself.")
                self._write_text(messages[idx], text + "\n\n---\n" + "\n".join(lines))
                body["messages"] = messages
        except Exception as exc:  # fail open
            logger.warning("[ citation grounding v0.5] error, answer untouched: %r", exc)
        return body
