#  Layer C — Promotion Broker Design (v0.1 DRAFT)
Written: Mokaima, 2026-09-26 (Full Auto part 13) | Status: DRAFT, awaiting the operator decisions (section 7)
Supersedes nothing. Builds on:  (proof gate),  (snapshot),  (arm/disarm),
 (auto-rollback),  neutral-escalation (2026-09-26).

## 0. Purpose
Promote a sandbox-proven change to production WITHOUT the operator arming each one, and WITHOUT
trusting Angkai's own report. Angkai can only REQUEST; the broker decides and applies.
 arm/disarm stays as the manual fallback for anything the policy does not allow.

## 1. Decided so far (the operator, 2026-09-26)
- Deterministic: no LLM anywhere in the promotion decision.
- Validation runs FIRST, no side effects, before the broker's own re-run check.
- FIXABLE rejections go back to Angkai with fixed reason codes; cap = 4 resubmits per task
  (5 attempts total), then escalate to the operator.
- POLICY DENIALS never go back to Angkai; escalated to the operator directly.
- A correct escalation does not reset  (deployed + live-verified 2026-09-26).

## 2. Q1 — Trust boundary (proposed)
Identity: dedicated system user `kaibroker` (nologin, no home). NOT in kaiju-agents, homelab,
docker or USER. Angkai (angkai) cannot become it, signal it, or write anything it runs.

Code and config (all root-owned, read-only to kaibroker):
  /opt/kaiju-broker/                 broker code        root:root 0755 / files 0644
  /etc/kaiju-broker/policy.yaml      targets + classes  root:root 0644
Broker-owned state (angkai has no access):
  /var/lib/kaiju-broker/             ledger, work dirs  kaibroker:kaibroker 0750
Run as systemd unit kaiju-broker.service: User=kaibroker, NoNewPrivileges=yes,
ProtectSystem=strict, ProtectHome=yes, PrivateTmp=yes, ReadWritePaths= only its state,
spool and the policy-listed production targets.

Applying changes: the broker writes production files itself (it must own or have group-write
on each listed target). For unit restarts it gets an exact-match sudoers rule per listed unit
(`systemctl restart <unit>`), same pattern as angkai-docker-ps. Nothing broader.

PREREQUISITES (the boundary is meaningless without them):
  P1  Hooks/settings lockdown (step 1 of the part-13 order) — ready, not yet run.
  P2  Governance state off vault (step 2) — checkpoint state + activity log currently on exFAT
      vault, writable by angkai via the homelab group.
  P3  NEW FINDING: the production gateway code lives at /srv/angkai/mcp-a2a-gateway,
      inside angkai's home and angkai-owned. Angkai can edit production directly today; only
      the (angkai-owned, until P1) hooks stop it. Every production target the broker manages
      must move out of angkai ownership — v1 proposal: relocate to /opt/kaiju-gateway/,
      owned kaibroker, unit repointed (same repoint pattern as the 2026-09-26 uv fix).
Known limit: a real shell as angkai could still rename directories inside /srv/angkai.
That is Layer A (deferred); the broker does not depend on anything under that path.

## 3. Q2 — Verification (proposed)
The broker never runs anything taken from the request. Every check comes from policy.yaml.
Per request, in order:
  1. Validate (section 4 codes). Any failure -> respond, stop.
  2. Intake copy: copy the artifact into /var/lib/kaiju-broker/work/<request_id>/ and hash
     THAT copy (closes the check-then-swap race; Angkai can't alter it after this point).
  3. Hash match: copy's sha256 == request.artifact_sha256 == the hash in the  proof
     record for proof_ref.
  4. Re-run the target's FIXED check against the SANDBOX TWIN (e.g. gateway: HTTP probe on
     :10099 + one read-only tool call). Fail -> E_SANDBOX_CHECK_FAILED (fixable).
  5. Snapshot production target ( pattern).
  6. Apply the intake copy to production.
  7. Re-run the same fixed check against PRODUCTION (e.g. :10000).
  8. Fail -> automatic rollback from the snapshot ( pattern), re-check, escalate.
  9. ntfy outcome; ledger entry.

