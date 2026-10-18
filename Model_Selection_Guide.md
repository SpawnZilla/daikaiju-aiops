╔══════════════════════════════════════════════════════════════════════╗
║  KAIJU OS — MODEL SELECTION GUIDE                                   ║
║  Version: 1.0 | Created: 2026-07-22 (Daikaiju AIOps)                ║
║  Fills: Kaiju_OS.md gap 4                                           ║
╚══════════════════════════════════════════════════════════════════════╝

Which local models to run for each Kaiju OS agent role, by hardware
tier. Covers the two roles Kaiju OS's Layer 1 (Orchestration) needs a
local model for: an EXECUTION AGENT (writes/generates scripts and
config under a planning agent's direction — Kaidosho calls this Angkai)
and a REASONING/CONVERSATION AGENT (general Q&A, drafting, tool-calling
against your vault-equivalent memory — Kaidosho calls this Bakaidah).

Research current as of 2026-07-22. Local model rankings shift fast —
re-verify before a public release if this guide is more than ~2-3
months old.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE ONE RULE THAT MATTERS MOST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Keep the whole model resident in VRAM. The moment any layer spills into
system RAM, throughput collapses and agent-style multi-step loops
become painfully slow — worse than just running a smaller model
entirely in VRAM. When in doubt, size down rather than let a model
spill over. This matters more for agentic/tool-calling use (execution
agent role) than for occasional chat.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HARDWARE TIERS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TIER 1 — LOW (≤8GB VRAM, or CPU-only)
────────────────────────────────────────
Realistic expectations: basic execution-agent tasks (simple scripts,
short briefs following Rule 1's ~200-line ceiling strictly), slower
turnaround, best for occasional use rather than a tight iterative loop.

  Execution agent: Qwen3 8B (Apache 2.0 license, ~6-8GB at Q4_K_M).
    Native tool-calling, currently the most consistently reliable small
    model for agent-style tasks in independent testing. Good default
    if you're not sure what else to pick.
  Reasoning/chat: Llama 3.1 8B (~5GB at Q4). Versatile general-purpose
    option if you want a different model for chat vs. execution rather
    than reusing Qwen3 8B for both (running two 8B models sequentially
    on 8GB is fine; running them concurrently is not — budget VRAM
    accordingly if both roles are active at once).
  CPU-only fallback: expect meaningfully slower responses. Any 7-8B
    model at Q4 will run, but agentic multi-step loops (execution
    agent role especially) will feel sluggish enough that Tier 1 users
    on CPU-only hardware may want to keep execution-agent tasks short
    and infrequent rather than iterative.

TIER 2 — MID (8-16GB VRAM)
────────────────────────────────────────
Meaningfully more headroom for genuine agentic use — this is where a
Mixture-of-Experts (MoE) architecture starts paying off, since only a
fraction of total parameters activate per token, keeping VRAM lower
than a dense model of similar quality.

  Execution agent: Qwen3 14B (dense, ~9.3GB download, leaves room for
    context on a 16GB card). Community comparisons rank the Qwen 3.x
    family ahead of alternatives at this size for local coding/agent
    work. (Changed 2026-10-09 from Qwen3 30B-A3B: its 19GB download
    does not fit 16GB.) Kaidosho's own Angkai runs the coder variant at a
    higher tier — see Tier 3.
  Reasoning/chat: same Qwen3 14B works fine for both roles if
    running them sequentially, not concurrently, on 16GB. If you want
    a dedicated chat model instead, Gemma 4 or Mistral Small 3.2 are
    reasonable alternatives in this range.
  16GB-specific note: gpt-oss:20b (OpenAI's open-weight release, MXFP4
    quantization, 128K context) is a solid pick if you specifically
    want a non-Qwen option at the top of this tier.

TIER 3 — HIGH (16-24GB VRAM)
────────────────────────────────────────
This is Kaidosho's own reference tier (Dokaisho's GPU setup runs Angkai
here) and the tier most independent rankings treat as the current
local-coding sweet spot — best quality-per-GB before jumping to
multi-GPU/workstation territory.

  Execution agent: qwen3-coder:30b (MoE, ~19GB at Q4_K_M, 256K
    context; pin it as qwen3-coder:30b-a3b-q4_K_M -- there is no bare
    30b-a3b tag for this model). This is what Kaidosho's Angkai runs today. Consistently
    ranked at or near the top for local coding/agentic work at this
    VRAM tier across independent benchmarks. Devstral 24B is a close
    alternative specifically strong on multi-file agentic edits if
    coding style leans toward touching several files per task.
  Reasoning/chat (Kaidosho's own pick): Gemma 4 31B (gemma4:31b, 19-20GB,
    256K context; Kaidosho runs it as gemma4-baragon:31b for Bakaidah, with
    context set explicitly -- see Troubleshooting notes on num_ctx).
    Gemma 4 26B (26b-a4b, 16-19GB) fits the lower end of this tier.
  Reasoning/chat (ranking pick): Qwen 3.6 27B (dense, not MoE) is the top overall pick
    for a 24GB card in current rankings — notably outperforms some
    larger models on real-world coding/agentic benchmarks despite being
    smaller. Qwen2.5-Coder 32B is an alternative if raw single-shot code
    quality matters more than agentic/tool-use reliability (it posts
    the highest raw code-completion benchmark scores at this tier but
    isn't as agent-tuned as the 3.6 or 3-coder families).
  Embedding model (for RAG/vector search over your vault-equivalent
    vault): nomic-embed-text (~274MB) is the current default choice
    across the Ollama ecosystem — small, fast, good enough for this
    use case. This is also what Kaidosho runs for Immich + Bakaidah's RAG.

TIER 4 — ENTHUSIAST (24GB+, workstation/multi-GPU)
────────────────────────────────────────
Beyond Tier 3's sweet spot, gains are real but diminishing relative to
hardware cost — worth it mainly if running both agent roles
concurrently at full size, or chasing the absolute top of current
benchmarks.

  Execution agent: Qwen2.5-Coder 32B if staying dense-model, or scale
    up the qwen3-coder MoE family if a larger variant is available.
  Reasoning/chat: Llama 3.3 70B (~43GB, needs to spill to a 48GB+ card
    or multi-GPU) is the current general-purpose workhorse at full
    scale, if hardware supports it.
  Server-class options exist (GLM-5.2, Kimi K2.7-Code) but need
    256GB+ unified memory or multi-GPU server hardware — out of scope
    for a homelab-tier Kaiju OS install. Not recommended for v1 of this
    guide; flag as a future "enthusiast+" tier if there's ever demand.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUICK-PICK TABLE (for the bootstrap installer's Phase 1 prompt)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

| Tier | VRAM     | Execution agent pull            | Reasoning/chat pull      |
|------|----------|----------------------------------|---------------------------|
| 1    | ≤8GB     | qwen3:8b                        | llama3.1:8b               |
| 2    | 8-16GB   | qwen3:14b                        | qwen3:14b (shared)        |
| 3    | 16-24GB  | qwen3-coder:30b-a3b-q4_K_M        | qwen3.6:27b                |
| 4    | 24GB+    | qwen2.5-coder:32b                | llama3.3:70b               |

Embedding model, any tier: nomic-embed-text

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NOTES FOR THE BOOTSTRAP INSTALLER (Phase 1 integration)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- The installer's hardware-tier prompt (the installer spec
  Phase 1, step 1) should map directly to the 4 tiers above.
