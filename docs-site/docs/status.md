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
- The installer for the packaged bundle (Kaiju Spine) — built, tested
  across multiple clean-environment rounds, closed.
- Distro portability to Arch Linux and Fedora 44 Cloud Base, alongside Debian/Ubuntu: minimal path tested on both; real model pull verified on Fedora only. RHEL/CentOS, Fedora Workstation/Server and non-systemd distros remain untested/out of scope.
- Clean-VM re-run of the installer on the renamed Kaiju Spine tree,
  2026-10-31: five of six rounds passed (Ubuntu 24.04 full and minimal,
  Debian 13, Arch and Fedora 44 Cloud Base, minimal). The full path on
  Ubuntu 24.04 took 395 s with the log kept, on a fast connection.
  Ubuntu 22.04 installs but skips mcpo, which needs Python 3.11+ (see the
  README). The earlier 11 min 33 s run predates the rename and its log
  was not kept.
- The orchestration/guardrail automation layer — built, and has
  reached fully autonomous operation at least once in testing. Its
  trust state resets to a more supervised mode automatically any time
  a mistake is detected, by design. It returned to fully autonomous
  operation on 2026-10-10 after three supervised qualifying rounds,
  and its live state was last verified on 2026-11-04.

## Designed but not yet built

- Nothing at the moment.

## Deliberately not yet started

- Packaging the agent adapters (planning, reasoning, execution) as part of Kaiju Spine.
- This documentation site (Dossier) is a locally buildable reference;
  its GitHub Pages deployment goes live with the next push of the
  repository.

## A word on reliability claims

No AI model available today, including the most capable frontier
models, reaches anywhere close to zero fabrication on hard, grounded
reasoning tasks. This project treats that as a permanent fact to
design around, not a temporary limitation to wait out — which is why
the guardrail and self-healing layers get engineering attention
proportional to the agent layer itself, rather than being an
afterthought bolted on at the end.
