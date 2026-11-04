╔══════════════════════════════════════════════════════════════╗
║  CREATED: 2026-07-20  │  Kaidosho (DoSho Daikaiju)  │  v1.0       ║
║  Update cycle: SESSION                                        ║
║  Product Document — Daikaiju AIOps                           ║
╚══════════════════════════════════════════════════════════════╝

# DAIKAIJU AIOPS
## Autonomous Agentic Infrastructure Operations

**Version:** 1.1
**Created:** 2026-07-20 (Kaidosho Daikaiju General)
**Status:** Phase 0 implementation, substantially in progress (updated
2026-09-24) -- the A2A gateway/orchestration automation is
built and has reached full autonomous operation at least once, though
its checkpoint is currently reset to a supervised state pending
re-graduation; day-to-day operation still runs at manual-trigger
maturity. Daikaiju AIOps is the product and first shippable package;
Kaiju GAIS is the substrate it owns and runs on;
Kaiju Spine is reserved for a second, later, separately-releasable
package built on both (downstream of this doc, not a prerequisite --
see Phase 7 "Kaiju Spine Packaging" below and Kaiju_Spine.md's own
"RELATIONSHIP TO DAIKAIJU AIOPS" section)
**Priority:** HIGH
**Related:** Kaiju_GAIS.md describes Kaiju GAIS, the substrate layer
this product owns and runs on (see "RELATIONSHIP TO KAIJU GAIS" below)

---

## ONE-LINER

*"Kaiju GAIS with a brain — autonomous agents that plan, execute, self-heal,
and remember, closing the loop without a human in the middle."*

---

## WHAT DAIKAIJU AIOPS IS

Daikaiju AIOps is the product. Kaiju GAIS is the self-healing
substrate it runs on -- not a separate product, one system (2026-08-06,
). Where Kaiju GAIS provides the substrate (self-healing,
memory, hardware, local AI hosting), Daikaiju AIOps provides
everything with agent reasoning in it: the autonomy itself.

Daikaiju AIOps owns two layers outright, not as future work but as
built-and-running-today components (moved here from Kaiju GAIS's own
layer list as of  -- they were always agent-reasoning
territory, not substrate):

**Orchestration Layer** (internal name: Kaidosho Pipeline / Kaiju Stack) --
the governed multi-agent workflow. Human intent -> structured brief
-> local LLM reasoning -> autonomous execution, with defined handoff
points, pause-and-approve checkpoints, and failure modes. Components:
Mokaima (planning), Bakaidah (reasoning), Angkai (execution), MABS
(governance protocol), the session keyword system. Built and running
today at MANUAL-TRIGGER maturity -- see Gap 1 below for what
AUTONOMOUS maturity still needs.

**Guardrail Layer** (internal name: MABS) -- the rules, pause points,
install-path restrictions, session formats, and failure-mode catalogs
that make autonomous execution trustworthy instead of terrifying.
Components: MABS.md, the install path rule, the session format rule,
the Angkai launch command, the Mokaima-generates/Angkai-executes/
Mokaima-reviews pipeline rule. Almost nobody doing agentic AI has this
formalized -- the most defensible, differentiated part of the whole
product.

Beyond those two, the agents themselves can:

- Detect infrastructure problems and fix them without being asked
- Pick up tasks from a queue and execute them end-to-end
- Coordinate with each other without a human acting as the bus
- Learn from past failures and improve over time
- Alert humans only when something is truly beyond their capability

---

## THE CURRENT STATE vs THE TARGET STATE

### Current State (Daikaiju AIOps at manual-trigger maturity)
```
You → Mokaima (plan) → You → Angkai (execute) → You → Mokaima (review)
```
Every handoff requires your manual intervention. You are the relay
between agents -- copy/paste brief, copy/paste result. The system is
governed and documented, and orchestration genuinely runs, but you are
still the wire between every step.

