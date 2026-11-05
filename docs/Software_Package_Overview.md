╔══════════════════════════════════════════════════════════════╗
║  CREATED: 2026-07-31  │  Kaidosho (Daikaiju AIOps)  │  v1.0       ║
║  Update cycle: SESSION (while packaging work is active)      ║
║  Audience: technically capable first-time reader — someone   ║
║  who could install and run this, but has never seen it       ║
╚══════════════════════════════════════════════════════════════╝

# KAIJU GAIS + DAIKAIJU AIOPS
## Software Package Overview — What It's Made Of, Where Everything Lives, How It Runs

---

## 0. Read this first

Two products, one stack:

- **Kaiju GAIS** (Governed Autonomous Infrastructure System) is the
  framework — self-healing, memory, guardrails, agent pipeline wiring.
  You can run Kaiju GAIS by hand, without any AI doing the driving.
- **Daikaiju AIOps** is the autonomy layer on top of it — the same
  framework, but with agents planning and executing instead of you
  running every command yourself.

You cannot run Daikaiju AIOps without Kaiju GAIS underneath it. You
*can* run Kaiju GAIS without Daikaiju AIOps — that's the lower-commitment
entry point.

Everything below is organized by the five layers that make up Kaiju GAIS.
Daikaiju AIOps doesn't add a 6th layer — it makes Layer 1 (Orchestration)
autonomous instead of human-driven.

---

## 1. THE FIVE LAYERS AND WHAT SOFTWARE LIVES IN EACH

| # | Layer | What it does | Software in this layer |
|---|-------|---------------|--------------------------|
| 1 | **Orchestration** | Turns human intent into a scoped brief, hands it to a reasoning model, then to an execution agent, with defined handoff points instead of one AI doing everything unsupervised | Mokaima (Claude Desktop), Bakaidah (Open WebUI + Ollama), Angkai (Claude Code), MCP filesystem/git servers, mcpo |
| 2 | **Guardrail** | Install-path restrictions, pause-and-approve checkpoints, session formats, failure-mode catalogs — what makes autonomous execution trustworthy instead of terrifying | MABS.md (the governance protocol), Stop hook validator, git snapshot/rollback backstop |
| 3 | **Self-Healing** | Watchdogs, alerting, Wake-on-LAN, remediation scripts, a living failure-mode catalog — detects and resolves known problems without a human in the loop | FASHSD watchdog scripts, ntfy, systemd timers |
| 4 | **Memory/Archive** | Versioned, git-backed, cross-referenced documentation agents read from and write to — without it, every session starts from zero | vault (git repo), Graphify (knowledge graph), mcpo (serves vault to Bakaidah) |
| 5 | **Onboarding/Transfer** | The documentation and templates that let someone else stand up their own instance without living through the incidents that produced this one | Bootstrap_Installer_Spec.md, MABS_Standalone.md, Model_Selection_Guide.md, Naming_Convention_Guide.md, DD_Glossary.md (portable subset), Hardware_Compatibility_Matrix.md, MABS brief template |
| 6 | **Naming/Identity** | A consistent metaphor scheme that makes a complex multi-agent, multi-node system legible at a glance | Kaiju naming convention (no software — a documentation convention) |

**Resolved 2026-07-31:** the naming conflict noted in this
doc's first draft is settled. Both candidate "Layer 5" definitions were
real, so rather than picking one, `Kaiju_Spine.md` now has six layers —
Onboarding/Transfer at 5, Naming/Identity moved to 6.

---

## 2. FULL SOFTWARE INVENTORY

### Layer 1 — Orchestration

| Software | What it does | Runs where | Status |
|---|---|---|---|
| **Mokaima** | Planning agent. Reads vault, writes MABS-formatted briefs, reviews Angkai's output before/after execution, updates memory | Claude Desktop (any machine) | Live |
| **Bakaidah** | Reasoning/drafting agent. Takes a brief from Mokaima, researches and drafts (scripts, docs, designs) using local knowledge + web search + vault read access | Open WebUI, backed by a local model via Ollama | Live |
| **Angkai** | Execution agent. Takes a Mokaima-reviewed brief and writes/generates the actual scripts and files, staged for human deployment | Claude Code, backed by a local model via Ollama | Live |
| **Ollama** | Local model runtime — serves the model(s) behind Bakaidah and Angkai | Same machine as the AI stack (a GPU-equipped node) | Live |
| **Open WebUI** | Chat interface + tool-calling front end for Bakaidah; also where Guardrail-layer Filters/Pipes attach | Docker container, any host reachable from the AI stack | Live |
| **mcpo** | MCP-to-HTTP proxy — gives Bakaidah (via Open WebUI tool calls) read access to vault and to Graphify | Docker/local process, default port 8200 | Live |
| **MCP filesystem/git servers** | Give Mokaima direct read/write file access and git operations against vault | Local MCP servers configured in Claude Desktop | Live |

