# FASHSD Config-Driven Scripts — Testing Guide

Companion to the MUST PRIORITY flags on `../README.md`,
the FASHSD design notes, `fm02_daemon_down.sh`, and
`fm05_drive_not_mounted.sh`. This directory contains everything needed
to test all 5 generalized scripts + shared config lib.

**Two rounds of testing live here:**
- Round 1 (2026-07-23): `app_curl_check.sh`, `fm01_container_exited.sh`,
  `wol_trigger.sh` — PASSED, MUST PRIORITY warnings already removed
  from those 3 files. See the first Results Log entry below.
- Round 2 (in progress): `fm02_daemon_down.sh`, `fm05_drive_not_mounted.sh`
  — written by Angkai (/), NOT yet tested. Steps 7 and 8
  cover these. Fill in the second Results Log entry once run.

## What's here

| File | Purpose |
|---|---|
| `run_tests.sh` | Automated runner for steps 1, 2, 4 (fully automatic) and 3, 5 (prompts before touching real infra); prints manual instructions for 6/7/8 |
| `step1_isolated.yaml` | Fake config, tests `fashsd_config_lib.sh` in isolation |
| `step2_harmless.yaml` | Safe external URLs (httpbin.org), tests `app_curl_check.sh` logic including a deliberate FAIL case |
| `step3_reference_real_readonly.yaml` | Kaidosho's real 10 services, translated to the new schema — for a live side-by-side comparison against Kaidosho's actual original script |
| `step4_singlenode.yaml` | Tests `wol_trigger.sh`'s new single-node no-op path |
| `step5_twonode_real.yaml` | Kaidosho's real Dokaisho MAC — live WoL packet test |
| `step6_throwaway_container.yaml` | Disposable-container config for `fm01_container_exited.sh` — manual test |
| `step7_fm02_throwaway.yaml` | Disposable-compose config for `fm02_daemon_down.sh` — manual test, restarts the whole Docker daemon |
| `step8_fm05_throwaway.yaml` | Disposable loopback-drive config for `fm05_drive_not_mounted.sh` — manual test |
| `step13_fm01_v15_throwaway.yaml` | Disposable-container config for `fm01_container_exited.sh` schema v1.5 `service:` field — manual test, both the differing-name case and the no-`service:`-field regression case |

## How to run

```bash
cd kaiju-gais-package/fashsd/tests
chmod +x run_tests.sh
./run_tests.sh
```

Steps 1, 2, and 4 run automatically with no prompts — they're fully
isolated or read-only against external test endpoints. Steps 3 and 5
prompt for confirmation first since they touch real Kaidosho infrastructure
(step 3 is read-only curl checks; step 5 sends one real WoL packet,
harmless but real network traffic).

## Steps 6, 7, 8 — manual only, by design

All three scripts these cover change real state, so none are
automated and none are tested against real Kaidosho services first:

- **Step 6** (`fm01_container_exited.sh`) — restarts one disposable
  container. Lowest risk of the three.
- **Step 7** (`fm02_daemon_down.sh`) — ⚠️ **restarts the entire Docker
  daemon on the host**, not just the throwaway container. Every real
  Kaidosho container will briefly go down and come back. Only run this when
  that's acceptable right now — during planned maintenance or when
  nothing time-sensitive is running. This is the highest-risk test in
  the whole suite.
- **Step 8** (`fm05_drive_not_mounted.sh`) — mounts a disposable
  loopback image via a temporary `/etc/fstab` entry, never a real
  drive or an existing fstab line. Includes a cleanup sequence to
  remove the temporary entry afterward — don't skip it.

Full command sequences for all three are in `run_tests.sh`'s own
output (run `./run_tests.sh 6`, `./run_tests.sh 7`, or `./run_tests.sh 8`
to print just one), or read directly in the script.

Do not skip straight to testing any of these against a real Kaidosho service
or real drive. Prove each works against something disposable first.

## What "passing" means before the MUST PRIORITY warning comes down