### Target State (Daikaiju AIOps at full autonomous maturity)
```
You approve the plan → Agents execute → You receive result or alert
```
You define intent. The system handles execution, verification, and
remediation. You are notified on completion or failure, not every step.

---

## THE AGENT ROSTER

### Mokaima (Planning/Documentation Agent)
- **Platform:** Claude Desktop
- **Role:** Strategic planning, brief generation, vault writes, sync, review
- **Current status:** Operational ✅
- **Gap for AIOps:** Cannot initiate tasks autonomously — human triggers required
- **AIOps upgrade:** Mokaima receives task queue items and generates briefs
  automatically on a schedule or event trigger, without waiting for you

### Angkai (Execution Agent)
- **Platform:** Claude Code → qwen3-coder:30b-a3b-q4_K_M via Ollama
- **Role:** Script generation, file writes to vault staging, execution
- **Current status:** Operational ✅ (with known reliability limitations)
- **Gap for AIOps:** Path invention, context drift, pause-point skipping,
  invented files — not yet trustworthy for fully autonomous execution
- **AIOps upgrade:** MABS v2.0 "structural not instructional" pipeline
  (phase-by-phase delivery, inline anchors, echo-back step, mechanical validator)

### Bakaidah (Reasoning/Conversation Agent)
- **Platform:** Qwen 32B via Open WebUI (ai.example.com)
- **Role:** Conversational reference, drafting, research, Graphify queries
- **Current status:** Operational ✅
- **Gap for AIOps:** No way to initiate actions — can only respond to queries
- **AIOps upgrade:** Bakaidah receives structured queries from the orchestrator
  and returns structured recommendations Mokaima can act on

### Rodkai (Remote Wake/Health Agent) — PLANNED
- **Platform:** ntfy.sh private topic + pi-node watcher script
- **Role:** Remote wake dokaisho, trigger health checks, relay results
- **Current status:** Brief written + approved, not yet built
- **AIOps role:** First autonomous inter-agent relay in the stack — Rodkai
  is the prototype for agent-to-agent communication via ntfy

---

## THE 9 GAPS — WHAT DAIKAIJU AIOPS NEEDS TO BUILD

### Gap 1 — Orchestration Layer (manual-trigger -> autonomous maturity)
**Problem:** Orchestration exists today and genuinely runs -- Mokaima
plans, Bakaidah reasons, Angkai executes, MABS governs. But every
handoff between agents requires you as the relay (copy/paste brief,
copy/paste result). The gap is AUTONOMOUS maturity: agents publishing
to and consuming from a queue/bus directly, no human as messenger for
routine steps.
**Options:**
  - CrewAI: role-based multi-agent orchestration, 52k GitHub stars, streaming
    tool call events (Jan 2026). Best for human-readable agent role definitions.
    Trade-off: abstractions work against you at production complexity.
  - LangGraph: graph-based, stateful, conditional logic, pause-at-checkpoints.
    Best for complex branching and human-in-the-loop approvals.
  - Custom lightweight orchestrator: shell script + ntfy + vault task queue.
    No framework dependency. Highest control, lowest abstraction.
**Kaidosho recommendation:** Start with the custom lightweight approach — it matches
  the existing stack (shell scripts, ntfy, vault) and avoids framework lock-in.
  Evaluate CrewAI or LangGraph when the custom approach hits limits.

### Gap 2 — Agent Memory Between Autonomous Runs
**Problem:** vault is manual memory — Mokaima reads it when you tell it to.
  An autonomous agent needs structured, queryable state it can access
  without human-mediated sync.
**Current partial solution:** Graphify (graph.example.com) — 110 nodes,
  195 edges, queryable via Bakaidah. This is the prototype for machine-queryable
  vault. Gap is that writes still go through Mokaima manually.
**Next step:** Define a structured agent-readable state format (JSON sidecar
  alongside state-doc) that autonomous agents can read and write directly.

