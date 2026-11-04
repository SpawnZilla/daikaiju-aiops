"""
title: Bakaidah Diagnostic History Enforcement
author: the operator / Mokaima
author_url: N/A
funding_url: N/A
version: 0.3
description: Deterministic inlet gate. (v0.3, 2026-10-16: the journal is now split into
  vault/reference/troubleshooting_journal/ category files; this filter reads the folder
  INDEX.md, fetches every category file in parallel, and falls back to the
  stub path if the INDEX cannot be read.) Prompt-only instruction (v2.7-v2.9)
  failed 3 consecutive live tests to get Bakaidah to actually read
  Troubleshooting_Journal.md before answering a diagnostic question --
  it kept answering from the knowledge graph alone. This Filter removes
  the choice: on inlet (before the model generates), it detects a
  diagnostic-shaped question, fetches Troubleshooting_Journal.md via
  mcpo, extracts the matching incident block(s) by keyword overlap, and
  injects them directly into the message list as a system message.
  Bakaidah then has the history in context regardless of whether it
  would have chosen to call the tool. Degrades gracefully (adds a note,
  never blocks) if the fetch fails or no match is found.

VERIFIED 2026-07-25: mcpo endpoint confirmed live via curl against the
  real dokaisho instance -- mcpo nests each MCP server's tools under
  /<server-name>/, so the vault server (secure-filesystem-server v0.2.0)
  exposes read_text_file at /vault/read_text_file, not at the mcpo root.
  Response body confirmed to be a raw JSON string (not a nested dict),
  which the isinstance(data, str) branch in _fetch_journal already
  handles. Regex parsing of real INCIDENT #NNN headers (including one
  with a "/" inside the SERVICE/COMPONENT field) verified correct via
  local test. Detection + keyword extraction verified against the
  actual test query used in the live Bakaidah test ("The gluetun
  container keeps dropping network connectivity...") -- correctly
  flagged as diagnostic and correctly extracted "gluetun" as a keyword,
  which would have surfaced INCIDENT #009 (gluetun namespace-dependency
  incident) in the real journal.
"""
# CONFIG NOTE: set mcpo_base_url and the journal path in the Valves below to match your install.
# The journal is a markdown file with one header per incident in the form "INCIDENT #NNN ..." (a roster block
# between <<<ROSTER-BEGIN and ROSTER-END>>> is used when present). Served to this filter through an MCP file server behind mcpo.

