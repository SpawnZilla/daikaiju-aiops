╔══════════════════════════════════════════════════════════════╗
║  CREATED: 2026-09-17  │  Kaidosho (DoSho Daikaiju)  │  v1.0       ║
║  Update cycle: SESSION                                        ║
║  Product Document — Kaiju Spine                                  ║
╚══════════════════════════════════════════════════════════════╝

# KAIJU SPINE
## A Separately-Releasable Shippable Package Under Daikaiju AIOps

**Version:** 1.0
**Created:** 2026-09-17 (split out of the original Kaiju_OS.md, which
is now Kaiju_GAIS.md — see that doc's "RELATIONSHIP TO DAIKAIJU AIOPS"
section)
**RENAMED 2026-10-26:** this document was Kaiju_OS.md and the package
was called "Kaiju Spine". the operator decided the new name Kaiju Spine means the
same thing (same six layers, same definition below); nothing was
redefined. Historical records (journal, handoffs, chat history, the
 rename entries) keep the old name on purpose, and live paths
such as /opt/kaiju-os/ and kaiju-gais-package are unchanged.
**Status:** the installer (install.sh) and the packaged FASHSD watchdog
are published in the public repo SpawnZilla/daikaiju-aiops (the public
tree already says Kaiju Spine); the agent adapters are packaged in `agent-wiring/`.
**Priority:** the full-release gaps listed below are still open.

---

## THE EXACT DEFINITION — DO NOT USE "KAIJU SPINE" FOR ANYTHING ELSE

"Kaiju Spine" refers to ONLY this specific combination, packaged as one
installable artifact (see `install.sh`, install.sh,
):

- **Orchestration Layer** (from Daikaiju AIOps)
- **Guardrail Layer / MABS** (from Daikaiju AIOps)
- **Self-Healing Layer / FASHSD** (from Kaiju GAIS)
- **Memory/Archive Layer / vault** (from Kaiju GAIS)
- **Onboarding/Transfer Layer** (from Kaiju GAIS)
- **Naming/Identity System** (from Kaiju GAIS)

Any other use of the term "Kaiju Spine" — as a stand-in for the substrate
generally, for Daikaiju AIOps generally, or for "the whole project" —
is incorrect. That usage should say "Kaiju GAIS" (if it means the
substrate) or "Daikaiju AIOps" (if it means the umbrella project)
instead. This correction was made 2026-09-17 — see AIOPS_PENDING.md
 for the full history and /areas/dosho-daikaiju.md for the
standing note.

---

## ONE-LINER

*"Daikaiju AIOps, packaged as one installable artifact someone else
can clone and run on their own hardware."*

---

## WHAT KAIJU SPINE IS