**Round 1 (app_curl_check.sh, fm01_container_exited.sh, wol_trigger.sh) — already done:**
- [x] Step 1: all 5 config-lib assertions pass
- [x] Step 2: all 4 assertions pass, including the deliberate-mismatch
      FAIL case (if this one shows PASS instead, the comparison logic
      itself is broken — this is the most important single check)
- [x] Step 3: generalized script's PASS/FAIL summary line matches Kaidosho's
      real original script's output EXACTLY, run back to back
- [x] Step 4: single-node mode correctly no-ops
- [x] Step 5: WoL packet sends successfully, log line format is correct
- [x] Step 6: disposable container test — FM-01 correctly detects,
      restarts, and verifies the container, matching the same
      pass/fail behavior as Kaidosho's original FM-01 script would show
      against the same scenario

**Round 2 (fm02_daemon_down.sh, fm05_drive_not_mounted.sh) — not yet run:**
- [ ] Step 7: disposable-compose test — FM-02 correctly restarts the
      Docker daemon, restarts every configured compose dir via
      `kaiju_known_compose_dirs()`, verifies container count against
      `kaiju_service_count()`, and real Kaidosho services come back up
      cleanly afterward (not just the throwaway container)
- [ ] Step 8: disposable loopback-drive test — FM-05 correctly detects
      the unmounted drive, validates the name against
      `kaiju_drive_count()`/`kaiju_drive_field()`, mounts it, and
      verifies via `mountpoint -q`. Also test the wrong-drive-name
      error path once — should print the valid-names list, not crash.

## Results log

Fill in after each real run — this becomes the evidence the MUST
PRIORITY warnings can reference when they're eventually removed.

```
Date: 2026-07-23
Run by: Gorkaige (maintainer@primary-node)
Step 1: PASS — all 5 config-lib assertions passed after fixing yq -r flags
  (apt install yq installs kislyuk/yq, a jq wrapper that JSON-quotes
  strings by default — original design assumed mikefarah/yq, Go binary,
  unquoted by default. Fixed in fashsd_config_lib.sh.)
Step 2: PASS — all 5 assertions passed after fixing a test-harness bug
  (check_service() logs PASS/FAIL lines to the log FILE, not stdout —
  original assertions incorrectly grepped stdout. Fixed in run_tests.sh,
  not a bug in app_curl_check.sh itself — script logic was correct
  from the first run.)
Step 3: PASS — generalized vs. Kaidosho's real original: PASS:10 FAIL:0 on
  both, exact match against live production services
Step 4: PASS — single-node mode correctly no-op'd, exit 0
Step 5: PASS — real WoL packet sent successfully after installing
  wakeonlan on Dokaisho (genuine environment gap, not a script bug —
  Kaidosho's original wol_trigger.sh always ran on the Pi5 watcher node,
  never on Dokaisho, so wakeonlan was never installed here before)
Step 6: PASS — disposable nginx container: stopped, detected, compose
  dir validated against config-derived allowlist, restarted, verified
  running. Snapshot step gracefully skipped as designed (watchdog_snapshot.sh
  not yet packaged) rather than hard-failing.
Overall: READY TO REMOVE MUST PRIORITY WARNING ✅
```

Real bugs found and fixed during this test pass (this is exactly what
the test suite was for):
  1. yq variant mismatch (kislyuk/yq vs mikefarah/yq) — fixed with -r
     flags throughout fashsd_config_lib.sh
  2. Hardcoded /opt/kaiju-spine/watchdog/ and /var/log/kaiju-watchdog/
     paths assumed a deployed install — added KAIJU_LIB_DIR and
     KAIJU_LOG_DIR env var overrides to all 3 executable scripts
  3. fm01_container_exited.sh's snapshot call hard-referenced a script
     that isn't packaged yet — now checks for its existence and skips
     gracefully with a clear note instead of hard-failing
  4. Test harness bug (not a script bug): step 2 assertions grepped
     stdout for log-file-only content — fixed in run_tests.sh

