# Daikaiju AIOps / Kaiju GAIS
## Full History, Current State, and Roadmap

> **Historical report, written as of 2026-08-03.** For the current state see [Status & Roadmap](../docs-site/docs/status.md); later work (incident loop, agent wiring) is covered there and in the repository README.

*Compiled by Mokaima (Claude Desktop) from vault source documents as of 2026-08-03.*
*Every claim below traces to a specific vault file or chat session. Where a fact
could not be confirmed against a real source, it is marked UNCONFIRMED rather
than presented as settled.*

---

## 1. What This Is

**The one-liner:** *Governed, self-hosted agentic infrastructure for the
homelab tier — agents that plan, execute, self-heal, and remember, with a
formal guardrail layer that catches them when they're wrong, instead of
trusting them unsupervised.*

This is actually two related products built on one stack:

- **Kaiju GAIS** (Governed Autonomous Infrastructure System) — the
  framework itself. Self-hosted, fully local-inference (no vendor-hosted
  LLM ever touches infrastructure decisions), pre-wired rather than
  stitched together from separate tools. Every design decision traces to a
  real incident it survived on a live homelab, not a whiteboard exercise.
- **Daikaiju AIOps** — the autonomy layer that runs on top of Kaiju GAIS.
  Same guardrails, same foundation, but with AI agents planning and
  executing instead of a human driving every step.

You can run Kaiju GAIS without Daikaiju AIOps (the lower-commitment entry
point). You cannot run Daikaiju AIOps without Kaiju GAIS underneath it.

**The core pitch — trust through built-in disagreement:** most agentic AI
tools ask you to trust one model's output directly. This system doesn't —
one agent verifies what another drafted before anything is allowed to
execute. This is the answer to what the project's own pitch document calls
the defining problem in agentic AI right now: widespread interest, very
low actual reliance, because nobody trusts a single model to act
unsupervised.

This isn't just narrative. As of 2026-07-31, every Bakaidah-drafted brief
tracked so far needed real correction before it was trustworthy — an
average of 3.0 rounds of correction for briefs eventually approved, and a
50% rate (2 of 4 tracked outcomes) where the draft was serious enough to
be abandoned and rewritten from scratch by Mokaima rather than iterated
further. Neither number is meant to look good in isolation; together
they're first-party evidence the guardrail layer catches real failures,
not hypothetical ones.

---

## 2. The People and Agents

The system is built and operated by one person (referred to throughout
vault as "the operatora" or "the operator"), working with three named AI agents that
form a pipeline:

| Agent | What it actually is | Role |
|---|---|---|
| **Mokaima** | Claude Desktop (Anthropic-hosted) | Orchestration, verification, documentation, judgment calls. Writes briefs, reviews everything before it ships. |
| **Bakaidah** | A local Qwen model (currently `qwen3:30b-a3b`) served via Ollama + Open WebUI | Research, drafting, brief-writing. Runs entirely locally, zero API cost. |
| **Angkai** | Claude Code, reconfigured to route to the same local Ollama backend rather than Anthropic's API | Execution — turns an approved brief into real file changes, at zero token cost. |

The pipeline is strictly ordered: **Mokaima writes/reviews a brief → Bakaidah
drafts (when the task fits its role) → Mokaima verifies → Angkai
executes → Mokaima reviews the result in staging → the operatora deploys.**
Angkai is explicitly *not* responsible for deployment; Mokaima owns
staging review, always.

A fourth infrastructure layer, **vault** (Vault, sometimes styled
vault), is the versioned, git-backed documentation system all three
agents read from and write to — the project's memory. Without it, every
session would start from zero.

---

## 3. Origins

The earliest recorded root of this pipeline is a **2026-05-21** session
("Doshozilla 1.3") that formally established the three-tool split (then
called Qwen WebUI / Mokaima / Angkai → Claude Code/Qwen 32B) and created
the `angu` system user account that Angkai still runs under.

Two more foundational sessions followed:
- **2026-05-24** ("Mattp Handoff") — assessed and absorbed the `/handoff`
  pattern, formalizing the session-keyword system (session start/mid/end)
  that Kaiju GAIS later packages as reusable onboarding.
- **2026-05-21** ("Angkai BMAD") — evaluated the BMAD-METHOD framework
  (a software-dev methodology, not homelab infra) and extracted three
  reusable patterns for Angkai's own instruction file rather than
  adopting it wholesale.

