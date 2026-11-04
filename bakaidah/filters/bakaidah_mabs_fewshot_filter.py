"""
title: Bakaidah MABS Brief Few-Shot Example
author: the operator / Mokaima
author_url: N/A
funding_url: N/A
version: 0.2
description: Deterministic inlet gate. (v0.2, 2026-10-25: the example's vault
  paths said kaiju-gais-package/, a folder that does not exist (real name
  kaiju-gais-package/); Bakaidah copied the wrong name into a drafted
  brief's REFERENCES on 10-24. Paths corrected, nothing else changed.) After 4 consecutive failed
  attempts at "draft a MABS brief for X" across v2.7-v2.9 (unrelated
  directory summary, an unrelated existing brief presented as
  progress, a generic PENDING.md status summary, and finally
  fabricated incident records that don't exist in the real journal),
  abstract structural rules (OUTPUT CONSTRAINT 8) were clearly not
  enough on their own. This Filter injects one complete, real,
  Mokaima-approved MABS brief (, for a different, unrelated
  service -- FM-05 drive-mount fix, NOT Vaultwarden or whatever is
  actually being requested) directly into context whenever a brief-
  drafting request is detected, so Bakaidah has a concrete shape to
  copy rather than only abstract rules to recall. The example is
  hardcoded rather than fetched live via mcpo -- its only job is to
  demonstrate structure, not stay current, and hardcoding means it
  still works even if mcpo/vault is briefly unreachable.

TESTED 2026-07-25: confirmed the filter injects a system message
  containing the real  content only when the triggering message
  matches the brief-request pattern, and leaves unrelated messages
  completely untouched.

NOTE: this does not by itself fix fabrication (inventing false content
  about the ACTUAL requested subject) -- it only demonstrates correct
  STRUCTURE. Pair with the MABS Brief Topic Match Gate (outlet) filter
  to catch fabricated or off-topic content even when structure looks
  right.
"""

import re
from pydantic import BaseModel, Field
from typing import Optional


# A real, Mokaima-approved MABS brief for a DIFFERENT, unrelated service
# (FM-05 drive-mount fix). Deliberately NOT about whatever the user is
# actually requesting -- Bakaidah should copy the SHAPE, not the content.
_EXAMPLE_BRIEF = '''#  — FM-05 Config-Driven Drive Not Mounted Fix Script
Brief for: Angkai (Claude Code / Qwen)
Written by: Mokaima (drafted by Bakaidah, corrected + approved by Mokaima) | 2026-07-24
Protocol version: MABS v2.1

════════════════════════════════════════
HARD PROHIBITIONS — no exceptions, ever:
════════════════════════════════════════
  ✗ Do not modify any file not explicitly listed in EXPECTED FILES below
  ✗ Do not introduce new dependencies beyond what's already in fashsd_config_lib.sh
  ✗ Do not change the core fix logic beyond what's required for config-driven operation
  ✗ Do not alter exit codes or behavior beyond what's explicitly required
  ✗ Do not execute anything you generate — write only, never deploy
  ✗ If uncertain: STOP and say so. Do not guess.

────────────────────────────────────────
CONFIRM BRIEF LOADED
────────────────────────────────────────
Before doing anything else, state:
  " loaded. Task: FM-05 config-driven drive-mount fix. 1 phase."
Then proceed.

────────────────────────────────────────
TASK
────────────────────────────────────────
Generalize Kaidosho's FM-05 drive-not-mounted fix script (remounts a named
drive by fstab mountpoint) to validate the drive name against
services.yaml's drives[] list via fashsd_config_lib.sh, instead of
Kaidosho's hardcoded regex (hola1-hola5). Follow the exact pattern already
proven in fm01_container_exited.sh's compose_dir validation loop.

────────────────────────────────────────
REFERENCES (read every one of these via mcp__vault__read_file before writing anything)
────────────────────────────────────────
  1. mcp__vault__read_file with path:
     "vault/angkai/staging//fm05_drive_not_mounted.sh"
     (the original script — preserve this logic exactly, per Rule 16)
  2. mcp__vault__read_file with path:
     "vault/kaiju-gais-package/fashsd/fashsd_config_lib.sh"
     (confirm kaiju_drive_count and kaiju_drive_field exist exactly as
     used below — there is NO kaiju_drive_names function, do not use it)
  3. mcp__vault__read_file with path:
     "vault/kaiju-gais-package/fashsd/fm01_container_exited.sh"
     (the proven pattern template for KAIJU_LIB_DIR/KAIJU_LOG_DIR sourcing)
  4. mcp__vault__read_file with path:
     "vault/kaiju-gais-package/fashsd/kaiju_fashsd_config.example.yaml"
     (config schema reference only, do not modify)

────────────────────────────────────────
EXPECTED FILES (closed list)
────────────────────────────────────────
This brief produces exactly 1 file:
  1. kaiju-gais-package/fashsd/fm05_drive_not_mounted.sh
Do not create any file not listed here.

────────────────────────────────────────
OUTPUT FORMAT — use exactly this structure
────────────────────────────────────────

Banner (paste this exact text — new untested script, unrelated to
fashsd_config_lib.sh's own current TESTED banner):
```bash
#!/bin/bash
# ============================================================
# WARNING: UNTESTED. DO NOT DEPLOY.
# Needs an actual test pass against a live config before use.
# See kaiju-gais-package/fashsd/tests/TESTING.md.
# ============================================================
# fm05_drive_not_mounted.sh — Kaiju Spine config-driven drive remount fix
# Generalized from Kaidosho's  fm05_drive_not_mounted.sh.
# Deploy to: /opt/kaiju-os/watchdog/
```

Environment setup (copy exactly from fm01_container_exited.sh's pattern):
```bash
: "${KAIJU_LIB_DIR:=/opt/kaiju-os/watchdog}"
source "$KAIJU_LIB_DIR/fashsd_config_lib.sh"

: "${KAIJU_LOG_DIR:=/var/log/kaiju-watchdog}"
mkdir -p "$KAIJU_LOG_DIR" 2>/dev/null || KAIJU_LOG_DIR="/tmp/kaiju-watchdog-fallback"
mkdir -p "$KAIJU_LOG_DIR"

LOG="$KAIJU_LOG_DIR/watchdog.log"
```

Replace the hardcoded regex validation with this exact block — builds
the valid-names list ONCE and reuses it in both the usage message and
the validation-failure message, using only the two real functions
(kaiju_drive_count, kaiju_drive_field — both take an index, never a name):
```bash
DRIVE_COUNT=$(kaiju_drive_count)
VALID_NAMES=""
for i in $(seq 0 $((DRIVE_COUNT - 1))); do
    VALID_NAMES="$VALID_NAMES $(kaiju_drive_field "$i" "name")"
done

if [ $# -ne 1 ]; then
    echo "Usage: $0 <drive_name>" >&2
    echo "drive_name must be one of:$VALID_NAMES" >&2
    exit 1
fi
drive_name=$1

VALID_DRIVE=false
for i in $(seq 0 $((DRIVE_COUNT - 1))); do
    CONFIG_DRIVE_NAME=$(kaiju_drive_field "$i" "name")
    if [ "$CONFIG_DRIVE_NAME" = "$drive_name" ]; then
        VALID_DRIVE=true
        break
    fi
done
if [ "$VALID_DRIVE" = false ]; then
    echo "Error: drive_name must be one of:$VALID_NAMES" >&2
    exit 1
fi
```

Preserve from the original (unchanged): the snapshot call, the
`sudo mount "/mnt/$drive_name"` command, the `sleep 5`, the
`mountpoint -q` verification, and the PASS/FAIL logging format.

────────────────────────────────────────
FINAL INSTRUCTION
────────────────────────────────────────
When complete, say: " complete. 1 file ready for review."
Then stop. Do not deploy, execute, test, or copy anything. Mokaima will
add this script to kaiju-gais-package/fashsd/tests/ for the same test
suite pass the first 3 scripts went through before this one's warning
banner comes down.
'''