## 4. Q3 — Contract (proposed)
Transport: spool directory (simpler to audit than a socket).
  /var/spool/kaiju-broker/incoming/   kaibroker:kaiju-agents 3730 (setgid, sticky; angkai can
                                      create, cannot list, read or delete others' files)
  /var/spool/kaiju-broker/outcomes/   kaibroker:kaiju-agents 2750 (angkai reads, cannot write)
Authentication: the kernel-recorded file OWNER uid of the request file must be angkai's uid.
Anything else -> E_OWNER, escalated. angkai cannot forge another uid's ownership.
Replay: request_id (UUIDv4) recorded in the ledger; any repeat -> E_REPLAY.

Request (JSON, one file per request, <request_id>.json):
  schema_version  "1"
  request_id      UUIDv4, one-shot
  task_id         A2A task id
  target          a policy target NAME (never a path)
  change_class    one of the policy's classes for that target
  artifact_path   must resolve (production_matcher.resolve_path) under the sandbox staging root
  artifact_sha256 hex
  proof_ref        proof record id
  submitted_at    UTC ISO-8601
  resubmit_of     previous request_id or null
  attempt         1..5

Outcome (<request_id>.json in outcomes/, written only by the broker):
  request_id, status, codes[], attempts_remaining, detail (fixed strings only), timestamps
  status: rejected_fixable | escalated | promoted | failed_rolled_back | failed_rollback_failed

Reason codes (fixed set):
  Fixable -> back to Angkai:
    E_SCHEMA_VERSION, E_FIELD_MISSING:<f>, E_FIELD_TYPE:<f>, E_ARTIFACT_MISSING,
    E_ARTIFACT_OUTSIDE_STAGING, E_HASH_MISMATCH, E_PROOF_MISSING, E_PROOF_STALE,
    E_SANDBOX_CHECK_FAILED
  Escalated to the operator (never "fix and retry"):
    E_OWNER, E_REPLAY, E_RESUBMIT_LIMIT,
    P_TARGET_NOT_ALLOWED, P_CLASS_NOT_ALLOWED, P_CHECKPOINT_STATE
  Escalations are  NEUTRAL (no ladder reset) unless paired with a real failure.

Policy interplay with : policy.yaml maps each change_class to the minimum
checkpoint_state it may auto-promote at; below that -> P_CHECKPOINT_STATE (escalate; the operator can
still arm manually via ).

## 5. Layer D regression fixtures (added to angkai_guardrail_regression.sh)
  D-C1  valid request, dummy target -> promoted
  D-C2  each missing field -> E_FIELD_MISSING:<f>, rejected_fixable
  D-C3  artifact outside staging (incl. ../ and symlink escapes) -> E_ARTIFACT_OUTSIDE_STAGING
  D-C4  artifact modified after submit -> E_HASH_MISMATCH (intake copy protects apply)
  D-C5  request file owned by USER -> E_OWNER, escalated
  D-C6  same request_id twice -> E_REPLAY
  D-C7  6th attempt on one task -> E_RESUBMIT_LIMIT, escalated
  D-C8  target not in policy -> P_TARGET_NOT_ALLOWED, escalated, NOT returned as fixable
  D-C9  post-apply check fails -> failed_rolled_back, production content == snapshot
  D-C10 angkai cannot read another request, write outcomes/, or write /opt/kaiju-broker

## 6. Build plan (each milestone its own stop point)
  B1  validator + ledger + outcomes, dry-run only (no apply), fixtures D-C2..D-C8, D-C10
  B2  intake copy + hash + sandbox re-check
  B3  apply + post-check + rollback against a DUMMY target (D-C1, D-C9)
  B4  first real target (after P3), policy v1 enabled

## 7. Decisions needed from the operator before B1
  1. Create the `kaibroker` system user? (proposed: yes) -- APPROVED by the operator 2026-09-26.
  2. P3: relocate the production gateway out of /srv/angkai to /opt/kaiju-gateway/?
     -- APPROVED by the operator 2026-09-26 (owned kaibroker; sandbox twin stays in Angkai's area).
  3. Policy v1 scope: proposed = gateway code file changes only, auto-promote only at
     fully_autonomous; everything else escalates. -- APPROVED by the operator 2026-09-26.
  4. Spool directory + file-owner auth (proposed) vs. Unix socket + SO_PEERCRED.
     -- APPROVED by the operator 2026-09-26: spool directory.
STATUS: all 4 decisions made -> design v0.1 is APPROVED for build (B1 first).
B1 BUILT 2026-09-26: angkai/staging// (kaiju_broker.py,
test_kaiju_broker.py 26/26 PASS in Mokaima's sandbox, policy.json,
b1_setup_install.sh, b1_host_check.sh). Deviations from this doc: policy is
JSON not YAML (stdlib-only); request adds a required target_relpath field;
proof_dir is deliberately UNALIGNED (fails closed) until B2 aligns it with
's real proof record. Host install + D-C10 check pending (sudo).
B1 DEPLOYED + VERIFIED 2026-09-26 (the operator, dokaisho): host unit tests 26/26;
b1_setup_install.sh created kaibroker (uid 995, own group only), dirs and
ACLs exactly per design; b1_host_check.sh 14/14 -- D-C10 all PASS as the real
angkai/kaibroker, and a real end-to-end request (angkai submits, kaibroker
processes) returned escalated P_CHECKPOINT_STATE (correct:  at
stage_0), outcome readable by angkai, request consumed. Next: P3 (gateway move),
then B2 (align proof record with , intake copy, sandbox re-check).
P3 DONE 2026-09-26 (the operator, dokaisho, p3_gateway_move.sh): preflight --
code copied to /opt/kaiju-gateway (kaibroker-owned), CODE_IDENTICAL, angkai write
DENIED, rehearsal as angkai on 127.0.0.1:10098 started in 3s and wrote nothing
into the read-only code (checked against the rehearsal log's mtime). Switch --
unit repointed (backup mcp-a2a-gateway.service.bak-p3-20260926), prod active on
:10000, Groups 1004 1005 1006, cmdline shows /opt/kaiju-gateway, live
get_task_result through the gateway OK. Old /srv/angkai/mcp-a2a-gateway
kept (rollback path) pending retirement; production_signatures.conf update
staged (adds /opt/kaiju-gateway, records the hooks-dir self-protection as
resolved at the OS level). Next: B2.
CLEANUP DONE 2026-09-26: production_signatures.conf installed (root:root 0644;
/opt/kaiju-gateway now the first gated path); 7 stale .bak-*/.new-* files removed
from /opt/kaiju-gateway/mcp_a2a_gateway; gateway still active.
B2 DEPLOYED + VERIFIED 2026-09-26 (the operator, dokaisho). DESIGN CHANGE: 's
proof store has no producer and no artifact hash, so the broker now makes its OWN
proof (approved Q2): intake copy + hash -> restart the sandbox twin (exact sudoers
rule /etc/sudoers.d/kaibroker-sandbox-restart; prod restart + other verbs refused,
verified via sudo -l) -> HTTP probe + still-active after settle -> re-hash staging
(E_ARTIFACT_CHANGED) -> state/proofs/<request_id>.json. proof_ref optional, never
trusted. Host: tests 30/30; installed broker sha256 == tested (pinned); B1 files
kept as *.b1-20260926. b2_host_check.sh 10/10 with the REAL sandbox twin:
dry_run_pass, kaibroker-owned proof, intake hash == sandbox file, angkai cannot read
broker state, sandbox really restarted and active, production code hash and
production PID unchanged. (Test used a temp policy copy with min state stage_0;
installed policy unchanged.) RESIDUAL: change-and-revert of the staging file
between pre-check and re-hash (Layer A); B3 applies only the intake copy.
Next: B3 (apply + post-check + rollback) against a DUMMY target.
B3 DEPLOYED + VERIFIED 2026-09-26 (the operator, dokaisho). the operator: dummy target only;
production restart rule only in B4. Broker applies ONLY to targets with
"apply_enabled": true (only broker-dummy); a2a-gateway has no apply flag and no
prod_check (installer refuses otherwise). Apply = snapshot -> atomic replace with
the INTAKE copy -> restart prod unit -> probe (+expect_body_contains) -> promoted,
else restore snapshot + restart + re-check -> failed_rolled_back /
failed_rollback_failed; guard refusals -> failed_not_applied. Dummy: two
localhost-only units (kaiju-broker-dummy :18000 = "prod", kaiju-broker-dummy-sandbox
:18099), exact sudoers rules for those two only (/etc/sudoers.d/kaibroker-dummy);
production gateway restart verified REFUSED. Host tests 37/37; installed broker
sha256 == tested (1ca837b0...). b3_host_check.sh 10/10 on the second run: good
change promoted, bad change auto-rolled back to v2, real gateway code/PID and real
sandbox PID unchanged, angkai cannot write dummy prod. FIRST RUN LESSON: the check
marker "OK" matched "BR-OK-EN" so the bad change was (correctly, per policy)
promoted -- marker changed to HEALTH_OK; health markers must be distinctive.
Remove the dummy any time: sudo bash b3_install.sh --remove.
B4 STILL NEEDS (not built): (1) exact sudoers rule for mcp-a2a-gateway.service
restart; (2) a real prod_check for the gateway + apply_enabled on it; (3) ntfy
alert on every escalated/failed_* outcome (none today -- outcome file + ledger
only); (4) automatic runs (systemd path/timer unit) -- today the broker runs only
when invoked with --once; (5) an Angkai-side way to submit: its vault MCP root is
/srv/angkai, it cannot reach /var/spool/kaiju-broker/incoming, and
CLAUDE.md has no submission instructions yet; (6)  at fully_autonomous.
B4 DEPLOYED + VERIFIED 2026-09-26 (the operator, dokaisho): broker B1..B4 (sha256
e74c63cf..., host tests 44/44). artifact_sha256 now OPTIONAL (Angkai has no
hashing tool; the broker always proves/applies its own intake copy). ntfy alerts:
/etc/kaiju-broker/ntfy.json (root:kaibroker 0640, kaiju-alerts, same user as );
NEEDS OPERATOR for escalated/failed_*, info for promoted; best-effort. Gateway target
apply-enabled + prod_check (:10000/mcp), still min_checkpoint_state fully_autonomous.
/etc/sudoers.d/kaibroker-prod-restart = exact `systemctl restart
mcp-a2a-gateway.service` (stop/other verbs refused). kaiju-broker.service (oneshot,
flock) + kaiju-broker.timer (30s) ACTIVE -- the broker now runs by itself.
Angkai submission path: /var/spool/kaiju-broker/incoming added as a second root of
its vault MCP server (preflight: server starts with both roots); .mcp.json now
root:kaiju-agents 0644 (angkai cannot edit). NOTE: the vault MCP root is
/srv/vault-drive (the whole vault drive), not /srv/angkai as said
earlier. b4_host_check.sh 7/7 over the FULLY AUTOMATIC path (angkai -> real vault MCP
server over stdio -> spool -> timer): dummy change promoted, gateway request
escalated P_CHECKPOINT_STATE, production gateway not restarted, no broker errors.
Phone confirmation of the two ntfy alerts: CONFIRMED by the operator 2026-09-26 (both
'Kaiju broker: PROMOTED' and 'Kaiju broker: NEEDS OPERATOR (escalated)' arrived).
STILL OPEN AFTER B4: (7) NEW -- Angkai cannot edit sandbox code with its allowed
tools (sandbox is under /srv/angkai, outside its MCP root; built-in
Write/Edit not in its --allowedTools), so a real Angkai-originated gateway
promotion needs a decision on how it edits the sandbox; (8) CLAUDE.md submission
instructions (after 7); (9)  at fully_autonomous.
ITEM 7 DECIDED 2026-09-26 (the operator): option A -- add the gateway sandbox tree as a
third root of Angkai's vault MCP server (its only new writable place; the sandbox
is ungated by design). Rejected for now: B (built-in Write/Edit -- reach = anywhere
angkai can write, contained only by hooks), C (manual sandbox edits -- never autonomous).

## 8. Long-term roadmap (the operator-approved direction, 2026-09-26)
  Phase A (now): sandbox tree = Angkai's workspace, reached via an MCP root.
  Phase G -- git commits as the unit of change (no Layer A prerequisite):
    Angkai's workspace becomes a git repo; a request names a COMMIT HASH, not a
    file. The broker fetches that commit into ITS OWN repo (Angkai read-only at
    most), runs the sandbox twin from the BROKER's checkout (Angkai's later edits
    cannot change what is being proven), applies the diff to production as a
    production commit (rollback = git revert). Wins: content-addressed artifacts
    close B2's change-and-revert residual; multi-file changes (v1 is one file per
    request); reviewable diffs + production history. Cost: new artifact type +
    multi-file policy rules in the broker; sandbox twin repointed to the broker's
    checkout.
  Phase L -- OS-level confinement of Angkai sessions (Layer A): run each session
    in an OS-enforced box (bubblewrap / systemd-run filesystem restrictions /
    rootless container) where the ONLY writable path is the workspace; production,
    hooks, settings, vault and other services read-only or absent. Containment then
    stops depending on tool lists and hooks, so full Write/Edit (even Bash) becomes
    safe inside the box, and the rename-directories-in-angkai's-home gap closes.
    Cost: a real project -- Claude Code, node, its MCP servers and API egress must
    work inside the box; hook-dependent paths need rethinking.
  Order: A -> G -> L. Nothing in A is thrown away: its workspace boundary is the
  same one G and L use.
