#!/bin/bash
# ============================================================
# Kaiju Spine Bootstrap Installer — install.sh
# Implements: the installer spec v1.0 (first draft 2026-09-17)
#
# STATUS: run end to end. The minimal path (Docker pre-installed, model
# pull skipped, FASHSD skipped) ran on clean VMs on Ubuntu 24.04, Debian
# 13 and Ubuntu 22.04 LTS; the bugs those runs found are fixed. The FULL
# path (Docker install, Tier 3 model pull, FASHSD Phase 5) on Ubuntu
# 24.04 was reported at 11m33s with no errors; its log was not kept, so
# that is unverified. The model-pull step had a startup race on Ubuntu,
# Arch and Fedora (fixed with wait_for_ollama_api); the fix was verified
# with a real pull on Fedora only. Arch and Fedora 44 Cloud Base ran the
# minimal path clean.
#
# Resolved design decisions this script follows (the installer spec's
# open questions, all resolved 2026-09-13):
#   #1 Docker/Compose missing at Phase 0 -> instruct and EXIT, never
#      auto-install (matches the project's autonomy-scope precedent).
#   #6 Script language -> bash (matches the rest of this package).
#   #7 Distribution -> public GitHub repo, MIT license. Repo created
#      2026-09-17: https://github.com/SpawnZilla/daikaiju-aiops -- this
#      file assumes it ships as part of that repo's checkout, with
#      sibling reference docs and kaiju-gais-package/ alongside it; see
#      SCRIPT_DIR resolution below.
#
# Expected layout (this script assumes it is run from inside a checkout
# of the Kaiju Spine repo, not copied out on its own — matches this
# project's own real existing directory layout, not a new one invented
# for this script):
#   <repo-root>/install.sh                          <- this file
#   <repo-root>/MABS_Standalone.md
#   <repo-root>/Model_Selection_Guide.md
#   <repo-root>/Naming_Convention_Guide.md
#   <repo-root>/Hardware_Compatibility_Matrix.md
#   <repo-root>/kaiju-gais-package/fashsd/fashsd_config_lib.sh
#   <repo-root>/kaiju-gais-package/fashsd/fm01_container_exited.sh ... fm08_drive_health_check.sh
#   <repo-root>/kaiju-gais-package/fashsd/kaiju_fashsd_config.example.yaml
#   <repo-root>/kaiju-gais-package/fashsd/watchdog_snapshot.sh
#   <repo-root>/kaiju-gais-package/fashsd/wol_trigger.sh
#   <repo-root>/kaiju-gais-package/fashsd/app_curl_check.sh
# ============================================================

set -uo pipefail
# Deliberately NOT `set -e` — this script talks to a human through many
# non-fatal branches (skip Phase 5, "n" to various prompts) and needs
# to control its own exit points explicitly, the same reasoning
# fashsd_config_lib.sh's own scripts already follow elsewhere in this
# package.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Docs live alongside this script (Model_Selection_Guide.md,
# Naming_Convention_Guide.md, MABS_Standalone.md,
# Hardware_Compatibility_Matrix.md) rather than in a separate docs/
# subdirectory — matches this repo's real existing layout (this script
# is staged at the same directory level as those files) instead of
# duplicating their content into a second copy.
DOCS_DIR="$SCRIPT_DIR"
FASHSD_SRC_DIR="$SCRIPT_DIR/kaiju-gais-package/fashsd"

KAIJU_HOME="${KAIJU_HOME:-$HOME/.kaiju-spine}"
MARKER_FILE="$KAIJU_HOME/installed.marker"

# --- Answer accumulator for Phase 6's receipt file ---
declare -A ANSWERS
ANSWERS[hardware_tier]=""
ANSWERS[exec_model]=""
ANSWERS[chat_model]=""
ANSWERS[vault_path]=""
ANSWERS[naming_choice]=""
ANSWERS[fashsd_enabled]="false"
ANSWERS[mcpo_ok]="unknown"

hr() { printf '%s\n' "------------------------------------------------------------"; }

phase_header() {
    echo
    hr
    echo "  $1"
    hr
}

confirm() {
    # Usage: confirm "Prompt text" [default: Y]
    local prompt="$1"
    local default="${2:-Y}"
    local reply
    read -r -p "$prompt [$default]: " reply
    reply="${reply:-$default}"
    case "$reply" in
        [Yy]*) return 0 ;;
        *) return 1 ;;
    esac
}