class Filter:
    class Valves(BaseModel):
        enabled: bool = Field(
            default=True, description="Master on/off switch for this filter."
        )
        debug_mode: bool = Field(
            default=True,
            description="If true, prepend a visible marker confirming this "
            "filter fired. Turn off once confirmed working.",
        )

    def __init__(self):
        self.valves = self.Valves()
        self._brief_request_pattern = re.compile(
            r"\b(mabs[- ]?format|mabs[- ]?brief|angkai brief|draft.*brief|"
            r"write.*brief)\b",
            re.IGNORECASE,
        )

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
        if not self._brief_request_pattern.search(user_text):
            return body

        injection = (
            "[FEW-SHOT EXAMPLE -- injected automatically because this looks "
            "like a MABS-brief drafting request]\n"
            "Below is a REAL, Mokaima-approved MABS brief, for a "
            "COMPLETELY DIFFERENT, unrelated service (an FM-05 drive-mount "
            "fix script). It is provided ONLY to show you the correct "
            "STRUCTURE and level of specificity a MABS brief needs -- do "
            "NOT draft anything about drives or FM-05. Study its shape: "
            "HARD PROHIBITIONS block, a CONFIRM BRIEF LOADED line, TASK, "
            "numbered REFERENCES (each with the exact tool call to use), a "
            "closed EXPECTED FILES list, an OUTPUT FORMAT section with "
            "exact code blocks to reuse, and a FINAL INSTRUCTION stating "
            "how to signal completion. Your own response must follow this "
            "exact same structure, but be entirely about the actual "
            "subject requested in this conversation -- every section must "
            "be freshly written for that real subject, not copied from "
            "this example's drive/FM-05 content.\n\n"
            "--- BEGIN EXAMPLE (different service, structure only) ---\n"
            f"{_EXAMPLE_BRIEF}\n"
            "--- END EXAMPLE ---"
        )

        if self.valves.debug_mode:
            injection = "[DEBUG: mabs_fewshot_filter fired]\n" + injection

        messages.insert(
            last_user_idx,
            {"role": "system", "content": injection},
        )
        body["messages"] = messages
        return body

    def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        return body