import re
import json
from concurrent.futures import ThreadPoolExecutor
from pydantic import BaseModel, Field
from typing import Optional, List, Tuple

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
            description="Base URL for the mcpo server on dokaisho exposing "
            "the vault MCP tools as HTTP endpoints. Confirmed correct "
            "2026-07-25.",
        )
        mcpo_read_endpoint_path: str = Field(
            default="/vault/read_text_file",
            description="Endpoint path for the read_text_file tool via mcpo. "
            "CONFIRMED 2026-07-25 via curl against the live dokaisho mcpo "
            "instance: mcpo nests tools under /<server-name>/ -- the vault "
            "MCP server (secure-filesystem-server v0.2.0) exposes its tools "
            "at /vault/*, not at the mcpo root. Root-level /read_text_file "
            "returned 404; /vault/read_text_file returned real file content.",
        )
        mcpo_request_body_key: str = Field(
            default="path",
            description="JSON body key expected by the read_text_file "
            "endpoint for the file path argument. Confirmed correct "
            "2026-07-25 via live curl test.",
        )
        journal_path: str = Field(
            default="/home/USER/.kaiju-spine/Troubleshooting_Journal.md",
            description="Absolute path to Troubleshooting_Journal.md as seen "
            "by the mcpo/vault MCP server. Confirmed correct 2026-07-25 -- "
            "this exact path returned real journal content via curl. Since the "
            "2026-10-16 split this path is a stub holding only incident header "
            "lines, so it is used only as a fallback.",
        )
        journal_folder: str = Field(
            default="/home/USER/.kaiju-spine/troubleshooting_journal",
            description="Absolute path to the split journal folder as seen by "
            "the mcpo/vault MCP server. INDEX.md in it lists the category files "
            "(troubleshooting_journal_*.md) that hold the full incident text.",
        )
        fetch_workers: int = Field(
            default=8,
            description="Parallel fetches of journal category files. Each fetch "
            "still uses request_timeout_seconds.",
        )
        request_timeout_seconds: int = Field(
            default=8,
            description="HTTP request timeout for the mcpo fetch. Keep short "
            "-- this runs on every diagnostic-shaped message before "
            "generation, so a hang here blocks the whole response.",
        )
        max_incidents_injected: int = Field(
            default=2,
            description="Maximum number of matching incident blocks to "
            "inject. Keeps context cost bounded -- the full journal is "
            "~56KB and should never be injected wholesale.",
        )
        debug_mode: bool = Field(
            default=False,
            description="If true, prepend a visible marker showing what was "
            "detected/matched/injected, so you can confirm this filter is "
            "actually firing during initial testing. Turn off once "
            "confirmed working -- it's noisy in normal use.",
        )

    def __init__(self):
        self.valves = self.Valves()

        # Symptom/diagnostic language -- broad on purpose, tightened by
        # requiring this OR a known service name, not pure keyword count,
        # to avoid over-triggering on every mention of a service name.
        self._diagnostic_pattern = re.compile(
            r"\b(keeps?\s+\w+ing|drop(?:ping|s|ped)?|fail(?:s|ing|ed)?|"
            r"broken|not\s+working|won'?t\s+\w+|can'?t\s+\w+|error|crash(?:ing|ed)?|"
            r"unhealthy|down|unresponsive|stuck|hangs?|timeout|timing\s+out|"
            r"what\s+should\s+i\s+check|why\s+is|how\s+do\s+i\s+fix|"
            r"troubleshoot|diagnos)",
            re.IGNORECASE,
        )

        # Known Kaidosho services/components -- used both to confirm diagnostic
        # intent and to extract keywords for incident matching. Extend this
        # list as new services are added to Kaidosho; it's not exhaustive by design
        # (the overlap-scoring below also works on generic terms from the
        # message itself, this list just biases toward known nouns).
        self._known_terms = [
            "gluetun",
            "sonarr",
            "radarr",
            "lidarr",
            "prowlarr",
            "qbittorrent",
            "immich",
            "jellyfin",
            "nextcloud",
            "gitea",
            "vaultwarden",
            "pihole",
            "pi-hole",
            "unbound",
            "caddy",
            "ntfy",
            "searxng",
            "open webui",
            "openwebui",
            "portainer",
            "watchtower",
            "uptime kuma",
            "wireguard",
            "mcp",
            "filesystem",
            "graphify",
            "angkai",
            "bakaidah",
            "mokaima",
            "hola1",
            "hola2",
            "hola3",
            "hola4",
            "hola5",
            "dokaisho",
            "varan",
            "pi-node",
            "pi-user",
        ]

        self._incident_header_pattern = re.compile(
            r"^INCIDENT\s+#(\d+)\s*\|\s*([^\|]+)\|\s*([^\|]+)\|\s*(.+)$",
            re.MULTILINE,
        )

    def _looks_diagnostic(self, text: str) -> bool:
        return bool(self._diagnostic_pattern.search(text))

    def _extract_keywords(self, text: str) -> List[str]:
        lowered = text.lower()
        found = [term for term in self._known_terms if term in lowered]
        # Also pull generic alphanumeric tokens 4+ chars as loose fallback
        # terms, in case the question names something not in the known list.
        generic = re.findall(r"\b[a-z][a-z0-9\-]{3,}\b", lowered)
        # De-dupe while preserving order, known terms first.
        seen = set(found)
        ordered = list(found)
        for g in generic:
            if g not in seen:
                ordered.append(g)
                seen.add(g)
        return ordered

    def _split_incidents(self, journal_text: str) -> List[Tuple[str, str]]:
        """Returns list of (header_line, full_block_text) tuples."""
        matches = list(self._incident_header_pattern.finditer(journal_text))
        blocks = []
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(journal_text)
            block = journal_text[start:end].strip()
            blocks.append((m.group(0), block))
        return blocks

    def _score_block(self, block_text: str, keywords: List[str]) -> int:
        lowered = block_text.lower()
        score = 0
        for kw in keywords:
            if kw in lowered:
                # Weight matches in the header line (service/category) higher
                # than matches buried in prose, by checking the first line.
                first_line = lowered.split("\n", 1)[0]
                score += 3 if kw in first_line else 1
        return score

    def _fetch_journal(self) -> Optional[str]:
        """v0.3: read the split journal. INDEX.md lists the category files;
        fetch them in parallel, strip each file's 2-line header and BODY
        marker, join in INDEX order. Falls back to the stub path (header
        lines only) if the INDEX or every category file fails."""
        folder = self.valves.journal_folder.rstrip("/")
        index_text = self._read_remote(folder + "/INDEX.md")
        names = re.findall(
            r"^\|\s*(troubleshooting_journal_[a-z0-9_]+\.md)\s*\|",
            index_text or "",
            re.MULTILINE,
        )
        if names:
            workers = max(1, min(self.valves.fetch_workers, len(names)))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                texts = list(
                    pool.map(lambda n: self._read_remote(folder + "/" + n), names)
                )
            parts = []
            for t in texts:
                if not t:
                    continue
                k = t.find("#---BODY---\n")
                parts.append(t[k + len("#---BODY---\n"):] if k >= 0 else t)
            if parts:
                return "\n".join(parts)
        return self._read_remote(self.valves.journal_path)

    def _read_remote(self, path: str) -> Optional[str]:
        if requests is None:
            return None
        url = self.valves.mcpo_base_url.rstrip("/") + self.valves.mcpo_read_endpoint_path
        try:
            resp = requests.post(
                url,
                json={self.valves.mcpo_request_body_key: path},
                timeout=self.valves.request_timeout_seconds,
            )
            resp.raise_for_status()
            data = resp.json()
            # mcpo/MCP tool results commonly nest text under a few possible
            # shapes -- try the likely ones rather than assuming one.
            # CONFIRMED 2026-07-25: the real response is a raw JSON string,
            # so the isinstance(data, str) branch below is the one that
            # actually fires in production.
            if isinstance(data, str):
                return data
            if isinstance(data, dict):
                for key_path in (
                    ("content",),
                    ("text",),
                    ("result", "content"),
                    ("content", 0, "text"),
                ):
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

    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        if not self.valves.enabled:
            return body

        messages = body.get("messages", [])
        if not messages:
            return body

        last_user_idx = None
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                last_user_idx = i
                break
        if last_user_idx is None:
            return body

        user_text = messages[last_user_idx].get("content", "") or ""
        if not self._looks_diagnostic(user_text):
            return body

        keywords = self._extract_keywords(user_text)
        journal_text = self._fetch_journal()

        injection_lines = [
            "[DETERMINISTIC DIAGNOSTIC HISTORY CHECK -- injected automatically, "
            "not something you need to fetch yourself]",
        ]

        if journal_text is None:
            injection_lines.append(
                "Troubleshooting_Journal.md could not be fetched automatically "
                "(mcpo request failed -- check Filter valves and mcpo status). "
                "You MUST still attempt to read vault/reference/Troubleshooting_Journal.md "
                "yourself via your normal vault tool before answering, per the "
                "DIAGNOSTIC HISTORY CHECK rule in your system prompt."
            )
        else:
            blocks = self._split_incidents(journal_text)
            scored = [
                (self._score_block(block, keywords), header, block)
                for header, block in blocks
            ]
            scored = [s for s in scored if s[0] > 0]
            scored.sort(key=lambda x: x[0], reverse=True)
            top = scored[: self.valves.max_incidents_injected]

            if not top:
                injection_lines.append(
                    "No matching incident found in Troubleshooting_Journal.md "
                    f"for detected keywords: {', '.join(keywords[:8]) or '(none detected)'}. "
                    "Proceed with normal first-principles diagnosis, but state "
                    "explicitly that the journal was checked and had no match "
                    "-- do not silently skip mentioning this."
                )
            else:
                injection_lines.append(
                    f"Matching incident(s) found in Troubleshooting_Journal.md "
                    f"for detected keywords: {', '.join(keywords[:8])}. "
                    "Lead your answer with this history -- state the incident, "
                    "what was tried, what worked/didn't -- before offering any "
                    "new steps. Do not re-propose anything listed under DEAD "
                    "ENDS TRIED unless circumstances have changed."
                )
                for score, header, block in top:
                    injection_lines.append(f"\n---\n{block}")

        injected_content = "\n".join(injection_lines)

        if self.valves.debug_mode:
            injected_content = (
                "[DEBUG: diagnostic_history_filter fired -- keywords: "
                f"{keywords[:8]}]\n" + injected_content
            )

        messages.insert(
            last_user_idx,
            {"role": "system", "content": injected_content},
        )
        body["messages"] = messages
        return body

    def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        return body