# wait_for_ollama_api -- the Ollama install step (curl|sh) returns as
# soon as its own download/extract/service-enable finishes, but on a
# fresh install this routinely takes 20-30s of real wall time (the
# binary download+extraction itself, confirmed via journalctl on
# Fedora and Arch test VMs, KAI-097) before ollama.service actually
# starts listening -- so the very next command, 'ollama pull', loses
# that race deterministically. Poll the real API instead of trusting
# the upstream installer's own "available" message (observed on Arch
# to print even when the daemon was not yet reachable).
wait_for_ollama_api() {
    local timeout=30 waited=0
    echo "Waiting for the Ollama API to come up (up to ${timeout}s)..."
    while [ "$waited" -lt "$timeout" ]; do
        if curl -s -m 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
            echo "Ollama API is up (after ${waited}s)."
            return 0
        fi
        sleep 2
        waited=$((waited + 2))
    done
    echo "Ollama API did not come up within ${timeout}s; continuing anyway (pull may fail)."
    return 1
}

# --- Package manager abstraction (KAI-097 distro portability) --
# apt (Debian/Ubuntu) behaves as before; pacman (Arch) and dnf (Fedora)
# were added and ran the minimal path clean on Arch and Fedora 44 Cloud
# Base. See Distro_Portability_Design.md. ---
detect_pkg_manager() {
    if command -v apt-get >/dev/null 2>&1; then
        PKG_MANAGER="apt"
    elif command -v pacman >/dev/null 2>&1; then
        PKG_MANAGER="pacman"
    elif command -v dnf >/dev/null 2>&1; then
        PKG_MANAGER="dnf"
    else
        PKG_MANAGER=""
    fi
}

# kaiju_install_pkg <generic-name> -- installs <generic-name> via the
# package manager PKG_MANAGER was set to, translating the name through
# the per-distro map below where a distro calls it something else.
kaiju_install_pkg() {
    local generic="$1" pkg="$1"
    case "$PKG_MANAGER" in
        apt)
            sudo apt-get update -y && sudo apt-get install -y "$pkg"
            ;;
        pacman)
            case "$generic" in
                pipx) pkg="python-pipx" ;;
            esac
            sudo pacman -Sy --noconfirm "$pkg"
            ;;
        dnf)
            # Fedora round (KAI-097): names verified against a real
            # Fedora 44 Cloud box, see RESULTS_fedora.md.
            sudo dnf install -y "$pkg"
            ;;
        *)
            echo "FATAL: no supported package manager (apt/pacman/dnf) found -- cannot install $generic." >&2
            return 1
            ;;
    esac
}

# ============================================================
# PHASE 0 — PRE-FLIGHT CHECKS
# ============================================================
phase_0() {
    phase_header "PHASE 0 — Pre-flight checks"

    # Step 1: distro gate
    if [ ! -f /etc/os-release ]; then
        echo "FATAL: /etc/os-release not found — cannot determine distro." >&2
        exit 1
    fi
    # shellcheck disable=SC1091
    . /etc/os-release
    case "${ID_LIKE:-$ID}" in
        *debian*|*ubuntu*) ;;
        *arch*) ;;
        *fedora*) ;;
        *)
            echo "Kaiju Spine v1 currently supports Debian/Ubuntu, Arch and Fedora." >&2
            echo "Other distros are a known future gap — see Distro_Portability_Design.md." >&2
            exit 1
            ;;
    esac
    detect_pkg_manager
    [ -n "$PKG_MANAGER" ] || { echo "FATAL: no supported package manager (apt/pacman/dnf) found." >&2; exit 1; }
    echo "Distro check: OK ($PRETTY_NAME)"

    # Step 2: sudo check (per INSTALL PATH RULE spirit — never silently
    # escalate or work around missing permissions)
    if ! sudo -n true 2>/dev/null; then
        echo "This installer requires sudo access. Checking interactively..."
        if ! sudo -v; then
            echo "FATAL: sudo access not available for this user. Exiting." >&2
            exit 1
        fi
    fi
    echo "Sudo check: OK"

    # Step 3: idempotency check
    if [ -f "$MARKER_FILE" ]; then
        echo "Existing Kaiju Spine install detected at $KAIJU_HOME."
        echo "  [R] Re-run full installer"
        echo "  [A] Add a layer only (e.g. just enable FASHSD)"
        echo "  [C] Cancel"
        read -r -p "Choice [R/a/c]: " existing_choice
        case "${existing_choice:-R}" in
            [Cc]*) echo "Cancelled."; exit 0 ;;
            [Aa]*)
                echo "Add-a-layer mode: jumping to Phase 5 (FASHSD) only."
                mkdir -p "$KAIJU_HOME"
                phase_5
                phase_7
                exit 0
                ;;
            *) echo "Re-running full installer." ;;
        esac
    fi

    # Step 4: Docker + Compose presence — OPEN QUESTION #1, RESOLVED:
    # instruct and exit, never auto-install.
    if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
        echo
        echo "Docker and/or Docker Compose (v2 plugin) were not found." >&2
        echo "Kaiju Spine does not install these automatically (INSTALL PATH RULE" >&2
        echo "spirit — this script never silently installs software you did not" >&2
        echo "explicitly ask it to)." >&2
        echo >&2
        echo "Install Docker Engine + the Compose plugin for your distro, then" >&2
        echo "re-run this installer. See: https://docs.docker.com/engine/install/" >&2
        exit 1
    fi
    echo "Docker + Compose check: OK"

    # decision 1 (2026-10-08): Claude Code is a user-installed
    # prerequisite for the Daikaiju AIOps execution agent, never bundled.
    # Warn only: Kaiju GAIS itself does not need it.
    if ! command -v claude >/dev/null 2>&1; then
        echo "Note: Claude Code ('claude') was not found on PATH. Kaiju GAIS works without it;"
        echo "the Daikaiju AIOps execution agent needs it. Install it yourself when ready."
    else
        echo "Claude Code check: OK"
    fi

    # Step 5: summary + ready?
    echo
    echo "Summary: distro OK, sudo OK, Docker/Compose OK, existing install: $([ -f "$MARKER_FILE" ] && echo yes || echo no)"
    if ! confirm "Ready to begin?" Y; then
        echo "Aborted by user."
        exit 0
    fi
}

