# Kaiju OS FASHSD Package (config-driven)

## ✅ TESTED 2026-09-08 — all 9 scripts + shared lib
All 9 generalized scripts (`fashsd_config_lib.sh`, `app_curl_check.sh`,
`fm01_container_exited.sh`, `wol_trigger.sh`, `fm02_daemon_down.sh`,
`fm05_drive_not_mounted.sh`, `fm03_gluetun_unhealthy.sh`,
`fm06_ghost_mount.sh`, `fm07_dns_failure.sh`, `fm04_clock_drift.sh` —
note that's 10 names but `fashsd_config_lib.sh` is the shared lib, not
a standalone remediation script) have passed the full test suite
across 3 rounds. See `tests/TESTING.md` for all three results logs.
Two known gaps flagged, not blocking: FM-02's daemon-down recovery
path itself wasn't exercised in Round 2 (Docker was already running
during testing); FM-03's fail-safe log claim ("NOT restarting
dependents") doesn't fully hold for `network_mode: service:<owner>`
topologies — Compose itself cascades a restart of the dependent the
moment the owner restarts, regardless of the script's own explicit
loop, found in Round 3.

Generalized, config-driven versions of Kaidosho's FASHSD scripts. This is
the exportable/packaged version — Kaidosho's own production watchdog scripts
remain unchanged and are NOT affected by
anything in this directory.

## Status (2026-09-08)

All 9 of Kaidosho's FASHSD scripts have been generalized and tested,
confirming the pattern from the FASHSD design notes holds
across every script type (health check, fix script, WoL trigger,
daemon restart, drive mount, network-namespace remediation, ghost
mount, DNS/outbound recovery, clock drift):

| File | Generalized from | What changed | Test status |
|---|---|---|---|
| `fashsd_config_lib.sh` | (new — no Kaidosho equivalent) | Shared yq-based config reader, used by all scripts below | ✅ TESTED |
| `app_curl_check.sh` | Kaidosho's original `app_curl_check.sh` | 10 hardcoded `check_service()` calls → loop over `services[]`. Function body unchanged. | ✅ TESTED |
| `fm01_container_exited.sh` | Kaidosho's original `fm01_container_exited.sh` | Hardcoded 14-entry `ALLOWED_DIRS` array → derived from `services[].compose_dir`. Restart/verify logic unchanged. | ✅ TESTED |
| `wol_trigger.sh` | Kaidosho's original `wol_trigger.sh` | Hardcoded MAC → read from `topology.target_node.mac`. New: `single-node` mode short-circuits to a no-op instead of Kaidosho's always-two-node assumption. | ✅ TESTED |
| `fm02_daemon_down.sh` | Kaidosho's original `fm02_daemon_down.sh` | Hardcoded `ALLOWED_DIRS` → `kaiju_known_compose_dirs()` loop. Hardcoded `MINIMUM_EXPECTED_CONTAINERS=20` → `kaiju_service_count()`. Written by Angkai; Mokaima fixed one bug (hardcoded snapshot path, same class as the FM-01 fix). | ✅ TESTED (daemon-down path itself not exercised, see note below) |
| `fm05_drive_not_mounted.sh` | Kaidosho's original `fm05_drive_not_mounted.sh` | Hardcoded hola1-5 regex → `kaiju_drive_count()`/`kaiju_drive_field()` loop. Written by Angkai, correct on first pass; Mokaima fixed the same snapshot-path bug as FM-02. | ✅ TESTED |
| `fm03_gluetun_unhealthy.sh` | Kaidosho's FM-03 runbook (gluetun/network-namespace-owner remediation) | Hardcoded owner/dependent restart → `kaiju_network_group_*` functions, real schema (owner/dependents/compose_dir/verify_via). | ✅ TESTED (Round 3, 2026-09-08) — both the fail-safe branch and the real restart/verify success path exercised live; see gap note above re: Compose's own dependent cascade |
| `fm06_ghost_mount.sh` | Kaidosho's hola3-only ghost-mount fix | Hardcoded `/mnt/hola3` + 3 hardcoded subdirs → `kaiju_drive_index_by_name()`/`kaiju_drive_expected_subdirs()`, schema v1.3. Force-unmount (x2, lazy) + remount + subdir verify logic preserved exactly. | ✅ TESTED (Round 3, 2026-09-08) |
| `fm07_dns_failure.sh` | Kaidosho's Prowlarr-only DNS fix | Hardcoded compose_dir + hardcoded nyaa.si check → `kaiju_service_index_by_name()`, schema v1.3 `dns_check_url` field. Restart + real curl verify logic preserved exactly. | ✅ TESTED (Round 3, 2026-09-08) |
| `fm04_clock_drift.sh` | Kaidosho's Prowlarr-only clock-drift fix | Hardcoded single-service restart → loop over ALL `services[]` (deliberate restart-scope decision, see script header). `timedatectl set-ntp` toggle logic preserved exactly. | ✅ TESTED (Round 3, 2026-09-08) — highest-risk script in the suite, confirmed real Kaidosho services untouched during test |

