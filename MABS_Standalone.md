╔══════════════════════════════════════════════════════════════════════╗
║  MABS — GOVERNED AGENT BRIEF STANDARD (STANDALONE)                 ║
║  Extracted from Kaidosho Daikaiju (Kaidosho) — Daikaiju AIOps Guardrail Layer║
║  Version: 1.0 (standalone) | Extracted: 2026-07-22                 ║
║  Source: Kaidosho's internal MABS.md v2.0 (Mokaima Angkai Brief Standard)║
╚══════════════════════════════════════════════════════════════════════╝

This is a portable version of Kaidosho's internal governance protocol for
directing a local/execution LLM agent safely. It generalizes the roles
and tooling so someone outside Kaidosho can adopt the same discipline for
their own planning-agent + execution-agent pipeline, regardless of which
specific models or tools they use.

This document is the reusable protocol, stripped of the reference
deployment's infrastructure-specific details and lesson log.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHY THIS EXISTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If you're running a local/smaller LLM as an execution agent (writing
scripts, generating configs, touching infrastructure) under direction
from a planning agent (you, or a larger/cloud model), you will run into
a predictable set of failure modes: the execution agent ignores
instructions under context pressure, invents plausible-looking but wrong
content, skips safety checkpoints, or does things nobody asked for.

This is NOT a reflection of a "bad" model. It's a structural property of
how these models behave when given ambiguous, lengthy, or multi-step
instructions in prose form. MABS is a set of rules for how to WRITE
instructions ("briefs") to an execution agent that route around this
weakness, discovered through repeated real-world failures and fixes.

The core insight (Section 4 below) is the most important part of this
document. Everything else is the specific rules that follow from it.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 1 — THE TWO-AGENT MODEL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Planning Agent** (in Kaidosho: Mokaima / Claude Desktop)
  - Writes structured briefs following the rules in Section 3
  - Reviews all execution-agent output before anything is deployed
  - Owns the "source of truth" — infrastructure details, file paths,
    expected formats — and embeds them into every brief
  - Never assumes the execution agent can discover missing context

**Execution Agent** (in Kaidosho: Angkai / Claude Code + local LLM)
  - Generates content (scripts, configs, files) from a brief
  - Does NOT deploy, execute what it generates, or make infrastructure
    changes directly — it produces output for review
  - Treated as a generator with known reliability limits, not as an
    autonomous operator

**Human** (you)
  - Approves plans, executes what's been reviewed, makes final calls
  - The only party with actual system access to run/deploy anything,
    unless you've explicitly built and tested an autonomous execution
    path (a significant additional trust step beyond what MABS covers)

Why split roles instead of one agent doing everything: a single model
context that both plans AND executes tends to blur its own guardrails —
the same session that decided "don't do X" can talk itself into doing X
under pressure to finish the task. Splitting review into a separate
agent/session enforces an actual checkpoint, not just a self-imposed one.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 2 — THE PIPELINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Planning agent writes a brief (see Section 3 format) and saves it
   somewhere the execution agent can read it.
2. You launch the execution agent with a SCOPED toolset (see Section 5
   — do not launch with unrestricted tool access).
3. You hand the execution agent the brief.
4. Execution agent reads the brief, generates output, and either prints
   it or writes it to a STAGING location only — never a live/production
   path.
5. Execution agent explicitly signals it's done and stops. It does not
   proceed to deploy, execute, or clean up on its own.
6. Planning agent reviews all output against the brief.
7. Planning agent fixes anything wrong, or sends it back for another
   pass.
8. You deploy from staging manually, once review is complete.

