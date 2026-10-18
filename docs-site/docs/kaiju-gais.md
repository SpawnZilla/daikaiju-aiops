# Kaiju GAIS

*The reproducible substrate underneath Daikaiju AIOps — self-healing
infrastructure, persistent memory, and onboarding, with no agent
reasoning of its own.*

## What it is

Kaiju GAIS is the substrate of Daikaiju AIOps, made of four layers. It
has no agent reasoning of its own — it's a named part of Daikaiju
AIOps, not a standalone product. Think of it like the base image a
Linux distribution is built from: opinionated, consistent,
self-contained, but not the whole experience by itself.

## What it does

It keeps the infrastructure alive, remembering, and replicable. It
heals known failures automatically, keeps persistent memory across
sessions so nothing has to be re-learned from scratch, packages the
setup so someone else could stand up their own instance, and keeps a
consistent naming scheme that makes a complex system legible at a
glance.

## How it's used

Kaiju GAIS isn't used on its own — it's the base that Daikaiju AIOps
runs on. Day to day, the substrate mostly stays invisible: watchdog
timers run on a schedule, alerts arrive only when something needs
attention, and the memory layer works silently in the background every
time an agent reads or writes a record.

## How it does it

**Layer 1 — Self-Healing.** A watchdog running on a schedule, wired to
push-notification alerting and remote wake-on-LAN so a sleeping node
can be brought back up automatically when needed. It works from a
living catalog of known failure modes, each with its own automated
fix — container crashed, a required daemon is down, a VPN-gated
service lost its tunnel, system clock drifted, a drive isn't mounted,
DNS resolution failing for one service. On top of the failure-mode
catalog sits an application-level health check (does the service
actually respond correctly, not just "is the process running"), and
every remediation attempt takes a snapshot first so a bad fix can be
rolled back rather than compounding the original problem.

**Layer 2 — Memory/Archive.** A git-backed, cross-referenced
documentation system that every agent reads from and writes to.
Content is organized in three tiers — the things that need checking
daily, reference material that changes rarely, and working notes from
day-to-day tasks — and mirrored to more than one location so it isn't
a single point of failure. This is the layer that lets the system
actually get smarter over time instead of every session starting from
zero and repeating the same mistakes.

**Layer 3 — Onboarding/Transfer.** Documentation and templates that
let someone else replicate the whole pattern without living through
the incidents that produced it — an installer design, a portable
version of the governance protocol with project-specific incident
history stripped out, a guide for matching a reasoning model to
available hardware, and a hardware compatibility reference. This layer
is the actual difference between "a personal setup that only makes
sense to the person who built it" and "something someone else can
deploy."

**Layer 4 — Naming/Identity.** A consistent naming convention for
nodes, agents, and subsystems. A memorable, consistent metaphor scheme
makes a genuinely complex system legible at a glance — and easier to
teach to someone else.

## Reference implementation, for scale

The real running instance this project is built from and tested
against costs under $500 in hardware (renewed/refurbished components)
and $0 in software — no cloud dependency, no subscription, no vendor
lock-in for the reasoning model itself.