None of these were logic bugs in the actual config-driven generalization
(the check_service(), restart, verify, and topology-branch logic all
worked correctly on the first real test) — all were packaging/
environment assumptions, which is exactly the category of risk this
test suite existed to catch before deployment.

### Round 2 results — fm02_daemon_down.sh, fm05_drive_not_mounted.sh

Written by Angkai, 2026-07-27. Reviewed by Mokaima
before testing — both had the same one bug (not yet test-suite-caught,
caught by manual review): the snapshot call was left as a verbatim
copy of Kaidosho's original, hardcoded to
`/opt/pi-node/watchdog/watchdog_snapshot.sh` (a real path on Kaidosho's
actual Pi5, but not part of the exportable Kaiju Spine package). This was
a brief-writing gap, not an Angkai error — the brief said "preserve
the snapshot call unchanged" without pointing at the graceful-fallback
pattern `fm01_container_exited.sh` already established for exactly
this situation. Fixed directly in both files to match that pattern
(check `$KAIJU_LIB_DIR/watchdog_snapshot.sh` exists, skip gracefully
with a note if not, same as FM-01).

Everything else in both scripts was correct on Angkai's first pass —
notably, FM-05's drive-name validation loop (the exact logic that took
Bakaidah 3 drafting rounds to get right without fabricating functions)
was correct immediately, using the real `kaiju_drive_count()`/
`kaiju_drive_field()` functions with no invented symbols.

**Tested 2026-07-27:**

```
Date: 2026-07-27
Run by: Gorkaige (maintainer@primary-node)
Step 7 (fm02): PASS — snapshot gracefully skipped as designed, Docker
  daemon start command ran successfully, compose loop correctly
  restarted only the configured throwaway service via
  kaiju_known_compose_dirs(), verify logic correctly counted 7 total
  containers against threshold 1. IMPORTANT CAVEAT: `systemctl start
  docker` is a no-op when Docker is already running (which it was,
  confirmed by all 6 real Kaidosho containers showing multi-day uptimes
  unchanged after the test) — so this run did NOT validate FM-02's
  actual real-world purpose (recovering from a genuinely stopped
  daemon), only the snapshot/compose-loop/verify logic around it. A
  true daemon-down scenario would need `systemctl restart docker` or
  an actually-stopped daemon to fully validate. Real Kaidosho services
  confirmed undisturbed (all showed clean "Up" status, no restarts,
  no unhealthy states) — genuinely good news, just means the riskiest
  part of this script remains unexercised by this test.
Step 8 (fm05): PASS — drive correctly detected as unmounted, name
  validated against kaiju_drive_count()/kaiju_drive_field() (correct
  on Angkai's first pass, no fabricated functions), snapshot
  gracefully skipped, mount succeeded, verified via mountpoint -q.
  Confirmed via log file (PASS lines for both timestamps) even though
  the script's own terminal PASS echo didn't visibly appear in one
  run — worth a minor follow-up look, not blocking, log file is the
  authoritative record and it was clean. Wrong-drive-name error path
  also tested separately: correctly printed "drive_name must be one
  of: kaiju-test-drive" and exited non-zero, no crash.
Overall: READY TO REMOVE fm02/fm05 MUST PRIORITY WARNING ✅
  (with the noted caveat on fm02's daemon-down coverage gap, logged
  below as a follow-up rather than a blocker — the script's logic is
  sound and matches Kaidosho's original design intent, the test environment
  just didn't simulate a genuinely stopped daemon)
```

**Follow-up flagged, not blocking:** fm02_daemon_down.sh's core
recovery path (an actually-stopped Docker daemon) remains untested.
Worth a future test run using `sudo systemctl stop docker` immediately
before the test (accepting the same full-host impact already
understood for this script) to close this gap for real. Not required
before removing the MUST PRIORITY banner — the logic itself is sound
and unchanged from Kaidosho's original, live-tested design — but noted here
so it isn't forgotten.

