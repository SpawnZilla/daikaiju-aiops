# Kaiju Relay — Multi-Stage Model Pipeline Design
## Bakaidah reliability, reframed as staged roles instead of one model doing everything

Status: DRAFT — design only, not yet built. RAISED BACK TO HIGH
2026-07-31 (Daikaiju AIOps 1.3) — / precondition
rescinded, see AIOPS_PENDING.md  UPDATE for full reasoning
(short version:  dropped as a precondition entirely since
Relay's staged design makes single-model-choice largely moot;
reframed from a blocking gate to a Stage A design input). Phase 0
measurement (model_relay.py) is the next concrete action.
Origin: the operator's idea, 2026-07-30 (dosho wan session, "Daikaiju AIOps 1.1"
continuation) — "use multiple Qwen models that feed their output into
the next model's input, each specializing in part of the final outcome"
Researched against: Ch3w3y/multipi (GitHub), read in full 2026-07-30
Author: Mokaima
Working name: **Kaiju Relay** (placeholder — pick something matching
the established naming convention; not locked)

---

## 1. THE ORIGINAL IDEA, RESTATED PLAINLY

Instead of one Bakaidah model doing retrieval, drafting, and
self-verification all in one context window — which is the exact shape
of every serious failure logged this session (fabricated function
names, the FM-04 task substitution, the fabricated sync-report) — split
those jobs across separate model calls, each with a narrow context and
a single job, chained so one stage's output becomes the next stage's
*only* input.

This is a sound instinct. It directly targets a past incident's leading
hypothesis: a single model loses the boundary between "reading
reference material" and "narrating a role" when both live in the same
context. Separating retrieval from drafting from review removes that
boundary problem structurally instead of asking one model to hold it
better.

---

## 2. WHAT MULTIPI ACTUALLY IS (research findings, 2026-07-30)

Read the full README + architecture section directly, not just search
snippets. Key facts:

- **multipi is a plugin for `pi` (pi.dev)**, a TypeScript coding-agent
  CLI — not a standalone Python library, not something you drop into
  Ollama or Open WebUI directly. It provides: 7 generic subagent role
  definitions (markdown prompt files), a `subagent` TypeScript
  extension that spawns child `pi` processes with tool-allowlists, a
  local SearXNG container for web search, and optional tmux
  window-per-agent visibility.
- **Its state machine is real and well-designed**: S0_INTAKE →
  S1_RESEARCH → S2_PLANNING → S3_IMPLEMENTATION → S4_REVIEW →
  S5_ITERATE | S6_DONE. Each state has a named output artifact and an
  explicit gate (PASS/BLOCK) before the next state can start. Every
  transition is logged (`[S1→S2] planner produced architecture.md
  (1.2k lines) — gate passed`).
- **Its reference model-routing config assumes multiple large models
  available simultaneously**: a 1T model (`kimi-k2.6`) for
  orchestration/research, a 123B model (`devstral-2`) for
  planning/implementation, plus a fast flash model for review and
  another for narrow lookups — routed via Ollama Cloud endpoints or
  separate compute backends, not one local GPU.
- **The reviewer role is adversarial by design**: it assumes the
  producing agent cut corners, checks against a red-team checklist
  (service dies mid-batch, volume spikes, duplicate data, PII leaks,
  license ambiguity), and returns PASS or BLOCK with ordered required
  changes. This is a distinct, separate role from the drafter — not a
  self-check the drafter performs on itself.
- **Agents are generic and project-aware**: no hardcoded project
  details in the role prompts themselves. Each agent reads, in order:
  a project-level ops-manual file → project-specific role overrides →
  locked project artifacts (schemas, architecture) → generic defaults.
  This is architecturally the same shape as Kaidosho's own MABS brief
  convention (a generic Angkai role + a project-specific brief
  file), just formalized as an explicit read-order.
- **Web search**: local SearXNG, queried in parallel across Google/
  DuckDuckGo/Brave/Startpage, JSON output, no API keys. Kaidosho already
  runs this exact pattern (192.0.2.21:8085, wired to Bakaidah).

### 2a. What this means for Kaidosho, honestly

**Cannot adopt as software.** `pi` is a different tool from anything
in the Kaidosho stack (Open WebUI/Bakaidah, Claude Code/Angkai, custom
Python Pipes). Installing it would mean a third orchestration surface
running alongside the other two — new footprint, new failure modes,
and directly against the lesson from tonight's Qwen3.6 incident: don't
take on new production surface without testing it isolated first.

**Cannot adopt the reference hardware assumption at all.** multipi's
example config assumes simultaneous access to a 1T-parameter model and
a 123B-parameter model. dokaisho has one GPU, ~24GB VRAM, and a
single ~24-27B model already uses 99% of it. Kaidosho cannot run multipi's
architecture as documented, full stop — this isn't a tuning problem,
it's a different hardware class entirely.

**Can adopt the architecture pattern, rebuilt natively.** The valuable
part isn't the code — it's the shape: isolated-context roles, a formal
state machine with gates, and a genuinely separate adversarial review
role. All three are buildable on infrastructure Kaidosho already has and
already proved tonight.

---

## 3. HARDWARE REALITY CHECK — the constraint that shapes everything below

Confirmed live tonight (2026-07-30): a single 27B-class model
(qwen3.6:27b) loads at **24GB / 99% VRAM allocated / 100% GPU** on
dokaisho's card. There is no meaningful headroom left once one
mid-size model is resident.

This means:
- **Kaidosho cannot run two large models simultaneously.** A multi-stage
  pipeline using different model tags per stage must load and unload
  sequentially — Ollama evicts the prior model to make room for the
  next. This is the SAME eviction mechanism already logged as a
  problem for Angkai/Bakaidah coexistence (see PENDING.md,
  "Angkai/Bakaidah VRAM contention").
- **Every model swap between stages costs real, measured time** — a
  cold reload, not free. Tonight's tests already showed Qwen3.6 alone
  is noticeably slower than qwen3-coder for a single generation; a
  multi-stage relay with model swaps between every stage could
  plausibly add real minutes per brief, not seconds. This has NOT been
  measured yet and must be, before committing past a 2-stage MVP.
- **A small, cheap model for the narrow retrieval/verification role is
  the one piece of multipi's design that's actually free on Kaidosho's
  hardware** — something in the 3-8B class could plausibly coexist
  alongside a larger drafting model, or at minimum reload fast enough
  not to matter. This needs its own test, not an assumption.