### Gap 3 — Machine-Readable Task Queue
**Problem:** PENDING.md is human-managed. An autonomous agent needs a task
  queue it can pop from, execute, and mark done without you touching it.
**Design:**
  - New file: vault root/AGENT_QUEUE.json
  - Format: array of tasks with status (queued/running/done/failed),
    priority, assigned agent, brief path, result path
  - Mokaima writes to AGENT_QUEUE.json when you approve a task
  - Angkai reads from AGENT_QUEUE.json at execution time
  - Result written back to AGENT_QUEUE.json on completion
  - PENDING.md remains human-facing; AGENT_QUEUE.json is agent-facing
**Prerequisite:** MABS v2.0 must be stable before autonomous queue consumption

### Gap 4 — Rollback/Safety Gate
**Problem:** Autonomous agents need a safety gate before every destructive action.
**Current state:**  (snapshot v2 + rollback) is DEPLOYED ✅ —
  watchdog_snapshot.sh captures state before remediation.
**Gap:** Snapshot is triggered by the watchdog, not by the agent autonomously
  deciding to take action. For full AIOps, the agent must:
  1. Check snapshot freshness before any destructive action
  2. Abort if snapshot is stale (configurable threshold)
  3. Write rollback manifest before executing
  4. Auto-rollback on failure (currently manual)
**Next step:** Extend watchdog_snapshot.sh to be callable by Angkai as a
  pre-execution gate, not just a watchdog-triggered checkpoint.

### Gap 5 — Agent-to-Agent Communication Protocol
**Problem:** Mokaima and Angkai communicate through you. A true multi-agent
system needs a defined handoff format they can exchange directly.
**Current prototype:** MABS brief format — structured enough to be machine-parsed.
**AIOps design:** Use ntfy as the message bus:
- Mokaima publishes brief-ready notification to ntfy topic "angkai-queue"
- Angkai watcher picks it up and reads the brief from vault
- Angkai publishes result to ntfy topic "mokaima-review"
- Mokaima reads result and writes to vault or escalates to human
- Rodkai is the prototype for this pattern
**Standard:** MCP (donated to Linux Foundation Dec 2025) — already in stack.
Leverage MCP as the agent tool-call protocol, ntfy as the event bus.
**Open question added 2026-07-24 (Minimum_Requirements_Plan.md):** once
  agents depend on ntfy for coordination rather than just human alerts,
  does the bus itself need dedicated uptime monitoring? Not yet
  answered — flag for Phase 2 design.

### Gap 6 — Self-Written Audit Log
**Problem:** Troubleshooting_Journal.md is manually maintained by Mokaima/you.
  An autonomous agent needs to log its own actions, decisions, and outcomes.
**Design:**
  - New file: vault root/AGENT_LOG.jsonl (newline-delimited JSON)
  - Each agent action writes one line: timestamp, agent, action, result, duration
  - Mokaima reads AGENT_LOG.jsonl at sync time and summarizes to state-doc
  - Troubleshooting_Journal.md remains human-curated; AGENT_LOG.jsonl is raw
**Prerequisite:** Agent-to-agent communication protocol (Gap 5) must exist first

### Gap 7 — Evaluation Pipeline
**Problem:** Agent systems take different execution paths for identical inputs.
  Without an evaluation layer, you can't know if autonomous agent output is
  correct before it hits production.
**Design:**
  - Each Angkai brief gets a corresponding test spec (expected outputs,
    forbidden side effects, verification commands)
  - After Angkai generates output, a validation step runs the test spec
  - Failures route to human review; passes route to deployment
  - This is the mechanical validator component of MABS v2.0
**Current partial solution:** MABS pause points — human validates between phases.
  AIOps replaces the human with an automated test spec.