### Layer 2 — Guardrail

| Software | What it does | Runs where | Status |
|---|---|---|---|
| **MABS.md** | The governance document itself — rules, pause-point format, install-path restrictions, failure-mode catalog, brief template. Not code — the protocol every brief is written against | Lives in vault, read by Mokaima before every brief | Live, versioned |
| **Stop hook validator** | A script that runs automatically when Angkai finishes a turn — checks its output against the brief's own source-of-truth data (named files, cross-reference tables) before letting the turn end | Registered as a Claude Code Stop hook on the execution node | Live, verified across 5 live-fire test cycles |
| **Git snapshot/rollback backstop** | Reverts vault to a known-good state if a brief's execution goes wrong mid-way | Git itself (vault's own repo) | Not yet built |

### Layer 3 — Self-Healing (FASHSD)

| Software | What it does | Runs where | Status |
|---|---|---|---|
| **Watchdog timer** | Polls known services on a schedule, detects known failure modes, triggers the matching remediation script | systemd timer on the services host | Live |
| **fashsd_config_lib.sh** | Shared function library the remediation scripts call — service lookups, drive checks, config reads | Services host | Live |
| **Remediation scripts (FM-0x)** | One script per known failure mode — e.g. container exited, daemon down, VPN-container unhealthy, drive not mounted — each detects and fixes its specific problem | Services host | 5 of ~10 planned scripts built and tested; rest in progress |
| **Snapshot/rollback script** | Captures state before a remediation script acts, so a bad fix can be undone | Services host | Live |
| **ntfy** | Push-notification relay — watchdog and remediation scripts alert a human (or another agent) when something happens | Self-hosted, default port 8201 | Live |
| **Wake-on-LAN trigger** | Remotely wakes a sleeping/offline node as part of a health-check or remediation flow | Relay script, triggered via ntfy | Live |

### Layer 4 — Memory/Archive (vault)

| Software | What it does | Runs where | Status |
|---|---|---|---|
| **vault (the git repo itself)** | Every piece of state, every pending item, every decision — the single source of truth agents read from and write to | Local filesystem + git, mirrored to a bare remote and a self-hosted git server | Live |
| **Git** | Version control for every vault change — what makes the memory auditable and revertible | Local + remote | Live |
| **Graphify** | Builds a queryable knowledge graph out of vault's contents (nodes/edges) so Bakaidah can query relationships instead of reading raw files | Local process, served on its own port, wired into Bakaidah via mcpo | Live |

### Layer 5 — Onboarding/Transfer

| Document | What it does | Status |
|---|---|---|
| **Bootstrap_Installer_Spec.md** | The install flow itself — 7-phase spec | Spec complete, script not built |
| **MABS_Standalone.md** | Portable version of the Guardrail Layer's protocol, Kaidosho-specific incident history stripped out | Complete |
| **Model_Selection_Guide.md** | Which model to run for which hardware tier | Complete |
| **Naming_Convention_Guide.md** | How to build a custom Layer 6 scheme, or adopt the Kaiju one | Complete |
| **DD_Glossary.md (portable subset)** | Grounding facts and terminology for a new install's own reasoning agent | Complete (internal version); portable extraction not yet split out |
| **Hardware_Compatibility_Matrix.md** | What hardware this actually needs, by role and VRAM tier | Complete |
| **MABS brief template** | The reusable shape of an agent handoff document | Complete |

### Layer 6 — Naming/Identity

No software — a documentation convention (a consistent metaphor scheme
applied to node names, agent names, and subsystem names so the whole
system stays legible as it grows). Packaged as `Naming_Convention_Guide.md`
(Layer 5) for anyone adopting their own naming scheme instead of the Kaiju one.

---

## 3. THE FULL RUNTIME FLOW — START TO FINISH

This is the actual path a piece of work takes through the system, with
every software component labeled at the point it's involved.

