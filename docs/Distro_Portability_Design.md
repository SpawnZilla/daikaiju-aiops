╔══════════════════════════════════════════════════════════════════════╗
║  KAIJU SPINE — DISTRO PORTABILITY DESIGN                               ║
║  Version: 1.1 | Created: 2026-07-24 | Results added 2026-10-26      ║
║  Fills: Kaiju_Spine.md gap 7(b)                                        ║
╚══════════════════════════════════════════════════════════════════════╝

DESIGN ONLY \u2014 not built, not tested. This is the research/scoping pass
for the second half of gap 7 (the first half, config-driven FASHSD, is
DESIGN COMPLETE + BUILD TESTED, see Config_Driven_FASHSD_Design.md).
Distro portability is untested against any real non-Debian system \u2014
treat every claim below as a plan to verify, not a confirmed fact.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCOPE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Bootstrap_Installer_Spec.md locked v1 to Debian/Ubuntu only. This
document scopes what "v2 supports Fedora/Arch too" would actually
require \u2014 it does NOT change the v1 lock. Nothing here is scheduled
work; it's a design reference for whenever distro portability is
prioritized.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT'S ALREADY PORTABLE (no work needed)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  - bash scripts themselves \u2014 no distro-specific syntax used anywhere
    in FASHSD or the installer spec
  - systemd unit files \u2014 systemd is the standard init system across
    Debian/Ubuntu, Fedora, and Arch (not universal \u2014 excludes
    non-systemd distros like Alpine, Void \u2014 see OUT OF SCOPE below)
  - Docker Compose syntax \u2014 identical across all Linux distros running
    Docker
  - Ollama \u2014 ships distro-agnostic install scripts and binaries
  - yq \u2014 available as a package (in some form) across all three target
    distros, though see the yq VARIANT RISK section below \u2014 this bit
    Kaiju Spine once already (2026-07-23 FASHSD testing) even within
    Debian/Ubuntu alone

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT ACTUALLY NEEDS WORK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. PACKAGE MANAGER ABSTRACTION
   Every `apt install` call in the installer (Docker, yq, wakeonlan,
   etc.) needs a per-distro equivalent:
     Debian/Ubuntu:  apt install <pkg>
     Fedora:         dnf install <pkg>
     Arch:           pacman -S <pkg>
   Design: a single detection function at the top of the installer
   (Bootstrap_Installer_Spec.md Phase 0) that sets a PKG_MANAGER
   variable based on which binary exists (`command -v apt/dnf/pacman`),
   then a thin wrapper function `kaiju_install_pkg <name>` used
   everywhere instead of calling apt directly. Package NAMES also
   differ occasionally between distros (e.g. some packages have
   different names on Fedora vs Debian) \u2014 needs a small per-package
   name-mapping table, not just a manager swap.

2. FIREWALL DIFFERENCES
   Kaidosho/Kaiju Spine assumes ufw (Debian/Ubuntu default). Fedora defaults to
   firewalld, which has a genuinely different command syntax and
   zone-based model, not just different command names. This is more
   than a find-and-replace \u2014 firewalld's zone concept doesn't map
   1:1 onto ufw's simpler allow/deny rules. Needs its own small design
   pass when actually tackled, not just a wrapper function.

3. SELINUX (Fedora) vs APPARMOR/NONE (Debian/Ubuntu)
   Fedora ships SELinux enforcing by default. Docker, Ollama, and
   custom systemd services can all hit SELinux denials that simply
   don't exist on Debian/Ubuntu \u2014 this is the single biggest UNKNOWN
   in this whole document. Nothing in Kaidosho's stack has ever been tested
   against SELinux. Risk: silent permission failures that look like a
   completely different bug (a denied file write looks like a bug in
   the script, not a security policy blocking it) unless someone
   specifically knows to check `audit.log` / `sealert`.
   Arch typically ships no MAC (mandatory access control) system by
   default \u2014 closer to Debian/Ubuntu's permissiveness, lower risk.

4. yq VARIANT RISK (already bit Kaiju Spine once)
   Confirmed 2026-07-23: `apt install yq` on Debian installs
   kislyuk/yq (Python/jq wrapper), not mikefarah/yq (Go binary) \u2014 they
   have DIFFERENT query syntax defaults (JSON-quoted strings by
   default vs. not). This was fixed for Debian/Ubuntu with `-r` flags
   in fashsd_config_lib.sh (see Config_Driven_FASHSD_Design.md /
   kaiju-gais-package/fashsd/README.md). Fedora and Arch's package
   repos may install yet another variant, or the same one \u2014 UNKNOWN,
   needs verification per-distro before assuming the existing `-r`
   fix generalizes. This is exactly the kind of packaging-level
   surprise the FASHSD test suite caught within Debian alone \u2014 expect
   more of these per new distro, not fewer.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VALIDATION PLAN (when this is actually prioritized)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Do not attempt to "port" the installer by reasoning alone \u2014 the