# ============================================================
# PHASE 1 — LAYER 1: ORCHESTRATION
# ============================================================
phase_1() {
    phase_header "PHASE 1 — Layer 1: Orchestration (Ollama, models, mcpo, MCP)"

    echo "What hardware tier is this machine?"
    echo "  [1] Low (<=8GB VRAM / CPU-only)"
    echo "  [2] Mid (8-16GB VRAM)"
    echo "  [3] High (16-24GB VRAM)"
    echo "  [4] Enthusiast (24GB+, workstation/multi-GPU)"
    read -r -p "Tier [1-4]: " tier
    local exec_model chat_model
    case "$tier" in
        1) exec_model="qwen3:8b";              chat_model="llama3.1:8b" ;;
        2) exec_model="qwen3:30b-a3b";          chat_model="qwen3:30b-a3b" ;;
        3) exec_model="qwen3-coder:30b-a3b-q4_K_M"; chat_model="qwen3.6:27b" ;;
        4) exec_model="qwen2.5-coder:32b";      chat_model="llama3.3:70b" ;;
        *) echo "Unrecognized tier '$tier', defaulting to Tier 2 (safer/smaller, per Model_Selection_Guide.md's own down-not-up rule)."
           tier=2; exec_model="qwen3:30b-a3b"; chat_model="qwen3:30b-a3b" ;;
    esac
    ANSWERS[hardware_tier]="$tier"
    ANSWERS[exec_model]="$exec_model"
    ANSWERS[chat_model]="$chat_model"
    echo "Selected: execution agent = $exec_model, reasoning/chat = $chat_model"
    echo "(Full rationale per tier: Model_Selection_Guide.md)"

    # Step 2: install Ollama if not present
    if ! command -v ollama >/dev/null 2>&1; then
        echo "Installing Ollama (official install script)..."
        curl -fsSL https://ollama.com/install.sh | sh
    else
        echo "Ollama already installed: $(ollama --version 2>/dev/null || echo 'version unknown')"
    fi

    # Step 3: pull models (warn about size first, per Model_Selection_Guide.md's note)
    echo "About to pull: $exec_model and $chat_model (if different) — these can be several GB each."
    if confirm "Proceed with model pull(s) now?" Y; then
        wait_for_ollama_api
        ollama pull "$exec_model"
        if [ "$exec_model" != "$chat_model" ]; then
            ollama pull "$chat_model"
        fi
    else
        echo "Skipped model pull — run 'ollama pull $exec_model' (and '$chat_model' if different) manually later."
    fi

    # Step 4: mcpo
    local mcpo_port=8200
    if command -v ss >/dev/null 2>&1 && ss -ltn | grep -q ":$mcpo_port "; then
        read -r -p "Port $mcpo_port is in use — enter an alternate mcpo port: " mcpo_port
    fi
    # NOTE 2026-09-17 (first real run, throwaway VM): a stock
    # Ubuntu 24.04 cloud image has neither pipx NOR a working `pip`
    # module at all (`python3 -m pip` -> "No module named pip") -- the
    # original version of this step tried `python3 -m pip install
    # --user mcpo` as its only fallback, never checked whether that
    # actually succeeded, and printed the "mcpo will listen on..."
    # line regardless. Result: no working mcpo binary, Phase 7's
    # summary never flagged it, and the user would have no idea until
    # something downstream that needs mcpo failed much later.
    #
    # NOTE 2026-09-17 ROUND 2 (fix-verification run): the first
    # fix (installing python3-pip via apt when pip itself is missing)
    # correctly got pip installed, but `python3 -m pip install --user
    # mcpo` then failed differently -- Ubuntu 24.04+ (PEP 668) makes
    # the system Python "externally managed" and refuses `pip install
    # --user` outright ("error: externally-managed-environment"),
    # pointing the user at exactly the tool this script should have
    # used from the start: pipx. Real fix: install pipx via apt as the
    # primary fallback (apt's pipx package exists specifically to work
    # inside PEP 668's restriction) instead of touching pip at all.
    if ! command -v mcpo >/dev/null 2>&1; then
        echo "Installing mcpo (requires pipx or pip)..."
        # fix (2026-09-25, Ubuntu 22.04 test): mcpo requires
        # Python 3.11+ (per its own PyPI metadata), but Ubuntu 22.04 LTS
        # ships 3.10.12 as python3 by default -- pipx/pip previously
        # attempted the install anyway and failed with a wall of
        # confusing "Requires-Python >=3.11" version-resolution errors
        # for every mcpo release, giving no clear guidance. Ubuntu 22.04
        # is a real, common Kaiju Spine target (the installer spec's
        # own locked Debian/Ubuntu-family scope), not an edge case -- this
        # needed a real check, not just a clearer error after the fact.
        MCPO_PY=""
        if command -v python3 >/dev/null 2>&1; then
            py_ver=$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null)
            py_major=${py_ver%%.*}
            py_minor=${py_ver##*.}
            if [ "${py_major:-0}" -gt 3 ] || { [ "${py_major:-0}" -eq 3 ] && [ "${py_minor:-0}" -ge 11 ]; }; then
                MCPO_PY="$(command -v python3)"
            fi
        fi
        if [ -z "$MCPO_PY" ] && command -v python3.11 >/dev/null 2>&1; then
            MCPO_PY="$(command -v python3.11)"
        fi
        if [ -z "$MCPO_PY" ]; then
            for cand in python3.12 python3.13; do
                if command -v "$cand" >/dev/null 2>&1; then
                    MCPO_PY="$(command -v "$cand")"
                    break
                fi
            done
        fi
        if [ -z "$MCPO_PY" ]; then
            echo "WARNING: mcpo requires Python 3.11+, but no such interpreter" >&2
            echo "  was found on this system (python3 is $py_ver). Per the INSTALL" >&2
            echo "  PATH RULE, this installer will not silently add a new Python" >&2
            echo "  version. Install one yourself (e.g. 'sudo apt install python3.11'" >&2
            echo "  if available on this distro's repos, or via the deadsnakes PPA on" >&2
            echo "  older Ubuntu/Debian releases), then re-run:" >&2
            echo "    pipx install --python python3.11 mcpo" >&2
            echo "  Skipping the mcpo install attempt entirely -- see the summary at" >&2
            echo "  the end for what this means for vault MCP registration." >&2
        elif command -v pipx >/dev/null 2>&1; then
            pipx install --python "$MCPO_PY" mcpo
            # fix (2026-09-24, Debian 13 test): the OTHER branch
            # below already exports this after installing pipx via apt,
            # but this branch (pipx already present) was missing the
            # same fix -- pipx's own install can print a PATH warning
            # ("'~/.local/bin' is not on your PATH") and the very next
            # `command -v mcpo` check below would then fail even though
            # mcpo installed correctly, since $PATH hadn't picked up the
            # change within this same shell process yet.
            export PATH="$HOME/.local/bin:$PATH"
        else
            echo "pipx not found -- installing it via $PKG_MANAGER (real, visible install," >&2
            echo "not silent). This is the correct path on Ubuntu 24.04+, where" >&2
            echo "PEP 668 blocks 'pip install --user' directly (" >&2
            echo "'externally-managed-environment')." >&2
            kaiju_install_pkg pipx
            pipx ensurepath >/dev/null 2>&1 || true
            export PATH="$HOME/.local/bin:$PATH"
            if command -v pipx >/dev/null 2>&1; then
                pipx install --python "$MCPO_PY" mcpo
            elif python3 -m pip --version >/dev/null 2>&1; then
                # Last-resort fallback if even apt's pipx package is
                # somehow unavailable: try pip directly. This will
                # still hit PEP 668 on Ubuntu 24.04+ and fail -- that's
                # fine, the check below reports it honestly either way.
                python3 -m pip install --user mcpo 2>/dev/null || true
            fi
        fi
    fi
    if ! command -v mcpo >/dev/null 2>&1; then
        MCPO_INSTALL_FAILED=true
        ANSWERS[mcpo_ok]="false"
        echo
        echo "WARNING: mcpo install did not produce a working 'mcpo' binary" >&2
        echo "  (checked via 'command -v mcpo' after the install attempt above)." >&2
        echo "  The vault MCP server registration below will not work until this" >&2
        echo "  is fixed manually -- try 'pipx install mcpo' or 'pip install" >&2
        echo "  --user mcpo' by hand and re-check with 'command -v mcpo'." >&2
        echo
    else
        MCPO_INSTALL_FAILED=false
        ANSWERS[mcpo_ok]="true"
        echo "mcpo will listen on port $mcpo_port (vault MCP server registration is written after Phase 3 creates the vault — see below)."
    fi

    # Step 5 note: vault MCP config path is recorded now, actual file
    # written at the end of Phase 3 once the vault directory exists —
    # this sequencing gap is called out explicitly in the spec itself
    # (Phase 1 runs before Phase 3), not an oversight here.
    export KAIJU_MCPO_PORT="$mcpo_port"

    # Step 6: Claude Desktop gate (Option B, locked decision)
    local claude_config_dir="$HOME/.config/Claude"
    if [ ! -d "$claude_config_dir" ]; then
        echo
        echo "Claude Desktop not detected at $claude_config_dir."
        echo "Download from claude.ai/download, install, and log in."
        read -r -p "Press Enter once ready to continue... "
    else
        echo "Claude Desktop config directory found: OK"
    fi

    echo "Layer 1 complete. Ollama + mcpo + MCP config path recorded ($claude_config_dir)."
}

