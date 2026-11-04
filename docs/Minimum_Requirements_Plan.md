╔══════════════════════════════════════════════════════════════════════╗
║  KAIJU SPINE + DAIKAIJU AIOPS — MINIMUM REQUIREMENTS PLAN               ║
║  Version: 1.0 | Created: 2026-07-24 (Daikaiju AIOps)                ║
║  Covers: current (Kaiju Spine) + forward-looking (Daikaiju AIOps) floor ║
╚══════════════════════════════════════════════════════════════════════╝

This document exists because Kaiju Spine and Daikaiju AIOps have two
DIFFERENT KINDS of minimum requirement, and conflating them would
undersell one or oversell the other:

  - Kaiju Spine's floor is mostly HARDWARE — already fully documented in
    Hardware_Compatibility_Matrix.md (4 VRAM tiers, watcher-node specs,
    network requirements). That document is NOT duplicated here.

  - Daikaiju AIOps's floor, once you actually work through its 9 gaps
    and 7 build phases, turns out to be mostly NOT hardware. Every gap
    that's genuinely new infrastructure (task queue, audit log,
    agent-to-agent bus) is lightweight — a JSON file, a log file, an
    ntfy topic. The real floor Daikaiju AIOps adds is a RELIABILITY
    floor: whether the execution agent and the guardrails around it
    are trustworthy enough to run with less human review than Kaiju Spine
    alone requires. This document exists to make that floor explicit,
    because "buy a bigger GPU" is not the fix for it.

Both floors matter. Neither should be assumed as a stand-in for the other.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 1 — KAIJU SPINE FLOOR (reference only, full detail elsewhere)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

See Hardware_Compatibility_Matrix.md for the complete, current version
of this. Summary only, so this document is self-contained enough to
skim:

  - AI/execution node: 4 VRAM tiers (≤8GB / 8-16GB / 16-24GB / 24GB+),
    each with an RAM/CPU/storage floor — see Model_Selection_Guide.md
    for which models map to which tier.
  - Watcher/services node (two-node topology only): as low as a pi-node
    4GB model, no GPU needed.
  - Software floor (not yet centrally listed anywhere — collected
    here for the first time): Docker + Docker Compose, Ollama, git,
    systemd (Debian/Ubuntu family — see Distro_Portability_Design.md
    for why this is a real constraint, not a formality), ufw, `yq`
    (kislyuk/yq specifically, per the -r flag fix — see
    Config_Driven_FASHSD_Design.md and the 2026-07-23 test-suite
    findings for why the OTHER popular `yq` variant silently breaks
    things), `wakeonlan` (two-node topology only, on the watcher node),
    ntfy (self-hosted or ntfy.sh account) if FASHSD alerting is enabled.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 2 — DAIKAIJU AIOPS: THE HARDWARE/SOFTWARE THAT ACTUALLY CHANGES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Walking through Daikaiju_AIOps.md's 9 gaps and asking "does this