## Orchestrator + notify wrapper (pi5_watchdog.sh, watchdog_notify.sh)

**SYNCED INTO THIS DIRECTORY 2026-09-20** — pulled
verbatim from the reference deployment's staging area, which is where the real
build/deploy work happened (2026-09-08/12, live on pi-node). This
package directory previously did not have copies at all; the
2026-09-14 correction note that used to sit here (explaining that gap)
is resolved and removed. `kaiju-watchdog.service`/`kaiju-watchdog.timer`
(the systemd units that run `pi5_watchdog.sh` hourly) were synced the
same pass.

`pi5_watchdog.sh` calls a `kaiju_clock_drift_threshold_ms()` function
that did not exist in this package's `fashsd_config_lib.sh` until this
sync — merged in from `fashsd_config_lib_ADDITION.sh` at the
same time. **This merged function has never been separately test-suite-
run** — it's the same code that's live on pi-node as part of the
production lib, just not yet exercised via `tests/run_tests.sh` in
*this* package copy.

**Status of the synced copies themselves:** these are the same file
contents already live and hourly-firing on pi-node's production
`/opt/kaiju-os/watchdog/` — genuinely working there — but this
particular package-directory copy, and the merged
`kaiju_clock_drift_threshold_ms()` addition to `fashsd_config_lib.sh`,
have not been run through `tests/run_tests.sh` here. Add a Step 14
(orchestrator dry-run against the package's own mocked `docker`) before
calling this package copy test-suite-clean end to end.

- `watchdog_snapshot.sh` — **BUILT 2026-09-14**, staged in
  this directory. Original Kaidosho script was searched for
  exhaustively across all of vault and genuinely not found anywhere, so
  this is a fresh implementation written directly against the exact
  calling contract fm01/fm02/fm05 already assumed (`<name> <keep_count>
  [compose_dir]`, prints only the snapshot path to stdout). Captures
  `docker inspect`/`docker logs`/`docker compose logs` when `<name>`
  resolves to a real container, `df -h` always, and rotates old
  snapshots per `<keep_count>`. Logic-tested in Mokaima's sandbox
  against a mocked `docker` (6 cases: real container w/ compose_dir,
  two pseudo-name shapes, rotation, missing-args, stdout-purity) — all
  pass. **NOT YET LIVE-TESTED** against real pi-node infrastructure.
- SMART/drive check — **BUILT 2026-09-14** as `fm08_drive_health_check.sh`,
  staged in this directory. Loops over `drives[]` the same way
  `app_curl_check.sh` loops over `services[]` (same PASS/FAIL/SKIP
  counters, same `watchdog.log` line format, same exit-code
  convention). Runs `smartctl -H <device>` per drive with
  `smart_check: true`; SKIPs (never FAILs) a disabled drive, a missing
  device path, a device smartctl can't query (bitmask bits 0/1), or an
  ambiguous smartctl output with no recognizable PASSED/FAILED string
  — a wrongly-parsed FAIL would be a false alert, worse than a missed
  one for a detection-only script. Detection/report only, no automated
  remediation (nothing safe to automate for a genuinely failing disk).
  Logic-tested in Mokaima's sandbox against a mocked `smartctl` (5 mixed
  drives: pass, fail, disabled, missing device, ambiguous output) plus
  zero-drives and smartctl-not-installed edge cases — all pass. **NOT
  YET LIVE-TESTED** against real pi-node infrastructure.