- **A chunk of the "retrieval" stage may not need to be an LLM call at
  all.** Confirming whether a function exists in `fashsd_config_lib.sh`
  is a grep, not a reasoning task. The existing
  `_mechanical_postcheck()` pattern already proves Kaidosho's own preference
  for mechanical checks over model calls wherever possible — the same
  logic applies to a retrieval stage. Worth treating "pure Python
  retrieval, no model at all" as the DEFAULT for Stage A, not "a small
  model" — only fall back to a model call for retrieval tasks that
  genuinely require judgment (e.g. summarizing which of several
  matching files is most relevant), not simple existence checks.

**Bottom line: this session's original framing ("multiple Qwen models
feeding each other") is the right instinct, but at Kaidosho's actual scale
that likely means 2 model stages, not 5-7 — plus a mechanical,
non-model retrieval layer doing more of the work than any model does.**

---

## 4. PROPOSED Kaidosho-NATIVE ARCHITECTURE

### 4a. Design principle, stated once so it can be checked against later

Every stage receives ONLY the structured output of the stage before
it — never the raw reference files, never free-form prose repeated
across stages. This is the actual fix for the boundary-confusion
failure (a past incident): a drafting-stage model that never sees
PENDING.md or Troubleshooting_Journal.md directly cannot narrate their
contents, because it never received them.

### 4b. Stages (MVP scope — 2 stages, 1 optional 3rd)

```
STAGE A: VERIFY               STAGE B: DRAFT              STAGE C: REVIEW (optional, Phase 2)
(mechanical, no LLM,          (existing Structured        (adversarial pass,
 OR small model)              Brief Drafter Pipe,         separate from drafter)
                               consuming ONLY Stage
                               A's JSON output)
     |                              |                            |
     v                              v                            v
verified_facts.json  ------>  rendered MABS brief  ------>  PASS/BLOCK + reasons
```

**STAGE A — VERIFY**
- Input: the user's request (e.g. "draft a brief for X, referencing
  fashsd_config_lib.sh")
- Job: read the actual reference files (mcpo/vault), extract ONLY the
  facts relevant to the request — real function names that exist,
  real schema fields present/absent, real confirmed addresses — into a
  small structured JSON object. No drafting, no prose, no creative
  content of any kind.
- Mechanism: primarily mechanical (Python + regex/grep against known
  files, same pattern as `_mechanical_postcheck()`), falling back to a
  small model call ONLY for retrieval tasks needing real judgment
  (e.g. "which of these 3 similarly-named files is the current one").
- Output schema (draft, refine during build):
  ```json
  {
    "confirmed_functions": ["kaiju_drive_count", "kaiju_drive_field"],
    "confirmed_absent": ["kaiju_drive_threshold — does not exist, use kaiju_drive_field with a new key instead"],
    "confirmed_facts": {"vaultwarden_port": "8090", "vaultwarden_health_endpoint": "UNCONFIRMED — 4 prior wrong guesses, do not guess a 5th"},
    "source_files_read": ["fashsd_config_lib.sh", "DD_Glossary.md"]
  }
  ```
- This is the stage most directly targeting tonight's actual
  fabrication failures — a model literally cannot invent
  `kaiju_drive_threshold` if it never had the chance to reason freely
  about the codebase, only to report back what a mechanical check
  found.

**STAGE B — DRAFT**
- Input: ONLY Stage A's JSON output, plus the original request. Never
  the raw reference files.
- Job: draft the actual MABS brief content, same as the existing
  Structured Brief Drafter Pipe already does — schema-forced
  generation via Ollama's native API, GBNF grammar enforcement,
  `_mechanical_postcheck()` for circularity/address/quoting/deliverable
  checks.
- Mechanism: **this is not new code** — it's the existing
  `bakaidah_structured_brief_drafter_pipe.py` (v0.6), modified so its
  `_call_ollama()` receives Stage A's JSON as additional grounded
  context instead of (or alongside) letting the model read files
  itself. This is the smallest, lowest-risk change in this whole
  design, since 90% of the machinery already exists and is tested.

**STAGE C — REVIEW (Phase 2, not MVP)**
- Input: Stage B's rendered brief + Stage A's fact JSON.
- Job: adversarial check — does the brief's content match Stage A's
  verified facts exactly, does the format match MABS structure, does
  anything in the brief NOT trace back to a Stage A fact (a hard
  fabrication signal, since Stage B was never given anything else to
  draw from). Returns PASS or BLOCK with specific reasons, appended to
  the rendered output for Mokaima — does NOT replace Mokaima's own
  review, raises the floor the same way the Structured Brief Drafter
  already does for structure.
- Mechanism: could be a second model call (same or different model,
  adversarially-framed system prompt) or could be extended mechanical
  checks — needs its own design pass once Stages A/B are proven.

### 4c. Where this runs

**Recommendation: extend the existing Pipe, don't build a new
surface.** `bakaidah_structured_brief_drafter_pipe.py` already has the
proven machinery this needs: `_run_with_heartbeat()` (no freeze risk),
schema-forced `_call_ollama()`, `_mechanical_postcheck()`. The natural
build path is a new version of this same Pipe that runs Stage A then
Stage B (then optionally C) inside one `pipe()` generator call,
yielding progress status between stages the same way it already yields
heartbeats during generation — no new Open WebUI model entry, no new
infrastructure, no new orchestration tool. This is a deliberate,
conservative choice: reuse what's tested rather than build parallel
machinery, consistent with the "structural not instructional" pattern
already used everywhere else in Kaidosho.

