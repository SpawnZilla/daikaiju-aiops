# Kaiju OS

!!! warning "Not released"
    Kaiju OS is a real, working artifact — built and tested — but it
    is **deliberately not being released or announced right now**,
    pending Daikaiju AIOps' own readiness to go public. Nothing below
    is a promise of availability on any particular timeline.

## What it is

Kaiju OS is a second, later, separately-releasable package under the
Daikaiju AIOps umbrella. By its exact definition, it's Daikaiju AIOps'
Orchestration and Guardrail layers combined with all four Kaiju GAIS
layers, packaged as one installable artifact. It is not an operating
system in the kernel sense — the name is a metaphor for "everything
you need, in one box."

## What it does

It lets someone else run the same self-healing, orchestrated,
guardrailed agent pattern on their own hardware, under their own
naming, without adopting this specific project's infrastructure or
branding.

## How it's used (illustrative — no install documentation exists yet)

1. Clone the repository, then run the installer script.
2. Point it at your own services (a small configuration file
   describing what you're running).
3. Plug in your own local reasoning model.
4. Leave the self-healing watchdog running on a timer.
5. Review and approve escalated fixes at your configured autonomy
   level — manual review by default.

## How it does it

The installer sets up the self-healing watchdog, a git-initialized
memory archive matching the substrate's own layout, and the
orchestration/guardrail scaffolding in one pass. If a required
dependency like a container runtime is missing, the installer tells
you exactly what to install and exits, rather than installing anything
on your system without asking. The self-healing watchdog is an
optional, pluggable step — you can skip it entirely if you don't want
it. The installer itself is built, tested, and closed; the only
remaining gap before release is the release decision itself.
