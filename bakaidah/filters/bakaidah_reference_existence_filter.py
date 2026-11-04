"""
title: Bakaidah Reference Existence Gate
author: the operator / Mokaima
author_url: N/A
funding_url: N/A
version: 0.9
description: v0.9 (2026-10-25): (a) a REFERENCES path that does not exist now
  gets a hint in the banner (same file name elsewhere in the vault, and
  same-numbered fmNN_ files in the cited folder); (b) NEW check on the
  EXPECTED FILES section of a brief: flags an entry that already exists
  (Angkai would overwrite it) and a new fmNN_ script that reuses an FM
  number already taken in that folder. Both use the existing directory
  index; nothing new is fetched. Valve enable_expected_files_check turns
  (b) off. Added after the 10-25 P2 re-run: drafts cited a nonexistent
  kaiju-gais-package/fashsd/fm07_prowlarr_dns_failure.sh and named a new
  file fm08_ while fm08_drive_health_check.sh exists.
  Deterministic outlet Filter, TWO independent checks.
  (1) ORIGINAL, unchanged: for MABS-brief-shaped responses, extracts
  every file path listed in the REFERENCES section and checks it
  actually exists in the vault via mcpo, flagging any that don't.
  (2) for ANY response, regardless of what the triggering message was,
  scans for a "this file doesn't exist" style claim and independently
  verifies it against the real vault -- if the claimed-missing path
  actually exists, flags the contradiction directly.

  v0.7 -> v0.8 (2026-09-05, "Mokaima help 1.1 Full Auto Angkai" part
  2, INCIDENT #033 close-out continued): v0.7's regex fix was real and
  correct, but a live re-test STILL showed no banner. Direct sqlite
  inspection of the actual persisted chat (bypassing the browser UI
  entirely) revealed the TRUE root cause, one level deeper than
  anything found so far: the assistant message's flat `content` field
  was GENUINELY EMPTY (`""`), not merely unrendered. The real reply
  text existed only inside `output[]`, in the item where
  `type == "message"`, as `content[0]["text"]` -- the exact same
  structure v0.6's WRITE-side dual-write already knew how to target,
  but this Filter's READ side (`response_text = message.get("content",
  "") or ""`, used by every version since v0.1) had never once looked
  there. Every prior version's negative-existence check was therefore
  scanning an empty string for this response shape -- no regex fix at
  any prior version could ever have caught this, since there was
  nothing to scan in the first place. Confirmed this is NOT
  intermittent/rendering-only: it is the actual persisted database
  content, verified via direct sqlite3 query against webui.db, no
  browser involved.
  FIX: added _extract_response_text(), used everywhere response_text
  was previously read via a bare `.get("content", "") or ""` -- tries
  the flat content field first (unchanged behavior for Legacy Mode or
  any Native Mode response that DOES populate it), and falls back to
  scanning `output[]` for a `type == "message"` item's `output_text`
  content when the flat field is empty. This is a READ-side fix,
  fully complementary to v0.6's WRITE-side dual-write -- together they
  now correctly handle a response shape where the real content lives
  ONLY in the structured output, on both ends.
  TESTED against a message object built to exactly mirror the real
  captured structure (reasoning + message output items, empty flat
  content) -- extraction correctly pulls the real text, the negative-
  existence check now fires on it, and the resulting warning banner is
  written to both the flat content field (now non-empty, populated
  with the real text + banner) and the structured output field
  (unchanged dual-write behavior). Also re-ran the full v0.7 regression
  suite (7 cases) against this version to confirm nothing regressed --
  all 7 still pass, since Legacy Mode / non-empty-content Native Mode
  responses take the unchanged first branch.
  ALSO APPLIES to the REFERENCES-section check (_extract_references_
  paths), which reads from the same response_text -- same underlying
  bug, same fix, one shared extraction point rather than two separate
  patches.
  NOT YET LIVE-TESTED as of this write -- logic/mock-tested only, using
  a mock built directly from the real captured object rather than a
  loosely-shaped guess (the same discipline the v0.4 lesson and this
  session's own v0.7 attempt both point to). Next step: paste into
  Open WebUI, re-run the SAME forced-claim test one more time, check
  the raw chat response for the banner directly, and if still absent,
  pull the same sqlite dump again to see the real persisted state
  rather than inferring from the UI.

  v0.6 -> v0.7 (2026-09-05, same session, earlier fix): _bare_path_
  pattern's character class included a bare space, letting it swallow
  leading prose ("The file PENDING.md" instead of "PENDING.md") into
  an unresolvable candidate. Fixed to disallow spaces in any matched
  segment. Real and necessary fix, confirmed via 7/7 regression tests
  -- but insufficient alone, since (per the v0.8 entry above)
  response_text was empty before this regex ever got a chance to run,
  for the specific response shape that triggered this whole
  investigation.

  v0.5 -> v0.6 (2026-08-13, To do and pending 2.0): ROOT CAUSE FOUND
  for why the outlet() warning banner never appeared in the live chat
  UI -- Open WebUI v0.10.2 Native Mode responses render from a
  structured output[type="message"].content[type="output_text"].text
  array, not the flat content field a Filter's outlet() traditionally
  writes to (GitHub open-webui/open-webui #27017). FIX: outlet() now
  dual-writes the banner into both fields when the structured output
  is present. This WRITE-side fix was correct and necessary, but (see
  v0.8 above) an equivalent READ-side gap on response_text extraction
  remained undiscovered until this session's live re-test.

  v0.4 -> v0.5 (2026-08-02, Daikaiju AIOps 1.5): bare-filename
  resolution via a directory-tree-built basename index
  (_get_file_index/_resolve_candidate), so a response naming only
  "fashsd_config_lib.sh" (no directory) can still resolve to its real
  full path instead of failing a literal mcpo lookup.

  v0.3 -> v0.4 (2026-08-02, Daikaiju AIOps 1.5): added the general,
  not-brief-gated existence-claim check (_negative_existence_pattern +
  _extract_any_paths + _check_existence_claims), broadening coverage
  beyond REFERENCES-section-only checking.

  v0.2 -> v0.3 (2026-07-26): a genuinely missing file returns HTTP 500
  with ENOENT text, not 404/400 -- fixed to recognize that as
  confirmed-missing rather than falling back to unverifiable.

  v0.1 -> v0.2 (2026-07-26): path normalization was prepending
  "vault/" when mcpo's root is already the vault root, causing every
  check to 500 silently. Fixed to strip a leading "vault/" instead.

  None of the 5 existing Filters (Diagnostic History Enforcement,
  Incident Fabrication Gate, MABS Brief Topic Match Gate, Enforcement
  Gate, MABS Brief Few Shot Example) check REFERENCES path existence --
  they check topic match, structure, incident-record fabrication, and
  few-shot contamination, but nothing verifies the file paths themselves
  resolve to real files. This Filter closes that specific gap.

  NOTE: this checks EXISTENCE only, not whether the brief's claims about
  a file's CONTENT are accurate -- that remains OUTPUT CONSTRAINT 8's
  job (verify function/variable names are real) and Mokaima's own review.
"""

