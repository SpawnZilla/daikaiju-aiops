╔══════════════════════════════════════════════════════════════╗
║  CREATED: 2026-07-20  │  Kaidosho (Daikaiju AIOps)  │  v2.0       ║
║  Update cycle: SESSION                                        ║
║  Product Document — Kaiju GAIS                                ║
╚══════════════════════════════════════════════════════════════╝

# KAIJU GAIS
## The Self-Healing Substrate Daikaiju AIOps Runs On

**Version:** 2.0
**Created:** 2026-07-20 (Kaidosho Daikaiju General), reworked 2026-09-17
**Status:** Active development — built on Daikaiju AIOps (Kaidosho) homelab
**Priority:** HIGH
**Part of:** Daikaiju AIOps (the umbrella project and first shippable
package). Kaiju GAIS is not a separate product -- see "RELATIONSHIP TO
DAIKAIJU AIOPS" below.

✅ TESTED 2026-07-23 — the config-driven FASHSD scripts referenced in
Layer 1 below (kaiju-gais-package/fashsd/) have passed the full test
suite, including an exact-match live comparison against Kaidosho's real
production script. See Config_Driven_FASHSD_Design.md STATUS or
kaiju-gais-package/fashsd/tests/TESTING.md for the full results.

---

## ONE-LINER

*"The reproducible substrate underneath Daikaiju AIOps — self-healing
infrastructure, persistent memory, and onboarding, with no agent
reasoning of its own."*

---

## WHAT KAIJU GAIS IS

Kaiju GAIS is the substrate layer of Daikaiju AIOps: a reproducible,
self-contained infrastructure stack that combines:
- Autonomous self-healing infrastructure (FASHSD)
- A persistent memory/documentation system (vault)
- An onboarding/transfer layer that packages the substrate for others
  to replicate
- A consistent naming/identity convention
- An alerting and observability stack

It is NOT an operating system, and it does NOT include agent reasoning,
orchestration, or guardrails on its own — those live in Daikaiju
AIOps (see "RELATIONSHIP TO DAIKAIJU AIOPS" below). Kaiju GAIS is the
body; Daikaiju AIOps' Orchestration and Guardrail layers are the brain
that runs on top of it.

Think of it like the base image a Linux distribution is built from:
opinionated, consistent, self-contained, but not the whole OS
experience by itself.

---

## WHAT KAIJU GAIS IS NOT