- Pull sizes are large (Tier 3's coder model is ~19GB) — the installer
  should warn about download size/time before starting the pull, not
  just silently begin a multi-GB download.
- If a user's VRAM doesn't cleanly match a tier boundary (e.g. exactly
  12GB), default DOWN to the safer/smaller tier rather than up — the
  "keep it all in VRAM" rule matters more than picking the nominally
  best model for the size.
- This guide resolves OPEN QUESTION #2 from the installer spec.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SOURCES / LAST VERIFIED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Synthesized from multiple independent 2026 local-LLM ranking sources
(coding-specific and general-agent-specific benchmarks, VRAM-tier
guides) plus Kaidosho's own live Angkai/Bakaidah configuration as a real-
world Tier 3 reference point. Web research performed 2026-07-22 — see
Daikaiju AIOps chat history for that date for search provenance.
Re-verify current model names/sizes before public release; this space
moves in weeks, not months.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RE-VERIFICATION NOTE 2026-10-09 (Mokaima, part 21) -- finding 1 APPLIED (Tier 2 and quick-pick row 2 now qwen3:14b, the maintainer 2026-10-09); findings 2 and 3 still open
Checked against ollama.com/library pages. Confirmed to exist, size within the guide's
figures: qwen3:8b (5.2GB), qwen3-coder:30b (19GB), qwen3.6:27b (18-19GB, 256K),
gpt-oss:20b (14GB, MXFP4), devstral:24b (14GB), qwen2.5-coder:32b (20GB, 32K ctx),
llama3.3:70b (43GB), llama3.1:8b (4.9GB), nomic-embed-text (274MB), mistral-small3.2 (15GB),
gemma4 (e4b 6.6-9.5GB, 12b ~8GB, 26b 16-19GB, 31b 19-20GB).
FINDINGS NEEDING A DECISION:
  1. Tier 2 (8-16GB) names qwen3:30b-a3b as fitting "comfortably". Ollama lists qwen3:30b at
     19GB; MoE lowers compute per token, not resident size. It breaks this guide's own
     one rule (whole model in VRAM) on a 16GB card. Candidates that fit: qwen3:14b (9.3GB),
     gpt-oss:20b (14GB). Quick-pick row 2 has the same issue.
  2. The Ollama landing pages do not show a 30b-a3b tag (qwen3:30b, qwen3-coder:30b only);
     the guide's tags qwen3:30b-a3b and qwen3-coder:30b-a3b-q4_K_M were not confirmed on the
     full tag lists.
  3. Tier 3 reasoning pick is qwen3.6:27b, but Kaidosho's own live reasoning model is
     gemma4-baragon:31b (gemma4:31b, 19-20GB); the guide does not mention that.
NOT RE-VERIFIED: the "independent ranking" claims.
UPDATE 2026-10-10 (Mokaima, part 21, the maintainer asked to finish): findings 2 and 3 APPLIED.
  Finding 2: ollama.com tag lists show qwen3:30b-a3b (19GB) and qwen3-coder:30b-a3b-q4_K_M (19GB)
    both exist; qwen3-coder has NO bare 30b-a3b tag (Tier 3 text corrected to qwen3-coder:30b).
  Finding 3: Tier 3 now names gemma4:31b (19-20GB, 256K) as Kaidosho's own reasoning pick.
  Tier 4: GLM-5.2 and Kimi K2.7 Code exist (both released mid-June 2026 per implicator.ai).
    GLM-5.2: 744B total / 40B active, MIT license. Kimi K2.7 Code: 1T total / 32B active; whether
    its weights are downloadable was not confirmed. The "256GB+ unified memory or multi-GPU"
    hardware claim was not confirmed by either source. Tier 4 names otherwise unchanged.
  Guide re-verified 2026-10-10; next re-verify due about 2027-01.

END OF MODEL SELECTION GUIDE v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