**Rejected alternative**: a standalone script/service outside Open
WebUI (closer to multipi's own `pi`-CLI shape). Rejected for MVP
because it's more new surface for no clear benefit at Kaidosho's scale — 2
stages inside one Pipe is simpler than a new orchestration layer for 2
stages.

---

## 5. BUILD PHASES

### Phase 0 — Measurement (do this BEFORE writing any pipeline code)
- [x] RUN 2026-07-31 (Daikaiju AIOps 1.3), USER@dokaisho, real Ollama:
      TASK: "Draft a MABS-formatted Angkai brief for a script that
      checks Vaultwarden's health endpoint and logs the result."
      RESULT: verify (qwen3-coder:30b-a3b-q4_K_M) 8.2s, draft
      (qwen3.6:27b) 34.5s, TOTAL 42.7s across 2 stages, sequential
      model swap included in both numbers (script doesn't isolate
      swap time from generation time separately — noted as a gap
      below). CONCLUSION: latency is NOT a blocker for a 2-stage relay
      on an async brief-drafting task — well under the "plausibly
      minutes" worst case flagged in Section 3. Clears the way to
      Phase 1.
      SEPARATE FINDING, not what this run was measuring but observed
      directly: task identity held across both stages (no a past incident-style topic substitution), and Stage B did not add new
      fabrication beyond what Stage A handed it — real evidence for
      the isolation principle (Section 4a) holding at the propagation
      level. HOWEVER: Stage A itself is NOT grounded in this version of
      model_relay.py — it's a raw Ollama call with no mcpo/vault file
      access, contradicting Section 4b's actual Stage A spec ("read
      the actual reference files... primarily mechanical/grounded,
      falling back to a model call only for judgment"). Concretely:
      Stage A fabricated the Vaultwarden health endpoint as `/health`,
      presented with zero hedging as a locked precondition and
      constraint, when DD_Glossary.md's actual status is "UNCONFIRMED,
      4 prior wrong guesses, do not guess a 5th." Stage B then
      faithfully transcribed that fabrication into the final brief
      without adding to it. NET READ: this run validates the
      propagation/isolation mechanic (Stage B doesn't invent beyond
      what it's given) but does NOT validate fabrication prevention,
      because Stage A was never actually wired to ground-truth data —
      that wiring is real, not-yet-done work, tracked as a new Phase 1
      prerequisite below.
- [x] NEW (2026-07-31): before Phase 1's "write Stage A as a new
      method" item, first fix model_relay.py's verify stage (or its
      Phase-1 successor) to actually call mcpo/vault for real file
      reads — the raw-model-guess version just used is a latency
      proxy only, not a working Stage A implementation. Re-run the
      SAME Vaultwarden test task once grounded, to confirm the
      endpoint fabrication doesn't recur when Stage A can actually
      read DD_Glossary.md.
      RESULT (v0.2, 2026-07-31, same session): CONFIRMED FIXED for
      this specific fact. Stage A output health_endpoint: "NOT
      CONFIRMED in reference document" instead of guessing a path;
      Stage B preserved that uncertainty verbatim instead of
      upgrading it to a confident claim. Real evidence grounding a
      narrow claim in fetched text beats instructing a model to
      self-report honesty (the v0.1 failure mode exactly).
      TWO THINGS THIS RUN DOES NOT PROVE, flagged rather than
      overclaimed:
        1. Stage B's output is NOT a real MABS-formatted brief — it's
           prose restating Stage A's facts, no task steps/references/
           expected-files/hard-prohibitions sections. This script's
           "draft" system prompt never had MABS schema-forcing (unlike
           the real bakaidah_structured_brief_drafter_pipe.py). Proves
           fact-grounding works; does not prove a usable brief comes
           out the other end yet — separate problem, not yet solved.
        2. This is NOT the  controlled test. a past incident's
           hypothesis is specifically about PENDING.md/
           Troubleshooting_Journal.md — files with first-person
           meta-instructions addressed to Mokaima. DD_Glossary.md has
           no such content (pure reference material, written for
           Bakaidah). This run is a positive but narrow, different data
           point — doesn't confirm or weaken the doc-bleed hypothesis
           either way. The actual  test (same Vaultwarden
           prompt, PENDING.md/Troubleshooting_Journal.md specifically
           in scope, excluded vs. included) is still not run.
      Timing note (not a trend, just observed): 20.9s total this run
      (verify 7.6s, draft 13.2s) vs. 42.7s the prior run — plausibly
      just a shorter generated output, possibly partial warm-state
      carryover. Not clean enough to draw a conclusion from.
- [ ] Confirm whether a small model (3-8B class) can coexist in VRAM
      alongside the current Bakaidah (General) model, or whether it
      also forces a full eviction. Determines whether Stage A can ever
      use a model at all without paying the full swap cost every time.
- [ ] Decide, based on the above: Stage A ships as pure-mechanical
      (no model call, extending `_mechanical_postcheck()`'s existing
      pattern), or Stage A gets a real small-model call. Default to
      pure-mechanical unless Phase 0 shows a real, cheap reason not to.

### Phase 1 — MVP: Stage A (mechanical) → Stage B (existing Pipe, modified)
- [ ] Write Stage A as a new method on the existing Pipe class (or a
      small standalone function it calls) — given a request, extract
      the relevant fact JSON via direct mcpo/vault reads + regex checks,
      reusing the SAME verification logic already proven in
      `_mechanical_postcheck()`.
- [ ] Modify `_call_ollama()`'s system prompt construction so Stage B
      receives Stage A's JSON as grounded context, and is explicitly
      told it has NO other access to files — same "YOU HAVE NO ACCESS
      TO vault FILES" framing the Pipe already uses, now literally true
      instead of aspirational.
- [ ] Test against the SAME test cases already used tonight: the
       disk-usage brief (should stay clean), and a
      version of the Vaultwarden brief (the one that triggered
      a past incident) — the real test of whether stage isolation
      actually prevents the task-substitution/role-confusion failure,
      not just the fabrication failure.
- [ ] Bump Pipe version, full changelog entry, same documentation
      standard as v0.5/v0.6.

### Phase 2 — Stage C (adversarial review)
- [ ] Only after Phase 1 is live-verified (not just deployed — same
      "deployed vs verified" standard as everything else this
      session).
- [ ] Design the adversarial check specifically against Stage A's
      fact JSON (does every claim in the draft trace back to a Stage A
      fact?) rather than a generic red-team checklist copied from
      multipi — Kaidosho's actual failure mode is fabrication/substitution,
      not the service-reliability corner cases multipi's reviewer
      checks for.

### Phase 3 — Reconsider a small model for Stage A
- [ ] Only if Phase 0's measurement showed a real, cheap coexistence
      option. Otherwise Stage A stays mechanical indefinitely — that's
      a legitimate, permanent design choice, not just a placeholder.

---

## 6. WHAT THIS DOES AND DOES NOT SOLVE

**Solves**: the boundary-confusion shape of failure (a past incident) —
a drafting model that never receives PENDING.md/Troubleshooting_
Journal.md directly cannot narrate their contents, because Stage A
never hands them over, only a small fact JSON.

**Does NOT solve, and isn't trying to**: which base model is best for
Stage B's actual drafting job. That's the still-open, still-unsettled
question from tonight's Qwen3.6 A/B test. This design is orthogonal to
that question — it should make EITHER model choice more reliable, not
replace the need to answer it.

**Does NOT eliminate the need for Mokaima review or the Stop Hook
Validator.** Same as every other reliability layer built this session
— this raises the floor, it doesn't replace human/mechanical review
downstream.

---

## 7. OPEN QUESTIONS (flagged, not guessed)

1. Exact JSON schema for Stage A's output — sketched above, needs
   refinement against a handful of real brief types (FASHSD scripts,
   the Stop-Hook-Validator-class briefs, documentation briefs) before
   locking.
2. Does Stage A's mechanical extraction generalize across brief types,
   or does each brief type need its own extraction logic? (FASHSD
   briefs need function-existence checks; a Vaultwarden brief needs
   service-fact checks; these may not share one extraction function.)
3. What happens when Stage A can't find a relevant fact at all (e.g.
   a genuinely novel task with no prior grounding)? Needs an explicit
   "insufficient grounding, flag for Mokaima" path rather than silently
   passing an empty/thin JSON to Stage B.