- Not a cloud product
- Not a SaaS
- Not a managed service
- Not dependent on any single AI provider
- Not an agent-reasoning or orchestration layer (that's Daikaiju
  AIOps' job, not this one)
- Not a toy — this is production-grade homelab infrastructure

---

## THE FOUR LAYERS OF KAIJU GAIS

(Orchestration and Guardrail are NOT part of Kaiju GAIS — they moved
to Daikaiju_AIOps.md as of v1.2/, 2026-08-06, and stay there.
They are the agent-reasoning/autonomy layers Daikaiju AIOps owns
outright. See "RELATIONSHIP TO DAIKAIJU AIOPS" below.)

### Layer 1 — Self-Healing Layer (the immune system)
**Internal name:** Kaidosho FASHSD (Full Autonomous Self-Healing System Design)
**What it is:** Watchdogs, alerting, Wake-on-LAN, remediation scripts, and a
  living catalog of failure modes and automated fixes.
**Components (deployed as of 2026-07-20):**
  - : pi-node hourly watchdog (now 30 min) + ntfy + WoL
  - : FM-01 (container exited), FM-02 (daemon down), FM-03 (gluetun
    unhealthy), FM-04 (clock drift)
  - : FM-05 (drive not mounted), FM-07 (prowlarr DNS failure)
  - : FM-09 app-level curl detection (10 services, PASS/FAIL)
  - : Pre-remediation snapshot v2 + rollback layer
  - : dokaisho disaster recovery runbook
  - : Rodkai remote wake/health-check trigger (deployed and
    live-tested; the gateway-wake extension specifically remains
    untested end-to-end -- see AIOPS_PENDING.md )
  - Functional health check: 13 services
  - pi-node daily health digest, SMART checks, backup verification
**Why it matters:** Detects and resolves known problems without human intervention.
  Infrastructure that heals itself is the headline feature of Kaiju GAIS.

  **Replicability status (2026-07-22):** FASHSD is currently Kaidosho-specific —
  hardcoded to this services list, these drive names (drive1-5), this VPN
  container topology (gluetun namespace), and Debian/Ubuntu (`apt`,
  systemd). Generalizing it is NOT a CPU-architecture problem (bash/
  systemd/Docker Compose already run identically on ARM64 pi-node and x86_64
  dokaisho). The real work is two-fold:
    - **Config-driven FASHSD:** turn hardcoded values (watched services,
      drive names, node WoL topology) into user-supplied config
      (e.g. services.yaml) the watchdog reads instead of assuming.
    - **Distro portability:** FASHSD assumes the Debian/Ubuntu family.
      Fedora, Arch, and non-systemd distros would break on install today.
  In the Kaiju Spine bootstrap installer (a separate, later-releasable
  package that combines this layer with Daikaiju AIOps' Orchestration
  and Guardrail layers, plus Kaiju GAIS's other 3 layers — see
  Kaiju_Spine.md), FASHSD ships as an **optional, pluggable component** —
  "enable FASHSD watchdogs? (requires knowing your services)" — so
  config-driven generalization doesn't block shipping the rest of the
  stack.

### Layer 2 — Memory/Archive Layer (long-term memory)
**Internal name:** vault (Vault)
**What it is:** Versioned, git-backed, cross-referenced documentation that
  agents read from and write to. Without this, every session starts from zero.
  This is what lets the system get smarter over time instead of repeating mistakes.
**Components:**
  - state-doc — current infrastructure state document
  - PENDING.md — all pending items (sole source of truth)
  - PA.md — possible additions parking lot
  - 11 master documents (chat history by subject, inventory, script registry, etc.)
  - 3-tier structure (Tier 1: critical/daily, Tier 2: reference, Tier 3: daily work)
  - Git versioning with pi-node bare remote + Gitea mirror
  - sync, chatsync, deep sync keyword system
  - Graphify knowledge graph (110 nodes, 195 edges, graph.example.com)
**Why it matters:** Most AI homelab projects reset every session. vault is the
  reason Kaiju GAIS accumulates knowledge instead of forgetting it.

### Layer 3 — Onboarding/Transfer Layer (the packaging)
**Internal name:** Onboarding Kit
**What it is:** The documentation and templates that let someone else
  stand up their own instance without living through the incidents that
  produced this one — the difference between "a personal setup" and
  "a product."
**Components:**
  - Bootstrap_Installer_Spec.md — the install flow itself
  - MABS_Standalone.md — portable version of the Guardrail Layer's
    protocol, Kaidosho-specific incident history stripped out
  - Model_Selection_Guide.md — which model for which hardware tier
  - Naming_Convention_Guide.md — how to build your own naming scheme,
    or adopt the Kaiju one
  - DD_Glossary.md (portable subset) — grounding facts and terminology
    for a new install's own reasoning agent
  - Hardware_Compatibility_Matrix.md — what hardware this actually needs
  - MABS-formatted brief template — the reusable shape of an agent
    handoff document
**Why it matters:** Without this layer, Kaiju GAIS is a personal setup
  that only makes sense to the person who built it. This is what turns
  it into something someone else can actually deploy.

### Layer 4 — Naming/Identity System (the culture)
**Internal name:** Kaiju Convention
**What it is:** A consistent metaphor scheme for roles, nodes, and concepts
  drawn from the Toho Kaiju universe.
**Components:**
  - Node names: dokaisho, pi-user, varan, rodan (planned)
  - Agent names: Mokaima (planner), Angkai (executor), Bakaidah (reasoner)
  - System names: FASHSD, vault, MABS, Kaidosho
  - Drive names: drive1-drive5, vault-drive
**Why it matters:** A consistent metaphor makes a complex system legible at a
  glance. Memorable names are part of why this works — and why it's teachable.

---

## CURRENT HARDWARE STACK (Kaidosho reference implementation)

| Node | Hardware | OS | Role |
|------|----------|----|------|
| dokaisho | AMD Ryzen 7 9800X3D, 64GB RAM, RTX + RX GPUs | Kubuntu 24.04 | Primary workstation, AI inference, Angkai |
| pi-user | Raspberry Pi 5 | Debian Trixie | Services host (26 Docker containers) |
| varan | Lenovo IdeaPad 110-15ISK (i3-6100U, 4GB RAM) | Debian Trixie | Mobile access node, Remoto test machine |

**Estimated total hardware cost:** Under $500 (renewed/refurbished components)
**Software cost:** $0 (fully open source)

---

## CURRENT SOFTWARE STACK

**AI Pipeline** (Daikaiju AIOps' Orchestration Layer runs on this,
listed here since it's part of the reference implementation's real
running stack):
  - Ollama (model runtime) — dokaisho
  - qwen3-coder:30b-a3b-q4_K_M (Angkai model)
  - Qwen 32B (Bakaidah model)
  - Open WebUI (Bakaidah interface)
  - Claude Desktop + Claude Code (Mokaima + Angkai interface)
  - mcpo (MCP proxy, port 8200) — wires vault + Graphify to Bakaidah

**Infrastructure:**
  - Docker Compose (all services)
  - Caddy (reverse proxy + HTTPS)
  - WireGuard (VPN, port 4443)
  - Pi-hole + Unbound (DNS)
  - UFW + YubiKey FIDO2 (security)
  - ntfy (alerting, port 8201)
  - Uptime Kuma × 2 (monitoring)
  - Gitea (vault git mirror)
  - Graphify (knowledge graph, port 8300)

**Services (self-hosted):**
  a media server, Nextcloud, Vaultwarden, Sonarr, Radarr, Lidarr,
  Prowlarr, qBittorrent (via Gluetun/ProtonVPN), SearXNG, Portainer, Dozzle

---

## RELATIONSHIP TO DAIKAIJU AIOPS

Corrected 2026-09-17 (supersedes the framing below from 2026-08-06,
which still implied a "one product, two names" symmetry rather than
containment): **Daikaiju AIOps is the umbrella project and the first
shippable package.** Kaiju GAIS is a named PART of Daikaiju AIOps — the
self-healing substrate, with no agent reasoning of its own. It is not
released or presented as a standalone thing.

A second, later, separately-releasable package also lives under the
Daikaiju AIOps umbrella: **Kaiju Spine** — the specific combination of
Daikaiju AIOps' own Orchestration and Guardrail layers with all four
Kaiju GAIS layers above, packaged as one installable artifact (see
Kaiju_Spine.md). Kaiju Spine is not being presented or released right now.

The original 2026-08-06  reconciliation's point stands and is
unaffected by this correction: an earlier "two separate products"
framing (Kaiju GAIS vs. Daikaiju AIOps as competing/parallel things)
was considered and explicitly rejected, since splitting them undercuts
the autonomy pitch itself. That is still true — Kaiju GAIS and Kaiju Spine
are both parts/packages of the one Daikaiju AIOps project, not rival
products.

See: Daikaiju_AIOps.md (the product)
See: Kaiju_Spine.md (the second, later shippable package)

---

## PRIORITY STATUS

**HIGH** — promoted 2026-07-20 (Kaidosho Daikaiju General)
See PENDING.md for active tasks.

---

*End of Kaiju_GAIS.md v2.0*
*Last updated: 2026-09-17 — Renamed from Kaiju_OS.md and reworked
(naming correction: Daikaiju AIOps is the umbrella project and first
shippable package; Kaiju GAIS is a part of it, the substrate only;
Kaiju Spine is reserved for a second, later, separately-releasable
package combining Kaiju GAIS with Daikaiju AIOps' Orchestration/
Guardrail layers). Title, one-liner, "WHAT X IS/IS NOT" sections
rewritten to describe only the substrate (no agent pipeline, no
guardrail standard — those are Daikaiju AIOps'). "WHAT'S MISSING FOR
FULL REPLICABILITY" (the install-script gaps list) and "DIFFERENTIATION
FROM EXISTING TOOLS" sections MOVED to the new Kaiju_Spine.md — both were
actually describing the combined shippable package, not the substrate
alone. "THE TARGET USER" and "WHAT MAKES THIS COMMERCIALLY INTERESTING"
sections also moved to Kaiju_Spine.md for the same reason. Full rationale:
AIOPS_PENDING.md  update, same date.*
*Last updated: 2026-08-06 (, product-structure reconciliation)
-- Layer 1 (Orchestration) and Layer 2 (Guardrail) removed entirely;
they belong to Daikaiju AIOps, not the substrate. Remaining four
layers renumbered (old 3/4/5/6 -> new 1/2/3/4).*
*Last updated: 2026-07-31 — added Layer 5 (Onboarding/Transfer Layer),
renumbering the former Layer 5 (Naming/Identity System) to Layer 6.
Tracked as  in AIOPS_PENDING.md.*
*Last updated: 2026-07-24 — gap 2 RESOLVED (Hardware_Compatibility_Matrix.md);
gap 3 IN PROGRESS; gap 7(a) remaining scripts context-prepped for Bakaidah;
gap 7(b) DESIGN COMPLETE (scoping only, Distro_Portability_Design.md).*
