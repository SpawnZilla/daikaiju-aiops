╔══════════════════════════════════════════════════════════════════════╗
║  KAIJU OS — HARDWARE COMPATIBILITY MATRIX                           ║
║  Version: 1.0 | Created: 2026-07-24 (Daikaiju AIOps)                ║
║  Fills: Kaiju_OS.md gap 2                                           ║
╚══════════════════════════════════════════════════════════════════════╝

What hardware a Kaiju OS install actually needs, split by the two node
roles the architecture requires (per Model_Selection_Guide.md and
the installer spec's topology.mode setting).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE TWO ROLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Kaiju OS supports single-node (everything on one machine) or two-node
(a small always-on watcher + a larger AI/execution node) topologies.
Hardware requirements differ sharply by role.

**AI/EXECUTION NODE** — runs Ollama, the execution + reasoning agents,
  and (if single-node) the watchdog/services too. This is the node
  the Model_Selection_Guide.md hardware tiers are written for.

**WATCHER/SERVICES NODE** (two-node topology only) — runs Docker
  services, the watchdog, and (if used) sends the WoL packet. Does
  NOT need a GPU or meaningful VRAM — this role is intentionally
  lightweight so it can stay powered on 24/7 cheaply.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AI/EXECUTION NODE — MINIMUM SPECS BY TIER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Maps directly to Model_Selection_Guide.md's 4 tiers.

| Tier | VRAM | System RAM floor | CPU floor | Storage floor |
|------|------|-------------------|-----------|-----------------|
| 1 Low | ≤8GB (or CPU-only) | 16GB | 4-core modern x86_64 | 50GB free (model + OS) |
| 2 Mid | 8-16GB | 32GB | 6-core | 80GB free |
| 3 High | 16-24GB | 32GB | 8-core | 100GB free (Tier 3 coder model alone is ~19GB) |
| 4 Enthusiast | 24GB+ | 64GB | 8-core+ | 150GB+ free |

Notes:
  - System RAM floor is set well above VRAM to leave headroom for the
    OS, Docker (if single-node), and the embedding model
    (nomic-embed-text, ~274MB, negligible but still counted).
  - CPU-only (bottom of Tier 1) works but expect noticeably slower
    agentic loops — acceptable for occasional use, frustrating for
    tight iteration. Not recommended as a primary execution-agent
    setup if avoidable.
  - GPU vendor: AMD (ROCm) confirmed working — Kaidosho's own Dokaisho
    runs an RX 7900 XTX (23.988 GiB VRAM, confirmed via lspci —
    corrected 2026-07-31, this doc previously said "XT" in error; see
    PENDING.md's VRAM contention entry for the original catch).
    NVIDIA (CUDA) should also work via Ollama's native CUDA support
    but is UNVERIFIED by Kaidosho directly — flag this to anyone trying it
    and ask them to report back.
  - Apple Silicon (Metal): Ollama supports this natively too, but is
    completely outside Kaidosho's own experience — mark UNVERIFIED, no
    installer support assumed for v1 (the bootstrap installer targets
    Debian/Ubuntu Linux only per the installer spec's locked
    decision, so macOS is out of scope for v1 regardless of Ollama's
    own Metal support).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WATCHER/SERVICES NODE — MINIMUM SPECS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Kaidosho's own reference: Raspberry Pi 5 (pi-node), running ~26 Docker
containers, the FASHSD watchdog, Pi-hole, Caddy, and the full Arr
stack simultaneously.

  Minimum: Raspberry Pi 5, 4GB RAM model (Kaidosho runs 8GB, but 26
    containers is a heavy real-world load — 4GB is plausible for a
    lighter install with fewer watched services)
  Recommended: Raspberry Pi 5, 8GB RAM (Kaidosho's actual spec)
  Storage: at least one USB3 external drive for Docker volumes — the
    Pi5's own SD/NVMe boot storage is not sized for container data at
    any real scale. Kaidosho uses 5 separate external drives (hola1-5); a
    single well-sized drive is sufficient for a smaller install.
  Alternative watcher hardware: any always-on x86_64 or ARM64 Linux
    box with 4GB+ RAM and Docker support works in principle — Pi5 is
    Kaidosho's choice for cost/power-draw, not a hard requirement. UNVERIFIED
    on other SBCs (Pi4, Orange Pi, etc.) — the watcher role's
    resource needs are modest enough that most modern SBCs should
    work, but this hasn't been tested by Kaidosho directly.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NETWORK REQUIREMENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  - Both nodes (if two-node) need to be on the same LAN, or reachable
    via a VPN overlay (Kaidosho uses WireGuard) for the watcher to reach the
    AI node's Ollama/mcpo ports.
  - Internet connectivity required for initial setup (Ollama model
    pulls are multi-GB — see Model_Selection_Guide.md's installer
    warning note) but NOT required for day-to-day operation once
    models are pulled — the whole point of local-first is offline
    capability after initial setup.
  - Two-node WoL topology requires the watcher and AI node to be on
    the same physical LAN segment (WoL magic packets don't traverse
    routers/VPNs without additional relay configuration — Kaidosho's setup
    keeps both nodes on the same physical network for exactly this
    reason).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT'S NOT COVERED HERE (deliberately out of scope for v1.0)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  - NVIDIA/CUDA verification — flagged above as unverified, not tested
  - Apple Silicon / macOS support — out of scope, installer targets
    Linux only for v1
  - Multi-GPU / server-class hardware — Model_Selection_Guide.md's
    Tier 4 already flags this as future "enthusiast+" scope, not v1
  - ARM64 AI/execution node (e.g. running the execution agent itself
    on a Pi rather than just the watcher role) — UNVERIFIED, Kaidosho's own
    execution agent has only ever run on x86_64. Ollama does support
    ARM64 in principle; untested by Kaidosho in this specific pipeline role.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RELATIONSHIP TO OTHER DOCS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  - Model_Selection_Guide.md — the 4-tier VRAM breakdown this matrix
    builds RAM/CPU/storage floors around
  - the installer spec Phase 0 — pre-flight checks could
    reference this matrix's minimums, though no automated hardware
    detection against this table is built yet (OPEN QUESTION for a
    future installer pass, not blocking v1)
  - Kaiju_OS.md gap 2 — this document resolves that gap

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
END OF HARDWARE COMPATIBILITY MATRIX v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