change the floor, and if so how":

  Gap 1 (Orchestration layer) — Kaidosho's own recommendation is the custom
    shell+ntfy+vault approach, not a framework. If that recommendation
    holds, NO new floor. See the CONDITIONAL note below for what
    changes if CrewAI/LangGraph gets adopted instead.

  Gap 2 (Agent memory / queryable state) — Graphify already runs
    (Kaiju Spine Layer 4). No new floor; this gap is about write access,
    not new infrastructure.

  Gap 3 (Task queue, AGENT_QUEUE.json) — a JSON file. No floor change.

  Gap 4 (Rollback/safety gate, snapshot-before-every-action) — REAL
    floor change, easy to miss: today's snapshots trigger
    only on watchdog-detected failures, a handful of times a week at
    most. If every autonomous destructive action requires a fresh
    snapshot first (as Gap 4 specifies), snapshot frequency could
    increase by an order of magnitude once Phase 5 is live. Storage
    floor should account for this — see STORAGE GROWTH below, not
    just the fixed "day one" numbers in Hardware_Compatibility_Matrix.md.

  Gap 5 (Agent-to-agent bus via ntfy) — needs a reliable ntfy instance,
    already a Kaiju Spine software-floor item (see Part 1). No NEW
    software requirement, but reliability matters more once agents
    depend on it for coordination, not just human alerts — an ntfy
    outage becomes a coordination failure, not just a missed
    notification. Worth a dedicated uptime check once Phase 2 is live
    (not yet planned — flagging here as a gap in the gap list itself).

  Gap 6 (Audit log, AGENT_LOG.jsonl) — append-only log file. Storage
    floor grows over time, same category as Gap 4's snapshots — see
    STORAGE GROWTH below.

  Gap 7 (Evaluation pipeline / mechanical validator) — compute cost is
    trivial (a validator script runs in seconds). The floor this gap
    actually sets is a PROCESS one: Phase 5 (autonomous queue
    consumption) should not be considered safe to enable until this
    gap is closed, regardless of how capable the hardware is. See
    THE RELIABILITY FLOOR below — this is the most important finding
    in this document.

  Gap 8 (Angkai reliability / MABS) — see THE RELIABILITY FLOOR below.

  Gap 9 (Orchestration framework decision) — CONDITIONAL floor change,
    only if CrewAI or LangGraph gets adopted instead of the custom
    approach. Both are Python frameworks with real dependency
    footprints (LangGraph especially, given its state-graph execution
    model) — this would add a dedicated Python environment requirement
    and additional RAM overhead for the orchestration process itself,
    on top of whatever's already running for Ollama/Docker. Kaidosho's own
    recommendation is to avoid this unless the custom approach hits a
    real limit — treat this as a possible FUTURE floor increase, not
    a current one.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE RELIABILITY FLOOR (the actual point of this document)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Daikaiju AIOps' entire value proposition — Phase 5's "you approve the
plan, agents execute, you're notified on completion or failure, not
every step" — depends on trusting execution output without a human in
the loop for every action. That trust has a floor, and this session
produced real, first-party evidence about where it currently sits.

