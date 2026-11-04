#!/bin/bash
INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // empty')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
KAIJU_RELAY_ROOT="/srv/kaiju-vault/kaiju-relay"
VAULT_ROOT="/srv/kaiju-vault"
KAI052_TOKENIZER="/srv/angkai/.claude/hooks/kai052_tokenize.py"
srv_ROOT="/srv"
#  Layer C (2026-09-26): the broker spool is where Angkai submits
# promotion requests -- a known root, but ONLY the incoming/ directory.
BROKER_SPOOL_IN="/var/spool/kaiju-broker/incoming"
EXPECTED_FILES_LIST="/srv/angkai/.claude/hooks/expected_files.txt"
REFERENCES_LIST="/srv/angkai/.claude/hooks/references.txt"

# ----  FIX (2026-09-24): normalize FILE_PATH before any check ----
# Every check below did a raw string-prefix compare against FILE_PATH
# with zero normalization. A RELATIVE path never starts with "/", so
# CHECK 0's own guard ([[ "$FILE_PATH" == /* ]]) skipped it entirely,
# and every other check's prefix match silently failed to match too --
# a relative path bypassed every single gate in this file. Reuses
# production_matcher.resolve_path() (built for /076: expands
# "~", joins a relative path against the call's cwd, resolves symlinks
# and ".." via realpath) instead of inventing new normalization logic.
# FAILS OPEN to the original literal FILE_PATH if production_matcher.py
# is missing or the python call errors -- this file's own checks below
# still run against whatever FILE_PATH they get, same as before this
# fix existed, rather than this fix itself becoming a new hard-block
# surface (production_matcher.py's own load is NOT a dependency this
# script should ever hard-fail on, unlike /076 which are
# purpose-built gates that SHOULD fail closed on a missing matcher).
if [[ -n "$FILE_PATH" ]]; then
  CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
  RESOLVED=$(python3 -c "
import sys
sys.path.insert(0, '/srv/angkai/.claude/hooks')
try:
    import production_matcher
    print(production_matcher.resolve_path(sys.argv[1], sys.argv[2] or '/srv/angkai'))
except Exception:
    print(sys.argv[1])
" "$FILE_PATH" "$CWD" 2>/dev/null)
  [[ -n "$RESOLVED" ]] && FILE_PATH="$RESOLVED"
fi

# ---- CHECK 0: unknown-root absolute path detection ----
if [[ -n "$FILE_PATH" ]] && [[ "$FILE_PATH" == /* ]]; then
  if [[ "$FILE_PATH" != "$VAULT_ROOT"* ]] && [[ "$FILE_PATH" != "$srv_ROOT"* ]] && [[ "$FILE_PATH" != "$BROKER_SPOOL_IN/"* ]]; then
    echo "BLOCKED: '$FILE_PATH' does not resolve under any known Kaidosho root (vault or /srv)." >&2
    echo "This looks like an invented or generic placeholder path, not a real one in this environment." >&2
    echo "Do NOT guess a plausible-sounding path. Use list_directory to confirm the real path, or stop and report to Mokaima if unsure." >&2
    exit 2
  fi
fi
# ---- CHECK 1: kaiju-relay-specific read-path correction ----
CHECK_TEXT="${FILE_PATH}${COMMAND}"
if [[ "$CHECK_TEXT" == *"kaiju-relay"* ]] || [[ "$CHECK_TEXT" == *"Kaiju"* ]]; then
  if [[ "$CHECK_TEXT" == *"Daikaiju  主"* ]]; then
    echo "BLOCKED: path contains a double space between 'Daikaiju' and '主'." >&2
    echo "The correct path has exactly ONE space:" >&2
    echo "$KAIJU_RELAY_ROOT" >&2
    exit 2
  fi
  if [[ -n "$FILE_PATH" ]] && [[ "$FILE_PATH" == *"kaiju-relay"* ]]; then
    if [[ "$FILE_PATH" != "$KAIJU_RELAY_ROOT"* ]] && [[ "$FILE_PATH" != "$VAULT_ROOT"* ]]; then
      echo "BLOCKED: '$FILE_PATH' does not resolve under the real kaiju-relay root." >&2
      echo "Use the FULL ABSOLUTE PATH, not a relative one:" >&2
      echo "$KAIJU_RELAY_ROOT/<filename>" >&2
      exit 2
    fi
  fi
fi
# ---- CHECK 2: write-path allowlist ----
IS_WRITE_TOOL=0
case "$TOOL_NAME" in
  Write|Edit|mcp__vault__write_file|mcp__vault__create_directory) IS_WRITE_TOOL=1 ;;
esac
PLANS_DIR="/srv/angkai/.claude/plans"
if [[ "$IS_WRITE_TOOL" -eq 1 ]] && [[ -n "$FILE_PATH" ]] && { [[ "$FILE_PATH" == "$VAULT_ROOT"* ]] || [[ "$FILE_PATH" == "$PLANS_DIR"* ]]; }; then
  if [[ -s "$EXPECTED_FILES_LIST" ]]; then
    TARGET_BASENAME=$(basename "$FILE_PATH")
    CLEAN_LIST=$(grep -v '^#' "$EXPECTED_FILES_LIST" | grep -v '^[[:space:]]*$')
    if ! grep -qxF "$TARGET_BASENAME" <<< "$CLEAN_LIST"; then
      echo "BLOCKED: '$TARGET_BASENAME' is not on this task's EXPECTED FILES list." >&2
      echo "Allowed deliverable(s) for this task:" >&2
      sed 's/^/  - /' "$EXPECTED_FILES_LIST" >&2
      echo "If this file genuinely needs to be created, stop and report to Mokaima -- do not create it unilaterally." >&2
      exit 2
    fi
  fi
fi
# ---- CHECK 2b: Plan Mode gate ( hard-stop) ----
PLAN_ELIGIBLE_FLAG="/srv/angkai/.claude/hooks/plan_mode_allowed.txt"
if [[ "$TOOL_NAME" == "EnterPlanMode" ]]; then
  if [[ ! -s "$PLAN_ELIGIBLE_FLAG" ]]; then
    echo "BLOCKED: Plan Mode entry is not authorized for this task." >&2
    echo "Self-initiated planning is a permanent hard-stop ( Section 6.1)." >&2
    echo "If this task genuinely requires a multi-step plan, STOP and report to" >&2
    echo "Mokaima -- do not enter Plan Mode unilaterally." >&2
    exit 2
  fi
fi
# ---- CHECK 3: read-side named-file allowlist ----
# Mirrors CHECK 2 exactly, mirrored for reads instead of writes.
# Fail-open if REFERENCES_LIST is missing or empty.
extract_bash_read_target() {
  local cmd="$1"
  local vault_root="$2"

  if [[ "$cmd" == *";"* || "$cmd" == *"&&"* || "$cmd" == *"||"* || \
        "$cmd" == *"|"* || "$cmd" == *'`'* || "$cmd" == *'$('* ]]; then
    return 1
  fi

  local -a tokens=()
  local tok
  while IFS= read -r -d '' tok; do
    tokens+=("$tok")
  done < <("$KAI052_TOKENIZER" "$cmd" 2>/dev/null)

  [[ "${#tokens[@]}" -eq 0 ]] && return 1

  local verb="${tokens[0]:-}"

  case "$verb" in
    ls|cat|find|head|tail) ;;
    grep)
      local has_r=0
      for t in "${tokens[@]:1}"; do
        [[ "$t" == "-r" || "$t" == "-R" || "$t" == "-rn" || "$t" == "-nr" ]] && has_r=1
      done
      [[ "$has_r" -eq 1 ]] || return 1
      ;;
    *) return 1 ;;
  esac

  local candidate=""
  local skip_one=0
  [[ "$verb" == "grep" ]] && skip_one=1
  for t in "${tokens[@]:1}"; do
    [[ "$t" == -* ]] && continue
    if [[ "$skip_one" -eq 1 ]]; then
      skip_one=0
      continue
    fi
    candidate="$t"
    break
  done

  [[ -z "$candidate" ]] && return 1
  [[ "$candidate" == "$vault_root"* ]] || return 1

  echo "$candidate"
  return 0
}

IS_READ_TOOL=0
case "$TOOL_NAME" in
  Read|mcp__vault__read_text_file|mcp__vault__read_file|mcp__vault__list_directory) IS_READ_TOOL=1 ;;
  Bash)
    BASH_READ_TARGET="$(extract_bash_read_target "$COMMAND" "$VAULT_ROOT")"
    if [[ -n "$BASH_READ_TARGET" ]]; then
      IS_READ_TOOL=1
      FILE_PATH="$BASH_READ_TARGET"
    fi
    ;;
esac
if [[ "$IS_READ_TOOL" -eq 1 ]] && [[ -n "$FILE_PATH" ]] && [[ "$FILE_PATH" == "$VAULT_ROOT"* ]]; then
  if [[ -s "$REFERENCES_LIST" ]]; then
    TARGET_BASENAME=$(basename "$FILE_PATH")
    CLEAN_REFS=$(grep -v '^#' "$REFERENCES_LIST" | grep -v '^[[:space:]]*$')
    if ! grep -qxF "$TARGET_BASENAME" <<< "$CLEAN_REFS"; then
      echo "BLOCKED: '$TARGET_BASENAME' is not on this task's REFERENCES list." >&2
      echo "Files you are permitted to read for this task:" >&2
      sed 's/^/  - /' "$REFERENCES_LIST" >&2
      echo "If you genuinely need a different file, STOP and report to Mokaima -- do not read it unilaterally." >&2
      exit 2
    fi
  fi
fi
# ---- CHECK 4: duplicate-read blocker ----
# session_id pulled from the same $INPUT stdin JSON already parsed
# above -- NOT an env var (unconfirmed in Claude Code's documented
# hook contract). Brief itself is exempt via ANG_BRIEF_BASENAME, set
# by whoever runs the launch command.
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "default"')
READ_LOG="/srv/angkai/.claude/hooks/session_reads_${SESSION_ID}.log"
CURRENT_BASENAME=$(basename "$FILE_PATH" 2>/dev/null)
if [[ "$IS_READ_TOOL" -eq 1 ]] && [[ -n "$FILE_PATH" ]] && [[ "$CURRENT_BASENAME" != "${ANG_BRIEF_BASENAME:-}" ]]; then
  touch "$READ_LOG" 2>/dev/null
  if [[ -f "$READ_LOG" ]] && grep -qxF "$FILE_PATH" "$READ_LOG" 2>/dev/null; then
    echo "BLOCKED: '$FILE_PATH' was already read once this session." >&2
    echo "Re-reading the same file without new information is a known drift pattern" >&2
    echo "(see vault/reference/Angkai_Execution_Error_Log.md, 2026-08-16, entry 2)." >&2
    echo "If you have a genuine reason to re-read, STOP and state it to Mokaima/the operator" >&2
    echo "instead of re-issuing the call." >&2
    exit 2
  fi
  echo "$FILE_PATH" >> "$READ_LOG" 2>/dev/null
fi
# ---- CHECK 5: Phase-2-review verbatim/duplicate check ----
# Fires ONLY when the write target's basename is exactly
# tier1_full_suite_reviewed.md. Every other Write/Edit passes through
# untouched. Two checks, both stdlib/deterministic, no GPU/model call:
#   5a. every "- Warning:" quoted string must be an exact substring of
#       a real stage_c_warnings entry in the 3 source JSON files.
#   5b. no two "- Rationale:" strings across different model/task pairs
#       may be near-identical (difflib ratio > 0.8) -- catches uniform
#       boilerplate stamping (see  item 3 Attempt 3).
if [[ "$IS_WRITE_TOOL" -eq 1 ]] && [[ "$(basename "$FILE_PATH" 2>/dev/null)" == "tier1_full_suite_reviewed.md" ]]; then
  CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // .tool_input.new_string // empty')
  if [[ -n "$CONTENT" ]]; then
    SRC1="$KAIJU_RELAY_ROOT/tier1_full_suite_results.json"
    SRC2="$KAIJU_RELAY_ROOT/qwen32b_retest_results_FINAL.json"
    SRC3="$KAIJU_RELAY_ROOT/retest_slow_models_results.json"
    REAL_WARNINGS=$(jq -r '.[].result.stage_c_warnings[]?' "$SRC1" "$SRC2" "$SRC3" 2>/dev/null)

    # 5a: verbatim warning-text check
    DRAFT_WARNINGS=$(grep -oP '(?<=- Warning: ").*(?=")' <<< "$CONTENT")
    if [[ -n "$DRAFT_WARNINGS" ]]; then
      while IFS= read -r DW; do
        [[ -z "$DW" ]] && continue
        if ! grep -qF -- "$DW" <<< "$REAL_WARNINGS"; then
          echo "BLOCKED: a Warning: string in the draft does not match any real stage_c_warnings entry in the source JSON files (verbatim substring check failed)." >&2
          echo "Non-matching text: $DW" >&2
          echo "Do NOT paraphrase or invent warning text. Copy it exactly from the real source files." >&2
          exit 2
        fi
      done <<< "$DRAFT_WARNINGS"
    fi

    # 5b: near-duplicate rationale check (python3 stdlib difflib, no deps)
    DRAFT_RATIONALES=$(grep -oP '(?<=- Rationale: ).*' <<< "$CONTENT")
    if [[ -n "$DRAFT_RATIONALES" ]]; then
      DUP_CHECK=$(python3 -c "
import sys
from difflib import SequenceMatcher
lines = [l for l in sys.stdin.read().splitlines() if l.strip()]
threshold = 0.8
flagged = []
for i in range(len(lines)):
    for j in range(i+1, len(lines)):
        r = SequenceMatcher(None, lines[i], lines[j]).ratio()
        if r > threshold:
            flagged.append((i, j, r))
if flagged:
    print('DUP_FOUND')
    for i, j, r in flagged[:3]:
        print(f'  pair ({i},{j}) ratio={r:.2f}: {lines[i][:80]!r} vs {lines[j][:80]!r}')
else:
    print('OK')
" <<< "$DRAFT_RATIONALES")
      if [[ "$DUP_CHECK" == DUP_FOUND* ]]; then
        echo "BLOCKED: two or more Rationale: strings are near-identical (similarity > 0.80)." >&2
        echo "This is the exact uniform-boilerplate fabrication pattern from Attempt 3 -- each" >&2
        echo "rationale must be genuinely grounded in that specific task's own real output." >&2
        echo "$DUP_CHECK" >&2
        exit 2
      fi
    fi
  fi
fi
exit 0
