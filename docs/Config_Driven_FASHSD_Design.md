╔══════════════════════════════════════════════════════════════════════╗
║  KAIJU SPINE — CONFIG-DRIVEN FASHSD DESIGN                             ║
║  Version: 1.0 | Created: 2026-07-22 (Daikaiju AIOps)                ║
║  Fills: Kaiju_Spine.md gap 7                                           ║
╚══════════════════════════════════════════════════════════════════════╝

✅ TESTED 2026-07-23
The generalized scripts this design describes (kaiju-gais-package/fashsd/)
have passed the full test suite — all 6 steps, including a live
side-by-side comparison against Kaidosho's real production script (exact
match, PASS:10 FAIL:0 both sides) and a disposable-container restart
test. See kaiju-gais-package/fashsd/tests/TESTING.md for the full results
log and the 4 real bugs found/fixed during testing (all packaging/
environment issues — yq variant, hardcoded paths, an unpackaged
dependency, one test-harness bug — not logic errors in the
generalization itself). Safe to build the remaining FM-02–FM-07/
orchestrator/drive scripts on this pattern.

Design for generalizing FASHSD from Kaidosho-specific hardcoded scripts into
a config-driven system someone else can point at their own
infrastructure. This is a DESIGN document — the actual script rewrite
is separate, tracked build work (see STATUS at the end).

Confirmed by inspecting Kaidosho's real FM-09 app-check script
(/app_curl_check.sh) while writing this: the underlying
function logic is ALREADY generic (a reusable check_service() function
taking name/URL/expected-code/timeout as arguments). The hardcoding is
entirely in the CALL SITES — 10 literal check_service calls with Kaidosho's
actual service names and URLs baked in. This is good news: the
generalization work is narrower than "rewrite FASHSD," it's "externalize
the call sites into config and loop over them instead."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCOPE REMINDER (from Kaiju_Spine.md gap 7 / Layer 3 section)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

NOT a CPU-architecture problem — bash/systemd/Docker Compose already
run unchanged on ARM64 and x86_64. Two real sub-problems:
  (a) Config-driven FASHSD (THIS DOCUMENT) — hardcoded services, drive
      names, and node topology need to become user-supplied config.
  (b) Distro portability (NOT covered here) — systemd units + `apt`
      calls assume Debian/Ubuntu; Fedora/Arch/non-systemd distros break
      today. Separate work, needs its own design pass later.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT NEEDS TO BECOME CONFIG (the three hardcoded categories)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. WATCHED SERVICES — currently 10 literal check_service() calls
   (name, URL, expected HTTP code, timeout) hardcoded in
   app_curl_check.sh, and similarly hardcoded container names in the
   FM-01 through FM-07 fix scripts.

2. DRIVES/STORAGE — currently Kaidosho's specific hola1-5 drive names and
   mount points hardcoded into SMART-check and snapshot scripts.

3. NODE TOPOLOGY — currently a hardcoded two-node pattern (pi-node wakes
   dokaisho via WoL) with Kaidosho's specific MAC address and IP baked into
   the WoL trigger script. Someone with a single-node setup, or a
   different wake direction, can't use this as-is.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROPOSED CONFIG FORMAT: services.yaml
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Single YAML file, one per Kaiju Spine install, read by all FASHSD scripts
at runtime instead of each script hardcoding its own values.