WHAT HAPPENED (2026-07-24, this session): Bakaidah (Qwen 32B, general-
purpose, NOT a coder-specialized model) was asked to draft two
relatively simple MABS-formatted briefs — generalizing existing,
proven fix scripts by swapping hardcoded values for config-driven
lookups, following patterns already demonstrated in reference files it
was told to read. Both briefs required 3 rounds of human review to
reach correctness. The specific failures: fabricating function names
that don't exist in files it had just been told to read, and — even
after being given the correct fix for one occurrence — not
re-scanning its own output for the SAME fabricated symbol reused
elsewhere in the same script. A dedicated self-check instruction
(Bakaidah v2.5's OUTPUT CONSTRAINT 8) measurably helped but did not
eliminate this — Mokaima's independent review still caught real bugs
in every single round, even under v2.5.

WHAT THIS MEANS FOR THE FLOOR:

  1. Model capability floor: this failure happened on a 32B-class
     model doing a genuinely modest task (2 straightforward function
     substitutions, patterns already demonstrated). This is not
     evidence that a bigger/better model would be immune — it's
     evidence that AT LEAST this capability level still needs human
     review for MABS-brief-drafting tasks. Daikaiju AIOps' Phase 5
     (autonomous, unreviewed execution) should not be attempted with
     a smaller/weaker model than what's already documented as the
     Kaiju Spine floor for the execution role (Model_Selection_Guide.md
     Tier 3, qwen3-coder:30b-a3b-class) — and even that tier is NOT
     confirmed sufficient for unreviewed autonomy, only for reviewed
     drafting. This is an open question, not a settled floor — see
     OPEN QUESTIONS below.

  2. Process floor, not just model floor: Gap 7's mechanical validator
     (deterministic, script-based — can literally check "does this
     function name appear in the file it claims to read from") is a
     structural fix for exactly the failure class observed. MABS
     Section 8's own design principle ("structural not instructional")
     applies here directly: a bigger model reduces HOW OFTEN this
     happens; the validator is what actually CATCHES it when it still
     does. Phase 5 should be gated on Gap 7 being built and tested,
     not on hardware specs alone — a Tier 4 (24GB+) execution model
     without the validator is not obviously safer than a Tier 3 model
     with it.

  3. Practical implication for the requirements plan: "minimum
     requirements to run Daikaiju AIOps" is not fully answerable by a
     hardware table the way Kaiju Spine's is. Part of the honest answer
     is "Gap 7 and Gap 8 must be built and demonstrated reliable
     first" — a software/process prerequisite that no amount of
     additional RAM or VRAM substitutes for.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STORAGE GROWTH (distinct from Hardware_Compatibility_Matrix.md's
fixed day-one storage floor)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Two Daikaiju AIOps components accumulate data over time in a way
Kaiju Spine alone does not: Gap 4's per-action snapshots and Gap 6's
AGENT_LOG.jsonl. Neither has a real growth-rate number yet — Kaidosho hasn't
run Phase 5 long enough to measure it (Phase 5 isn't built). Flagging
as a genuine open question rather than guessing a number: once Phase
5 is live, measure actual snapshot/log growth over a real week of
autonomous operation before setting a hard storage-floor number here.
A retention/rotation policy (e.g. "keep 30 days of snapshots, prune
older") will likely be necessary regardless of raw disk size — same
pattern Kaidosho already uses for the daily webui.db backup (7-day
retention) and pi-node health reports.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OPEN QUESTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. Is Tier 3 (qwen3-coder:30b-a3b-class) actually sufficient for
     UNREVIEWED autonomous execution once Gap 7's validator exists, or
     does Phase 5 need a higher model floor regardless? Not answerable
     without actually building Gap 7 and running real trials — flag
     for revisit once that exists, don't guess a number now.
  2. Snapshot/log storage growth rate under real Phase 5 operation —
     unmeasurable until Phase 5 exists. Revisit once it's live.
  3. Does the ntfy agent-to-agent bus (Gap 5) need its own uptime
     monitoring once agents depend on it for coordination, not just
     human alerts? Currently not in Daikaiju_AIOps.md's own gap/phase
     list — worth adding there, not just here.
  4. If CrewAI/LangGraph ends up adopted (Gap 9), what's the actual
     RAM/dependency floor for that framework specifically? Not
     researched yet — Kaidosho's stated position is to avoid this path
     unless the custom approach hits a real limit, so this is
     deliberately not pre-researched.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RELATIONSHIP TO OTHER DOCS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  - Hardware_Compatibility_Matrix.md — the full current Kaiju Spine
    hardware floor, referenced not duplicated in Part 1 above
  - Model_Selection_Guide.md — the tier definitions Part 1 and the
    reliability-floor discussion both reference
  - Daikaiju_AIOps.md — the 9 gaps and 7-phase build path this
    document walks through; THE RELIABILITY FLOOR section should be
    read before Phase 5 is attempted, and Gap 5's own listing should
    be updated to mention the ntfy-uptime open question above
  - MABS.md Section 8 — the "structural not instructional" principle
    this document's reliability-floor argument depends on
  - PENDING.md — Stop hook / mechanical validator entry (Gap 7's
    concrete build) and git snapshot backstop entry (part of Gap 4)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STATUS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

v1.0. Part 1 (Kaiju Spine floor) is stable, references an already-tested
document. Part 2 (Daikaiju AIOps floor) is necessarily forward-looking
and will need real revision once Gaps 4, 5, 7 actually get built —
several numbers here are explicitly flagged as unmeasurable yet rather
than guessed. Revisit this document at each Daikaiju AIOps phase
milestone, not just on a fixed schedule.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
END OF MINIMUM REQUIREMENTS PLAN v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
