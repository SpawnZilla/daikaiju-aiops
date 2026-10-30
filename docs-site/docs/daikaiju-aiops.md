# Daikaiju AIOps

*Kaiju GAIS with a brain — autonomous agents that plan, execute,
self-heal, and remember, closing the loop without a human in the
middle.*

## What it is

Daikaiju AIOps is the umbrella project and its own first shippable
package — the intelligence layer that runs on top of [Kaiju
GAIS](kaiju-gais.md)'s substrate. Where the substrate provides
self-healing, memory, and hardware, Daikaiju AIOps provides everything
with agent reasoning in it: the autonomy itself. It owns two layers
outright:

- **Orchestration Layer** — a governed multi-agent workflow. Human
  intent becomes a structured brief, a local reasoning agent drafts a
  plan, a separate execution agent carries it out, with defined
  handoff points and pause-and-approve checkpoints at every stage.
- **Guardrail Layer** — the rules, checks, and failure-mode catalogs
  that make autonomous execution trustworthy instead of terrifying.
  Nearly nobody building agentic AI systems has this part formalized —
  it's the most defensible, differentiated part of the whole project.

## The three agents

Three named agents make up the orchestration layer, each with a
distinct role:

- **Mokaima** — drafts structured briefs, coordinates the pipeline, and
  performs the final review before anything executes.
- **Bakaidah** — the reasoning agent. Analyzes a brief and drafts a
  proposed fix or response.
- **Angkai** — the execution agent. Carries out an approved plan.

## What it does

Agents plan, execute, self-heal, and remember — closing the loop
without a human acting as the messenger between steps. A human is
alerted only when something is genuinely beyond the agents' own
authorized scope or confidence.

## How it's used

By default the system runs at **manual-trigger maturity** (the orchestration
automation has also reached fully autonomous operation in testing; see
[Status & Roadmap](status.md)): a human hands
off a task, Bakaidah drafts an approach, Mokaima and a human review and
approve it, Angkai carries it out, a human reviews the result. The
target end state removes the human from that loop entirely for routine
work — approve a plan once, then get a result or an alert, not a
play-by-play.

## How it does it

The runtime pipeline runs in seven steps:

1. A watchdog (part of the substrate layer) detects a problem.
2. Known-fix triage — if it matches a documented failure mode with an
   existing automated fix, it's resolved right there, no escalation
   needed.
3. If it's novel, the system escalates: Mokaima writes a structured
   brief describing the problem and what's known about it.
4. Bakaidah works through the brief and proposes an approach.
5. Mokaima reviews the proposal — approved work moves to Angkai for
   execution, rejected work goes back for a human decision.
6. Angkai carries out the approved plan.
7. A resolution check confirms the fix actually worked, or triggers a
   retry/escalation if it didn't.

Guardrails apply at every one of those seven steps, not just at the
review gate — a chain of mechanical checks runs before, during, and
after execution, checking things like: does this touch a genuinely
authorized target, does this match what was actually approved, does
this claim cite something that's actually true, has anything changed
since the plan was made. None of these checks are prompt-level
instructions asking the agents to "please be careful" — they're
deterministic code that blocks the action outright on failure, the
same way a compile error blocks a build regardless of how confident
the programmer felt.

Persistent, versioned memory ([Kaiju GAIS](kaiju-gais.md)'s Layer 2)
feeds every one of these steps — nothing starts from zero, and every
decision leaves a record another agent (or a human) can check later.