# ============================================================
# PHASE 2 — LAYER 2: GUARDRAILS (MABS)
# ============================================================
phase_2() {
    phase_header "PHASE 2 — Layer 2: Guardrails (MABS)"

    mkdir -p "$KAIJU_HOME"
    if [ -f "$DOCS_DIR/MABS_Standalone.md" ]; then
        cp "$DOCS_DIR/MABS_Standalone.md" "$KAIJU_HOME/MABS.md"
        echo "Copied MABS_Standalone.md -> $KAIJU_HOME/MABS.md"
    else
        echo "WARNING: MABS_Standalone.md not found in this checkout — skipping copy." >&2
        echo "Guardrail rules will not be deployed until this file is added." >&2
    fi

    # INSTALL PATH RULE + SESSION FORMAT RULE as a small standalone
    # config file — exact downstream format (a CLAUDE.md-equivalent for
    # a user's own execution agent) is left as a build-time detail per
    # the spec; this writes a plain reference doc any such file can
    # source content from.
    cat > "$KAIJU_HOME/install_path_rule.md" <<'EOF'
# INSTALL PATH RULE (Kaiju Spine default)
Nothing installs to boot, EFI, swap, root (/), or home (/home) without
explicit approval. All AI-stack software goes to a dedicated data
directory (this install used: see KAIJU_HOME below). Before any install
command: (1) state where it installs, (2) state which drive/path,
(3) get approval, (4) run a dry-run first when practical.

# SESSION FORMAT RULE (Kaiju Spine default)
Any multi-step automated/agent-driven change uses pause points between
phases: "PAUSE — <description>. Type GO to proceed or STOP to hold."
EOF
    echo "Wrote $KAIJU_HOME/install_path_rule.md"
    echo "Layer 2 complete. Guardrail rules in place."
}