import re
import time
import json as _json
import requests
from pydantic import BaseModel, Field
from typing import Optional, List


class Filter:
    class Valves(BaseModel):
        enable_reference_check: bool = Field(
            default=True,
            description="Check every REFERENCES path against the real vault "
            "and flag any that don't exist.",
        )
        mcpo_read_url: str = Field(
            default="http://localhost:8200/vault/read_text_file",
            description="mcpo endpoint for reading vault files, confirmed "
            "live this session via curl.",
        )
        mcpo_tree_url: str = Field(
            default="http://localhost:8200/vault/directory_tree",
            description="v0.5: mcpo endpoint for directory_tree, used to "
            "build a basename -> full path index for resolving bare "
            "filenames a response mentions without their directory.",
        )
        request_timeout_seconds: int = Field(
            default=10,
            description="Per-path timeout for the existence check.",
        )
        tree_timeout_seconds: int = Field(
            default=20,
            description="v0.5: timeout for the directory_tree call used to "
            "build the file index -- longer than a single read, since it "
            "walks the whole vault tree.",
        )
        index_cache_seconds: int = Field(
            default=300,
            description="v0.5: how long the file index is cached before "
            "re-walking the tree. vault doesn't change fast enough to need "
            "a fresh walk on every single check.",
        )
        max_paths_checked: int = Field(
            default=10,
            description="Safety cap on how many REFERENCES paths to check "
            "in one response, in case of a malformed/huge REFERENCES block.",
        )
        enable_expected_files_check: bool = Field(
            default=True,
            description="v0.9: check a brief's EXPECTED FILES entries "
            "against the vault directory index (overwrite and FM-number "
            "clash).",
        )
        priority: int = Field(
            default=0, description="Filter execution priority. Lower runs first."
        )

    def __init__(self):
        self.valves = self.Valves()
        self._file_index_cache = {}
        self._file_index_cache_time = 0

        self._brief_request_pattern = re.compile(
            r"\b(mabs[- ]?format|mabs[- ]?brief|angkai brief|draft.*brief|"
            r"write.*brief)\b",
            re.IGNORECASE,
        )

        self._references_section_pattern = re.compile(
            r"^\s*REFERENCES\b.*?\n[─═\-=]{4,}\n(.*?)(?=\n[─═\-=]{4,})",
            re.IGNORECASE | re.DOTALL | re.MULTILINE,
        )

        self._path_pattern = re.compile(
            r'["`]([^"`\n]+\.(?:sh|md|txt|py|yaml|yml|json|conf|cfg))["`]'
        )

        self._negative_existence_pattern = re.compile(
            r"\b(does\s+not\s+exist|doesn'?t\s+exist|not\s+present|"
            r"no\s+such\s+file|could\s+not\s+find|was\s+not\s+found|"
            r"no\s+matching\s+file|not\s+found\s+in|is\s+not\s+found)\b",
            re.IGNORECASE,
        )

        self._bare_path_pattern = re.compile(
            r"\b([A-Za-z0-9_\-\u4e00-\u9fff]+(?:/[A-Za-z0-9_\-\u4e00-\u9fff]+)*\."
            r"(?:sh|md|txt|py|yaml|yml|json|conf|cfg))\b"
        )

    def _extract_response_text(self, message: dict) -> str:
        """NEW v0.8: the real fix for why NO version of this Filter's
        checks ever fired on a whole class of live responses. Flat
        `content` first -- unchanged for Legacy Mode and any Native
        Mode response that DOES populate it. Falls back to scanning
        `output[]` for a `type == "message"` item's `output_text`
        content when flat content is empty -- confirmed via direct
        sqlite inspection of a real persisted chat (2026-09-05) that
        this is a genuine, non-rendering-related empty field, not just
        a UI display quirk. This is the READ-side counterpart to
        v0.6's WRITE-side dual-write, targeting the exact same
        output[] structure that logic already knew how to write to.
        """
        flat = message.get("content", "") or ""
        if flat:
            return flat
        for item in message.get("output", []) or []:
            if item.get("type") != "message":
                continue
            for part in item.get("content", []) or []:
                if part.get("type") == "output_text":
                    return part.get("text", "") or ""
        return ""

    def _extract_any_paths(self, text: str) -> List[str]:
        found = self._bare_path_pattern.findall(text)
        seen = set()
        result = []
        for p in found:
            p = p.strip()
            if not p or len(p) > 200 or len(p) < 3:
                continue
            if p not in seen:
                seen.add(p)
                result.append(p)
        return result[: self.valves.max_paths_checked]

    def _extract_references_paths(self, text: str) -> List[str]:
        m = self._references_section_pattern.search(text)
        if not m:
            return []
        section_body = m.group(1)
        paths = self._path_pattern.findall(section_body)
        seen = set()
        result = []
        for p in paths:
            p = p.strip()
            if p and p not in seen:
                seen.add(p)
                result.append(p)
        return result[: self.valves.max_paths_checked]

    def _normalize_path(self, path: str) -> str:
        if path.startswith("vault/"):
            return path[len("vault/") :]
        return path

    def _path_exists(self, path: str) -> Optional[bool]:
        normalized = self._normalize_path(path)
        try:
            resp = requests.post(
                self.valves.mcpo_read_url,
                json={"path": normalized},
                timeout=self.valves.request_timeout_seconds,
            )
            if resp.status_code == 200:
                return True
            if resp.status_code in (404, 400):
                return False
            if resp.status_code == 500:
                body_lower = (resp.text or "").lower()
                if "enoent" in body_lower or "no such file or directory" in body_lower:
                    return False
                return None
            return None
        except requests.exceptions.RequestException:
            return None

    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        return body

    def _get_file_index(self) -> dict:
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

    def _resolve_candidate(self, candidate: str) -> List[str]:
        if "/" in candidate:
            return [candidate]
        index = self._get_file_index()
        matches = index.get(candidate, [])
        if matches:
            return matches
        return [candidate]

    @staticmethod
    def _dir_matches(full_dir: str, dirpart: str) -> bool:
        if not dirpart:
            return True
        return full_dir == dirpart or full_dir.endswith("/" + dirpart)

    def _suggest_for_missing(self, path: str) -> str:
        """v0.9: for a REFERENCES path that does not exist, say where the
        same file name really lives and which same-numbered files sit in
        the cited folder. Empty string if nothing useful or no index."""
        index = self._get_file_index()
        if not index:
            return ""
        if path.startswith("vault/"):
            path = path[len("vault/"):]
        base = path.rsplit("/", 1)[-1]
        dirpart = path.rsplit("/", 1)[0] if "/" in path else ""
        parts = []
        elsewhere = index.get(base, [])
        if elsewhere:
            parts.append("same file name exists at: " + " | ".join(elsewhere[:3]))
        m = re.match(r"(fm\d+)_", base)
        if m and dirpart:
            pre = m.group(1) + "_"
            near = []
            for name, fulls in index.items():
                if name.startswith(pre) and name != base:
                    for full in fulls:
                        if self._dir_matches(full.rsplit("/", 1)[0], dirpart):
                            near.append(full)
            if near:
                parts.append("same-number file(s) in the cited folder: " + " | ".join(sorted(near)[:3]))
        if not parts:
            return ""
        return " (" + "; ".join(parts) + ")"

    def _check_expected_files(self, response_text: str) -> List[str]:
        """v0.9: EXPECTED FILES entries must not already exist (overwrite)
        and a new fmNN_ script must not reuse an FM number already taken
        in the same folder."""
        sec = re.compile(
            r"^\s*EXPECTED FILES\b.*?\n[─═\-=]{4,}\n(.*?)(?=\n[─═\-=]{4,}|\Z)",
            re.IGNORECASE | re.DOTALL | re.MULTILINE,
        )
        m = sec.search(response_text)
        if not m:
            return []
        index = self._get_file_index()
        if not index:
            return []
        pat = re.compile(
            r"([A-Za-z0-9_\-一-鿿]+(?:/[A-Za-z0-9_\-一-鿿]+)*\."
            r"(?:sh|md|txt|py|yaml|yml|json|conf|cfg))"
        )
        paths = []
        for p in pat.findall(m.group(1)):
            if p not in paths:
                paths.append(p)
        notes = []
        for p in paths[: self.valves.max_paths_checked]:
            base = p.rsplit("/", 1)[-1]
            dirpart = p.rsplit("/", 1)[0] if "/" in p else ""
            exact = [f for f in index.get(base, []) if self._dir_matches(f.rsplit("/", 1)[0], dirpart)]
            if exact:
                notes.append(
                    "EXPECTED FILES entry '" + p + "' already exists in the vault ("
                    + exact[0] + ") -- Angkai would overwrite it."
                )
                continue
            fm = re.match(r"(fm\d+)_", base)
            if fm and dirpart:
                pre = fm.group(1) + "_"
                clash = []
                for name, fulls in index.items():
                    if name.startswith(pre) and name != base:
                        for full in fulls:
                            if self._dir_matches(full.rsplit("/", 1)[0], dirpart):
                                clash.append(full)
                if clash:
                    notes.append(
                        "EXPECTED FILES entry '" + p + "' reuses FM number "
                        + fm.group(1) + ", already taken in that folder by: "
                        + " | ".join(sorted(clash)[:3]) + "."
                    )
        return notes

    def _check_existence_claims(self, response_text: str) -> List[str]:
        if not self._negative_existence_pattern.search(response_text):
            return []
        candidate_paths = self._extract_any_paths(response_text)
        if not candidate_paths:
            return []
        contradicted = []
        for candidate in candidate_paths:
            resolved_list = self._resolve_candidate(candidate)
            for resolved in resolved_list:
                result = self._path_exists(resolved)
                if result is True:
                    contradicted.append(resolved)
                    break
        return contradicted

    def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        if not self.valves.enable_reference_check:
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

        # v0.8: real text may live only in output[], not flat content --
        # see module docstring's v0.8 entry.
        response_text = self._extract_response_text(messages[last_assistant_idx])
        warnings = []

        contradicted = self._check_existence_claims(response_text)
        if contradicted:
            warnings.append(
                "warning: THIS RESPONSE CLAIMS A FILE DOES NOT EXIST, BUT "
                "IT ACTUALLY DOES -- confirmed via a direct vault read "
                "(resolved via directory index, not just the response's own "
                "bare filename): "
                + "; ".join(contradicted)
                + ". The 'does not exist' conclusion above is INCORRECT for "
                "this path -- do not trust it without re-checking directly."
            )

        triggering_msg = ""
        for i in range(last_assistant_idx - 1, -1, -1):
            if messages[i].get("role") == "user":
                triggering_msg = messages[i].get("content", "") or ""
                break

        if self._brief_request_pattern.search(triggering_msg):
            paths = self._extract_references_paths(response_text)
            if paths:
                missing = []
                unverifiable = []
                for p in paths:
                    result = self._path_exists(p)
                    if result is False:
                        missing.append(p)
                    elif result is None:
                        unverifiable.append(p)

                if missing:
                    warnings.append(
                        "warning: REFERENCE PATH(S) NOT FOUND in vault -- these "
                        "REFERENCES entries do not resolve to real files: "
                        + "; ".join(p + self._suggest_for_missing(p) for p in missing)
                        + ". Do not trust these paths without independent "
                        "verification before this brief reaches Angkai."
                    )
                if unverifiable:
                    warnings.append(
                        "note: could not verify these REFERENCES path(s) against "
                        "vault (connection/timeout issue, not a fabrication finding): "
                        + "; ".join(unverifiable)
                    )

            if self.valves.enable_expected_files_check:
                for note in self._check_expected_files(response_text):
                    warnings.append("warning: " + note)

        if warnings:
            banner = "\n\n---\n" + "\n".join(warnings)
            new_text = response_text + banner
            messages[last_assistant_idx]["content"] = new_text
            for _output_item in messages[last_assistant_idx].get("output", []) or []:
                if _output_item.get("type") != "message":
                    continue
                for _content_part in _output_item.get("content", []) or []:
                    if _content_part.get("type") == "output_text":
                        _content_part["text"] = new_text
            body["messages"] = messages

        return body