The execution agent never deploys. The planning agent reviews everything.
Always. No exceptions, regardless of how "obviously correct" the output
looks or how much time it would save to skip the step.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 3 — BRIEF FORMAT RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RULE 1 — LENGTH CEILING. Smaller/local models degrade badly (silent
  truncation, garbage output, or context-window overflow) on long
  instruction prose. Keep INSTRUCTION text (not embedded reference
  content — that doesn't count) under roughly 200 lines / 400 words. If
  a task needs more, split it into phases delivered across sessions.

RULE 2 — EMBED EVERYTHING. Never make the execution agent discover
  information. All specifics — paths, names, ports, credentials,
  expected formats — go in the brief verbatim. Never say "check X to
  find Y"; state what Y is.

RULE 3 — ONE OUTPUT PER PHASE. Each phase produces exactly one artifact.
  Execution agents handle single, well-scoped outputs far more reliably
  than juggling several at once.

RULE 4 — USE CONSISTENT, EXPLICIT PATHS. Whatever your execution
  environment's root/working directory is, state the exact target path
  the same way in every brief. Don't rely on the model to resolve a
  relative reference correctly — it often won't.

RULE 5 — MINIMIZE TOOL-CALL ROUND TRIPS DURING EXECUTION. If your
  execution agent has a noticeable delay after a tool call returns (e.g.
  an MCP read), that delay can itself trigger the model to lose its
  place or exit early. Prefer embedding reference content directly in
  the brief over having the agent fetch it mid-task. If a lookup is
  unavoidable, limit it to one, at the very start.

RULE 6 — HARD PROHIBITIONS IN EVERY BRIEF (adapt to your environment,
  but always include an explicit list). Example:
    ✗ Do not run destructive or system-level commands (install
      packages, restart services, modify permissions) unless the brief
      explicitly says so
    ✗ Do not execute anything you generate
    ✗ Do not write files outside the designated staging path
    ✗ Do not improvise paths, names, or values — use only what's given
    ✗ If uncertain: stop and say so. Do not guess.

RULE 7 — PAUSE POINTS BETWEEN EVERY PHASE. Use a consistent, unambiguous
  marker, e.g.:
    ⛔ PAUSE — [what was produced]. STOP and present this output now.
    Do not proceed to the next phase in this response.
  See Rule 18 (below) for why phrasing matters more than it seems like
  it should.

RULE 8 — ONE DELIVERABLE PER BRIEF. Multiple supporting files for a
  single deliverable is fine. Bundling unrelated tasks into one brief
  is not.

RULE 9 — TELL THE AGENT HOW TO END. The final line of every brief
  should give an explicit stop instruction and completion phrase, e.g.
  "When complete, say: 'Ready for review.' Then stop. Do not deploy,
  execute, or copy anything."

RULE 10 — REFERENCE MATERIAL GOES INLINE, NOT BY PATH. If the agent
  needs to match an existing pattern/format, paste the relevant section
  directly rather than pointing at a file to go read.

RULE 11 — SEQUENCE STEPS EXPLICITLY. NEVER IMPLY ORDER. If step B
  depends on step A, say so directly with numbered sub-steps. Do not
  assume logical order is obvious to the model.

RULE 12 — SPECIFY THE EXACT COMMAND FOR EVERY NON-TRIVIAL SECTION. A
  section header with no command given invites the model to invent one.
  When in doubt, paste the literal command.

RULE 13 — STATE PERMISSIONS NEGATIVELY, NOT POSITIVELY. "sudo is
  available" gets read as "use sudo everywhere." Say what's NOT allowed
  and under what constraint the script runs, rather than what's possible.

RULE 14 — VERIFY ENVIRONMENT ASSUMPTIONS BEFORE WRITING ANY BRIEF THAT
  TOUCHES LIVE INFRASTRUCTURE. Two common traps:
  (a) Assuming a directory/resource already exists with correct
      ownership/permissions without verifying — include an explicit
      setup step if there's any doubt.
  (b) Missing shared-resource dependents — if the brief restarts or
      modifies something shared (a network namespace, a shared volume,
      a shared process), check what else depends on it FIRST, and
      require dependents to be handled together, not independently.
  This is a planning-agent responsibility before the brief is even
  written — the execution agent will faithfully build whatever the
  brief specifies, so an unverified assumption becomes a live bug
  regardless of how well it's executed.

RULE 15 — NEVER MAKE THE AGENT CROSS-REFERENCE TWO TABLES. Pre-join
  them into one flattened table, or express the lookup as explicit
  if/case blocks the agent copies verbatim. Execution agents reliably
  fail at holding two tables in working memory and joining them
  correctly under their own initiative — they collapse both into
  invented, generic values instead.

RULE 16 — WHEN EXTENDING EXISTING CONTENT, PASTE THE FULL CURRENT FILE.
  PRESERVE IT EXACTLY. ADD ONLY. A prose description of an addition
  ("add a check for X") without the actual current file as an anchor
  invites the model to substitute a generic pattern from its training
  data instead of extending what's actually there. State explicitly:
  preserve as-is, add only after [marker], no restructuring unless
  explicitly instructed.

RULE 17 — NAME EVERY EXPECTED FILE UP FRONT. A permission scoped to "the
  staging directory" is not the same as a closed list of expected
  files — the model will happily invent helper files, configs, or docs
  it decides are needed, all technically within the allowed path. State
  the exact file list up front ("this brief produces exactly N files:
  ...") and prohibit anything beyond it explicitly. Check the output
  file count against the list during review.

RULE 18 — STRENGTHEN PAUSE POINTS: EXACT STOP PHRASING, AND PREFER
  DELIVERING MULTI-PHASE BRIEFS AS SEPARATE MESSAGES. An in-document
  pause marker competes with the model's drive to finish the document
  it's reading — it's a suggestion within the text, not a hard stop in
  the environment. "STOP and present this output now" (telling the
  model what to do THIS turn) tests more reliably than "type X to
  proceed" (asking it to wait for something outside its own turn). For
  complex or high-risk briefs (3+ phases, anything infrastructure-
  touching), the strongest fix is structural, not phrasing: deliver
  phases as SEPARATE messages, so the next phase does not exist for
  the model to see or act on until you actually send it.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 4 — THE CORE DESIGN PRINCIPLE: STRUCTURAL NOT INSTRUCTIONAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This is the single most important idea in this document. Everything
else follows from it.

Execution agents follow what is STRUCTURALLY TRUE of their environment
(a file literally pasted in front of them, a phase they haven't been
sent yet, a case block they can copy verbatim) far more reliably than
something they merely read as an INSTRUCTION to remember and obey (a
rule stated in prose, a table they have to cross-reference themselves,
a pause marker they're asked to respect on their own initiative).

Rules 15-18 above are four instances of one design move, not four
separate patches:
  - Cross-table lookups → pre-joined rows / case blocks to copy
  - "Don't restructure" → the literal file pasted, extend after a marker
  - "Don't invent files" → a closed, checkable list
  - "Remember to pause" → the next phase literally doesn't exist yet

**Practical test for any brief you write:** for each requirement, ask —
"if the agent ignores this instruction, does something in its actual
environment still stop it, or does the whole thing depend on it choosing
to comply?" If the answer is "depends on compliance," look for a way to
make it structural instead.

This principle generalizes beyond any specific model or tool. It's the
part of MABS worth adopting even if none of the specific rules above fit
your exact setup.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 5 — LAUNCH / SCOPING GUIDANCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Whatever tool you use to run your execution agent, launch it with the
MINIMUM tool/permission set it needs for the task — not full access.
Kaidosho's concrete experience: launching Claude Code with unrestricted MCP
tool access (hundreds of tool definitions) caused the model to silently
exit with zero output, because the flood of tool definitions overwhelmed
its context before it even started the task. Restricting to 2-3 named
tools fixed this entirely, as a side effect of solving a completely
different-looking problem. Lesson: broad access isn't just a safety
concern — bloated tool surfaces measurably degrade smaller models'
ability to function at all. Scope tightly for both reasons.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 6 — BRIEF TEMPLATE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

════════════════════════════════════════
[TASK-ID] — [TASK NAME IN CAPS]
Brief for: [execution agent name/description]
Written by: [planning agent] | YYYY-MM-DD
Protocol version: [your MABS version]
════════════════════════════════════════

HARD PROHIBITIONS — no exceptions, ever:
  ✗ [adapt Rule 6 list to your environment]
  ✗ Do not create any file not explicitly named below
  ✗ If uncertain: STOP and say so. Do not guess.

────────────────────────────────────────
CONFIRM BRIEF LOADED
────────────────────────────────────────
Before doing anything else, state:
  "[TASK-ID] loaded. Task: [task name]. [N] phases."
Then proceed to Phase 1.

────────────────────────────────────────
TASK
────────────────────────────────────────
[One paragraph — what does this produce, what problem does it solve.
No background history, just the task.]

────────────────────────────────────────
ENVIRONMENT (use exactly — do not discover)
────────────────────────────────────────
[Every specific the agent needs: paths, names, ports, formats, values.
Everything needed to avoid guessing.]

────────────────────────────────────────
EXPECTED FILES (closed list — see Rule 17)
────────────────────────────────────────
This brief produces exactly [N] files:
  1. [filename] — [purpose]
  2. [filename] — [purpose]
Do not create any file not listed here.

────────────────────────────────────────
OUTPUT FORMAT / PATTERN TO MATCH
────────────────────────────────────────
[Paste exact lines to replicate, if matching an existing pattern.]

────────────────────────────────────────
EXECUTION ORDER (if steps are dependent — see Rule 11)
────────────────────────────────────────
  Step 1: [first thing]
  Step 2: [depends on step 1]
[Omit if order isn't critical.]

────────────────────────────────────────
PHASE 1 — [PHASE NAME]
────────────────────────────────────────
Output file: [exact path]

[Exact requirements. Paste every non-trivial command per Rule 12.]

⛔ PAUSE — [what was produced]. STOP and present this output now.

────────────────────────────────────────
PHASE 2 — [PHASE NAME]
────────────────────────────────────────
[repeat pattern per phase]

────────────────────────────────────────
FINAL INSTRUCTION
────────────────────────────────────────
When complete, say: "[TASK-ID] complete. [N] files ready for review."
Then stop. Do not deploy, execute, or copy anything.

════════════════════════════════════════
END TEMPLATE
════════════════════════════════════════

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 7 — ADOPTING THIS FOR YOUR OWN PIPELINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Identify your planning agent and execution agent (may be the same
   underlying model in different sessions, or genuinely different tools
   — what matters is the separation of write vs. review).
2. Scope the execution agent's tool/permission access to the minimum
   needed (Section 5).
3. Use the brief template (Section 6) for any non-trivial task.
4. Keep a lessons-learned log for YOUR pipeline. The 18 rules above came
   from repeated real failures in one specific setup (Kaidosho/Angkai,
   qwen3-coder via Ollama) — your execution agent will fail in its own
   particular ways. Expect to add rules, not just use these as-is.
5. Revisit Section 4's core test regularly: for anything going wrong,
   ask whether it was instructional (fixable by rephrasing) or
   structural (needs an actual environmental constraint, not stronger
   wording).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NOT INCLUDED IN THIS STANDALONE VERSION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Kaidosho's internal MABS.md v2.0 additionally contains: the full 18-entry
failure-mode catalog with specific incident writeups, a session-by-
session lessons-learned log, and full version history. Those are kept
reference-deployment-specific (they reference real Kaidosho infrastructure, incident dates, and
Angkai/qwen3-coder specifics) rather than generalized here — the value
for an external adopter is the RULES and the PRINCIPLE (Sections 3-4),
not Kaidosho's specific incident history. Build your own failure-mode log as
you go; that's the point of Section 7 step 4.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
END OF STANDALONE MABS v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
