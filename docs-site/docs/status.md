# Status & Roadmap

This project draws a hard line between "designed" and "built and
verified" everywhere else in its own internal records, and this page
keeps that same standard for anyone reading from the outside.

## Built and verified today

- The self-healing watchdog and its full failure-mode catalog — tested
  across multiple rounds against real, disposable infrastructure, not
  just reviewed on paper.
- The persistent memory/documentation layer — live, versioned, and in
  daily use.
- The installer for the packaged bundle (Kaiju OS) — built, tested
  across multiple clean-environment rounds, closed.
- Distro portability to Arch Linux and Fedora 44 Cloud Base, alongside Debian/Ubuntu: minimal path tested on both; real model pull verified on Fedora only. RHEL/CentOS, Fedora Workstation/Server and non-systemd distros remain untested/out of scope.
- The orchestration/guardrail automation layer — built, and has
  reached fully autonomous operation at least once in testing. Its
  trust state resets to a more supervised mode automatically any time
  a mistake is detected, by design. It returned to fully autonomous
  operation on 2026-10-10 after three supervised qualifying rounds,
  and its live state was last verified on 2026-10-18.

## Designed but not yet built

- A fuller clean-environment timing test of the "deployable by someone
  else in a reasonable amount of time" claim.

## Deliberately not yet started

- Public release of Kaiju OS, pending Daikaiju AIOps' own readiness.
- This documentation site's own public deployment, for the same
  reason — it exists today as a locally buildable, previewable
  reference, not a published site.

## A word on reliability claims

No AI model available today, including the most capable frontier
models, reaches anywhere close to zero fabrication on hard, grounded
reasoning tasks. This project treats that as a permanent fact to
design around, not a temporary limitation to wait out — which is why
the guardrail and self-healing layers get engineering attention
proportional to the agent layer itself, rather than being an
afterthought bolted on at the end.
