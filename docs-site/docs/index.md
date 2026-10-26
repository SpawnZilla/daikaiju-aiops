# Kaidosho

Autonomous, self-healing agentic infrastructure operations — built
from the ground up as a real, running system, not a demo.

Kaidosho is the umbrella brand. **Daikaiju AIOps** is the product
underneath it — the actual running system these docs describe, and the
agent harness you work through to operate it.

## The short version

Most self-hosted infrastructure either runs unattended and silently
breaks, or gets babysat by a human checking dashboards. Daikaiju AIOps
takes a third path: a stack of software agents that plan, execute,
self-heal, and remember — closing the loop without a human standing in
the middle for routine problems, while keeping a human in the loop for
anything that genuinely needs judgment.

## The three layers, in one sentence each

- **[Daikaiju AIOps](daikaiju-aiops.md)** is the brain — the agents
  that reason about problems and act on them.
- **[Kaiju GAIS](kaiju-gais.md)** is the heart — the self-healing,
  memory-keeping, replicable substrate that keeps the whole system alive.
- **[Kaiju Spine](kaiju-spine.md)** is the spine — the orchestration and
  guardrails that carry work between the brain and the rest of the
  system, with a check at every handoff. It is a separately
  packaged part of Daikaiju AIOps. The installer is released; the agent
  adapters are not packaged yet.

## Why this is different from "just automate it with a cron job"

Automated scripts fix what they were written to fix. The interesting
failures are the ones nobody anticipated. Daikaiju AIOps' answer isn't
a bigger script — it's a reasoning agent that can look at an
unanticipated problem, draft a proposed fix, have that fix mechanically
checked for fabrication and safety before anything touches production,
and only then execute it. No AI model — including today's best
frontier models — reaches anywhere close to zero fabrication on hard,
grounded reasoning tasks. The honest response to that fact isn't to
wait for a better model; it's to build mechanical guardrails that catch
a bad answer regardless of which model produced it. That's the actual
bet this project makes, and it's why the guardrail layer gets as much
engineering attention as the agents themselves.

See [Status & Roadmap](status.md) for an honest account of what's
actually built and running today versus what's still designed but not
yet shipped.