4. Naming — "Kaiju Relay" is a placeholder. Worth a real name matching
   the established convention before this becomes a real artifact in
   vault.
5. Should this eventually extend to Angkai's side of the pipeline
   too (a verify-stage before Angkai executes), or stay scoped to
   Bakaidah's brief-drafting role only? Deliberately not scoped in this
   version — MVP is Bakaidah-side only.

---

## 8. RECOMMENDATION

Build Phase 0 (measurement) next — it's cheap, fast, and determines
whether the rest of this design is even shaped correctly (mechanical
Stage A vs. model Stage A is a real fork, not a detail).

UPDATE 2026-07-31 (Daikaiju AIOps 1.3): the prior ordering rule ("do
not start until / resolved") is RESCINDED — see
AIOPS_PENDING.md  for the full reasoning.  (which single
model runs Bakaidah) is dropped as a precondition since Relay's whole
point is that no single model should do the full job.
(document-bleed) is not dropped but demoted from gate to input: its
controlled test result shapes whether Stage A reads PENDING.md/
Troubleshooting_Journal.md raw or filtered — that's a Stage A design
decision, not a reason to delay starting. Section 4b/4c's design above
already anticipates this (Stage A extracts only a narrow fact JSON,
never hands raw file content to Stage B), so the  test result
refines Stage A's extraction scope rather than blocking it.

Previous state (2026-07-30, for the record): deprioritized to LOW
same session the standalone Phase 0 script (model_relay.py) was built
ready-to-run but not yet executed against real Ollama. That script is
still the correct next action — see Phase 0 checklist above, unchanged.

---

## 9. STAGE C (ADVERSARIAL REVIEW) -- INITIAL DESIGN DRAFT

Drafted 2026-07-31 (dosho lan, Daikaiju AIOps 1.3). Not previously
scoped at all -- Stage A (VERIFY) and Stage B (DRAFT) exist and are
tested through v0.4; Stage C does not exist yet, even as a design,
until now.

PROPOSED SCOPE (draft, needs review before being treated as locked):
Stage C's job is to adversarially re-check Stage B's OUTPUT against
Stage A's original facts JSON -- NOT against the raw reference
document again (that would just repeat Stage A's job). Three concrete
checks, all targeting real bugs found live this session:
  1. Did Stage B silently upgrade any Stage A "unconfirmed"/"NOT
     CONFIRMED" fact into a confident claim? Mechanical version
     already exists -- uncertainty_preservation_check() in
     model_relay.py v0.4. Stage C's job is to run that same check,
     plus catch anything the current keyword-based version misses.
  2. Did Stage B's REFERENCES section name anything NOT actually
     present in Stage A's fact JSON? Directly targets the SearXNG
     Condition B finding (an entire fabricated parallel library --
     kaiju-gais-package/watchdog/health_check_lib.sh, none of it real --
     invented in REFERENCES). Checkable: every REFERENCES path/
     function name in Stage B's output should trace to something
     Stage A actually asserted, not something Stage B introduced
     independently.
  3. Does the assigned brief_id collide with a real existing one?
     Ties directly to brief_id_check.py (same session, kaiju-relay/
     folder) -- Stage C is a natural integration point, and this is
     exactly the check that would have caught the  collision
     reproduced 3 times this session before it ever reached a real
     brief file.
Stage C model choice: NOT yet decided. Could reuse qwen3-coder (proven
reliable this session) or could deliberately use a DIFFERENT model for
genuine adversarial diversity -- a single model checking its own
sibling-stage output has an obvious blind-spot risk (same failure
mode, same model, might not catch its own kind of mistake). Worth
deciding once Stage C is actually being built, not assumed here.
Output: PASS/BLOCK gate, matching the state-machine pattern from
Section 3's Ch3w3y/multipi research. On BLOCK, the specific check(s)
that failed should be listed explicitly (same "mechanical, not vague"
pattern as every other check this session) -- not just a generic
"review needed."
NOT YET DONE: no code written for Stage C at all. This is scope only.
Natural integration with AIOPS_PENDING.md 's checkpoint gate
design -- Stage C BLOCK is exactly the kind of mandatory-checkpoint
trigger that design is built around (see kaiju-relay/
checkpoint_gate_design.md).

BUILT 2026-08-01 (Daikaiju AIOps 1.4): all three checks above
implemented in model_relay.py v0.5 (check 1 reuses
uncertainty_preservation_check(), check 2 is new
check_references_fabrication(), check 3 imports
brief_id_check.py's check_brief_id_collision()). Model choice landed
on the SAME model for both stages by default (not yet the deliberate-
diversity option floated above) -- see model_ab_test.py results below
for why that default is now itself in question.

REAL LIMITATION FOUND, first live run 2026-08-01 (model_ab_test.py,
qwen3-coder:30b-a3b-q4_K_M both stages): check 2 as designed ONLY
catches a fabrication Stage B adds ON TOP OF Stage A's facts -- it has
NO mechanism to catch a fabrication that originates IN Stage A itself.
Concretely: Stage A's own output invented an entire fictional config
file (/etc/kaiju-os/services.yaml plus a made-up YAML schema with
plausible Kaidosho-style fake service names) that doesn't exist anywhere in
the real reference document. Stage B faithfully cited that fabricated
path in its REFERENCES section. Check 2 compares Stage B's REFERENCES
against Stage A's raw output text -- since the fake path WAS present
in Stage A's own output, the check read it as "grounded" and passed it
clean. The whole three-check design as scoped above only ever asks
"did Stage B stay within what Stage A asserted," never "was what Stage
A asserted actually true." That second question has no check at all
right now. NOT YET DESIGNED: a Stage A self-grounding check (e.g. Stage
A's facts should themselves be substring-verifiable against the
original reference document text, the same mechanical pattern already
used for Stage B, just applied one stage earlier). Real gap, not a
hypothetical one -- caught on the first live run this scope was ever
exercised against. See AIOPS_PENDING.md  item 6 for full
A/B result.

## 10. GENERALIZATION TEST -- second task type, not yet run

Everything tested this session used ONE task family (SearXNG/
Vaultwarden health checks). Untested: does the working Stage A/B
pipeline (grounding + schema-forcing + uncertainty-preservation,
qwen3-coder for both stages) hold on a STRUCTURALLY DIFFERENT brief
type -- not another health-check script, something that exercises
different REFERENCES/EXPECTED_FILES shapes.

PROPOSED SECOND TEST TASK (ready to paste into model_relay.py's TASK
constant, needs live Ollama -- not yet run):

  "Draft a MABS-formatted Angkai brief for a script that adds ntfy
  alerting to an existing FASHSD fix script that currently has none."

Chosen deliberately because it's NOT a health-check (different shape:
modifying an existing file's behavior, not writing a new standalone
check), and there's a real, verifiable reference target for Stage A to
ground against -- the ntfy port/topic conventions already documented
in DD_Glossary.md and the wake/health-check relay pattern from
. Reference document for Stage A: DD_Glossary.md (same file
used in the original clean 3x baseline runs, known-good grounding
source).
NOT YET RUN.

---

## 11.  -- MULTI-PERSPECTIVE GROUNDING PASS (STORM-INSPIRED)

Status: SCOPED 2026-08-08 (Kaidosho Daikaiju General 1.3, dosho wan session),
NOT YET BUILT. Origin: AIOPS_PENDING.md , Priority NOW (raised
from SOON same session the operator's rationale: needed for both Bakaidah and
Angkai-facing briefs). Sourced from Stanford STORM's
perspective-guided question-asking method.

### 11a. Two distinct problems, initially conflated, now separated

Scoping conversation surfaced that "multi-perspective grounding" as
originally framed collapses two different things that need different
mechanisms:
  1. COVERAGE (STORM's actual purpose) -- did retrieval check all the
     relevant source CATEGORIES, not just whichever one the first
     query happened to surface?
  2. CONTRADICTION-CATCHING -- do two independently grounded sources
     disagree, and did anything notice?
Both are real and worth building. They turn out to be cheap together:
once 3 independently-grounded lenses exist for coverage, comparing
them for contradictions is comparison logic on already-grounded
output, not additional model calls. One retrieval pass, two outputs.

### 11b. Hard prerequisite, not just a nice-to-have ordering: self-grounding first

Multi-lens coverage on top of UNGROUNDED single-lens extraction doesn't
give 3 chances to find the truth -- it gives 3x the surface area to
fabricate, since each lens can independently hallucinate. Worse
failure modes this creates if skipped: two lenses that coincidentally
hallucinate the SAME wrong fact read as agreement (false confidence);
a real fact that disagrees with a hallucinated one reads as a
"contradiction" when one side is just wrong. Self-grounding per lens
must exist before multi-lens coverage is trustworthy.

Directly closes the gap already found and documented in Section 9:
Stage A fabricated an entire fictional config file
(/etc/kaiju-os/services.yaml) with no check catching it, because no
check today verifies Stage A's own output against the source text it
claims to have read -- only Stage B's output against Stage A's.

NOT a new model call -- reuses the SAME mechanical substring-match
already built and proven in bakaidah_citation_grounding_pipe.py's
_verify_quote() (whitespace/case-normalized substring check), applied
one stage earlier: to Stage A's claimed facts against the reference
text Stage A read, instead of to Stage B's claimed quote against a
fetched web page. Added cost of the full  design is therefore
3x retrieval/extraction (Phase 1.6), not 6x -- grounding checks are
cheap comparison logic layered on top, not additional Ollama calls.

### 11c. Design: extend Stage A, no new named stage

Per the operator's explicit call to "keep it consistent" -- no separate
"Stage A0." Stage A itself gains an internal loop over FIXED lens
categories before handing off to Stage B, same Pipe, same "extend
don't build new surface" principle used for every other piece of this
design.

Lens categories are FIXED, not model-generated. STORM normally has an
LLM brainstorm diverse personas/angles -- real hallucination risk here
(an ungrounded lens QUESTION adds cost with no safety benefit). Kaidosho's
document taxonomy is already stable, so three lenses are hardcoded
instead:
  - STATE   -- current config/fact source (state-doc,
              DD_Glossary.md, the relevant config file)
  - HISTORY -- precedent (Troubleshooting_Journal.md, past briefs of
              similar shape, INCIDENT entries)
  - RULES   -- constraint source (MABS.md, system prompt hard rules,
              INSTALL PATH RULE-class constraints)
Each lens either produces a grounded fact (self-grounding-verified per
11b) or explicitly reports "no relevant fact in this category" --
never silence. Fixed categories sidestep lens-hallucination entirely,
since only the retrieval WITHIN a category varies per request, not the
categories themselves.

### 11d. Contradiction handling

CONFIRMED (2026-08-08): contradictions between lenses ESCALATE TO
MOKAIMA, do not pass silently into Stage B's drafting context. Rationale
locked: a contradiction is two confidently-grounded, individually-true
claims disagreeing -- letting Stage B pick one unsupervised would be
inventing a new failure mode, not preventing one.

Missing-lens case (nothing found in a category) is treated differently
-- CONFIRMED: passes through as an explicit gap Stage B is told about,
does NOT block. An honest "don't know" lets Stage B hedge accordingly;
escalating on every gap would make MVP unusably high-friction for the
common case of a category genuinely having no precedent.

Contradiction detection: CONFIRMED reuse of
kaiju-relay/update_preservation_check.py rather than new logic. A
STATE-vs-HISTORY disagreement is frequently the same "stale info"
shape  already tracks (a dated update superseding an earlier
claim) -- unifying the two under one mechanism rather than building
parallel comparison logic.

### 11e. Angkai side, reframed against MABS.md Section 1

Original  wording ("applies to... Angkai pre-plan research
discipline") cannot mean new Angkai capability -- MABS.md Section 1
is explicit that Angkai is generator-only, never a
research/synthesis role; documentation/synthesis work is routed to
Mokaima direct-write (Rule 20's classification test). Reframed as: a
MABS brief-format rule, written into the brief by Mokaima/Bakaidah at
draft time, not new Angkai behavior. Candidate: MABS Rule 22 --
briefs should cite confirmation from more than one lens category in
REFERENCES where more than one genuinely applies. NOT YET DRAFTED as
an actual MABS rule; this is a placeholder pending a real rule-writing
pass.

### 11f. Build sequence -- slotted into existing phase numbering, not a parallel scheme

**Phase 1.5 -- Self-grounding check on current single-lens Stage A**
(prerequisite, build first)
- [ ] Apply _verify_quote()-style substring verification to each fact
      in Stage A's current output against the reference text it claims
      to have read.
- [ ] Test against known cases already in this doc: the Vaultwarden
      endpoint case (known-good, Section 5), the fabricated
      /etc/kaiju-os/services.yaml case (known-bad, Section 9).
- [ ] Bump Pipe/script version, full changelog entry, same
      documentation standard as v0.5/v0.6.

**Phase 1.6 -- Multi-lens coverage + contradiction escalation**
(depends on Phase 1.5 being live-verified, not just built)
- [ ] Extend Stage A to loop over the 3 fixed lens categories
      (STATE/HISTORY/RULES), each running the now-grounded single-lens
      extraction independently.
- [ ] Wire update_preservation_check.py's dated-freshness comparison
      logic to run across the 3 lens outputs; on a detected
      contradiction, escalate to Mokaima rather than passing into Stage
      B's context (per 11d).
- [ ] Missing-lens case: pass through as an explicit gap in Stage A's
      output JSON, Stage B told directly (per 11d) -- extend the
      existing fact-JSON schema (Section 4b) with an explicit
      per-category found/not-found field rather than omitting absent
      categories silently.
- [ ] Test against the same Vaultwarden/ cases, PLUS a
      deliberately constructed contradiction case (a fact that differs
      between a config file and an incident-log entry) to confirm
      escalation actually fires.

**Sequencing vs. other open work, confirmed 2026-08-08:**
  -  (quantization testing) stays sequenced AFTER  (per
    AIOPS_PENDING.md, unchanged) -- so a latency/quality change and a
    grounding-architecture change aren't conflated in the same
    measurement.
  - Stage C (Section 9, adversarial review, not yet live) waits until
     lands, so it reviews lens-reconciled output rather than
    pre-lens output -- confirmed 2026-08-08.

NOT YET SCOPED INTO AN ACTUAL BUILD SESSION -- this section is design
only, matching the same "scope now, build later" discipline used for
Stage C in Section 9 before it was built 2026-08-01.

### 11g. Phase 1.5 built, live-verified, and a real architecture correction (2026-08-08, dosho lan continuation)

Phase 1.5 (self-grounding check + reference-path injection) is DONE,
not design-only -- model_relay.py bumped v0.5 -> v0.9 same session.
Full build/bug/fix history lives in that file's own module docstring
(the authoritative changelog for this work, not duplicated here) --
summary: stage_a_self_grounding_check() built (v0.6), a real Stage A
scope-creep false-positive found and fixed at the root (v0.7),
inject_reference_path_fact() built to close the REFERENCES-path
fabrication gap found via model_ab_test.py (v0.8), a self-inflicted
ensure_ascii Unicode-escaping bug in that fix found and fixed (v0.9).
First fully clean end-to-end pipeline pass achieved after v0.9,
live against real Ollama on dokaisho.

Also confirmed live, same re-test: qwen3:30b-a3b's verify-stage
reasoning-bleed (documented above, Section 9's  cross-
reference) is severe enough on some tasks to disable the new
self-grounding check outright, not just add latency -- and this is
the model actually configured live for Bakaidah (General). No model
switch made from this single result; deferred to a proper
comprehensive comparison, see Model_Comparison_Test_Suite.md
(kaiju-relay/, new 2026-08-08).

**REAL ARCHITECTURE CORRECTION, prompted by the operator's direct question
("how come [] does not touch [Bakaidah/Angkai] in practice?"):**
Everything in 11a-11f and the v0.5-v0.9 build above happened entirely
inside model_relay.py -- a standalone script that calls raw Ollama
directly (see the top of this document, Section 1: built specifically
to prototype without touching production Bakaidah). None of it had
been ported into the actual Pipes Bakaidah runs live in Open WebUI.
This section's language ("extends Stage A," "Bakaidah's brief
drafting") was written assuming that porting would be trivial once
the logic was proven -- it wasn't examined until directly questioned.

Investigated porting into bakaidah_structured_brief_drafter_pipe.py
(the real, live Pipe closest in shape to Kaiju Relay's Stage B) --
found a genuine blocker, not a convenience problem: that Pipe's own
system prompt states "YOU HAVE NO ACCESS TO vault FILES OR ANY LIVE
SYSTEM DATA," a deliberate design choice (relies entirely on
placeholder-flagging). Self-grounding has nothing to check a fact
against if Stage A never actually reads a reference file. Porting the
check in as-is would be dead code.

**DECIDED (the operator, 2026-08-08): Option B** -- build a new, separate
Pipe rather than adding file I/O to a Pipe deliberately built without
it (Option A, rejected). New Pipe:
bakaidah_grounded_brief_
drafter_pipe.py (v0.1 -> v0.2 same session) -- the real, live home for
the Stage A/B/C pattern this section describes. Sibling to, not a
replacement for, bakaidah_structured_brief_drafter_pipe.py; gated
behind an explicit REFERENCE: <path> line in the chat message (no
guessing, matching this project's standing no-invented-paths
discipline). LIVE-TESTED on both qwen3:30b-a3b and qwen3-coder;
qwen3-coder confirmed the full v0.9 fix chain working end-to-end in
the actual deployed Pipe. v0.2 split the single model_tag Valve into
model_tag_verify/model_tag_draft after finding Stage A and Stage B
have shown different, non-overlapping model failure modes -- deployed
live, confirmed by the operator.

All 6 Bakaidah Filters were also audited for model dependency before
any Valve decision touched them (same session) -- confirmed none call
Ollama; the model-choice question raised throughout this section
stays scoped to the 3 Pipes only, never the Filters.

**STATUS NOW:** Phase 1.5 -- DONE, live-verified, now genuinely live
in Open WebUI via the new Pipe, not just proven in a standalone
script. Phase 1.6 (multi-lens coverage + contradiction escalation,
11b-11d/11f above) -- STILL NOT BUILT, remains design only. Phase 1.5
being done was the stated prerequisite for starting Phase 1.6 (11b),
not a substitute for it -- Phase 1.6 is the next real  work,
whenever it's picked up. MABS Rule 22 (11e) remains correctly
unwritten, blocked on Phase 1.6 existing.

---

## 12. GENERALIZATION TEST -- "EDIT AN EXISTING FILE" BRIEF TYPE (2026-09-19, Open Question #2)

Runner: relay_generalization_edit_test.py (this folder). Model: qwen3-coder:30b-a3b-q4_K_M, single run per case, temperature 0.3 (Stage B), run on dokaisho. Results JSON: relay_generalization_edit_results_20260919_162301.json. Two cases against REAL files: E1 = change one URL on one line of Content_Curation/content_feeds.txt; E2 = change one constant in the  staging content_curation.py. Both earlier relay cases asked for a NEW bash script.

**RESULT: DOES NOT GENERALIZE CLEANLY. Stage C BLOCKED both drafts, mostly for the wrong reasons, and the two drafts differ sharply in quality (the same model, two near-identical tasks).**

- **E1 (config line) -- wrong brief type and a broken command.** The draft turned an edit into 'create a NEW script' (EXPECTED FILES = /srv/angkai/scripts/content_feeds_modification.sh; the target file is NOT in EXPECTED FILES) while its own HARD PROHIBITIONS said 'Do not create new files or directories' (self-contradiction). The drafted command was `sed -i 's|homelab|r/homelab|https://...|homelab|r/homelab|https://.../top/.rss?t=day|'` -- `|` used as the sed delimiter while the feed line itself contains `|`, so it cannot work as written. The CONFIRM BRIEF LOADED sentence quoted the file's old line instead of naming the brief. The first-version scorer reported only 2 problems and saw 'old line verbatim: True / new line exact: True' because the lines appeared as substrings inside the broken command.
- **E2 (code constant) -- content correct, structure impaired.** OUTPUT FORMAT quoted the exact real old line and the exact new line as standalone blocks (verified verbatim, occurring once in the file), EXPECTED FILES = the target, prohibitions said 'Do not create a new file'. But: (1) **REFERENCES came out EMPTY** -- mechanical_postcheck()'s circularity rule (and rule 5 of the draft prompt) removed the target because it is also in EXPECTED FILES, so Angkai is never told to read the file first; (2) FINAL INSTRUCTION said 'The script has been written' although nothing is written; (3) the CONFIRM BRIEF LOADED sentence again quoted the old line. The first-version scorer called E2 'MECHANICALLY CLEAN' while (1) and (3) were present.
- **Stage C's self-grounding check false-positives on every edit task.** Stage A produced 'replacement_line', 'replacement_text', 'modification_type', 'change_description' facts derived from the TASK (the new content is supplied by the task, so it can never appear in the reference file). stage_a_self_grounding_check() flags them as fabrication; v0.14's echo strip missed them (the full replacement line is not similar enough to the whole task string, ratio < 0.4) and none of those key names is in _SCOPE_CREEP_KEYS. So an edit brief will ALWAYS BLOCK today -- the mandatory checkpoint fires, which is the safe outcome, but for a reason that has nothing to do with the draft's correctness.
- **Root causes are design issues, not runner bugs:** (a) rule 5 / circularity assume the deliverable is a NEW file; (b) the single MABS schema (code_sections + expected_files + 'script written and ready') and system prompt are script-oriented, so a model can read 'write a brief' as 'write a script'; (c) self-grounding assumes every fact comes from the reference, not the task.

**NOT concluded:** n=1 run per case; one model only. The E1/E2 split shows the same model is unstable across near-identical tasks, so two runs cannot rank the causes. Unverified whether qwen3:30b-a3b (Bakaidah's production tag, known reasoning-bleed) does better or worse.

**OPTIONS (the operator's call, none built):** (1) a separate EDIT brief type/schema with `edits: [{file, old_text, new_text}]` in place of code_sections, and a mechanical Stage C check that every old_text occurs exactly once in the real file (the runner's scorer is essentially that check) -- the structurally correct fix; (2) smaller patches to the existing pipeline: make the circularity rule conditional when the target is meant to be modified, exempt task-provided facts from self-grounding, fix the FINAL INSTRUCTION wording for edits; (3) do nothing now -- the relay stays a script-brief drafter and edit briefs stay hand-written or Bakaidah-drafted. Runner scorer v2 (2026-09-19, after this run) adds standalone-quote, empty-REFERENCES, confirm-line and self-contradiction checks; it has been tested only against drafts reconstructed from these two real outputs.

---

## 13. EDIT BRIEF TYPE -- BUILT 2026-09-20 (section 12, option 1; NOT yet run against a real model)

Files (this folder): relay_edit_brief.py (22,754 B), apply_edit_brief.py (6,151 B), test_edit_brief_suite.py (15,849 B, 61 offline cases, all pass). A NEW module that imports model_relay.py's tested primitives (fetch_vault_file, call_model, JSON extraction, uncertainty / brief-id / checkpoint checks); model_relay.py and the live Pipe are UNCHANGED.

**Design -- each 2026-09-19 finding is fixed by construction, not by prompt:**
- *Wrong brief type (E1 drafted a new script; its own prohibitions forbade creating files) and script-shaped boilerplate (E2's 'the script has been written', confirm line quoting file content):* the model writes ONLY title, task_description and `edits: [{old_text, new_text, reason}]` (+ optional extras). CODE writes the confirm line, the steps, the base prohibitions, the expected-files list (= exactly the target), the final instruction, the target path and the file's sha256. The steps contain no 'create' language (tested).
- *Empty REFERENCES (circularity rule):* the target is its own field and is rendered under BOTH 'read first' (REFERENCES, first) and 'edit' (EXPECTED FILES). No rule strips it.
- *Stage A self-grounding false positives (new content comes from the TASK):* Stage A may only emit keys named `excerpt_N` (verbatim lines from the file); EVERY other key is dropped -- an allowlist, not another strip-list entry, so task-derived facts (replacement_line, modification_type, ...) can never reach a grounding check. Each excerpt must occur EXACTLY in the file or Stage C warns.
- *Stage C (mechanical, any warning = BLOCK):* every old_text occurs EXACTLY ONCE in the real file (0 -> FABRICATED, whitespace-only mismatch named as such, >1 -> AMBIGUOUS), edits do not overlap, none is a no-op or empty, none is a whole-file rewrite, no triple backticks (they would break the machine block), extra references must be readable, brief-id collision, uncertainty preservation (via a shim onto the existing check).
- *Execution:* the brief carries an `EDITS_JSON` block; `apply_edit_brief.py` applies it by exact replacement with NO model in the loop: CHECK by default, `--apply` writes a backup then replaces atomically (mode preserved) and re-verifies; it REFUSES if the file's sha256 changed since drafting (unless --allow-drift), any old_text occurs 0 or >1 times, edits overlap, or an edit is a no-op. This is the deterministic executor the  'typed actions' direction calls for, in miniature.
- *Scoring:* the runner applies the drafted edits to the real file text and compares byte for byte with the intended result (`result_matches_intent`).

**Tested offline only (stubs for the models and mcpo):** applier CLI on a real temp file (check mode changes nothing, apply is exact, backup holds the original, mode preserved, drift refused, missing target refused), render -> parse -> apply round trip, the allowlist, every Stage C check, and the whole pipeline against scripted Stage A/B outputs (good run PASSES; fabricated, ambiguous, altered-excerpt, id-collision, unreadable-reference, unconfirmed-excerpt and malformed-JSON cases behave). I checked every model_relay function the module calls against the real source.
**NOT tested:** any real model output. Whether qwen3-coder copies old_text character for character, keeps a fixed delimiter like `|` intact, and stays within excerpts is exactly what the live run measures -- the E1/E2 split showed the same model is unstable across near-identical tasks. Run: `python3 relay_edit_brief.py` on dokaisho (writes relay_edit_brief_results_<timestamp>.json). Known limits: the applier needs the operator (targets may be owned by angkai; use sudo -u), and Angkai itself cannot run it under the runner.

**FIRST LIVE RUN 2026-09-20 ~01:39 EDT (the operator, dokaisho, qwen3-coder:30b-a3b-q4_K_M, n=1 per case; results relay_edit_brief_results_20260920_013937.json):** both 2026-09-19 cases PASS -- Stage C PASS with 0 warnings, the drafted edits apply cleanly to the real file and produce EXACTLY the intended file (E1: base sha256 c3bb6f98..., E2: 6575fb69...). Mokaima read the raw results: one exact edit each, target under both 'read first' and 'edit', code-generated confirm line and edit-shaped final instruction, no create-language, Stage A emitted only excerpt_1 (the allowlist had nothing to drop), about 5 s per case with the model warm. Every 2026-09-19 defect is absent. CAVEATS: n=1, and the E1/E2 split last time showed this model is unstable across near-identical tasks; both cases are the easy shape (one edit, text already unique). NEXT: relay_edit_brief_runs.py (6,916 B, 9 offline tests) runs 5 cases x N runs -- adds a TWO-EDIT case, an AMBIGUOUS-TOKEN case (homelab| occurs on several lines, so the model must choose unique context) and an IMPOSSIBLE change that must NOT yield a passing brief -- scored by applying the drafted edits to the real file and comparing with the intended file. Run: `python3 relay_edit_brief_runs.py qwen3-coder:30b-a3b-q4_K_M 5`.

**RELIABILITY RUN 2026-09-20 ~01:45 EDT (the operator, dokaisho, qwen3-coder, 5 cases x 5 runs = 25; relay_edit_brief_runs_results_20260920_014509.json): 25 of 25 OK.** Mokaima parsed the raw JSON. E1 5/5, E2 5/5, E3 (two edits) 5/5 -- two correct edits every time; E4 (ambiguous token: homelab| occurs on 4 lines) 5/5 -- the model used the unique whole line `homelab|ServeTheHome|https://www.servethehome.com/feed/` as old_text every run, not the bare token; E5 (IMPOSSIBLE change: a FEED_HOST_DELAY_SECONDS edit asked of a feeds file) 5/5 -- NO passing brief in any run: run 1 hallucinated an edit (old_text 'FEED_HOST_DELAY_SECONDS=10') that Stage C's exactly-once check caught as FABRICATED, i.e. the mechanical check stopped a REAL fabrication; runs 2-5 got NOT CONFIRMED from Stage A and produced a placeholder no-op edit, blocked as FABRICATED + NO-OP. Every normal run: Stage C PASS, 0 warnings. About 2 s per run (56 s for all 25, model warm). **HONEST LIMITS:** (1) the Stage A excerpt_N allowlist NEVER FIRED live (dropped_keys was empty in all 25 runs) -- it is proven offline only; (2) E4's five runs were identical, so at temperature 0.3 with a fixed prompt this measures near-determinism on THESE prompts, not general reliability -- a real broader test needs paraphrased requests, multi-line blocks, quotes/backslashes/tabs, a large file with edits spread out, genuinely duplicate lines, and non-ASCII; (3) one model, and the production Bakaidah tag (qwen3:30b-a3b, known reasoning-bleed) is untested. **FIX MADE the same day:** the NOT CONFIRMED path drafted a meaningless placeholder edit and reported two confusing warnings; run_edit_pipeline now stops after Stage A with a clear `NOT APPLICABLE ... no edit brief was drafted` error (result['not_applicable']=True) and never calls Stage B (one model call saved). relay_edit_brief.py 23,185 B, test_edit_brief_suite.py 16,836 B, 63 offline cases; relay_edit_brief_runs.py unchanged (an error still counts as OK for the negative case).