```yaml
# kaiju_fashsd_config.yaml
# Generated interactively by the bootstrap installer's Phase 5,
# or hand-edited later to add/remove watched resources.

topology:
  mode: single-node          # single-node | two-node-wol
  # Only present if mode is two-node-wol:
  watcher_node:
    name: "watcher"          # the always-on small node doing the watching
    ip: "192.0.2.21"
  target_node:
    name: "primary"          # the node being watched/woken
    ip: "192.0.2.45"
    mac: "AA:BB:CC:Kaidosho:EE:FF" # required for WoL

services:
  - name: "jellyfin"
    container: "jellyfin"          # docker container name, for FM-01 style checks
    health_url: "http://localhost:8096/health"
    expected_code: "200"
    timeout_seconds: 10
  - name: "vaultwarden"
    container: "vaultwarden"
    health_url: "http://localhost:8090/api/config"
    expected_code: "200"
    timeout_seconds: 10
  # ... one entry per watched service, repeatable

drives:
  - name: "data1"
    mount_point: "/mnt/data1"
    device: "/dev/sda"             # for SMART checks
    smart_check: true
  # ... one entry per monitored drive, repeatable

alerting:
  ntfy_topic: "kaiju-alerts"       # or full ntfy.sh URL if using public relay
  ntfy_self_hosted_url: ""         # optional, empty = use ntfy.sh public

watchdog:
  interval_minutes: 60             # Kaidosho currently runs 30; default conservative
```

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOW SCRIPTS CHANGE: BEFORE / AFTER (using the real FM-09 example)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BEFORE (Kaidosho's actual current script — hardcoded call sites):
```bash
check_service "open-webui"  "http://192.0.2.21:3000/health"  "200" 15
check_service "gitea"       "http://192.0.2.21:3002/api/healthz" "200" 10
check_service "immich"      "http://192.0.2.21:2283/api/server/ping" "200" 15
# ... 7 more identical hardcoded lines
```

AFTER (config-driven — same check_service() function, unchanged, just
called from a loop reading services.yaml instead of literal lines):
```bash
CONFIG="/etc/kaiju-os/services.yaml"

# Requires yq (yaml CLI parser) — add as a Kaiju Spine dependency,
# installed by the bootstrap installer alongside Docker/Ollama.
SERVICE_COUNT=$(yq '.services | length' "$CONFIG")

for i in $(seq 0 $((SERVICE_COUNT - 1))); do
  NAME=$(yq ".services[$i].name" "$CONFIG")
  URL=$(yq ".services[$i].health_url" "$CONFIG")
  EXPECT=$(yq ".services[$i].expected_code" "$CONFIG")
  TIMEOUT=$(yq ".services[$i].timeout_seconds" "$CONFIG")
  check_service "$NAME" "$URL" "$EXPECT" "$TIMEOUT"
done
```

The check_service() function body itself needs ZERO changes — this
confirms the earlier observation that the generalization work is
narrower than a full rewrite. The same before/after pattern applies to
the FM-01 through FM-07 fix scripts (swap hardcoded container names for
a loop over services[].container) and the drive/SMART scripts (swap
hola1-5 for a loop over drives[]).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NODE TOPOLOGY HANDLING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The WoL trigger script needs an early branch on topology.mode:

  single-node: skip WoL entirely. The watchdog and the watched services
    run on the same machine — "wake" doesn't apply; a failed health
    check just triggers the fix-script/restart path directly, no
    cross-node relay needed.

  two-node-wol: read watcher_node/target_node from config instead of
    Kaidosho's hardcoded pi-node-wakes-dokaisho pattern. The WoL magic-packet
    call becomes `wakeonlan $(yq '.topology.target_node.mac' "$CONFIG")`
    instead of a literal MAC address in the script.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BOOTSTRAP INSTALLER INTEGRATION (Phase 5)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This design resolves the Phase 5 config-writing step described in
Bootstrap_Installer_Spec.md (OPEN QUESTION #5). The installer's
interactive prompts (service name/container/URL, repeatable; drive
name/mount/SMART check, repeatable; topology single vs two-node) map
directly to writing this services.yaml file. Once written, the
generalized scripts above read from it — the installer doesn't need to
generate custom bash per user, just the one config file plus deploying
the already-generalized scripts as-is.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NEW DEPENDENCY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This design introduces `yq` (YAML CLI parser) as a new Kaiju Spine
dependency, not currently part of Kaidosho's own stack. The bootstrap
installer needs to install it (`apt install yq` on Debian/Ubuntu — one
more small piece of surface area for the distro-portability gap to
eventually cover on other package managers).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT THIS DOCUMENT DOES NOT COVER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Distro portability (package manager abstraction, firewalld vs ufw,
  SELinux considerations) — separate gap, not designed here.
- Actually rewriting Kaidosho's own live FASHSD scripts to read from
  services.yaml — Kaidosho itself is not obligated to migrate off its
  current hardcoded scripts; this design is for the PACKAGED/exportable
  version of FASHSD, not a mandate to change Kaidosho's production system.
  (Though Kaidosho adopting its own config-driven version eventually would be
  good dogfooding, if ever prioritized.)
- MABS.md updates for briefs that would build this — if this design
  moves to an actual Angkai brief, it needs to go through MABS
  (config-driven scripts touch live infrastructure patterns, so Rule 14
  applies: verify shared-resource dependents before any brief that
  modifies the watchdog scripts).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STATUS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DESIGN COMPLETE, BUILD TESTED ✅ as of 2026-07-23: 3 scripts
generalized as a proof-of-concept set (app_curl_check.sh,
fm01_container_exited.sh, wol_trigger.sh) plus the shared
fashsd_config_lib.sh they depend on. Confirmed against Kaidosho's real live
scripts that the pattern holds across three different script types
(health check, fix script, WoL trigger). Full test suite passed 2026-
07-23 (all 6 steps) — including step 3, the strongest evidence: a live
side-by-side comparison against Kaidosho's real production script produced
an EXACT match (PASS:10 FAIL:0 both sides). Package location:
kaiju-gais-package/fashsd/ — see that directory's
README.md and tests/TESTING.md for full status and results log.
Next step: generalize the remaining FM-02 through FM-07 fix scripts,
pi5_watchdog.sh orchestrator, and drive/SMART checks following the same
now-validated pattern.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
END OF CONFIG-DRIVEN FASHSD DESIGN v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