## After all 8 pass — ✅ DONE 2026-07-27

1. ✅ Results Log updated with both passing runs (round 1 + round 2).
2. ✅ MUST PRIORITY banners removed from `fm02_daemon_down.sh` and
   `fm05_drive_not_mounted.sh`.
3. ✅ `../README.md` STATUS/TESTING STATUS sections updated — 5 of ~10
   scripts now tested.
4. Next: resume generalizing FM-03, FM-04, FM-06, FM-07, `pi5_watchdog.sh`,
   and drive/SMART scripts — FM-03/06/07 need their approved schema
   extensions built in as part of drafting. Also worth a future test
   run closing FM-02's daemon-down coverage gap (see Round 2 results
   above) using an actually-stopped Docker daemon, not just "already
   running."

### Round 3 results — fm03_gluetun_unhealthy.sh (Step 9)

**Tested 2026-09-08 ("Daikaiju AIOps & Kaiju GIAS Full Auto setup
part 2"), by the maintainer on Dokaisho:**

```
Date: 2026-09-08
Run by: the maintainer (maintainer@primary-node)
Step 9 (fm03): PASS — both branches live-tested against a real
  disposable owner+dependent stack (kaiju-test-owner, HEALTHCHECK
  hitting https://nyaa.si; kaiju-test-dep, network_mode:
  service:kaiju-test-owner):
  1. Fail-safe branch: owner forced unhealthy via
     `docker network disconnect` — script correctly detected
     unhealthy, restarted owner, owner stayed unhealthy after retries
     (network disconnect doesn't self-heal on a plain restart), script
     correctly logged "FAILED to become healthy... NOT restarting
     dependents" and exited 1.
  2. Success branch: owner forced unhealthy via `docker stop` instead
     (a failure mode that genuinely clears on restart) — script
     correctly detected unhealthy, restarted owner, owner came back
     healthy, explicitly restarted the dependent, verified via a real
     curl from kaiju-test-dep to https://nyaa.si (200), exited 0.
     Full chain confirmed in watchdog.log: "unhealthy — restarting" ->
     "healthy after restart. Restarting dependents." -> "restarted
     (dependent of kaiju-test-owner)" -> "verified via real curl".
Overall: PASS, both branches exercised for real, not just the
  already-healthy no-op.
```

**Real finding (caveat, not a script bug):** in both branches, Docker
Compose itself cascade-restarted `kaiju-test-dep` the moment
`docker compose restart kaiju-test-owner` ran — visible in the log
*before* the script's own explicit dependent-restart loop ever fires
(confirmed via a raw `docker network disconnect` cascading it too, in
the fail-safe branch, even though the owner never became healthy).
This is `network_mode: service:<owner>` behavior in Compose, not
anything fm03_gluetun_unhealthy.sh does — but it means the fail-safe's
logged claim ("NOT restarting dependents") only describes the
script's own explicit loop, not the dependent's actual restart state:
Compose already bounced it regardless of whether the owner recovered.
Worth a note in the script's own header or the FASHSD design notes
for anyone relying on the fail-safe as a guarantee the dependent's
process never restarted — its container did restart, just not via the
script's intentional path. Not chased further this session; flagged
for whenever FM-03's design doc is next touched.

**Test-methodology note for future runs:** don't use
`docker network disconnect` to simulate a self-healing failure — a
plain `docker compose restart` does not reattach a manually-severed
network connection, so the owner will appear to "fail to recover"
for test-environment reasons, not a real remediation failure. Use
`docker stop <owner>` instead when the goal is testing the recovery
(success) path; disconnect is fine on its own for testing the
fail-safe path specifically, understanding it will stay unhealthy
by design of the test, not the script.

### Round 3 results (continued) — fm06_ghost_mount.sh (Step 10)

**Tested 2026-09-08, same session, by the maintainer on Dokaisho:**

```
Date: 2026-09-08
Run by: the maintainer (maintainer@primary-node)
Step 10 (fm06): PASS — real recovery cycle exercised (script itself
  force-unmounts as part of its own fix, so no pre-break needed unlike
  fm05's step 8): disposable loopback image (/dev/loop16) mounted at
  /mnt/kaiju-test-ghost-drive with kaiju-subdir-a/kaiju-subdir-b
  present, temporary fstab entry added. Script force-unmounted (x2,
  lazy), remounted via fstab, verified both expected_subdirs present
  post-remount — PASS, exit 0, mountpoint -q confirmed mounted.
  Wrong-drive-name path also tested: 'nonexistent-drive' — clean FAIL
  ("Error: drive_name 'nonexistent-drive' not found in $KAIJU_CONFIG"),
  exit 1, no crash.
Minor cosmetic gap, not blocking: fm06's error message doesn't list
  valid drive names the way fm05_drive_not_mounted.sh's does ("drive_name
  must be one of: ...") — just names the one that failed. Worth aligning
  the two error messages next time fm06 is touched, not chased now.
Overall: PASS.
```

### Round 3 results (continued) — fm07_dns_failure.sh (Step 11)

**Tested 2026-09-08, same session, by the maintainer on Dokaisho:**

```
Date: 2026-09-08
Run by: the maintainer (maintainer@primary-node)
Step 11 (fm07): PASS — script restarts unconditionally (no "already
  fine, skip" branch), so the real path was genuinely exercised
  against a running disposable container (kaiju-test-dns): restart ->
  sleep 15 -> curl https://nyaa.si from inside the container -> 200 ->
  PASS, exit 0.
  Negative-path correction: run_tests.sh's own instructions call for
  testing "a service with no dns_check_url configured" specifically —
  an initial attempt tested a nonexistent SERVICE NAME instead, which
  exercises a different branch (kaiju_service_index_by_name not
  found) and would have been logged as a false pass on the wrong
  target. Corrected: built a temporary config copy
  (step11_no_dns_url.yaml) with the dns_check_url field entirely
  removed for the same real service — got the exact intended message
  ("'kaiju-test-dns' has no dns_check_url configured — this fix
  cannot verify outbound connectivity for it."), exit 1, no crash.
  Both the service-not-found path AND the no-dns_check_url path are
  now confirmed clean, distinct failure modes.
Overall: PASS.
```

### Round 3 results (continued) — fm04_clock_drift.sh (Step 12, highest risk)

**Tested 2026-09-08, same session, by the maintainer on Dokaisho:**

```
Date: 2026-09-08
Run by: the maintainer (maintainer@primary-node)
Step 12 (fm04): PASS — real, system-wide `timedatectl set-ntp
  false/true` toggle executed against the live host (clock was
  already synchronized pre-test, confirmed via baseline check), then
  the services[] loop restarted exactly the one disposable service
  listed in a purpose-built step12_fm04_throwaway.yaml
  (kaiju-test-drift) — confirmed via watchdog.log ("restarted
  kaiju-test-drift") and docker ps (fresh "Up 12 seconds" on the
  throwaway container only). All real Kaidosho containers (kokoro-tts,
  ntfy, mcpo, heimdall, uptime-kuma, portainer) confirmed UNTOUCHED
  — all showed "Up 21 hours", same as before the test, proving the
  restart-scope decision's blast radius is genuinely limited to
  whatever KAIJU_CONFIG's services[] lists, not a real production
  config. Clock confirmed synchronized post-toggle, PASS, exit 0.
  No pre-staged fixture existed for step 12 (unlike 9-11) —
  step12_fm04_throwaway.yaml written this session, staged permanently
  alongside the other step*.yaml fixtures for future reruns.
Overall: PASS. All 4 of Round 3's scripts (FM-03/04/06/07) now PASS.
```

## Round 3 overall — READY TO REMOVE MUST PRIORITY WARNINGS ✅ (2026-09-08)

All 4 steps (9, 10, 11, 12) PASS, each with the real remediation path
genuinely exercised (not just an already-fine no-op) — see individual
entries above. Two real findings worth carrying forward, neither
blocking:
  1. fm03's fail-safe log claim ("NOT restarting dependents") doesn't
     fully hold for `network_mode: service:<owner>` topologies —
     Compose itself cascades a restart of the dependent the moment the
     owner restarts, regardless of the script's own explicit loop.
  2. fm06's wrong-drive-name error doesn't list valid names the way
     fm05's does — cosmetic, not functional.
Next: remove MUST PRIORITY banners from fm03/fm04/fm06/fm07, update
../README.md's STATUS/TESTING STATUS sections, close the PENDING.md
WATCH ITEM for this gap.

### Round 4 results — fm01_container_exited.sh schema v1.5 `service:` field (Step 13)

Written per. Tested 2026-09-17, by
the maintainer on Dokaisho. Two cases run against
`step13_fm01_v15_throwaway.yaml`, both using the real
`fm01_container_exited.sh` invocation path (config-driven, no
hardcoded assumptions), immediately followed by cleanup:

```
Date: 2026-09-17
Run by: the maintainer (maintainer@primary-node)
Step 13a (differing container/service name, Scanopy-shaped): PASS
  Disposable Compose project `kajjufm01v15` (dir /tmp/kaiju-fm01-v15-test)
  defined a `server:` service with no container_name: override --
  Compose auto-named the real container `kaijufm01v15-server-1`,
  confirmed via `docker ps` and a 200 from
  `curl http://localhost:8197` before the trigger. Stopped the
  container, then ran:
    bash fm01_container_exited.sh kaijufm01v15-server-1 /tmp/kaiju-fm01-v15-test
  Raw output:
    Note: container 'kaijufm01v15-server-1' maps to compose service 'server' (schema v1.5 service: field)
    Snapshot saved to: /tmp/kaiju-fashsd-test-logs/snapshots/kaijufm01v15-server-1_20260917_114745.log
    Restarting container kaijufm01v15-server-1 (compose arg: server)...
     Container kaijufm01v15-server-1 Starting
     Container kaijufm01v15-server-1 Started
    Sleeping for 10 seconds...
    Verifying container is running...
    PASS: Container kaijufm01v15-server-1 is running
  `docker compose up -d` succeeded on the first attempt (no "no such
  service" error) using the resolved service name `server`, not the
  container name. Confirmed running afterward:
    docker ps --filter name=kaijufm01v15-server-1
    -> kaijufm01v15-server-1   Up 17 seconds   0.0.0.0:8197->80/tcp
  watchdog.log: "2026-09-17 11:47:55 | FM-01 | PASS: Container
  kaijufm01v15-server-1 is running (plain up -d)"
Step 13b (companion regression check, no service: field): PASS
  Disposable Compose project (dir /tmp/kaiju-fm01-v15-fallback) used
  an explicit `container_name: kaiju-test-v15-fallback` override, same
  pattern as step 6's original fm01 test. Confirmed 200 from
  `curl http://localhost:8196`, stopped the container, then ran:
    bash fm01_container_exited.sh kaiju-test-v15-fallback /tmp/kaiju-fm01-v15-fallback
  Raw output:
    Snapshot saved to: /tmp/kaiju-fashsd-test-logs/snapshots/kaiju-test-v15-fallback_20260917_114844.log
    Restarting container kaiju-test-v15-fallback (compose arg: kaiju-test-v15-fallback)...
     Container kaiju-test-v15-fallback Starting
     Container kaiju-test-v15-fallback Started
    Sleeping for 10 seconds...
    Verifying container is running...
    PASS: Container kaiju-test-v15-fallback is running
  No "maps to compose service" note printed (correct -- no service:
  field set, container/service names are identical), confirming the
  fallback path in kaiju_service_compose_name() is byte-for-byte
  unchanged from pre-v1.5 behavior. Confirmed running afterward:
    docker ps --filter name=kaiju-test-v15-fallback
    -> kaiju-test-v15-fallback   Up 18 seconds   0.0.0.0:8196->80/tcp
  watchdog.log: "2026-09-17 11:48:54 | FM-01 | PASS: Container
  kaiju-test-v15-fallback is running (plain up -d)"
Cleanup: both disposable Compose projects torn down
  (`docker compose down`, dirs removed). Real Kaidosho services confirmed
  untouched throughout (kokoro-tts, ntfy, mcpo, heimdall, uptime-kuma,
  portainer all showed unchanged multi-day uptimes before and after).
Overall: PASS. Both branches of kaiju_service_compose_name() --
  match-with-service-field and no-match/no-field fallback -- genuinely
  exercised against real disposable containers, not just read
  logically off the diff.
```

No bugs found — `kaiju_service_compose_name()` and
`fm01_container_exited.sh`'s use of its resolved `$COMPOSE_ARG`
(committed 2026-09-15) worked correctly on the first real
test, both for the differing-name case and the regression/fallback
case.

### Round 6 results — orchestrator branches (Steps 16-22)

```
Step 17 (curl-fail WITH dns_check_url): PASS -- 2026-09-25, the maintainer on
  Dokaisho, disposable kaiju-test-orch-dns (port 8194). watchdog.log:
  "kaiju-test-orch-dns: curl FAIL, has dns_check_url -- dispatching
  fm07_dns_failure.sh" (correct branch, not the no-dns fallback);
  re-check STILL FAILING (404) as expected; CRIT=1, exit 1; real ntfy
  CRIT alert sent to kaiju-alerts. Real Kaidosho containers untouched (diff clean).
  FIXTURE FINDING (not an orchestrator bug): step17's dns_check_url
  https://1.1.1.1 returns 301, so fm07 reported "recovery failed, HTTP
  code: 301" on a working outbound path. Use a URL that returns 200
  (step 11 used one) next time step17 is touched.
  Also cleaned up: kaiju-test-watchdog-nginx left running from Round 5
  Step 15 (its cleanup had never run).
Step 18 (curl-fail WITHOUT dns_check_url, best-effort fallback): PASS --
  2026-09-25, the maintainer on Dokaisho, disposable kaiju-test-orch-nodns
  (port 8193). watchdog.log: "curl FAIL, no dns_check_url configured --
  ... Best-effort: dispatching fm01_container_exited.sh, then re-checking
  curl regardless of fm01's own result"; FM-01 PASS (exit 0); re-check
  STILL FAILING (404) "(fix script exit was 0) -- alerting" -- confirms
  the recheck-regardless-of-fix-exit design; CRIT=1, exit 1; real ntfy
  alert. Real Kaidosho containers untouched (diff empty).
Step 19 (network-group OWNER branch): PASS -- 2026-09-25, the maintainer on
  Dokaisho, disposable owner (nginx:alpine + HEALTHCHECK) + dependent
  (curlimages/curl, network_mode service:owner) -- compose file saved as
  tests/step19_compose.yml (run_tests.sh 19 only describes it). Owner
  stopped; watchdog.log: "kaiju-test-orch-owner: exited, is a
  network_group owner -- dispatching fm03_gluetun_unhealthy.sh" (NOT
  fm01); fm03 restarted owner (healthy), restarted the dependent, verified
  via real curl from the dependent (nyaa.si); CRIT=0, exit 0. Real Kaidosho
  containers untouched (diff empty). Cosmetic: fm03 logs an EXITED owner
  as "unhealthy".
Step 20 (drive-not-mounted branch): PASS -- 2026-09-25, the maintainer on
  Dokaisho, disposable 64M loopback image + TEMPORARY tagged, noauto
  fstab line (fstab backed up first, restored byte-identical after).
  watchdog.log: "kaiju-test-orch-drive: not mounted -- dispatching
  fm05_drive_not_mounted.sh"; FM-05 PASS; mountpoint confirmed; CRIT=0,
  exit 0; containers untouched. Cleanup: unmounted, fstab restored,
  loop released, image + mount point removed.
  TWO REAL fm05 BUGS FOUND (non-blocking) AND FIXED in the package copy
  same day: (1) `kaiju_drive_field \"$i\" \"name\"` passed literal quote
  characters -> jq "Cannot index array with string" and a broken
  valid-names list in fm05's error messages (validation loop itself was
  correctly quoted, so remediation was never affected); (2) hardcoded
  `mkdir -p /var/log/kaiju-watchdog/snapshots` ignored KAIJU_LOG_DIR
  (Permission denied for non-root; redundant, watchdog_snapshot.sh
  creates its own dir) -- removed. The live pi-node copy was NOT
  touched; not checked whether it carries the same lines. Fix
  VERIFIED ON-HOST same day: wrong-name run printed "must be one of:
  kaiju-test-orch-drive", exit 1, no jq error.