**2026-07-17** ("Side Income Potential from Doshozilla Project") was the
first time the underlying homelab system was assessed as a potential
product rather than purely personal infrastructure. Six systems were
identified inside what was being built (orchestration, self-healing,
governance/guardrails, documentation/memory, knowledge-transfer, and a
naming/identity system) and the name **Kaiju Spine** (later renamed Kaiju
GAIS) was coined to describe all of them as one product. The decision at
the time was to focus on the system's own growth rather than a commercial
path — superseded three days later.

**2026-07-20** ("Kaidosho Daikaiju General") formally split the single "Kaiju
OS" concept into the two products described above (Kaiju Spine as the
framework, Daikaiju AIOps as the autonomy layer running on it), wrote the
first one-liners for each, and identified six gaps standing between the
current system and full agentic operation (an orchestration layer,
queryable agent memory, a machine-readable task queue, a rollback/safety
gate, an agent-to-agent communication protocol, and a self-written audit
log). Both products were promoted to HIGH PRIORITY the same session.

---

## 4. MABS — The Guardrail Layer

**MABS** (Mokaima Angkai Brief Standard) is the project's most
defensible, least-commodity component — a formal set of rules governing
how a task gets turned into a brief Angkai can safely execute. It
exists because Angkai, run without hard structural constraints,
repeatedly failed in documented, specific ways: inventing wrong compose
paths, guessing at architecture instead of reading it, losing task
identity mid-brief and building something unrelated, and reverting to
wrong tools even after being given exact correct paths multiple times in
the same session (all logged under "ANGUIRUS IMPROVEMENT" in
`PENDING.md`, 2026-07-17 through 07-19).

MABS has grown through direct incident response, not speculative design:

- **v1.x** established the base rule set.
- **v2.0** (2026-07-22) consolidated all 8 outstanding Angkai-improvement
  fix items into one tracked blocker section, explicitly named "Daikaiju
  AIOps Phase 0 Blocker" — nothing else could proceed until these closed.
- **v2.1** (2026-07-24) closed the remaining items with **Rule 19**
  (a literal manifest block — exact absolute path + exact MCP tool call —
  for every REFERENCES entry, folding three separate failure symptoms
  that turned out to be one root cause) and **Rule 20** (a pre-brief
  triage step: classify a task as code-generation vs. synthesis before
  writing the brief; synthesis-type work is never handed to Angkai,
  it routes to Mokaima direct-write). This closed Daikaiju AIOps's Phase 0
  blocker on the brief-wording side entirely.

Two pieces of Section 8 infrastructure named alongside v2.0 — a
mechanical (script-based, not prompt-based) post-execution validator, and
a git snapshot/rollback backstop — were tracked separately as ****
and ****. (the **Stop hook validator**) is done;
remains open (see §8).

A parallel, portable version — **MABS_Standalone.md** — generalizes the
same 18 rules and the "structural not instructional" core principle into
vendor-agnostic planning-agent/execution-agent language, for anyone
replicating this system without the Kaidosho-specific incident history baked
in.

---

## 5. vault — The Memory Layer

vault lives at `/srv/vault`, is git-versioned with a
bare remote on the edge-node and a Gitea mirror, and is organized in a 3-tier
structure. Its key living documents, referenced throughout this report:

- `kajazilla7.txt` — the current-state snapshot of every service and
  infrastructure component. Never holds pending items — those live
  exclusively in `PENDING.md` (general homelab) or `AIOPS_PENDING.md`
  (product-scoped, split out 2026-07-31).
- `Troubleshooting_Journal.md` — the numbered INCIDENT log (see §9).
- `PA.md` — "Possible Additions," where ideas and designs live before
  they're committed to PENDING.md.
- The `dosho_daikaiju_chat_history_*.txt` files — one per subject
  (Kaidosho Pipeline, Daikaiju AIOps, Infrastructure, etc.), each a
  chronological, newest-first consolidated record of every session
  touching that subject. These are this report's primary source.

A knowledge graph (**Graphify**, deployed 2026-07-18, live at
`graph.operatoralabs.org`) indexes vault into a queryable structure — 110
nodes, 195 edges as of its last full rebuild — and is wired into Bakaidah
via `mcpo` so it can be queried directly rather than read file-by-file.

---

## 6. Kaiju Naming Convention