`
┌─────────────────────────────────────────────────────────────────┐
│  1. HUMAN INTENT                                                 │
│     A person decides something needs doing.                      │
└───────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. MOSURA — Claude Desktop                                      │
│     Reads vault (via MCP filesystem tools) for current state.     │
│     Writes a MABS-formatted brief: scoped task, closed list of   │
│     expected files, exact reference paths, pause points.         │
└───────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. BARAGON — Open WebUI + Ollama                                 │
│     Human pastes the brief into Bakaidah. Bakaidah researches/     │
│     drafts using web search + vault read access (via mcpo) +      │
│     Graphify queries. Guardrail-layer Filters (Reference          │
│     Existence Gate, Citation Grounding Pipe) check its output     │
│     before it's shown.                                            │
└───────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. MOSURA REVIEWS THE DRAFT                                      │
│     Checks Bakaidah's draft against the real vault facts before     │
│     it goes anywhere near execution. Corrects or rewrites if      │
│     Bakaidah fabricated anything.                                  │
└───────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  5. ANGUIRUS EXECUTES — Claude Code + Ollama                      │
│     Launched with a restricted tool allowlist (never a bare       │
│     launch). Reads the approved brief, generates the actual       │
│     scripts/files, writes them to a staging area — never          │
│     directly to production.                                       │
└───────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  6. STOP HOOK VALIDATOR fires automatically                       │
│     Checks Angkai's output against the brief's own source-of-   │
│     truth data (named file list, cross-reference tables) before   │
│     the turn is allowed to end. Blocks and reports if something   │
│     doesn't match.                                                │
└───────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  7. MOSURA REVIEWS STAGED OUTPUT                                  │
│     Human-facing review of what Angkai actually produced,       │
│     before anything touches a running system.                     │
└───────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  8. HUMAN DEPLOYS                                                 │
│     Person moves the staged, reviewed output into production.     │
│     Angkai is never responsible for deployment itself.          │
└───────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  9. vault IS UPDATED                                                │
│     Mokaima writes the outcome back to vault (git-committed),       │
│     Graphify's graph updates on the next sync so the knowledge     │
│     is queryable going forward.                                   │
└─────────────────────────────────────────────────────────────────┘
`

**Running in parallel to all of the above, continuously:** the FASHSD
watchdog polls known services on its own schedule, independent of any
human-initiated task. When it detects a known failure mode, it runs the
matching remediation script itself, snapshots state first, and alerts
via ntfy — no brief, no Mokaima/Bakaidah/Angkai involvement, no human
needed unless the failure mode is unrecognized.

**Where Daikaiju AIOps changes this diagram:** steps 2 through 8 above
are currently human-triggered and human-reviewed at every arrow. Daikaiju
AIOps's build path (Gaps 1–9 in `Daikaiju_AIOps.md`) is about replacing
the human-triggered arrows with agent-to-agent handoffs (a task queue,
an ntfy-based message bus, a self-written audit log, an automated
evaluation gate) so the loop can close without a person in the middle —
while keeping the Guardrail layer intact underneath it.

---

## 4. THE INSTALL FLOW (for someone standing this up for the first time)

Per `Bootstrap_Installer_Spec.md` — spec complete, not yet built:

`
Phase 0 — Pre-flight checks (Debian/Ubuntu-family gate, sudo check,
           existing-install detection, Docker presence check)
Phase 1 — Layer 1: install Ollama, pull the model(s) for your hardware
           tier, install mcpo, write MCP config, gate on Claude Desktop
           being installed and logged in
Phase 2 — Layer 2: deploy MABS.md, configure the install-path rule
Phase 3 — Layer 4: bootstrap vault directory structure, git init,
           template docs
Phase 4 — Layer 6: choose the Kaiju naming convention or a custom one
Phase 5 — Layer 3 (OPTIONAL): enable FASHSD watchdogs — asks which
           services and drives to watch; skippable, re-runnable later
Phase 6 — Writes an answers-file (receipt of what was installed and
           answered — doubles as disaster-recovery reference)
Phase 7 — Summary + "what to do next"
`

Layer 5 (Onboarding/Transfer) has no phase of its own — it ships as
static reference docs included in the artifact (this document among
them), read before/during install rather than deployed by it.

One artifact, one script, covers the full 6-layer stack. FASHSD is the
only layer that's optional and pluggable — everything else installs as
one unit.

---

## 5. WHAT'S NOT YET BUILT (as of 2026-07-31)

- Git snapshot/rollback backstop for brief execution (Layer 2 gap)
- Remaining FASHSD remediation scripts (5 of ~10 done)
- The bootstrap installer script itself (spec is complete; script is not written)
- Audit/observability aggregation layer (stitching Stop hook + watchdog + ntfy logs into one view)
- Cost/resource governor (capping agent token/query spend per task)
- Public-facing trademark-safe names (internal names reference Toho-owned kaiju IP — fine for development, not for public marketing/sale)

See `AIOPS_PENDING.md` for the live, itemized tracking of all of the above.

---

*End of Software_Package_Overview.md v1.0*
*Sources: Kaiju_Spine.md, Daikaiju_AIOps.md, Bootstrap_Installer_Spec.md,
AIOPS_PENDING.md, kaiju-os-package/fashsd/ (live directory listing) —
all read directly this session, not reconstructed from memory.*