# ============================================================
# PHASE 3 — LAYER 4: MEMORY/VAULT BOOTSTRAP
# ============================================================
phase_3() {
    phase_header "PHASE 3 — Layer 4: Memory/Vault bootstrap"

    local default_vault="$HOME/KaijuVault"
    read -r -p "Where should your memory vault live? [$default_vault]: " vault_path
    vault_path="${vault_path:-$default_vault}"
    ANSWERS[vault_path]="$vault_path"

    mkdir -p "$vault_path"/{docs,briefs,state}
    cat > "$vault_path/PENDING.md" <<'EOF'
# PENDING — <your project name>
Nothing goes on this list unless you or your agent proposes it and you approve it.
Format: [STATUS] ITEM — notes
Status: PENDING | IN PROGRESS | BLOCKED | DONE (date)
EOF
    cat > "$vault_path/state/state_snapshot.md" <<'EOF'
# State snapshot
(Populate with a running summary of current infrastructure state —
this is the file your reasoning/chat agent should read first each
session, mirroring Kaidosho's own state snapshot pattern.)
EOF
    cat > "$vault_path/README.md" <<EOF
# $(basename "$vault_path")
This is your Kaiju Spine memory vault. Structure:
  PENDING.md      — the standing task list
  state/          — running state-snapshot doc(s)
  docs/           — reference documents (naming scheme, model choices, etc.)
  briefs/         — task briefs handed to your execution agent

Initialized by the Kaiju Spine bootstrap installer, $(date '+%Y-%m-%d').
EOF
    echo "Vault structure written to $vault_path"

    if [ ! -d "$vault_path/.git" ]; then
        # fix (KAI-097, Arch round): git was assumed present -- true on
        # the Debian/Ubuntu cloud images this was tested on, but Arch's
        # cloud image ships without it, and this block had no check,
        # so git init/add/commit all silently failed ("command not
        # found") while Phase 3 still printed "Layer 4 complete."
        if ! command -v git >/dev/null 2>&1; then
            echo "git not found -- installing it via $PKG_MANAGER." >&2
            kaiju_install_pkg git
        fi
        git -C "$vault_path" init -q
        echo "git init'd the vault."
        read -r -p "Set up a git remote for backup/sync now? (URL, or leave blank to skip): " remote_url
        if [ -n "$remote_url" ]; then
            git -C "$vault_path" remote add origin "$remote_url"
            echo "Remote 'origin' set to $remote_url — push manually once you're ready."
        else
            echo "Skipped remote setup — you can add one later with 'git remote add origin <url>'."
        fi
        git -C "$vault_path" add -A
        # NOTE 2026-09-17 (first real run, throwaway VM): the
        # original `|| true` here silently swallowed a real failure --
        # a fresh VM/user with no git identity configured makes this
        # commit fail ("unable to auto-detect email address"), and
        # "Layer 4 complete" printed as if it had succeeded, with zero
        # commits ever actually made. Fix: if no identity is configured
        # for this repo (checked via `git config`, not assumed), set a
        # local-to-this-repo placeholder identity so the initial commit
        # can succeed without touching the user's global git config or
        # requiring them to already have one -- then commit for real
        # and report plainly if it still fails for some other reason.
        if ! git -C "$vault_path" config user.email >/dev/null 2>&1; then
            git -C "$vault_path" config user.email "kaiju-spine-installer@localhost"
            git -C "$vault_path" config user.name "Kaiju Spine Installer"
            echo "No git identity was configured -- set a local-only placeholder"
            echo "identity for this repo (kaiju-spine-installer@localhost). Change it"
            echo "anytime with 'git config user.email/user.name' inside $vault_path."
        fi
        if git -C "$vault_path" commit -q -m "Kaiju Spine bootstrap: initial vault structure"; then
            echo "Initial commit created."
        else
            echo "WARNING: initial git commit failed -- vault files are staged but" >&2
            echo "  not committed. Run 'git -C $vault_path commit' manually to see why." >&2
        fi
    fi

    # Now that the vault exists, finish Phase 1's deferred vault MCP
    # config write (see the sequencing note in phase_1 above).
    local claude_config_dir="$HOME/.config/Claude"
    if [ -d "$claude_config_dir" ]; then
        local mcp_config="$claude_config_dir/claude_desktop_config.json"
        echo "NOTE: registering the vault filesystem MCP server for $vault_path"
        echo "  in $mcp_config requires care not to clobber any existing config"
        echo "  in that file — this installer does NOT auto-edit it (a malformed"
        echo "  Claude Desktop config can break unrelated MCP servers). Add an"
        echo "  entry like this to its \"mcpServers\" object manually:"
        cat <<EOF
    "kaiju-vault": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "$vault_path"]
    }