Every component of the system is named after a kaiju (Godzilla-universe
monster), giving a complex multi-agent, multi-node system a consistent,
memorable identity: Mokaima, Bakaidah, Angkai, Vakai (a Debian node added
to the fleet), the operatora (the operator's own handle), and so on. A
standalone **Naming_Convention_Guide.md** packages this into four reusable
naming categories (nodes/agents/subsystems/storage) for anyone building
their own instance with a different naming scheme.

**Known constraint:** Toho actively holds trademarks on Godzilla, Mothra,
Angkai, Bakaidah, and related names. Internal development names stay as
they are; a public-facing, trademark-safe naming scheme is required
before any external advertising, sale, or app-store/marketing listing.
This is logged as low priority *until demand is validated* — see §11 —
but was reaffirmed as a real sequencing dependency once the YouTube
documentation series (§11) started being planned, since filming under
the internal names would need to precede any rename.

---

## 7. The Six-Layer Product Structure

As formalized in the project pitch and `Kaiju_Spine.md` (v1.1, resolving a
naming conflict between two earlier drafts):

1. **Orchestration Layer** — the Mokaima→Brief→Bakaidah→Angkai pipeline,
   generalized. The spine everything else plugs into.
2. **Guardrail Layer** — MABS (§4). The most defensible, least-commodity
   piece; almost nobody in the homelab-agentic space has this formalized.
3. **Self-Healing Layer** — FASHSD (§8): watchdogs, alerting,
   Wake-on-LAN, remediation scripts, a living failure-mode catalog.
4. **Memory/Archive Layer** — vault (§5).
5. **Onboarding/Transfer Layer** — brief templates, system prompts,
   glossaries, the bootstrap install spec, the hardware compatibility
   matrix. What turns this from a personal setup into something someone
   else can stand up.
6. **Naming/Identity Layer** — the Kaiju convention (§6), what makes the
   system legible and teachable.

Layers 2 and 3 are the differentiators; layers 1 and 4 are the plumbing
that makes them work; layer 5 is what makes it a product; layer 6 is what
makes it teachable.

---

## 8. FASHSD — The Self-Healing Layer

**FASHSD** (Full Autonomous Self-Healing System Design) is Kaidosho's own
self-healing pipeline, and — generalized and stripped of Kaidosho-specific
hardcoding — becomes Kaiju GAIS's packaged self-healing layer.

**Phase 1 (Watchdog + Alert)** — DONE, deployed 2026-07-12 (see Status & Roadmap).
Runs on the edge-node (interval later tightened from hourly to 30 minutes),
pushes ntfy notifications and triggers Wake-on-LAN to intake-host on
failure.

**Phase 2 (Automated Remediation)** — built around a **symptom-driven
decision tree**, not blind escalation through a fixed ladder. The
project's stated core principle: only branches confirmed by a real
incident belong in the tree; nothing is added from theory. As of
2026-07-12, the tree had 5 confirmed branches and 1 explicitly
unvalidated design-only branch:

| Failure Mode | Symptom | Fix (confirmed live) |
|---|---|---|
| **FM-01** | Container exited cleanly | `docker compose up -d` on the one container |
| **FM-02** | Docker daemon itself down | `systemctl start docker`, then down/up-d across all compose dirs |
| **FM-03** | GlueTun (VPN gateway) unhealthy | Restart GlueTun → verify healthy → **then** restart its 5 network-namespace-sharing dependents → verify with a real curl check, not just health status. Never route this symptom through the generic FM-01 fix. |
| **FM-04** | edge-node clock drift (post power-loss) | NTP toggle off/on + restart Prowlarr specifically (time-sensitive) |
| **FM-05** | Drive not mounted | `mount` the drive (unvalidated design as of 07-12, later built/tested) |
| **FM-09** (new) | Container shows "Up" but app unreachable (stale docker-proxy) | `docker compose down && up -d` — status-only detection cannot see this; requires an application-level curl check |

A separate **generalization effort** turned Kaidosho's own hardcoded scripts
into a config-driven Kaiju GAIS package (`kaiju-os-package/fashsd/`),
driven by a `services.yaml`-style config with a schema that's evolved
twice: v1.1 added `compose_dir` per service; v1.2 (2026-07-29) added
`network_groups` for FM-03-style owner/dependents restart ordering.

**Full test suite run 2026-07-23**, all 6 steps passed after finding and
fixing 4 real bugs (a `yq` variant mismatch — Debian's `apt install yq`
is a different tool than the one originally assumed; several hardcoded
paths that needed env-var overrides; a script that hard-failed instead of
gracefully skipping an unpackaged dependency). **/025** (FM-02 and
FM-05, generalized) were executed by Angkai and test-passed
2026-07-27. **FM-03's own generalized script**
(`fm03_gluetun_unhealthy.sh`) was written directly by Mokaima on
2026-08-03 after an earlier Bakaidah-drafted brief for it was found to
reference three fabricated config-lib functions and facts not present in
any real vault doc — written instead, correctly, against the real
functions and the documented decision-tree procedure above. **It has not
yet been tested** — no test harness for it exists yet either.

**Status as of this report:** 5 of ~10 planned FASHSD scripts generalized
and test-passed (FM-01, FM-02, FM-05, plus the underlying app-level curl
check and Wake-on-LAN trigger); FM-03 written but untested; FM-04, 06,
and 07 not yet drafted; the top-level orchestrator script and drive/SMART
checks not yet located/built.

---

## 9. Reliability Work — The Incident History

A large share of this project's actual engineering effort has gone into
making Bakaidah (the drafting agent) trustworthy enough for its brief
output to be used with only Mokaima-level review rather than full
rewrites. This section is a condensed account of that work; item-level
detail lives in `Troubleshooting_Journal.md` and `AIOPS_PENDING.md`.

**The core finding, repeated across the project:** individual facts in a
Bakaidah draft are very often each independently correct — the more
common and more dangerous failure mode is a fabricated function name, a
dropped status-changing update, or content invented to fill a plausible
gap, sitting alongside otherwise-accurate material. This is why the
guardrail layer is mechanical (scripts, structural schema-forcing) rather
than purely prompt-based — prompt-only fixes have been tried repeatedly
and have not reliably held.

**Confirmed infrastructure/tooling bugs found along the way** (not
Bakaidah's fault, but real production issues):
- **incident / #016** — a stale, root-owned `server-filesystem`
  process pattern causing MCP disconnects; recovery is the
  `claude-clean-restart` alias. Root cause of the original triggering
  event remains unconfirmed despite thorough investigation.
- **incident** — Bakaidah's custom Pipe functions could freeze the
  entire Open WebUI instance; fixed via background-thread-plus-polling.
- **incident** (2026-07-30) — two severe production failures on
  Bakaidah (General): a completely unrelated brief returned once, then (with
  Memory confirmed OFF) a fabricated "SYNC CONFIRMED" status report
  reciting the session's own tracking-doc content back as if it had been
  performed. Leading hypothesis — document-content-as-instruction bleed
  from Mokaima-addressed meta-instructions mixed into Bakaidah-facing
  reference files — was tested across several controlled sub-experiments
  and remains **MIXED, not confirmed or ruled out**. Open WebUI's Memory
  feature was disabled instance-wide as an independent fix regardless.
- **incident** (2026-08-01) — `search_files` in the filesystem MCP
  server is silently non-recursive beyond direct children, despite its
  own description claiming full recursion. This caused at least 5
  documented real false-negatives ("this file doesn't exist") on files
  that were simply nested deeper than one level. No upstream fix
  available; workaround is to never trust `search_files` beyond an
  immediate directory.
- **incident** (2026-08-01) — Open WebUI chats hanging indefinitely
  mid-response; cleared by a container restart, root cause unconfirmed.
- **incident** — a related but distinct failure: a complete
  reasoning-monologue response with no final answer ever given, despite
  thinking mode confirmed off at the time. Traced in part to an open,
  unresolved upstream Open WebUI bug (GitHub #26072).

**Real configuration fixes, found and applied directly:**
- **Native Mode** — all three Bakaidah model entries were found running
  on deprecated Legacy prompt-injection instead of real function calling
  (fixed 2026-07-29). Confirmed via regression testing to **not**, on its
  own, fix the core fabrication problem.
- **num_ctx never set** — Bakaidah had likely been running at Ollama's
  bare 2048–4096-token default instead of its real 40,960-token capacity
  for the entire deployment lifetime, discovered 2026-08-01 and fixed
  2026-08-02. This immediately surfaced a real, previously-unmeasured
  cost: at full context, Bakaidah alone uses ~94–98% of the GPU's VRAM,
  meaning Bakaidah and Angkai can never both stay loaded simultaneously
  — confirmed via live testing, not a blocker since the pipeline already
  runs them sequentially, but a real cold-reload cost on every handoff.
- **ENABLE_KB_EXEC** — a long diagnostic chain (6+ live rounds) root-caused
  Bakaidah's model-default Knowledge Base attachment as a real, filed
  upstream Open WebUI bug (GitHub #21299); explicit in-chat attachment is
  the confirmed working alternative.

**The mechanical fixes that actually moved the needle:**
- **Citation Grounding Pipe** and **Structured Brief Drafter Pipe** —
  purpose-built Open WebUI Pipe functions that check Bakaidah's output
  against real, fetched source content rather than trusting the model's
  self-report. Directly, head-to-head validated as the actual fix for
  citation fabrication, where prompt-only and Native-Mode fixes were not.
- **Stop hook validator** (`) — a deterministic,
  script-based Claude Code hook that checks Angkai's phase output
  against a brief's own source-of-truth data before the turn can end.
  Verified across 5 live-fire test cycles, catching 3 real bugs review
  alone had missed.
- **`bakaidah_reference_existence_filter.py`** () — the most
  actively-worked mechanical fix as of this report. Originally scoped
  only to MABS-brief REFERENCES sections; generalized (v0.3→v0.5) to
  fire on any assistant response claiming a file doesn't exist, checking
  directly against a real `mcpo` read rather than trusting the model.
  **As of 2026-08-02, 8 live test attempts have been made against a
  standing fabrication-check question — zero clean passes, but each
  round found and fixed a real, distinct bug** (a false-positive
  pre-deployment test that masked a real bare-filename-resolution bug;
  an intermittent underlying non-completion issue in Open WebUI that
  keeps interrupting the test before the Filter is ever exercised).

**Kaiju Relay** () — a separate architectural response to the
same reliability problem: instead of one model doing retrieval, drafting,
and self-verification together, a staged pipeline (`model_relay.py`) runs
narrow-job models in sequence with mechanical checks between stages.
Built and live-tested through v0.6 as of 2026-08-01, including a
dedicated **Stage C** adversarial-review stage (uncertainty preservation,
reference-fabrication, and brief-ID-collision checks feeding a
mandatory/auto-proceed checkpoint gate). A real, confirmed limitation:
Stage C can only catch a fabrication Stage B *adds on top of* Stage A's
facts — it has no mechanism yet for one that originates in Stage A
itself, confirmed live when a model's own first-stage output invented an
entire fictional config file that a later stage then faithfully (and
undetectably) cited back.

---

## 10. Current State — What's Actually Built and Live

As of 2026-08-03:

- The full three-agent pipeline, running, with MABS v2.1 guardrails.
- The Stop hook validator, deployed and verified.
- 5 of ~10 FASHSD scripts generalized and test-passed; a 6th (FM-03)
  written but not yet tested.
- Both production Bakaidah Pipes (Citation Grounding, Structured Brief
  Drafter) deployed and live-verified.
- Kaiju Relay Stages A/B/C built and live-tested against real Ollama
  through model_relay.py v0.6.
- `bakaidah_reference_existence_filter.py` v0.5 deployed, not yet
  confirmed working against a genuine live false-negative (the
  underlying intermittent-response problem keeps preempting the test).
- num_ctx and Native Mode fixed and verified on Bakaidah (General).
- vault's 3-tier structure, git-versioned with a edge-node bare remote and
  Gitea mirror.
- Graphify knowledge graph, live and queryable by Bakaidah via `mcpo`.
- Voice interface (`vbakaidah`, Whisper.cpp + Kokoro TTS) — working, full
  round-trip confirmed. A parallel Mokaima-facing voice interface
  (`vmokaima`) is **parked**, not working — it currently routes to a
  local model instead of genuinely reaching Claude, and the explicit
  standing decision is to scrap it entirely rather than ship a version
  that only wears a Mokaima label without really being Mokaima.
- the project pitch, `Software_Package_Overview.md`, and
  `Audit_Observability_View.md` — the first vault-native versions of the
  business narrative and software inventory, previously scattered only
  across chat history.
- A knowledge graph extension design (chat-logic graph, ) is
  fully spec'd but not yet built.

---

## 11. In Progress

- **** (the reference-existence filter) — the single
  most-actively-worked item, 8 live attempts and counting, no clean pass
  yet but real fixes shipped each round (see §9).
- ** Kaiju Relay Stage 1** — the actual "read real files, output
  verified facts" stage has not yet had its real build started; Stage
  0/A/B/C work so far has been on the relay mechanism itself.
- **Demand validation** — an anonymized guardrail-framework write-up
  went live on r/selfhosted 2026-07-31. As reported back (not
  independently re-verified against the live thread as of this report),
  the response was read as meaningful validation on three signals: the
  guardrail problem is seen as controversial, more assumed-about than
  actually understood, and capable of drawing real attention. An
  r/homelab post was planned for 2026-08-01; its live status is not
  confirmed as of this report.
- **YouTube documentation series** — decided 2026-08-02 to start now
  rather than waiting for the system to be "done" (which, as a
  continuously-running system, it structurally never will be). A
  Bakaidah-first drafting workflow was proposed (Bakaidah drafts from raw
  incident detail plus a voice sample for cadence, Mokaima verifies
  against vault incident records, the operatora corrects) but has not yet
  started — no script drafted, no voice sample yet supplied.
- **Bakaidah config verification** — a full customization table
  (model, Native Mode, thinking-mode state, num_ctx, Pipe/Filter
  versions, system prompt version) was reconstructed from memory during
  a `dosho wan` session on 2026-08-03 and explicitly flagged as unverified
  recall, pending a live cross-check against the actual Admin Panel.

---

## 12. Roadmap — What's Planned, Not Yet Started

Pulled directly from `AIOPS_PENDING.md`'sxx tracker, current as of
this report:

- **** — Git snapshot/rollback backstop for Angkai brief
  execution (distinct from the personal-infra rollback layer, which is
  already built). Not started.
- **** — Audit/observability aggregation layer. **v1 already
  built** (§1's reliability numbers come from it) but explicitly
  incomplete: ntfy alert history not yet wired in, and the current n=4
  sample is a starting point, not a mature track record.
- **** — Cost/resource governor. Not started; needs scoping first
  (what "cost" even means for a fully local, non-metered stack).
- **** — Portable install/bootstrap script (`./install.sh`).
  Prerequisites (hardware compatibility matrix, distro portability
  design, the 7-phase interactive install spec) are complete; the
  script itself has not been written.
- **** — Build and test a full Kaiju GAIS install inside a clean
  VM, to genuinely verify the "under 1 hour to deploy" claim. Explicitly
  blocked on existing first.
- **Public-facing trademark-safe naming** — required before any external
  marketing, sale, or listing (see §6). Low priority until demand is
  validated.
- **`ponytail`** (GitHub, DietrichGebert) — a Claude Code plugin
  candidate for reducing Angkai's documented scope-creep/over-build
  failure mode. Identified 2026-08-02, not yet evaluated in depth.
- A backlog of ~15 external-research items (Hermes Agent patterns, a
  Karpathy "lint pass for stale/contradictory docs" concept, ref-graph
  dependency tracking for vault pages, and others) sits in `PENDING.md`'s
  DOSHO WAN DEFERRED ITEMS section, evaluation-only, not yet acted on.

---

## 13. Honest Gaps in This Report

In the interest of not doing exactly what this whole project exists to
guard against — presenting a confident, complete-sounding account that
quietly omits what isn't actually known — three things are flagged here
rather than smoothed over:

1. **Reddit demand-validation outcome** is reported secondhand, from a
   session that itself was reconstructing it from a compacted transcript
   summary rather than a fresh read of the live thread. Treat the
   "meaningful validation" framing in §11 as the operatora's read, not an
   independently verified fact.
2. **The Bakaidah config table** referenced in §11 was explicitly built
   from memory during a `dosho wan` (no-tool-access) session and has not
   yet been cross-checked live — several fields (thinking-mode state in
   particular) are known to have flipped more than once recently.
3. **This report itself has not been reviewed by Bakaidah or run through
   the project's own drafting pipeline** — it was written directly by
   Mokaima from source documents, at your request, rather than following
   the Bakaidah-drafts/Mokaima-verifies pattern described throughout the
   report. If you want a second pass checking this document's own
   claims against source the way the pipeline would normally do for any
   other deliverable, that's a reasonable next step.

---

*Sources: `kajazilla7.txt`, `PENDING.md`, `AIOPS_PENDING.md`, `PA.md`,
`angkai/MABS.md`, `TSInfo/Troubleshooting_Journal.md`,
`project chat history`,
`project chat history`, the project pitch,
all read directly from vault on 2026-08-03.*
