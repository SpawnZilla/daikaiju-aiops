# Kaiju Spine

Kaiju Spine is the installable part of Daikaiju AIOps: the orchestration
and guardrail layers packaged together with the Kaiju GAIS substrate they
run on, so someone else can stand up the same pattern on their own
hardware. It is a part of Daikaiju AIOps, not a separate product and not
the whole of it.

## What it is

In the brain / heart / spine picture, Daikaiju AIOps is the brain,
Kaiju GAIS is the heart, and Kaiju Spine is what carries work between
them with a check at every handoff. It is a software stack for
Debian/Ubuntu, Arch and Fedora, not an operating system.

## What it does

It lets someone run the same self-healing, orchestrated, guardrailed
agent pattern on their own hardware, under their own naming, without
adopting this specific project's infrastructure or branding.

## How it's used

1. Clone the repository, then run `install.sh` as a normal user.
2. Point it at your own services (a small configuration file
   describing what you're running).
3. Plug in your own local reasoning model.
4. Leave the self-healing watchdog running on a timer.
5. Review and approve escalated fixes at your configured autonomy
   level — manual review by default.

## How it does it

The installer sets up the self-healing watchdog, a git-initialized
memory archive matching the substrate's own layout, and the guardrail
scaffolding in one pass. If a required dependency like a container
runtime is missing, the installer tells you exactly what to install and
exits, rather than installing anything on your system without asking.
The self-healing watchdog is an optional, pluggable step — you can skip
it entirely if you don't want it.

## What is and isn't in this repository

The installer, the guardrail standard (MABS), the memory vault layout
and the watchdog are here and tested. The agent adapters that connect
your own planning, reasoning and execution agents are not packaged yet.
See [Status & Roadmap](status.md).