**THIS IS THE GATE FOR PHASE 5, not hardware (2026-07-24, see
  Minimum_Requirements_Plan.md's THE RELIABILITY FLOOR section):** this
  session produced direct evidence that a capable model (Bakaidah, Qwen
  32B) drafting genuinely modest briefs still needed 3 human-review
  rounds each, and a dedicated self-check instruction reduced but did
  not eliminate the failures. Phase 5 (autonomous, unreviewed
  execution) should be gated on this gap being built and demonstrated
  reliable, not on hardware tier alone — a bigger model without this
  validator is not obviously safer than a smaller one with it.

### Gap 8 — Angkai Reliability (MABS v2.0)
**Problem:** Angkai has 5 documented failure modes that make it untrustworthy
  for fully autonomous execution:
    1. Reverts to training-data patterns instead of following the spec
    2. Loses critical details under context window pressure
    3. Fails to cross-reference multiple tables correctly
    4. Skips embedded pause points
    5. Generates files not requested in the brief
**Solution design (approved, in PENDING):** "Structural not instructional" pipeline:
    1. Phase-by-phase brief delivery as separate turns with "done when" conditions
    2. Inline concrete anchor material (full existing scripts, pre-joined lookup data)
    3. Mandatory echo-back step before Angkai writes any code
    4. Post-generation mechanical validator + git-level snapshot before each phase
**Status:** PENDING — must be implemented before autonomous queue execution is safe
**LangGraph licensing decision (2026-07-22, merged here per ;
  full doc: internal-docs/LangGraph_Licensing_Decision.md):**
  `langgraph`, `langchain-core` and model integrations are MIT --
  commercial use permitted. `langgraph-api` (the hosted server runtime
  behind `langgraph dev` / `langgraph build`) is Elastic License 2.0 and
  needs a paid Enterprise key for production. Kaidosho's decided usage:
  LangGraph strictly as an orchestration LIBRARY, imported and run
  inside Kaidosho's own self-hosted Python processes (nodes = Mokaima/Angkai/
  Bakaidah/validation, state = vault/AGENT_QUEUE.json, checkpoints =
   snapshots), never any LangChain server/platform component.
  Guardrail: do not reach for `langgraph dev`/`langgraph build` while
  prototyping -- the one path that crosses into ELv2/Enterprise
  territory. If Daikaiju AIOps is ever commercialized, this library-only,
  self-hosted pattern keeps the LangGraph dependency fully MIT-covered.

### Gap 9 — Orchestration Framework Decision
**Problem:** No formal decision made on which framework (if any) coordinates
  the multi-agent system.
**Options assessed:**
  - CrewAI (role-based, 52k stars, streaming events Jan 2026)
  - LangGraph (graph-based, stateful, human-in-the-loop checkpoints)
  - Custom shell + ntfy + vault (no framework, highest control)
**Kaidosho recommendation:** Custom first. The existing stack (shell, ntfy, vault,
  MCP) is already an orchestration pattern. Formalize it before adding a
  framework dependency. Revisit CrewAI/LangGraph at scale.
  (If LangGraph is adopted, library-only usage is already licensing-
  cleared -- see the LangGraph licensing decision under Gap 8.)

---

## STEP-BY-STEP BUILD PATH

### Phase 0 — Prerequisites (must be done first)
  [ ] MABS v2.0 designed and approved (structural not instructional pipeline)
  [ ]  (Rodkai) deployed — first agent-to-agent relay prototype
  [ ]  rollback gate extended to be Angkai-callable
  [ ] Graphify wired to Angkai (Bakaidah already has access)

### Phase 1 — Machine-Readable Task Queue
  [ ] Design AGENT_QUEUE.json schema
  [ ] Mokaima generates queue entries when tasks are approved
  [ ] Manual queue consumption (you trigger Angkai to read queue)
  [ ] Verify round-trip: queue item → brief → execution → result → queue update
  [ ] Deliverable: AGENT_QUEUE.json live, first manual task completed via queue