**Deployment, both new scripts:** copy to `/opt/kaiju-os/watchdog/`
alongside the existing FM scripts, `chmod +x`. `watchdog_snapshot.sh`
needs no wiring — fm01/fm02/fm05 already check for it via `[ -x
"$KAIJU_LIB_DIR/watchdog_snapshot.sh" ]` and will start using it
automatically the moment it exists at that path (fm05 calls it
unconditionally, no such check — same as before). `fm08_drive_health_
check.sh` needs to be added to whatever calls `app_curl_check.sh` today
(cron/orchestrator) if periodic execution is wanted, or can be run
standalone/on-demand. Neither has been live-tested — run each once by
hand against real pi-node config/hardware before trusting either in
an automated cycle, per this package's own standing verification
discipline (see the TESTED banners on every other script in this
directory for the bar to match).

## Dependencies

- `yq` — YAML CLI parser. **Important:** `apt install yq` on Debian/
  Ubuntu installs `kislyuk/yq` (a Python wrapper around `jq`), NOT
  `mikefarah/yq` (the Go binary). This library's queries use `-r` flags
  written for `kislyuk/yq`'s behavior (JSON-quotes strings by default,
  same as jq) — confirmed via live test 2026-07-23. If a future install
  environment has `mikefarah/yq` instead, the `-r` flags are harmless
  no-ops there too, so no environment-specific branching was needed.
- `wakeonlan` — needed only on whichever node actually runs
  `wol_trigger.sh` (the watcher node in a two-node-wol topology, e.g.
  Kaidosho's Pi5). NOT a given on every node — confirmed via live test
  2026-07-23 that it wasn't installed on Dokaisho (Kaidosho's original
  wol_trigger.sh always ran on the Pi5, never on Dokaisho). Bootstrap
  installer's Phase 5 should install this on whichever node the user
  designates as the topology.watcher_node.
- Config file at `/etc/kaiju-os/services.yaml` (see
  `kaiju_fashsd_config.example.yaml` in this directory for the schema).

## Environment variable overrides (for testing / non-deployed runs)

All 3 executable scripts default to the real deployment paths
(`/opt/kaiju-os/watchdog/`, `/var/log/kaiju-watchdog/`) but accept
overrides, added 2026-07-23 while building the test suite:

- `KAIJU_LIB_DIR` — where to find `fashsd_config_lib.sh` (and
  `watchdog_snapshot.sh` if present). Default: `/opt/kaiju-os/watchdog`
- `KAIJU_LOG_DIR` — where to write `watchdog.log`. Default:
  `/var/log/kaiju-watchdog`. Falls back to `/tmp/kaiju-watchdog-fallback`
  automatically if the default path isn't writable (e.g. no root).
- `KAIJU_CONFIG` — already existed, path to `services.yaml`.

`tests/run_tests.sh` sets `KAIJU_LIB_DIR` and `KAIJU_LOG_DIR` to point
at this package directory and `/tmp` respectively, so the full suite
runs without requiring a real `/opt` deployment or root access.

## Testing status