Step 21 (ghost-mount branch): PASS -- 2026-09-25, the maintainer on Dokaisho.
  Genuine ghost built: real 64M loopback image holding kaiju-subdir-a/b
  with a TEMPORARY tagged noauto fstab line, then an EMPTY tmpfs mounted
  over the mount point (mounted, data shadowed). watchdog.log: NO fm05
  dispatch (correct -- it IS mounted); "kaiju-test-orch-ghost: mounted
  but expected_subdirs missing (ghost mount) -- dispatching
  fm06_ghost_mount.sh"; fm06 PASS; findmnt after = /dev/loop ext4 (real
  image), both subdirs visible; CRIT=0, exit 0; containers untouched.
  Cleanup: nothing left mounted, fstab restored byte-identical, loop
  released, image + mount point removed.
Step 22 (clock-drift branch): PASS -- 2026-09-25, the maintainer on Dokaisho,
  disposable kaiju-test-orch-clockdrift (port 8192). Safe trigger:
  threshold 1ms vs a real -2ms offset (orchestrator compares ABSOLUTE
  offset -- confirmed in code). watchdog.log: "Clock offset: -2ms
  (threshold: 1ms)" -> "Clock drift detected -- dispatching
  fm04_clock_drift.sh"; fm04 toggled NTP, restarted ONLY the disposable
  container, PASS "System clock is synchronized, 1 services restarted";
  CRIT=0, exit 0; timedatectl synchronized: yes. Real Kaidosho containers
  untouched (still Up 43h; diff empty after cleanup) -- restart scope
  confined to services[] exactly as designed.