PHASE A DONE 2026-09-26 (the operator, dokaisho, itemA_install.sh 10/10 + Layer D
regression 17/17): (1) GAP FOUND + FIXED -- validate-kaiju-relay-path.sh CHECK 0
blocked every path outside vault and /srv, so a REAL Angkai session could never
have submitted a broker request (B4's check drove the MCP server directly and
bypassed Claude Code's hooks, so it could not see this). CHECK 0 now also accepts
exactly /var/spool/kaiju-broker/incoming/<file> (tested: outcomes/, the bare dir,
other /var/spool paths and /etc still blocked; sandbox writes still allowed). Backup
*.bak-itemA-20260926. (2) vault MCP roots now: /srv/vault-drive,
/var/spool/kaiju-broker/incoming, /srv/angkai/mcp-a2a-gateway-sandbox
(preflight + real MCP write into the sandbox as angkai OK). Regression suite lives at
vault angkai/regression-tests/angkai_guardrail_regression.sh (not under
/srv/angkai). KNOWN GAP: Angkai cannot READ outcomes/ (not an MCP root, and
CHECK 0 blocks it) -- outcomes are relayed by Mokaima/the operator for now.
LIVE PROBE 2026-09-26 (ANG-PROBE-spool, a REAL runner-launched headless -p session,
normal tool set): (1) sandbox write OK (angkai-owned probe file); (2) spool submission
REACHED THE BROKER through Claude Code + all hooks (ledger: rejected_fixable, the
probe was deliberately not a full request) -- so the CLI roots hold, no roots-protocol
override; (3) every tool call CHAIN_ALL_PASS stages=6 on the root-owned hooks (the
lockdown's owed live check: PASSED); (4)  SessionEnd fired in -p mode
(reason=other, marker consumed -> idle) -- 's last open item CLOSED.
FOUND ON THE WAY (lockdown side effect): fs.protected_regular=2 + the now sticky,
group-writable hooks dir made the kernel refuse O_CREAT opens of angkai-owned files
(even for root) -> every release_task.sh run (manual AND Mokaima's auto-release) had
failed since the lockdown, and  arm/disarm too. FIXED
(fix_protected_regular.sh 12/12): both writers now update in place without O_CREAT
(files stay angkai-owned); backups *.bak-protreg-20260926.  arm/disarm now
require sudo (settings.json is root-owned) -- by design: arming grants Angkai a new
permission. CLAUDE.md v4.10: MCP ROOT section corrected to the live 3 roots.

PHASE G -- G0 RECON (read-only), 2026-10-09, Claude Code session on dokaisho.
Evidence gathered before answering Q-G1..Q-G4 (handoff angkai/staging//HANDOFF_code.md):
  - angkai's HEADLESS tool list (angkai_launch_runner.py:56-59, matches CLAUDE.md v4.7+
    LAUNCH COMMAND) is exactly 4 tools: mcp__vault__read_text_file, mcp__vault__write_file,
    mcp__vault__list_directory, mcp__vault__create_directory. No delete, no move, no git tool,
    no Bash (absent from --allowedTools; project settings.json only scopes Bash(graft:*)
    variants, which --allowedTools overrides away in headless runs regardless).
  - git IS installed (/usr/bin/git 2.43.0) but angkai has no path to invoke it headless.
    command_fidelity_pretooluse.sh exists specifically because a prior *scoped* Bash git
    invocation (a past incident, 2026-08-24: git clone https vs ssh) slipped past volume-only
    budget checks -- i.e. the project has already been burned once by giving Angkai any
    git-shaped Bash surface, even scoped.
  - /opt/kaiju-gateway already contains a .git (kaibroker:kaibroker 2755, mtime predates
    the P3 move -- it is the upstream clone, origin https://github.com/yw0nam/mcp_a2a_gateway,
    branch main) carried over by P3's copy. It is NOT currently used for commit tracking:
    `git status` shows 3 files modified (agent_manager.py, server.py, task_manager.py) with
    no commits since -- B1..B4 applied by direct file-replace, never by commit. This repo
    predates Phase G and its history is upstream's, not production's.
  - /srv/angkai/mcp-a2a-gateway-sandbox has NO .git (plain dir, angkai:kaiju-agents 2775).
    /opt/kaiju-broker has NO .git (root:root, just kaiju_broker.py + numbered backups).
  - Existing sudoers (/etc/sudoers.d/): kaibroker-dummy, kaibroker-prod-restart,
    kaibroker-sandbox-restart -- all exact-match `systemctl restart <unit>` only. No
    git-related sudoers rule exists anywhere.
  - policy.json's current path gate is single-path: evaluate() glob-matches one
    target_relpath against allowed_relpaths (kaiju_broker.py:228-230); there is no
    multi-path / whole-tree check yet.

Q-G1 answer: (b) -- the broker snapshots the sandbox tree into a commit in its OWN repo;
Angkai never touches git. Option (a) is ruled out by the evidence above, not by
preference: angkai's headless tool list has no git tool and no general Bash, and the one
precedent for giving it ANY git-shaped Bash surface (even scoped/exact-match) already
caused a past incident. Adding a 5th MCP tool or a scoped Bash(git commit:*) rule would be new
trust surface on angkai's side, which is exactly what Phase A/B1-B4's design avoids
(Angkai requests, never trusted). (b) needs nothing new from angkai: it already writes
only inside its one sandbox root via write_file/create_directory, and the broker already
does an intake-copy-and-hash of that root in B2. G1 generalizes that existing copy step
from one file to a tree snapshot + commit in the broker's own checkout.

Q-G2 answer: extend policy.json's per-class allowed_relpaths (already a glob list) from a
single target_relpath check to a whole-commit check: `git diff --name-only <parent>..<new
commit>` inside the broker's OWN checkout (never trust a file list from the request), run
safe_relpath() + glob_match() per touched path, same as today; any path outside the set
fails closed with the existing P_PATH_NOT_ALLOWED code (already escalate-only via
status_for()'s "P_" prefix rule, no new code needed).

Q-G3 answer: repoint the sandbox-twin unit's WorkingDirectory to a kaibroker-owned
checkout (e.g. /var/lib/kaiju-broker/gitrepo/checkout), same repoint pattern already
proven in P3 (gateway moved out of angkai's home to /opt/kaiju-gateway, unit repointed, angkai
write access verified DENIED). angkai cannot write it because it is outside all 3 of angkai's
vault MCP roots and validate-kaiju-relay-path.sh's CHECK 0 allowlist -- no hook change
needed, just don't add the new path to that allowlist. Flag for G1: decide whether to
reuse /opt/kaiju-gateway's existing (dirty, upstream-sourced) .git as the production repo
-- recommend baseline-committing the current production tree first so git revert has a
correct parent -- or init a fresh repo and keep /opt/kaiju-gateway as a plain deploy
target the broker writes/restarts as it does today.

Q-G4 answer: confirmed compatible -- recommend keeping schema_version "1" (current
single-file path) live in policy.json/evaluate() unchanged, and branching a new
schema_version "2" (commit hash, target, change_class) alongside it. No structural
conflict found in kaiju_broker.py's current evaluate() dispatch.

RECOMMENDATION to the operator: Q-G1 = (b) broker-side snapshot/commit, no new angkai tool or Bash
surface. Proceed to G1 (broker repo + fetch + sandbox-from-checkout, dry-run only) on that
basis, with the Q-G3 baseline-commit decision for /opt/kaiju-gateway made explicitly
before G1 touches it.
STATUS: G0 done, read-only, no changes made to any live system. STOP -- PAUSE for the operator's
GO on Q-G1..Q-G4 before G1 begins.

PHASE G -- G1 BUILD (dry-run only), 2026-10-09, Claude Code session on dokaisho.
the operator's GO (2026-10-09): Q-G1 = (b) confirmed; two additions -- (1) broker's own repo
gets an ignore list so sandbox build junk never enters a commit or trips
P_PATH_NOT_ALLOWED; (2) baseline-commit /opt/kaiju-gateway's existing dirty tree before
G1 relies on it as a target. Baseline-commit done by the operator: 236b433, on top of the
upstream clone's 09e46b8, status clean.

Staged in angkai/staging//kaiju_broker.py (not yet installed on any
host), schema_version "2" alongside the unchanged "1" path:
  - evaluate() dispatches on schema_version before the v1 REQUIRED-field loop; v1
    requests are unaffected (verified by regression checks: all-fields-missing, missing
    schema_version alongside other missing fields, wrong type, unsupported value "3").
  - evaluate_v2() shares the existing ledger (replay / resubmit-limit, same MAX_ATTEMPTS
    and E_RESUBMIT_LIMIT code as v1) and checkpoint-state gate, then: ensure_repo() on
    the broker's own checkout; writes a generated .gitignore from the target's
    ignore_patterns (__pycache__, *.pyc, *.pyo, *.log); mirrors the sandbox tree in
    (sync_tree); stages; diffs every changed path in the commit against the target's
    allowed_relpaths glob (P_PATH_NOT_ALLOWED + reset-to-prior-HEAD on any path outside
    the set -- generalizes Q-G2's single-path check to the whole commit); commits with a
    fixed kaiju-broker/kaibroker@localhost author (no global git config touched); then
    sandbox-proves the new HEAD (restart + HTTP probe + re-check HEAD is unchanged,
    E_CHECKOUT_HEAD_CHANGED + reset if something else moved it mid-check). Always returns
    dry_run_pass on success -- no apply path exists in this schema version's code at all,
    regardless of any config flag.
  - Two bugs found and fixed during build (both in kaiju_broker.py, not in the design):
    (1) sync_tree's empty-directory pruning walked into .git's own internals (e.g.
    refs/heads, legitimately empty right after `git init` pre-first-commit) and deleted
    them, corrupting the repo -- fixed by skipping any path with ".git" anywhere in its
    relative components, not just as the directory basename. (2) the broker's own
    generated .gitignore showed up in `git diff --cached --name-only` and incorrectly
    tripped allowed_relpaths -- fixed by excluding ".gitignore" from the changed-paths
    list before the policy check.
  - test_kaiju_broker_g1.py: 28/28 passing (v1 regression + v2 field/policy checks +
    G1-1..G1-9: first snapshot, multi-file diff, no-op request, ignore patterns,
    disallowed path, sandbox-check failure, checkout mutated mid-check, replay, resubmit
    limit). One test-only bug found during this: G1-9 originally looped 4 prior submits
    then checked a 5th expecting E_RESUBMIT_LIMIT, but the cap triggers at >= 5 prior
    entries (MAX_ATTEMPTS=5) -- that checked submit was only the 5th attempt, still
    within the limit. Fixed by looping 5 prior submits so the checked one is the 6th.
    Not a code bug: evaluate_v2's resubmit-limit check (kaiju_broker.py:556-557) is the
    identical check v1 uses, sharing the same ledger -- the cap was never skipped.

STATUS: G1 done -- code + tests staged and committed locally (not installed, not pushed).
Dry-run only, no production apply path exists in schema_version "2". STOP per handoff.
G2 begins only on the operator's GO.

PHASE G -- G2 BUILD (apply + post-check + automatic revert, DUMMY target only),
2026-10-09, Claude Code session on dokaisho.
the operator's GO (2026-10-09): apply as a production commit, post-check, automatic git revert
on a failed check, against the DUMMY target ONLY -- same B3 pattern (dummy units,
exact-match sudoers, apply per-target opt-in). Real a2a-gateway target explicitly NOT
touched; that needs a separate GO. Two additions required: an independent re-check that
production never receives a path outside allowed_relpaths (not just trusting G1's
checkout-side check), and a fixture proving angkai cannot write the production repo.

Staged in angkai/staging//kaiju_broker.py, apply_change_v2():
  - Reached only when target["git"]["apply_enabled"] is True, after evaluate_v2's
    dry_run_pass (G1's checkout commit + sandbox proof). Mirrors B3's apply_change with
    git: production gets a FRESH commit of its own (mirrored from the already-proven
    checkout tree via sync_tree), never the checkout's own foreign commit history --
    production keeps its own lineage, parent = production's prior HEAD captured before
    anything is touched. production_root must already be a baseline-committed repo
    (the operator runs this by hand, once, outside the broker -- the broker never auto-inits a
    production repo, same refusal-not-silent-fix guard as B3's missing prod_check).
  - allowed_relpaths is re-checked independently against PRODUCTION's own diff before
    committing -- defense in depth, never assumes the checkout-side check (G1) was
    sufficient.
  - Restarts + probes the production unit (reusing v1's restart_unit/service_ok); pass
    -> "promoted"; fail -> git reset --hard to the captured pre-apply HEAD, restart +
    re-probe: ok -> "failed_rolled_back", not ok -> "failed_rollback_failed" (both
    escalate via the existing ALERT_STATUSES, no new code needed).
  - New policy: "broker-dummy" target's "git" sub-block now has apply_enabled: true,
    production_root "/opt/kaiju-broker-dummy-git" (new path, distinct from v1 dummy's
    /opt/kaiju-broker-dummy so the two never collide), new throwaway units
    (kaiju-broker-dummy-git-sandbox.service / kaiju-broker-dummy-git.service, ports
    19099/19000) -- none of this installed on any host yet, config only.
  - test_kaiju_broker_g2.py: 8/8 passing -- good change promoted (production file +
    git history updated); bad change auto-reverted with production's HEAD and tree hash
    (`rev-parse HEAD^{tree}`) proven identical to the pre-apply hash; a revert whose own
    recheck also fails escalates as failed_rollback_failed; a commit touching a
    disallowed path never reaches production and never restarts anything; calling
    apply_change_v2 directly against a hand-crafted checkout with a disallowed path
    (bypassing evaluate_v2 entirely) proves the independent production-side check
    actually works, not just the already-covered front-door check; the staged
    production_root/broker_checkout sit outside all 3 of angkai's known MCP roots (same
    reasoning as G0/Q-G3; OS-level permission enforcement itself stays host-only, same
    as B1's D-C10).
  - No code bugs found this round (unlike G1's two). Zero lines of v1's or G1's existing
    functions changed -- apply_change_v2 is new code, called only from evaluate_v2's
    final branch.
  - Regression: 17/17 guardrail suite (angkai_guardrail_regression.sh) and 28/28 G1
    checks (test_kaiju_broker_g1.py) re-run and still green after this change.

STATUS: G2 done -- code + tests staged and committed locally (not installed, not pushed).
DUMMY target only; a2a-gateway's apply flag untouched. No sudo steps were needed (no host
install in this milestone, same as G1 -- real systemd units/production directory would be
a future, separate step). STOP per handoff. G3 begins only on the operator's GO.

PHASE G -- G2 REVIEW FIXES (2026-10-09, same session, before any G3 work): the operator reviewed
the G2 build above and found two real gaps before allowing G3 to start.
  1. apply_change_v2 had no guard against a dirty production working tree. sync_tree mirrors
     by deleting as well as copying; against uncommitted tracked or untracked changes it
     would have silently destroyed them, and `git reset --hard` cannot protect work it was
     never told about. Fix: new git_is_clean(path) (`git status --porcelain` empty), called
     right after confirming production's prior HEAD exists; a dirty tree now returns
     failed_not_applied before sync_tree ever runs.
  2. The G2 BUILD section above says rollback is "git reset --hard to the captured pre-apply
     HEAD" -- that was a real deviation from the handoff's literal "automatic git revert,"
     and from the design's own "reviewable history" goal: reset --hard leaves the bad commit
     an unreferenced, eventually-garbage-collected dangling object, not part of visible
     history. No technical justification was found for preferring reset --hard here (within
     apply_change_v2's synchronous flow nothing else touches production between the bad
     commit and the rollback attempt, so reverting the single most recent commit can never
     conflict). Fix: new git_revert_commit(path, commit) (`git revert --no-edit
     --no-gpg-sign`); the post-commit rollback path now calls this instead of
     git_reset_hard. git_reset_hard is kept, unchanged, for PRE-commit guard refusals (bad
     diff, disallowed path, failed git commit) where no commit has landed yet and there is
     nothing to revert. The no-op case (sync_tree produced zero diff, so no new commit was
     made) is guarded separately so a failed post-check there can never attempt to revert an
     unrelated prior commit.
  3. Neither the ledger nor any proof/snapshot file recorded which commit was applied to
     production or which commit reverted it. Fix: every terminal outcome (promoted,
     failed_rolled_back, failed_rollback_failed) is now recorded to
     state/snapshots/<rid>.json with prev_head, applied_commit, and revert_commit (null
     unless a revert happened) -- an auditable hash trail alongside the existing ledger
     entry.
  - test_kaiju_broker_g2.py: 12/12 passing (was 8/8). New: G2-7 (dirty production tree --
    tracked edit + untracked file both left untouched, request refused before the prod
    twin is even restarted). Updated: G2-1/G2-2/G2-3 now also assert the snapshot audit
    record's prev_head/applied_commit/revert_commit fields; G2-2's assertion changed from
    "prod_head() == pre" to "prod_head() != pre and prod_tree() == pre_tree and pre in the
    production log" -- revert correctly produces a NEW commit hash with identical tree
    content, and the bad commit stays visible in history instead of disappearing.
  - Regression: 17/17 guardrail suite and 28/28 G1 checks re-run and still green.
  - "angkai cannot write the production repo" (G2-6/G2-6b) is still a structural path check
    only, as the operator flagged. What a REAL check would need, deferred to G3 (not built in this
    round):
      a. Host-only verification that production_root's actual Unix ownership/mode genuinely
         deny angkai's real uid write access (e.g. root:kaibroker 0750, angkai's uid not in
         group kaibroker) -- a live `sudo -u <angkai-uid> test -w production_root` or
         equivalent, the same pattern as B1/B2's D-C10, which is host-only and lives in a
         shell script (b1_host_check.sh / b2_host_check.sh), not the root-less Python suite.
      b. A live/simulated write attempt through validate-kaiju-relay-path.sh's CHECK 0
         (unknown-root absolute path detection) confirming production_root is actually
         rejected as outside angkai's known roots (KAIJU_RELAY_ROOT, VAULT_ROOT, srv_ROOT),
         not just a string-prefix comparison done from inside the test.
      c. Confirmation that angkai's actually-deployed MCP filesystem server config (not just
         the checked-in angkai_mcp.json) has no root covering production_root, since the
         deployed config is what actually governs angkai's runtime filesystem access.
    This is a description for G3 planning only -- nothing above has been built or run.

STATUS: G2 review fixes done -- code + tests staged and committed locally (not installed,
not pushed). STOP per handoff. G3 begins only on the operator's GO.

PHASE G -- G3 (host install on the DUMMY target: live checks + v2 end-to-end),
2026-10-09, Claude Code session on dokaisho.
G3 step 1 (read-only host check) done, PASS. G3 step 2 APPLIED by the operator: dummy-git
prod repo /opt/kaiju-broker-dummy-git, checkout
/var/lib/kaiju-broker/dummy-git-checkout, units kaiju-broker-dummy-git(.service)
:19000 and kaiju-broker-dummy-git-sandbox(.service) :19099,
/etc/sudoers.d/kaibroker-dummy-git -- all PASS.
G3 step 3 (g3_step3_broker_replace.sh --apply, the operator) installed the G1+G2 code
(sha256 c4e91852...) live and patched policy.json with the dummy-git target block
(structural assert: a2a-gateway and broker-dummy's existing fields byte-for-byte
unchanged). v1 regression (b4_host_check.sh) PASSED. v2 end-to-end FAILED with a
real incident:

  INCIDENT (2026-10-09): kaibroker could not list
  /srv/angkai/broker-dummy-staging -- an ACL left user:kaibroker:--x on that
  directory (execute/traverse only, no read), denying it the ability to enumerate
  entries. list_tree()'s os.walk(root) has no onerror handler, so Python's default
  behaviour (onerror=None) silently treats a scandir PermissionError exactly like
  an empty directory. sync_tree() then mirrored that bogus "empty" source: first
  into the broker's own checkout (deleting app/health.html there and committing
  that deletion), then from the checkout into production via the SAME function on
  the second hop -- promote commit 26de964 deleted app/health.html in production.
  The post-apply check correctly failed and the bad commit was auto-reverted
  (git_revert_commit, working as designed). But the NEXT TWO test requests then
  read the ALSO-STILL-UNREADABLE staging dir as empty again, diffed it against
  the checkout's now-reverted (non-empty) HEAD, saw "no change," and returned
  dry_run_pass at evaluate_v2's early-exit branch -- which meant the G3v2-3
  dirty-production-tree test case never actually reached apply_change_v2's
  git_is_clean(prod) guard at all, so that guard went completely unexercised
  despite the test script reporting activity. The ACL bug masked a gap in the
  test script's own setup, not just a broker bug.

  FIX (staged, kaiju_broker.py, sha256 12cef81c...): list_tree() now passes
  onerror=_raise to os.walk, so any unreadable directory anywhere in the tree
  (root or a subdir) raises OSError instead of being silently skipped --
  "unreadable" can no longer look identical to "empty" to the caller. sync_tree()
  additionally refuses outright (RuntimeError) whenever list_tree(src_root) comes
  back empty while list_tree(dst_root) does not, independent of WHY the source
  read back empty (ACL denial already raises before this point; this guard also
  catches a genuinely-empty-but-readable source, wrong path, or race). Both
  existing call sites already caught (OSError, RuntimeError,
  subprocess.SubprocessError) around their sync_tree() calls, so no call-site
  change was needed -- evaluate_v2 now returns E_GIT_OPERATION_FAILED and
  apply_change_v2 now returns failed_not_applied instead of mirroring a deletion.
  New tests: test_kaiju_broker_g1.py G1-10/10b/10c (list_tree/sync_tree raise on
  an unreadable root, destination untouched), G1-11/11b (sync_tree refuses a
  genuinely-empty readable source against a non-empty destination), G1-12/12b
  (full evaluate_v2 reproduction: unreadable staging_root ->
  E_GIT_OPERATION_FAILED, checkout HEAD/content unchanged) -- 35/35 passing (was
  28/28). test_kaiju_broker_g2.py G2-8 (same reproduction through the full apply
  pipeline: unreadable staging_root -> E_GIT_OPERATION_FAILED, checkout AND
  production both untouched) and G2-9 (apply_change_v2 called directly with an
  empty-but-valid checkout against non-empty production, same defense-in-depth
  pattern as G2-5) -- 14/14 passing (was 12/12). The test script's own gap (the
  G3v2-3 dirty-tree case never writing a new staging value, so it could hit
  evaluate_v2's no-op early exit before ever reaching the guard under test) was
  also fixed, by writing a genuinely new staging value immediately before
  building that request.

G3 STEP 3 SUPERSEDED by G3 STEP 3b for the code-install path: step 3 installed
the PRE-FIX broker (sha256 c4e91852...) and its own copy of the v2 end-to-end
checks carries the same now-fixed test-script gap described above (edited
in-place for the historical record, not re-run -- see g3_step3_broker_replace.sh).
Treat g3_step3_broker_replace.sh as historical/reference only from here on; the
dummy-git target's policy.json block it installed stays live and is NOT
re-touched by step 3b.

G3 STEP 3b (g3_step3b_v2_checks.sh --apply, the operator, 2026-10-09): installed the
FIXED broker code ONLY (policy.json untouched -- the dummy-git block from step 3
was already live and correct). Took a NEW numbered backup
(/opt/kaiju-broker/kaiju_broker.py.b6-20261009) without touching or overwriting
the existing step-3 backup (.b5-20261009); the script aborts outright if that
prior backup is missing, or if a .b6-20261009 backup already exists. Re-ran ONLY
the v2 end-to-end checks against the dummy-git target (not the v1 regression,
which already passed under step 3 and is unaffected by this code-only change):
good change -> promoted, bad change -> failed_rolled_back (bad commit + revert
both visible in history), dirty production tree -> failed_not_applied (now
actually exercised, per the fix above), real /opt/kaiju-gateway left untouched,
ownership check clean. RESULT: 12/12 PASS. Live broker is now the FIXED version,
sha256 12cef81c....

CARRIED ITEM for G3 continuation (not yet done, flagged so it is not silently
inherited): before G2 is ever attempted against the REAL a2a-gateway target (as
opposed to the dummy-git target used throughout G3 so far), kaibroker's actual
read permission on /srv/angkai/mcp-a2a-gateway-sandbox must be verified --
not assumed -- e.g. `sudo -u kaibroker test -r
/srv/angkai/mcp-a2a-gateway-sandbox && sudo -u kaibroker ls
/srv/angkai/mcp-a2a-gateway-sandbox`. This incident is exactly the failure
mode such a check would have caught ahead of time on the dummy target; the real
target needs the same verification before it is ever relied on, not just the
same code fix.

ROLLBACK PATHS currently on disk (host, as of 2026-10-09): code --
/opt/kaiju-broker/kaiju_broker.py.b5-20261009 (pre-step-3, i.e. the original B4
code, sha256 e74c63cf...), /opt/kaiju-broker/kaiju_broker.py.b6-20261009
(pre-step-3b, i.e. step 3's installed PRE-FIX G1+G2 code, sha256 c4e91852...);
policy -- /etc/kaiju-broker/policy.json.bak-g3-20261009 (pre-dummy-git-block
policy, from step 3; step 3b did not touch policy.json so there is no separate
policy backup for it). Rollback commands are printed by each script's own
--apply run and are not repeated here to avoid a stale copy drifting from the
scripts.

G3 STEP 4 + 5 (g3_step4_permission_checks.sh --apply, the operator, dokaisho,
2026-10-09): RESULT 10 passed, 0 failed (non-mutating test -w/-r/-x and ls
only). As angkai: no write to /opt/kaiju-broker-dummy-git, /opt/kaiju-gateway,
/opt/kaiju-broker, /etc/kaiju-broker/policy.json,
/var/spool/kaiju-broker/outcomes; no read or list of
/var/lib/kaiju-broker/dummy-git-checkout; CAN write
/var/spool/kaiju-broker/incoming and /srv/angkai/broker-dummy-staging.
As kaibroker: cannot write /srv/angkai/broker-dummy-staging. Step 5
report (kaibroker, GIT_OPTIONAL_LOCKS=0): /opt/kaiju-gateway working tree
clean on main at 236b433 (Baseline: B1-B4 production file-replace applies),
directly on top of upstream 09e46b8 (origin/main).

CARRIED ITEM CLEARED (the operator, dokaisho, 2026-10-09): the check found
kaibroker could NOT list /srv/angkai/mcp-a2a-gateway-sandbox (find as
kaibroker: Permission denied on the top folder). Cause: a named ACL entry
user:kaibroker:--x on the folder (owner angkai, group kaiju-agents, drwxrwsr-x),
which overrides other::r-x for kaibroker -- the same ACL pattern as the
dummy-staging incident. Fix: `sudo setfacl -R -m u:kaibroker:rX
/srv/angkai/mcp-a2a-gateway-sandbox` (r-x on directories, read on files,
no write; owner/group/other unchanged). Re-check
(`sudo -u kaibroker find ... 2>&1 >/dev/null`) printed nothing, so kaibroker can
now read and list the whole sandbox tree.

REAL GATEWAY STAGE 1 (g3_real_stage1_gateway_v2_setup.sh --apply
--dryrun-gate-open, the operator, dokaisho, 2026-10-09): preflight 19/19, final 39/39
PASS. v2 for the REAL a2a-gateway is installed in DRY-RUN-ONLY form. Created:
broker checkout /var/lib/kaiju-broker/a2a-gateway-git-checkout (kaibroker-only,
seeded with a baseline commit of production HEAD 236b433, checkout HEAD
ae7a8ce, identical to staging); twin data dir + uv cache under
/srv/kaiju-broker-gateway-twin; sandbox twin unit
mcp-a2a-gateway-git-sandbox.service (127.0.0.1:10098, User=kaibroker because
angkai cannot read the checkout; ExecStart derived from the existing v1 sandbox
twin; warm-up probe HTTP 400, same as production's bare GET); exact-match
sudoers rule /etc/sudoers.d/kaibroker-gateway-git-sandbox; and a "git" block
under targets.a2a-gateway in policy.json with apply_enabled FALSE, written last
(backup /etc/kaiju-broker/policy.json.bak-stage1-20261009). The class minimum
was written as stage_0 (--dryrun-gate-open) so a dry run can run while
is at graduated_window; it MUST be set back to fully_autonomous in the same
edit that ever turns apply_enabled on. Production untouched: HEAD still
236b433, gateway not restarted (MainPID 3654), the four existing sudoers files
byte-identical, v1 apply flag unchanged. Rollback: `sudo bash
g3_real_stage1_gateway_v2_setup.sh --remove --apply` (policy backup kept).

FINDINGS for the apply decision: the gateway's prod_check has no
expect_body_contains and a bare GET /mcp returns HTTP 400, so "healthy" means
unit active after the 8 s settle plus any answer under 500 -- it catches a crash,
an import error or an unbound port, not a logic bug (v1 has the same weakness; a
stricter probe needs a broker code change). A revert is a git revert commit in
/opt/kaiju-gateway followed by a second restart of mcp-a2a-gateway.service, so
the worst case is two gateway restarts and failed in-flight calls during each.

STAGE 2 DRY RUN, FIRST RUN FAILED (g3_real_stage2_dryrun.sh --apply, the operator,
dokaisho, 2026-10-09): 21 passed, 2 failed. Both v2 requests (even the no-op
restore) escalated P_PATH_NOT_ALLOWED. Root cause: the real gateway tracks
release.sh as 100755 (checkout index and staging both executable), and
sync_tree forced os.chmod(dest, 0o644) on every copied file, so every sync
showed a mode-only change on release.sh, outside allowed_relpaths
(mcp_a2a_gateway/*.py). The dummy target had no executable files, so G1-G3
never hit it. No harm: escalated before the twin restart, nothing applied,
production untouched, staging restored, checkout reset. apply_change_v2 uses
the same sync_tree, so apply would have hit it too (failed_not_applied).

FIX (broker code, local commit 8e0169c; installed by g3_step3c_install_fix.sh
--apply, 2026-10-09, 10/10 PASS): in sync_tree a destination that already
exists keeps its own executable state (0o755 if any x bit, else 0o644); a new
file is always 0o644; the SOURCE mode is never consulted, so angkai cannot grant
execute through staging. Tests: G1 41/41 (new G1-13..15c), G2 15/15 (new G2-10),
guardrail 17/17. Installed sha256 4e5e4038... ; new backup
/opt/kaiju-broker/kaiju_broker.py.b7-20261009 (b6 untouched). Rollback: sudo cp
-p /opt/kaiju-broker/kaiju_broker.py.b7-20261009
/opt/kaiju-broker/kaiju_broker.py. Dummy good/bad/dirty re-check after install:
promoted / failed_rolled_back / failed_not_applied, 10/10.

STAGE 2 DRY RUN, RE-RUN (same script, banner fixed to print DONE only when 0
failures): 29 passed, 0 failed. Both requests dry_run_pass (ledger
G3-REAL-DRYRUN-c1028f7b and G3-REAL-DRYRUN-55b52d37), each moved the checkout
by exactly one commit touching only mcp_a2a_gateway/agent_manager.py, proof files
record pass; production HEAD 236b433, tree clean, MainPID 3654 unchanged, twin
stopped. The v2 pipeline now runs end to end on the real gateway up to, not
including, apply. Note: the ledger ids of the two earlier escalations quoted in
the broker docstring (36bed22c..., 11b693f9...) were not verified against the
ledger.

STRICTER HEALTH PROBE (2026-10-09, built via Code, local commit 1583399): new
optional per-check "probe" object in policy (method GET/POST, headers, body,
expect_status, expect_body_contains, max_read_bytes); validate_probe() fails
closed on a malformed object; probe_alive() is a raw-socket client that reads at
most max_read_bytes and never waits for EOF (MCP initialize answers as a held-open
text/event-stream); service_ok() uses it only when "probe" is present, so checks
without it (dummy target, v1) behave byte-for-byte as before (http_alive
unchanged). Live facts: POST initialize to 127.0.0.1:10000/mcp returns HTTP 200,
SSE body with serverInfo.name "MCP A2A Gateway Server" 4.0.11. Tests: G1 60/60,
G2 17/17 (new G2-11 promoted via probe, G2-12 wrong marker -> failed_rolled_back),
guardrail 17/17. INSTALLED: g3_step3d_install_probe.sh --apply (the operator): sha pin
matched, backup kaiju_broker.py.b8-20261009 (b7 untouched), dummy re-check 10/10.
POLICY: g3_real_stage3_probe_policy.sh --apply (the operator): probe added to the real
gateway's git.sandbox_check (127.0.0.1:10098) and git.prod_check
(127.0.0.1:10000) only, 9/9, backup /etc/kaiju-broker/policy.json.bak-stage3-20261009,
apply_enabled still false, class min still stage_0; stage 2 dry run re-run with
the probe on the twin: 29/0, production untouched (HEAD 236b433, MainPID 3654).
Rollback: policy `sudo bash g3_real_stage3_probe_policy.sh --remove --apply`;
code `sudo cp -p /opt/kaiju-broker/kaiju_broker.py.b8-20261009
/opt/kaiju-broker/kaiju_broker.py`.

KNOWN WEAKNESS (found on review, FIXED 2026-10-09 by step 3e, see below):
probe_alive stopped reading as soon as it had headers plus one body byte. If the server's first chunk of an
SSE reply arrives as a chunk-size line in one segment and the JSON in the next, the
marker is not yet in the data read and the probe returns False. The poll loop
retries, but service_ok's final check after the settle is a single attempt, so a
false negative there on production would trigger a needless revert (two restarts).
It passed every live run so far. Fix: keep reading until the marker is found,
max_read_bytes is reached, or the timeout expires.

PROBE READ-LOOP FIX (local commit 4aad6a1, installed by g3_step3e_install_probe_fix.sh
--apply, the operator, 2026-10-09): after the headers are complete probe_alive keeps
reading until the marker is in the body read so far (re-checked after every recv,
so a marker split across segments is found), max_read_bytes is reached, the
timeout expires or the peer closes. Tests G1 66/66 (new G1-25..28: split chunk-size
line + JSON, split marker, no marker with open connection, peer close after
marker), G2 17/17, guardrail 17/17. Install: sha pin 6617960b... matched, backup
kaiju_broker.py.b9-20261009 (b8 untouched), dummy re-check 10/10, stage 2 dry run
re-run against the real gateway with the fixed probe 29/0, production untouched
(HEAD 236b433, MainPID 3654). Rollback: sudo cp -p
/opt/kaiju-broker/kaiju_broker.py.b9-20261009 /opt/kaiju-broker/kaiju_broker.py.

STAGE 4 RUN (g3_real_stage4_enable_apply.sh --apply, the operator, dokaisho, 2026-10-09,
preflight 8/0, final 12 passed / 0 failed): APPLY IS NOW ENABLED for the real
a2a-gateway. policy.json now has targets.a2a-gateway.git.apply_enabled true and
classes.code_file_replace.min_checkpoint_state fully_autonomous, probes intact;
backup /etc/kaiju-broker/policy.json.bak-stage4-20261009. Production untouched
(HEAD 236b433, tree clean, MainPID 3654). Nothing was promoted.  is
graduated_window, so every real-gateway v2 request escalates P_CHECKPOINT_STATE
until it reaches fully_autonomous. Disable: sudo bash g3_real_stage4_enable_apply.sh
--remove --apply (apply_enabled false, class min stays fully_autonomous), or
sudo cp -p /etc/kaiju-broker/policy.json.bak-stage4-20261009
/etc/kaiju-broker/policy.json. Script design:
dry-run by default; --preflight, --apply, --remove [--apply]. One edit, two keys
under targets.a2a-gateway.git: apply_enabled false -> true AND
classes.code_file_replace.min_checkpoint_state stage_0 -> fully_autonomous, with a
structural assert (undo just those two keys, require equality with the old policy),
refusal unless the new class min is exactly fully_autonomous, a preflight that
requires the step 3e broker sha and probes on both checks, a typed ENABLE-APPLY
confirmation, backup policy.json.bak-stage4-20261009, and post-checks that
production HEAD, tree and MainPID are unchanged. Effect today: none, because
 is graduated_window so requests escalate P_CHECKPOINT_STATE before any
sync or restart; the stage 2 dry run script then reports GATE_BLOCKS (intended).
Disable: --remove --apply sets apply_enabled false only (class min stays
fully_autonomous, fail closed); whole-file restore from the backup also works.
The policy-edit logic was exercised against a fake policy before delivery.
The real apply path (sync, commit, restart, probe, revert) has NOT yet run on
the real gateway; it has only run on the dummy target.

STATUS: G3 DONE on the DUMMY target; real a2a-gateway has v2 stage 1 + stage 2
dry run (29/0) + stricter probe configured and fixed (apply_enabled false, v1
apply flag untouched) and apply ENABLED with the class gate at fully_autonomous
(stage 4). Phase G build and install work is complete. Open:  must reach
fully_autonomous before any real-gateway promotion can run; the first real
promotion should be watched (two gateway restarts in the worst case). Nothing
pushed; all commits local.