### Phase 2 — Agent-to-Agent Communication (ntfy bus)
  [ ] Define ntfy topic structure (angkai-queue, mokaima-review, agent-log)
  [ ] Mokaima publishes brief-ready to angkai-queue when queue item is ready
  [ ] Angkai watcher script reads ntfy topic on pi-node (via watchdog pattern)
  [ ] Angkai publishes result to mokaima-review
  [ ] Mokaima reads result and writes to vault
  [ ] Deliverable: first fully automated Mokaima→Angkai→Mokaima loop

### Phase 3 — Self-Written Audit Log
  [ ] Define AGENT_LOG.jsonl schema
  [ ] Angkai writes one log line per action
  [ ] Mokaima reads AGENT_LOG.jsonl at sync and summarizes
  [ ] Deliverable: audit trail exists without human transcription

### Phase 4 — Evaluation Pipeline
  [ ] Define test spec format for Angkai briefs
  [ ] Write test specs for 3 existing briefs
  [ ] Validation step runs after Angkai generates output
  [ ] Failures auto-route to human review queue
  [ ] Deliverable: first brief with automated validation

### Phase 5 — Autonomous Queue Consumption
  [ ] Angkai watcher polls AGENT_QUEUE.json on a schedule
  [ ] Picks up queued items, executes with MABS v2.0, writes result
  [ ] Safety gate: checks snapshot freshness before any destructive action
  [ ] Auto-rollback on validation failure
  [ ] Human notified via ntfy on completion or escalation only
  [ ] Deliverable: first task executed autonomously, start to finish

### Phase 6 — Orchestration Formalization
  [ ] Document the custom orchestration pattern as a reusable component
  [ ] Evaluate CrewAI/LangGraph — adopt if custom approach hits limits
  [ ] Deliverable: orchestration layer documented as Kaiju Spine component