EOF
    fi

    echo "Layer 4 complete. Vault initialized at $vault_path."
}

# ============================================================
# PHASE 4 — LAYER 5: NAMING CONVENTION
# ============================================================
phase_4() {
    phase_header "PHASE 4 — Layer 5: Naming convention"

    echo "Use the Kaiju naming convention as a starting template, define"
    echo "your own scheme, or skip naming structure entirely?"
    echo "  [K] Kaiju template   [C] Custom   [S] Skip"
    read -r -p "Choice [K/c/s]: " naming_choice
    naming_choice="${naming_choice:-K}"
    ANSWERS[naming_choice]="$naming_choice"

    local vault_path="${ANSWERS[vault_path]:-$HOME/KaijuVault}"
    case "$naming_choice" in
        [Kk]*)
            cat > "$vault_path/docs/naming_scheme.md" <<'EOF'
# Naming scheme: Kaiju convention (starter list)
Nodes (physical/virtual machines): pick by role prominence.
  e.g. primary compute node, services/always-on node, secondary/mobile node
Agent roles:
  planning/documentation agent, execution agent, reasoning/conversation agent
Subsystems: prefer descriptive acronyms over kaiju names (e.g. your own
  self-healing layer, your own memory-vault layer).
Full guide: Naming_Convention_Guide.md (bundled with this installer).
EOF
            [ -f "$DOCS_DIR/Naming_Convention_Guide.md" ] && cp "$DOCS_DIR/Naming_Convention_Guide.md" "$vault_path/docs/"
            echo "Kaiju naming template recorded in $vault_path/docs/naming_scheme.md"
            ;;
        [Cc]*)
            read -r -p "Briefly describe your own naming scheme (for your own future reference): " custom_scheme
            printf '# Naming scheme: custom\n%s\n' "$custom_scheme" > "$vault_path/docs/naming_scheme.md"
            echo "Custom scheme note recorded in $vault_path/docs/naming_scheme.md"
            ;;
        *)
            echo "Skipped naming structure."
            ;;
    esac
    echo "Layer 5 complete."
}

