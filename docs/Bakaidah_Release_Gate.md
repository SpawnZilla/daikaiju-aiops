# Bakaidah release gate (decided 2026-10-28, part 30; reversible)
Rule: NO change to the Bakaidah chat model, its system prompt, any Filter or Pipe, its tools, num_ctx, Keep Alive, or the Ollama service settings goes onto Bakaidah Daikaiju until this gate passes on the staging copy. Anything that fails is reverted from git or the backup, not patched live.

## 0. Staging copy
Bakaidah Online is the staging model (loader off, web search on). CAVEAT found 10-28: its base model is qwen3:30b-a3b, Bakaidah Daikaiju's is gemma4-bakaidah:31b, so a pass on Bakaidah Online does not prove the real model. Before relying on it: Admin > Models > Bakaidah Online > set the base model to gemma4-bakaidah:31b (reversible), then refresh its system field from bakaidah_system_prompt.txt.

## 1. Before the change (on dokaisho, in the vault root)
- `git status` clean enough to roll back; copy the model's current system field to a backup file (the drift check can print it).
- Drift check, identical expected for Bakaidah Daikaiju and Bakaidah Online (command in vault_tools/prompt_drift_check.py, docstring).

## 2. Run the gate on the staging copy (Open WebUI chat, each prompt in its own NEW chat)
a. INCIDENT_045_regression_set.md: P1, P2, P3, each x3 = 9 runs, pass rule in that file (no "I'm ready. What do you need?", P3 quote found on the page, P2 all MABS sections, P2 header/paths correct).
b. Journal read x3: "Read /srv/kaiju-vault/vault/reference/Troubleshooting_Journal.md and summarize its last 5 entries." Pass = one read_text_file call each, no INDEX.md read, no placeholder, summaries match the stub roster.
c. Ollama truncation check, on dokaisho (reads the log, changes nothing; no output = pass): `sudo journalctl -u ollama --since "HH:MM" | grep -i truncating`
d. Filter-ran check, on the pi-node (reads the log, changes nothing; at least one line per P2 run = pass): `docker logs open-webui 2>&1 | grep "structured brief drafter v0.1" | tail`
e. Tool-error check, on the pi-node (no output = pass; Mokaima can read the same lines through the read-only collector): `docker logs --since 1h open-webui 2>&1 | grep -E "Tool not found|Tool-call limit"`

## 3. Verdict
PASS only if a to e all pass. Any FAIL: record it in INCIDENT_045_regression_set.md's result log, revert, and do not retry the same change in the same session.

## 4. Promote and record
Apply to Bakaidah Daikaiju, re-run 2b and 2c once (3 minutes), re-run the drift check (expect IDENTICAL), bump the version and VERSION HISTORY, append a result-log row, commit.

## Retired
The never-run TEST-001..013 suite (bakaidah_regression_test_suite.md) is retired as a separate suite: it was tied to the superseded model comparison and prompt versions. This gate replaces it. Reopen only if a new failure class appears that the gate does not cover.