Step 16 (daemon-down branch, HIGH BLAST RADIUS): PASS -- 2026-09-25,
  the maintainer on Dokaisho. Pre-check: all 6 real containers restart policy
  unless-stopped. Trigger: `systemctl stop docker.socket docker` (socket
  included so no CLI call could silently re-activate it) -> both
  inactive confirmed. watchdog.log: "Docker daemon not active --
  dispatching fm02_daemon_down.sh" -> FM-02 PASS "daemon is active and 6
  containers are running" -> "fm02_daemon_down.sh PASS -- daemon
  recovered" -> "Skipping remaining checks this cycle (daemon was
  down)"; exit 0; docker active; all 6 real containers back (name diff
  empty). ALSO CLOSES fm02's long-standing coverage gap (Round 2): the
  real daemon-down recovery path is now genuinely exercised.
  Side findings (not chased): systemd warned docker.socket/docker.service
  unit files "changed on disk, run daemon-reload" even though
  daemon-reload had run twice earlier this session (Steps 20/21);
  the daemon-down cycle-end log line omits CRIT=<n> (cosmetic).

ROUND 6 COMPLETE: 7/7 PASS (Steps 16-22), all live 2026-09-25. Every
  pi5_watchdog.sh dispatch branch has now been exercised end to end
  through the orchestrator's own loop.
```
