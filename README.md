# Kaidosho Daikaiju AIOps

Daikaiju AIOps is a governed multi-agent operations setup for a homelab or small
infrastructure: a planning agent, a reasoning agent and an execution agent, each
held to written guardrails, with a self-healing watchdog underneath.

This repository holds the part that can be installed by someone else today:

- **Kaiju GAIS**, the substrate: a bootstrap installer, the guardrail standard (MABS),
  a version-controlled memory vault and a config-driven self-healing watchdog (FASHSD).
- **docs-site/**, a local MkDocs reference site (not deployed anywhere yet).

The agent orchestration layer itself (the planning, reasoning and execution agents)
is not packaged here. See `docs-site/docs/status.md` for what is built and verified
and what is not.

## Quick start

Requirements: Ubuntu or Debian, a normal user with `sudo`, and Docker with the
Compose plugin already installed. Tier 3 needs about 40 GB of free disk for the
models; the model pull can be skipped.

```bash
git clone https://github.com/SpawnZilla/daikaiju-aiops.git
cd daikaiju-aiops
bash install.sh        # run as a normal user, NOT with sudo
```

Run it as your own user. `sudo bash install.sh` moves `$HOME` to `/root` and puts
files in the wrong place.

The installer asks for your hardware tier (see `Model_Selection_Guide.md`), pulls the
models with Ollama, installs `mcpo`, copies the MABS guardrails, creates a git-tracked
memory vault, records a naming scheme (`Naming_Convention_Guide.md`) and optionally
sets up the FASHSD watchdog from a short list of your services and drives.

## Measured install time

One clean-VM run on Ubuntu 24.04 (CPU-only VM, 493 Mbps connection):

| Step | Time |
|---|---|
| Docker install | 19 s |
| `install.sh` end to end (Tier 3, both models pulled, FASHSD enabled) | 11 min 33 s |
| Whole deploy from a bare VM | about 12 min |

About 8 minutes of that was Ollama and the two models (35 GB). The rest includes about
two minutes of typing answers. On a slower connection the model download dominates:
at 100 Mbps, 35 GB alone takes about 47 minutes. Debian 13 and Ubuntu 22.04 were
tested on the minimal path only (no model pull, no FASHSD).

## What is verified

- The installer ran clean on Ubuntu 24.04, Debian 13 and Ubuntu 22.04 (minimal path)
  and on Ubuntu 24.04 (full path above).
- The FASHSD watchdog scripts (container exited, daemon down, network-namespace
  owner, clock drift, drive not mounted, ghost mount, DNS failure) were each tested
  against disposable infrastructure; results are in
  `kaiju-gais-package/fashsd/tests/TESTING.md`.
- In the full-path run the installed watchdog timer ran unattended every hour and
  every check passed.

Not verified: non-Debian distributions, the full path on Debian or Ubuntu 22.04,
and the agent layer outside the reference deployment.

## Claude Code

The Daikaiju AIOps execution agent runs on Claude Code. Claude Code is not bundled
and is not needed for Kaiju GAIS. The installer prints a note if it is not on your
`PATH`; install it yourself when you want the execution agent.

## Layout

| Path | What |
|---|---|
| `install.sh` | Bootstrap installer (phases 0 to 7) |
| `MABS_Standalone.md` | Portable guardrail standard for planning and execution agents |
| `Model_Selection_Guide.md` | Model picks per hardware tier |
| `Hardware_Compatibility_Matrix.md` | Hardware and topology compatibility notes |
| `Naming_Convention_Guide.md` | Optional naming scheme for nodes, agents and subsystems |
| `kaiju-gais-package/fashsd/` | Config-driven watchdog scripts, example config and tests |
| `docs-site/` | MkDocs reference site |

## License

MIT, see `LICENSE`.