**✅ TESTED 2026-07-23 (round 1) — all 6 steps PASS** for
`fashsd_config_lib.sh`, `app_curl_check.sh`, `fm01_container_exited.sh`,
`wol_trigger.sh`. See `tests/TESTING.md` for the full round 1 results
log. Summary: step 3 (the strongest evidence) showed the generalized
app_curl_check.sh matching Kaidosho's real live production script EXACTLY
(PASS:10 FAIL:0 on both, run back to back against real infrastructure).
Step 6 confirmed fm01_container_exited.sh correctly detects, restarts,
and verifies a real (disposable) failed container.

Four real bugs were found and fixed during round 1 testing (see
TESTING.md for full detail) — all were packaging/environment
assumptions (yq variant mismatch, hardcoded deployment paths, an
unpackaged dependency handled ungracefully, and one test-harness
assertion bug), not logic errors in the actual config-driven
generalization itself.

**✅ TESTED (round 2) — `fm02_daemon_down.sh`, `fm05_drive_not_mounted.sh`.**
Tested 2026-07-27 by Gorkaige, both PASS. One coverage gap flagged: FM-02's
core daemon-down recovery path (`systemctl start docker` on a genuinely
stopped daemon) wasn't exercised since Docker was already running during
the test — `systemctl start` is a no-op against an already-running
service. All other logic confirmed correct: snapshot gracefully skipped
(watchdog_snapshot.sh not yet packaged), compose-loop restart via
`kaiju_known_compose_dirs()`, verify/threshold logic, and (for FM-05)
drive-name validation via `kaiju_drive_count()`/`kaiju_drive_field()`
plus the wrong-drive-name error path. Real Kaidosho services confirmed
undisturbed after FM-02's test run. See `tests/TESTING.md` for the full
Round 2 results log.

**✅ TESTED (round 3) — `fm03_gluetun_unhealthy.sh`, `fm06_ghost_mount.sh`,
`fm07_dns_failure.sh`, `fm04_clock_drift.sh`.** Tested 2026-09-08 by
the maintainer. All 4 PASS, each with the real remediation path genuinely
exercised, not just an already-fine no-op:
- FM-03: both branches tested (fail-safe when owner stays unhealthy;
  full restart→healthy→dependent-restart→curl-verify success path).
  Real finding: Compose's own `network_mode: service:<owner>` behavior
  cascade-restarts the dependent the instant the owner restarts,
  independent of the script's own fail-safe logic — the fail-safe's
  log claim ("NOT restarting dependents") describes the script's own
  loop only, not the dependent container's actual restart state.