Kaiju Spine is a reproducible, open-source homelab framework — the
shippable, installable form of Daikaiju AIOps. It combines:
- A self-hosted AI agent pipeline (Orchestration Layer)
- A governed brief/execution standard (Guardrail Layer / MABS)
- Autonomous self-healing infrastructure (Kaiju GAIS's FASHSD layer)
- A persistent memory/documentation system (Kaiju GAIS's vault layer)
- Onboarding/transfer documentation (Kaiju GAIS's Onboarding layer)
- A naming/identity convention (Kaiju GAIS's Naming layer)

It is NOT an operating system. It is a framework — an opinionated,
documented, deployable stack that another person can clone and run on
their own hardware. Think of it like a Linux distribution: opinionated,
consistent, self-contained. Someone else can deploy the same stack,
use the same conventions, and get the same results — because the
entire system is documented as code and as memory.

---

## WHAT KAIJU SPINE IS NOT

- Not a cloud product
- Not a SaaS
- Not a managed service
- Not dependent on any single AI provider
- Not enterprise AIOps (different buyer, different scale, different cost)
- Not a toy — this is production-grade homelab infrastructure
- **Not being released right now** — this is documentation for a
  future package, not a current announcement

---

## THE TARGET USER (once released)

Self-hosters who:
- Run open source stacks (Jellyfin, Immich, Arr, Pi-hole, etc.)
- Can't afford enterprise tooling
- Want AI integration but don't know where to start
- Would replicate a well-documented, working system
- Are tired of babysitting their homelab

The homelab community (r/homelab, r/selfhosted, r/raspberry_pi) is millions of
people. Most of them are running similar stacks and facing the same problems.

---

## WHAT'S MISSING FOR FULL RELEASE (relocated from the original
## Kaiju_OS.md/now-Kaiju_GAIS.md 2026-07-20 "v1.0 gaps" list —
## these were always about the combined package, not the substrate)

1. **Bootstrap installer** — BUILT 2026-09-17 (, `install.sh`),
   TESTED across 3 real rounds, CLOSED. See
   AIOPS_PENDING.md  for the full build+test history. This gap
   is now RESOLVED — the remaining gaps below are what's left before a
   public release would make sense.

2. **Hardware compatibility matrix** — RESOLVED 2026-07-24. See
   Hardware_Compatibility_Matrix.md — specs by role,
   4 VRAM tiers, network requirements, explicit unverified-hardware flags.

3. **Public documentation site** — IN PROGRESS 2026-07-24, blocked on
   the repo/distribution decision. **UPDATE 2026-09-17:** the repo now
   exists (https://github.com/SpawnZilla/daikaiju-aiops, branded as
   Daikaiju AIOps per the current naming correction, not Kaiju Spine,
   since Kaiju Spine isn't being released yet) — a docs site specifically
   for a future Kaiju Spine release would need its own separate decision
   once release is actually being planned.

4. **Model selection guide** — RESOLVED 2026-07-22. See
   Model_Selection_Guide.md.

5. **Kaiju naming guide** — RESOLVED 2026-07-22. See
   Naming_Convention_Guide.md.

6. **MABS as a standalone document** — RESOLVED 2026-07-22. See
   MABS_Standalone.md.

7. **FASHSD generalization (config-driven + distro-portable)** —
   config-driven half DESIGN COMPLETE, BUILD TESTED ✅ (2026-07-23),
   see Config_Driven_FASHSD_Design.md. Distro-portability half DESIGN
   COMPLETE (scoping only) 2026-07-24, NOT built/tested against any
   real non-Debian system — see Distro_Portability_Design.md.

8. **The actual release decision itself** — added 2026-09-17. Even
   once the above gaps close, Kaiju Spine is deliberately not being
   presented or released until the operator decides to. This is a real,
   standing gate, not a technical gap.

---

## DIFFERENTIATION FROM EXISTING TOOLS (relocated 2026-09-17 — this
## was comparing the combined package's experience, not the substrate
## alone)

| Tool | What it does | Why Kaiju Spine is different |
|------|-------------|--------------------------|
| OpenClaw | Self-healing homelab agent | Requires K3s + Terraform + Ansible — high barrier |
| Hermes Agent | Self-hosted agent with persistent memory | No infrastructure focus, no FASHSD |
| AGiXT | Self-hosted agent platform with GUI | No guardrail layer, no homelab-specific design |
| Home Assistant | Smart home automation | No AI agent pipeline, no self-healing infra |
| Uptime Kuma | Monitoring | No remediation, no AI integration |
| Standard MABS-less agentic setups | AI + execution | No governance, no guardrails, no audit trail |

**The gap Kaiju Spine fills:** Production-grade, governed, agentic homelab
infrastructure for people who can't spend $50K on enterprise AIOps but
can spend $500 on hardware and $0 on software.

---

## WHAT MAKES THIS COMMERCIALLY INTERESTING (relocated 2026-09-17)

1. **Content race, not code race** — the homelab AI space rewards documented
   process over technical novelty right now. Publishing first matters.

2. **The audience exists** — r/homelab, r/selfhosted, r/raspberry_pi = millions
   of people running similar stacks, facing identical problems, looking for
   exactly what Kaiju Spine provides.

3. **Low replication cost** — someone else can deploy this for under $500 in
   hardware (bought 2024–2026) and $0 in software.

4. **MABS as a standalone product** — the guardrail layer is so differentiated
   it could be extracted and published independently.

5. **Anthropic terms compliance** — consulting where YOU operate the pipeline
   is fine on Pro/Max. Programmatic resale requires API billing. Keep this clean.

---

## RELATIONSHIP TO DAIKAIJU AIOPS AND KAIJU GAIS

Daikaiju AIOps is the umbrella project and the first shippable package
(currently at https://github.com/SpawnZilla/daikaiju-aiops). Kaiju GAIS
is the substrate, a part of Daikaiju AIOps (see Kaiju_GAIS.md). Kaiju
OS — this document — is a SECOND, later, separately-releasable package:
the combination of Daikaiju AIOps' Orchestration + Guardrail layers
with all four of Kaiju GAIS's layers, as one installable artifact. It
is not a competing product to either of them — it's a packaging of
both, held for a later release.

See: Daikaiju_AIOps.md (the product)
See: Kaiju_GAIS.md (the substrate)

---

## USAGE SCENARIO (added 2026-09-19, illustrative — no install docs
## exist yet; this is a worked example of intended use, not a spec)

**Persona:** a self-hoster running a handful of Docker services on
their own hardware (e.g. Jellyfin, *arr apps, a reverse proxy) who
wants the same self-healing, orchestrated, guardrailed agent pattern
Kaidosho runs, without adopting Kaidosho's specific hardware or agent naming.

**Install flow (illustrative):**
```bash
git clone https://github.com/<org>/kaiju-os.git
cd kaiju-os
./install.sh
```
- Missing Docker → instruct-and-exit, no silent auto-install (same
  precedent as 's autonomy scope).
- Installer stands up the watchdog (FASHSD), an vault-style
  git-initialized archive directory, and the orchestration/guardrail
  scaffolding.

**Post-install, the user:**
1. Points the substrate at their own services (their `services.yaml`
   equivalent)
2. Plugs in their own local model as the reasoning-agent role
   (Kaidosho's Bakaidah equivalent)
3. Leaves FASHSD running on a timer to catch failures
4. Reviews/approves escalated fixes at their configured autonomy
   level — manual-trigger by default

**Concrete example:** their reverse-proxy container exits. FASHSD
snapshots its logs and tries a scripted restart first. If that fails,
it escalates: their local model drafts a diagnosis + fix referencing
their archive of past incidents; the fix queues for manual review
(guardrail default) before an execution agent applies it; the
incident, fix, and outcome all commit to their local git-versioned
archive automatically.

Net effect: Kaidosho's self-healing/orchestration pattern on their own
infra, under their own naming, without adopting the Kaidosho project itself.

---

## PRIORITY STATUS

**HELD** — 2026-09-17. Not being worked toward release until the operator
says otherwise. `install.sh` (the actual installable artifact) is
built, tested, and CLOSED — the remaining gap is purely the
release decision itself (gap 8 above), not more building.

---

*End of Kaiju_Spine.md v1.0*
*Created 2026-09-17, split out of the original Kaiju_OS.md (now
Kaiju_GAIS.md) as part of the naming correction: Daikaiju AIOps is the
umbrella project and first shippable package; Kaiju GAIS is a part of
it (the substrate); Kaiju Spine is this document's exact, narrow
definition — a second, later, separately-releasable package — and
should not be used to mean anything else anywhere else. Full
rationale: AIOPS_PENDING.md , 2026-09-17.*
