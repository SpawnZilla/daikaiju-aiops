# Check Alerts: the human review loop

*One phrase from the operator turns every alert since the last review into a colour-coded report, has the planning agent fix what it can reach, and leaves a short list for a human.*

## Where it sits

Check Alerts is the review loop at the end of Daikaiju AIOps' detection layers: the uptime monitor, the port watcher, the watchdog, the scheduled health checks and the incident loop. It catches two things those layers leave over: alerts that were raised but not fixed, and failures that no layer sees at all.

The second kind is the reason it exists. In its first real run, a service reported healthy by its container check had been dead in function for 13 days, because a status file it depends on was missing. Nothing alerted. The report surfaced it, it was fixed, and a dedicated detector and a known-fix script were added so it does not need a human next time.

Every item in a run ends in one of three states: fixed and proven, handed to the operator with an exact command, or accepted on purpose.

## The process

1. The operator says "check alerts".
2. Mokaima runs the report script. It reads the alert history since the last run, the incident loop's records and the port watcher's state, prints the first report and moves the last-run marker.
3. Mokaima fixes every red item on its own, without waiting. For each one it confirms the failure is real, runs the known fix or follows the no-known-fix process, and then re-checks the original symptom itself. A fix script passing its own check is not accepted as proof.
4. Each proven fix is recorded, so the item shows green in the next report.
5. Anything it could not fix or could not reach becomes a yellow, with the exact command, the host to run it on and what the command does to the machine.
6. A second report (same script, marker not moved) shows what is left.
7. The operator and Mokaima work the yellows together.
8. Each white item gets a command that closes the blind spot, or is accepted on purpose.
9. An item that keeps coming back gets a root-cause fix, not another restart. A recurring cause with no fix script yet becomes a new known-fix script in the same session.

## The colour model

| Colour | Meaning | Who acts | Next step |
|---|---|---|---|
| Red | Not fixed: a monitor's last state is down, or a check failed with no clean re-run | Mokaima, autonomously, right after the first report | Fix and prove; if it cannot be fixed or reached it becomes yellow |
| Yellow | Needs a human: a decision, a command on a host Mokaima cannot reach, an unreviewed draft, a capped incident | Operator and Mokaima together | Mokaima supplies the command and its effect; the operator runs it or decides |
| Green | Fixed or recovered, with how | Nobody | None; shown so the run can be audited |
| White | Could not be checked from where Mokaima runs | Operator and Mokaima | Run the supplied command to close the blind spot, or accept it on purpose |

A red item also shows how long it has been down and whether a known-fix script exists for it.

## What the report contains

The report opens with the time window, the count per colour and how far back the alert history reaches. Then one line per item, sorted red, yellow, green, white, followed by:

| Section | What it shows |
|---|---|
| What was done | Incident loop activity since the last run: incidents opened, fix scripts run, results |
| Current state (live) | Live reachability of each service; white, with the command to run, when the report cannot reach it |
| Repeat offenders | Items that alerted two or more times: candidates for a root-cause fix |
| Missing alerts | Scheduled alerts that should have arrived and did not, or fell before the history window |
| Suspend windows | Times the main host was asleep, when no alert could be delivered |
| Alert plumbing | Whether the alert path itself works: history readable, port watcher fresh, incident orchestrator updated, watchdog state |

Three small state files carry information between runs: the last-run marker, a list of acknowledged yellow items, and a list of fixed items with the time and how. An item turns green when its recorded fix is later than its last failure, and turns red again by itself if it fails again.

## Guardrails for autonomous fixes

- Confirm the failure is real before touching anything; re-check it live.
- Use the known fix script when one exists. When none exists, diagnose, build and test a fix script in staging, and have the operator deploy it. Never improvise a one-off change on a live system.
- Prove the fix by re-checking the original symptom.
- Check the drive and kernel log before any restart that depends on storage.
- Never delete files that belong to the system, the pipeline or the memory vault. Never run a destructive network or storage command.
- Never write directly into a live code directory; stage the change and let the operator deploy it.
- Cap repeated fixes: a fix that has run several times in a day stops and becomes yellow.
- A decision that cannot be undone and could reasonably go either way stops the run. Mokaima prepares it and hands it to the operator.

## Limits

The "fix reds on its own" step stops at what Mokaima can reach. From its own workspace it cannot reach the services on the main host or the edge host, so live checks and fixes there are yellow items with a command. The fix scripts that run on the edge host are executed by a signed-ticket runner that accepts only scripts on a root-owned allowlist, so a new script is inert until the operator adds its line.

The alert history covers about one day, so "missing alert" checks older than that are white by design. Detection gaps also limit what "autonomous" can mean: a watchdog that reacts to exited containers and failed health checks will not see a service that is healthy by container check and dead by function. Those failures need a dedicated detector.

## Status

See [Status & Roadmap](status.md). The process is documented here and has been run for real; the report script is not part of the published package yet.