FASHSD test suite proved that packaging-level assumptions (yq variant,
deployment paths) are exactly the class of bug that reasoning misses
and only a real test run catches. Recommended sequence:

  1. Spin up one real Fedora VM/box and one real Arch VM/box (not
     required to be permanent hardware \u2014 a throwaway VM is enough for
     validation).
  2. Run the CURRENT Debian-only installer against each, expecting it
     to fail at the first `apt` call \u2014 this establishes the actual
     first failure point empirically rather than guessing.
  3. Fix forward one failure at a time, the same iterative pattern
     that found and fixed the 4 real FASHSD bugs in one afternoon
     (2026-07-23) \u2014 don't try to pre-solve every distro difference
     from this document alone before testing.
  4. Build a per-distro test suite mirroring
     kaiju-gais-package/fashsd/tests/ structure once the installer
     itself is portable, before declaring gap 7(b) resolved.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUT OF SCOPE (not even a future v2 target without a separate decision)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  - Non-systemd distros (Alpine, Void, Gentoo without systemd) \u2014
    FASHSD's watchdog deployment is fundamentally systemd-timer-based;
    supporting init systems without systemd is a much larger rewrite,
    not a portability tweak. Not recommended without a strong specific
    reason to target Alpine/Void users.
  - Windows/WSL, BSD \u2014 never in scope, not discussed further here.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STATUS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DESIGN COMPLETE (scoping only). NOT BUILT. NOT TESTED against any
real non-Debian system. Four real work items identified (package
manager abstraction, firewall differences, SELinux unknown, yq variant
re-verification), ranked roughly by risk with SELinux as the biggest
unknown. Recommended next step if prioritized: the validation plan
above, starting with a real Fedora VM \u2014 not further design-by-reasoning.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VALIDATION RESULTS (added 2026-10-26 from the  rounds of 2026-10-19;
sources: angkai/staging//RESULTS_arch.md, RESULTS_fedora.md,
RESULTS_pull_and_merge.md; real throwaway VMs, run by Claude Code on
dokaisho). This section supersedes "DESIGN ONLY / not tested" above for the
items it covers. Note: the package folder is now kaiju-gais-package/ (the
text above still says kaiju-gais-package/).

  1. FIRST FAILURE: the Phase 0 distro gate, not an apt call (the guess in
     the validation plan was wrong). Fixed with *arch* and *fedora* gate arms.
  2. PACKAGE MANAGER: built. detect_pkg_manager + kaiju_install_pkg cover
     apt, dnf (dnf5 symlink on Fedora 44) and pacman; one name-map entry
     (pipx -> python-pipx on pacman). Docker stays instruct-and-exit.
  3. FIREWALL: nothing to port. Arch has no ufw/firewalld; Fedora 44 Cloud
     Base has no firewalld installed; the repo has zero ufw references.
     Fedora Workstation/Server (firewalld present) NOT tested.
  4. SELINUX (Fedora, enforcing): zero AVC denials across Docker, Ollama
     install/start, pipx/mcpo, git, yq and one real watchdog run; permissive
     mode was never needed. Fedora Workstation/Server not tested.
  5. yq VARIANT: Arch and Ubuntu = kislyuk/yq (4.4.5 and 3.1.0); Fedora =
     mikefarah/yq 4.53.3 (the opposite variant). All five -r query shapes
     used by fashsd_config_lib.sh returned correct unquoted values on all
     three, so no code change. Re-test if a variant-specific flag is added.
  6. UNLISTED FINDINGS: (a) Phase 3 assumed git is installed (the Arch
     cloud image has none; the script still printed "Layer 4 complete") --
     fixed; (b) the model pull failed because Ollama needs ~20-30 s after the
     installer returns before it listens (startup race on Ubuntu, Arch and
     Fedora) -- fixed with wait_for_ollama_api (30 s cap); a real pull with
     the fix is verified on Fedora only.
  7. STILL OPEN: per-distro test suite (validation plan step 4); Debian-path
     source diff is not byte-identical (3-4 existing lines replaced; the
     records differ on the count; behavior and output identical on the
     Ubuntu run); RHEL/CentOS, Fedora Workstation/Server and non-systemd
     distros untested. Gap 7(b) is therefore NOT fully resolved.

END OF DISTRO PORTABILITY DESIGN v1.1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