### Phase 7 — Kaiju Spine Packaging
  [ ] Bootstrap installer script — single artifact, full 6-layer stack;
      FASHSD (Layer 3) installs as an optional, pluggable step ("enable
      FASHSD watchdogs? requires knowing your services") per Kaiju_Spine.md
      decision 2026-07-22, so it doesn't block the rest of the install
  [ ] FASHSD config-driven generalization (services.yaml, drive config,
      node WoL topology) + distro portability beyond Debian/Ubuntu —
      see Kaiju_Spine.md gap 7 (not a CPU-architecture problem; ARM64/x86_64
      already work unchanged)
  [ ] Hardware compatibility matrix
  [ ] Public documentation site
  [ ] Model selection guide by hardware tier
  [ ] MABS as standalone extractable document
  [ ] Build + test full install inside a clean VM — verifies
      the "under 1 hour, someone else can deploy" claim against an
      environment with zero pre-existing Kaidosho state, not dokaisho itself.
      Depends on the bootstrap installer script above existing first.
  [ ] Deliverable: someone else can deploy Kaiju Spine in under 1 hour

---

## COMPETITIVE LANDSCAPE

**Enterprise AIOps** (Dynatrace, LogicMonitor, Zscaler, Palo Alto Prisma):
  Different market. Different buyer. Different scale. Different cost.
  Daikaiju AIOps is not competing here.

**Homelab agentic tools:**
  - OpenClaw: closest competitor. Requires K3s + Terraform + Ansible.
    High barrier. Daikaiju AIOps targets Docker Compose + pi-node.
  - Hermes Agent (Nous Research): persistent memory, self-improving skills,
    MIT license, crossed from research to production 2026. Watch this.
    No infrastructure focus, no FASHSD equivalent.
  - AGiXT: self-hosted agent platform, popular in homelab/privacy deployments.
    No guardrail layer, no homelab-specific design.

**The gap Daikaiju AIOps fills:**
  Nobody in the homelab tier has:
  1. MABS-style formal guardrail rules (most defensible differentiator)
  2. FASHSD self-healing layer integrated with AI agent pipeline
  3. Docker Compose + pi-node target (accessible hardware, $0 software)
  4. Persistent, versioned, git-backed memory system (vault)
  5. Kaiju naming convention (memorable, teachable, human-legible)

---

## WHAT MAKES THIS COMMERCIALLY INTERESTING

1. **Content race, not code race** — the homelab AI space rewards documented
   process over technical novelty right now. Publishing first matters.

2. **The audience exists** — r/homelab, r/selfhosted, r/raspberry_pi = millions
   of people running similar stacks, facing identical problems, looking for
   exactly what Daikaiju AIOps provides.

3. **Low replication cost** — someone else can deploy this for under $500 in
   hardware and $0 in software. That's the value proposition: enterprise-grade
   agentic infrastructure for homelab budgets.

4. **MABS as a standalone product** — the guardrail layer is so differentiated
   it could be extracted and published independently. Even YC is funding this
   problem (Bylaw) at the enterprise level.

5. **Anthropic terms compliance** — consulting where YOU operate the pipeline
   is fine on Pro/Max. Programmatic resale requires API billing. Keep this clean.

---

## OPEN QUESTIONS (to resolve before Phase 5)

1. What's the right ntfy topic naming scheme for agent communication?
2. Does AGENT_QUEUE.json live at vault root or in angkai/?
3. How do we handle queue items that require human approval mid-execution?
4. What's the rollback SLA — how old can a snapshot be before execution is blocked?
5. Does Bakaidah have a role in autonomous queue execution or is it purely Mokaima+Angkai?
6. When do we evaluate CrewAI/LangGraph? What would trigger that evaluation?

---

## RELATIONSHIP TO KAIJU GAIS

Daikaiju AIOps is the product -- the intelligence layer, the agents,
the orchestration, the guardrails, the closed-loop autonomous
operation that makes the system self-managing rather than just
self-healing. Kaiju GAIS is the substrate it runs on: the reproducible
stack (hardware, vault, FASHSD, monitoring, local AI hosting), with no
agent reasoning of its own. One product, not two (2026-08-06,
) -- an earlier "two services" framing was considered and
explicitly rejected, since splitting them undercuts the autonomy
pitch itself.

See: Kaiju_GAIS.md

---

## PRIORITY STATUS

**HIGH** — promoted 2026-07-20 (Kaidosho Daikaiju General)
Current phase: Phase 0 (prerequisites)
Blocking item: MABS v2.0 design (in PENDING.md — see "MABS v2.0 — DAIKAIJU
AIOPS PHASE 0 BLOCKER" section, consolidated 2026-07-22)
See PENDING.md for all active tasks.

---

*End of Daikaiju_AIOps.md v1.1*
*Last updated: 2026-08-06 (, product-structure reconciliation)
-- Orchestration and Guardrail layers added as owned, built-and-
running components (moved from Kaiju_Spine.md's own layer list -- they
were always agent-reasoning territory). "Current State vs Target
State" reframed from Kaiju-GAIS-vs-Daikaiju-AIOps to manual-trigger-
vs-autonomous maturity of the SAME product. Gap 1 corrected from
"orchestration doesn't exist" (false -- it runs today) to "exists at
manual-trigger maturity, autonomous maturity is the actual gap."
"RELATIONSHIP TO KAIJU OS" renamed "RELATIONSHIP TO KAIJU GAIS" and
rewritten from "Kaiju Spine can be adopted without Daikaiju AIOps" to
containment -- one product, not two. Full rationale:
AIOPS_PENDING.md .*
*Last updated: 2026-07-24 — Gap 5 and Gap 7 cross-referenced to the new
Minimum_Requirements_Plan.md, which distinguishes Kaiju Spine's hardware
floor from Daikaiju AIOps' reliability floor and documents first-party
evidence (this session's Bakaidah brief-drafting) for why Phase 5 should
gate on Gap 7, not hardware tier*
*Last updated: 2026-09-18 -- : LangGraph licensing decision
(LangGraph_Licensing_Decision.md) merged into Gap 8, cross-referenced
from Gap 9.*
*Next update: when Phase 0 prerequisites begin or MABS v2.0 design is approved*