# ============================================================
# PHASE 5 — LAYER 3: FASHSD (OPTIONAL, PLUGGABLE)
# ============================================================
phase_5() {
    phase_header "PHASE 5 — Layer 3: FASHSD (optional)"

    if ! confirm "Enable FASHSD watchdogs? This requires knowing your services and drives." N; then
        echo "Skipped. Re-run this installer anytime with --fashsd-only to add this later."
        ANSWERS[fashsd_enabled]="false"
        return 0
    fi
    ANSWERS[fashsd_enabled]="true"

    local kaiju_config="/etc/kaiju-spine/services.yaml"
    sudo mkdir -p /etc/kaiju-spine
    echo "Building $kaiju_config interactively. Press Ctrl+C at any point to abort Phase 5 only."

    # Topology
    echo "Is this a single-node setup, or does a smaller always-on node"
    echo "need to wake a bigger node via WoL?"
    read -r -p "  [single-node / two-node-wol]: " topo_mode
    topo_mode="${topo_mode:-single-node}"
    {
        echo "topology:"
        echo "  mode: $topo_mode"
        if [ "$topo_mode" = "two-node-wol" ]; then
            read -r -p "  Target node MAC address: " target_mac
            read -r -p "  Target node IP address: " target_ip
            echo "  target_node:"
            echo "    ip: \"$target_ip\""
            echo "    mac: \"$target_mac\""
        fi
        echo
        echo "services:"
    } | sudo tee "$kaiju_config" >/dev/null

    while confirm "Add a service to watch?" Y; do
        read -r -p "  Service name: " svc_name
        read -r -p "  Container name: " svc_container
        read -r -p "  Compose directory: " svc_dir
        read -r -p "  Health check URL (blank if none): " svc_health
        {
            echo "  - name: \"$svc_name\""
            echo "    container: \"$svc_container\""
            echo "    compose_dir: \"$svc_dir\""
            if [ -n "$svc_health" ]; then
                echo "    health_url: \"$svc_health\""
                echo "    expected_code: \"200\""
            fi
            echo "    timeout_seconds: 10"
        } | sudo tee -a "$kaiju_config" >/dev/null
    done

    echo "drives:" | sudo tee -a "$kaiju_config" >/dev/null
    while confirm "Add a drive to monitor?" N; do
        read -r -p "  Drive name: " drv_name
        read -r -p "  Mount point: " drv_mount
        read -r -p "  Device path (e.g. /dev/sda): " drv_device
        if confirm "  Enable SMART checks for this drive?" Y; then smart_check=true; else smart_check=false; fi
        {
            echo "  - name: \"$drv_name\""
            echo "    mount_point: \"$drv_mount\""
            echo "    device: \"$drv_device\""
            echo "    smart_check: $smart_check"
        } | sudo tee -a "$kaiju_config" >/dev/null
    done

    {
        echo
        echo "alerting:"
        echo "  ntfy_topic: \"kaiju-alerts\""
        echo "  ntfy_self_hosted_url: \"\""
        echo
        echo "watchdog:"
        echo "  interval_minutes: 60"
    } | sudo tee -a "$kaiju_config" >/dev/null

    # Deploy the FASHSD scripts + shared lib
    sudo mkdir -p /opt/kaiju-spine/watchdog
    if [ -d "$FASHSD_SRC_DIR" ]; then
        sudo cp "$FASHSD_SRC_DIR"/*.sh /opt/kaiju-spine/watchdog/
        sudo chmod +x /opt/kaiju-spine/watchdog/*.sh
        echo "FASHSD scripts deployed to /opt/kaiju-spine/watchdog/"
    else
        echo "WARNING: fashsd/ source directory not found in this checkout — FASHSD scripts NOT deployed." >&2
    fi

    if ! command -v yq >/dev/null 2>&1; then
        echo "Installing yq (required by FASHSD scripts)..."
        kaiju_install_pkg yq
    fi

    # Systemd timer + service (interval read back from the config just written)
    local interval_min
    interval_min=$(yq -r '.watchdog.interval_minutes' "$kaiju_config" 2>/dev/null || echo 60)
    sudo tee /etc/systemd/system/kaiju-watchdog.service >/dev/null <<EOF
[Unit]
Description=Kaiju Spine FASHSD watchdog
[Service]
Type=oneshot
Environment=KAIJU_CONFIG=$kaiju_config
Environment=KAIJU_LIB_DIR=/opt/kaiju-spine/watchdog
ExecStart=/opt/kaiju-spine/watchdog/app_curl_check.sh
EOF
    sudo tee /etc/systemd/system/kaiju-watchdog.timer >/dev/null <<EOF
[Unit]
Description=Run Kaiju Spine FASHSD watchdog every ${interval_min} minutes
[Timer]
OnBootSec=2min
OnUnitActiveSec=${interval_min}min
[Install]
WantedBy=timers.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable --now kaiju-watchdog.timer

    echo "Layer 3 complete. Config at $kaiju_config, timer enabled (every ${interval_min}m)."
}

# ============================================================
# PHASE 6 — ANSWERS-FILE / RECEIPT GENERATION
# ============================================================
phase_6() {
    phase_header "PHASE 6 — Answers-file / receipt generation"

    mkdir -p "$KAIJU_HOME"
    local receipt="$KAIJU_HOME/install-receipt-$(date '+%Y-%m-%d').yaml"
    {
        echo "kaiju_spine_install_receipt:"
        echo "  date: \"$(date -Iseconds)\""
        echo "  hardware_tier: \"${ANSWERS[hardware_tier]}\""
        echo "  execution_model: \"${ANSWERS[exec_model]}\""
        echo "  chat_model: \"${ANSWERS[chat_model]}\""
        echo "  vault_path: \"${ANSWERS[vault_path]}\""
        echo "  naming_choice: \"${ANSWERS[naming_choice]}\""
        echo "  fashsd_enabled: ${ANSWERS[fashsd_enabled]}"
    } > "$receipt"
    echo "Receipt written to $receipt"
    echo "This file is NOT read by the installer on a future run (no unattended"
    echo "mode in v1) — it exists purely as a human-readable record."

    touch "$MARKER_FILE"
}

# ============================================================
# PHASE 7 — SUMMARY + NEXT STEPS
# ============================================================
phase_7() {
    phase_header "PHASE 7 — Summary"

    echo "Installed:"
    echo "  Layer 1 (Orchestration): Ollama + mcpo, models = ${ANSWERS[exec_model]:-<skipped>} / ${ANSWERS[chat_model]:-<skipped>}"
    if [ "${ANSWERS[mcpo_ok]}" = "false" ]; then
        echo "    ^ WARNING: mcpo did NOT install correctly -- see the Phase 1 warning above."
    fi
    echo "  Layer 2 (Guardrails):    $KAIJU_HOME/MABS.md, install_path_rule.md"
    echo "  Layer 4 (Vault):         ${ANSWERS[vault_path]:-<skipped>}"
    echo "  Layer 5 (Naming):        ${ANSWERS[naming_choice]:-<skipped>}"
    echo "  Layer 3 (FASHSD):        $([ "${ANSWERS[fashsd_enabled]}" = "true" ] && echo enabled || echo skipped)"
    echo
    echo "Next steps:"
    echo "  - Open Claude Desktop and confirm it shows the MCP tools for your vault."
    echo "  - Re-run this installer with --fashsd-only anytime to add FASHSD later."
    echo "  - Your receipt file: $KAIJU_HOME/install-receipt-$(date '+%Y-%m-%d').yaml"
    echo
    echo "Kaiju Spine bootstrap complete."
    exit 0
}

# ============================================================
# MAIN
# ============================================================
main() {
    if [ "${1:-}" = "--fashsd-only" ]; then
        mkdir -p "$KAIJU_HOME"
        phase_5
        phase_6
        phase_7
        return
    fi

    phase_0
    phase_1
    phase_2
    phase_3
    phase_4
    phase_5
    phase_6
    phase_7
}

main "$@"