- FM-06: force-unmount(x2)→remount-via-fstab→subdir-verify cycle
  confirmed live; wrong-drive-name path fails cleanly (message doesn't
  list valid names like FM-05's does — cosmetic gap).
- FM-07: restart→curl-verify confirmed live; both negative paths
  (unknown service, missing `dns_check_url`) confirmed as distinct,
  correctly-handled failure modes.
- FM-04 (highest risk): real system-wide NTP toggle + services[] loop
  confirmed scoped correctly — only the disposable test container
  restarted, all real Kaidosho containers confirmed untouched ("Up 21
  hours", unchanged) during and after the test.
See `tests/TESTING.md` for the full Round 3 results log.

**✅ TESTED (round 4) — schema v1.5 / `service:` field.** `fm01_container_exited.sh` and `fashsd_config_lib.sh`'s new
`kaiju_service_compose_name()` (updated 2026-09-15) resolve a service's
`docker compose up -d` argument to the real Compose service name when
it differs from the container name, instead of assuming they're always
identical. Tested 2026-09-17 by the maintainer via `tests/run_tests.sh` Step 13,
two cases against real disposable containers:
- Differing-name case (Scanopy-shaped: a `server:` service with no
  `container_name:` override, Compose auto-named the real container
  `kaijufm01v15-server-1`) — PASS. Script printed the "maps to compose
  service 'server'" note, `docker compose up -d server` succeeded (not
  "no such service"), container confirmed running via `docker ps`.
- Companion regression case (no `service:` field set, container name
  == service name, same pattern as the original round-1 fm01 test) —
  PASS. No "maps to compose service" note printed, plain `up -d`
  still worked unchanged, container confirmed running — the fallback
  path in `kaiju_service_compose_name()` is byte-for-byte unchanged for
  the ~18 existing services that don't set the field.
No bugs found — worked correctly on the first real test. Real Kaidosho
services confirmed untouched throughout. See `tests/TESTING.md`
Round 4 for the full raw output.

**Not yet run:** a dedicated test step for `pi5_watchdog.sh`/`watchdog_notify.sh`/
`kaiju_clock_drift_threshold_ms()` themselves — Steps 1-13 cover the config
lib and the individual FM scripts, not the orchestrator. **Confirmed 2026-09-24:**
`tests/run_tests.sh` Steps 1-5 pass clean (14/0) with these 3 files present in
the directory — no regression to the 9 already-tested scripts, and
`fashsd_config_lib.sh` sources cleanly with the merged function. That run also
found and fixed a pre-existing, unrelated bug in Step 3's comparison logic
(exact string match broke once the `SKIP` field was added to
`app_curl_check.sh`'s summary — now compares parsed PASS/FAIL counts).

**Round 5, added 2026-09-25:** dedicated Steps 14 and 15 now exist for
exactly this gap.
- **Step 14** (semi-automated): sends a real ntfy notification through
  `watchdog_notify.sh` to the actual self-hosted `kaiju-alerts` channel,
  clearly marked as a package test. Confirms both the HTTP call succeeds
  and the log line format matches the established convention.
- **Step 15** (manual, disposable container): exercises `pi5_watchdog.sh`'s
  own detection+dispatch logic (the container-exited branch specifically —
  the most fundamental of its 8 internal branches) end to end, confirming
  the orchestrator correctly detects an exited container, looks it up,
  dispatches `fm01_container_exited.sh` with the right `compose_dir` on
  its own, and that its later curl-recheck phase correctly sees the fix
  its own earlier phase made.

**(CLOSED by Round 6, 2026-09-25) Former gap, stated honestly:** Step 15 covers ONE of
`pi5_watchdog.sh`'s 8 internal branches. The other 7 (daemon-down,
curl-fail dispatch with/without `dns_check_url`, network-group
owner/dependent restart, drive-not-mounted, ghost-mount, clock-drift) are
each already tested at the FM-script level directly (Steps 7, 9-12) but
not yet re-exercised through the orchestrator's own detection loop the way
Step 15 does for container-exited.

**Round 6, added 2026-09-25 -- RUN LIVE, 7/7 PASS (see tests/TESTING.md; the paragraph below was written before the run, corrected 2026-10-08):** Steps 16-22
cover exactly those 7 remaining branches, each following the same
pattern (a disposable scenario, run `pi5_watchdog.sh` itself, confirm the
log shows the ORCHESTRATOR's own detection+dispatch decision, not just
re-testing the FM script's own remediation logic). Step 18 in particular
is genuinely orchestrator-unique -- no FM script tests the "no
`dns_check_url` configured" best-effort fallback path directly, since it's
purely `pi5_watchdog.sh`'s own logic. Step 22 uses a safe trigger (setting
`clock_drift_threshold_ms` to 1, so ordinary NTP jitter legitimately
exceeds it) rather than actually skewing the system clock. Steps 16 and
22 carry the same HIGH BLAST RADIUS warnings as Steps 7 and 12
respectively. Structurally verified (bash -n clean, each step isolates
correctly via `./run_tests.sh <N>`, default full-run listing updated) but
(SUPERSEDED: all 7 steps were then run live on 2026-09-25, 7/7 PASS -- tests/TESTING.md Round 6.)

## Relationship to other docs

- `install.sh` Phase 5 — where these scripts get deployed during a real install
- `MABS_Standalone.md` — the guardrail standard bundled with the installer
