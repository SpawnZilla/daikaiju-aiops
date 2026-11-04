#!/usr/bin/env python3
"""
kaiju_broker.py --  Layer C promotion broker, milestones B1..B4
(validator + ledger + outcomes + intake copy + BROKER-OWN sandbox proof +
apply / post-check / automatic rollback).
APPLY IS PER-TARGET OPT-IN: only a target with "apply_enabled": true is ever
written. B3 enables it for the throwaway DUMMY target only; the a2a-gateway
target stays dry-run until B4 (the operator, 2026-09-26: production restart rule
only in B4).
Design: .md (v0.1, approved
2026-09-26). Written by Mokaima 2026-09-26, Full Auto part 13.

Deterministic, stdlib only, no LLM. Nothing from a request is ever
executed. Each request file is processed exactly once and removed from
incoming/; its outcome is written to outcomes/<request_id>.json and a line
is appended to the ledger.

Check order (first failure wins):
  1. File-level:  symlink/non-regular -> E_OWNER (escalate); owner uid !=
                  allowed uid -> E_OWNER (escalate); too large / bad JSON /
                  bad name -> fixable
  2. Schema:      required fields + types -> fixable
  3. Replay:      request_id already in ledger -> E_REPLAY (escalate)
  4. Resubmits:   >= MAX_ATTEMPTS prior ledger entries for task_id ->
                  E_RESUBMIT_LIMIT (escalate). The ledger is the authority;
                  the request's own "attempt" field is informational only.
  5. Policy:      target / change_class / target_relpath / checkpoint state
                  -> P_* (escalate; never returned as fixable)
  6. Artifact:    must resolve to staging_root/target_relpath, regular
                  file, sha256 match -> fixable
  7. B2 sandbox proof (the broker's OWN, replaces any agent-supplied proof):
       a. intake copy of the artifact into state/work/<request_id>/, hashed
          -> must equal artifact_sha256 (E_HASH_MISMATCH)
       b. restart the SANDBOX twin unit (exact-match sudoers rule) so it
          runs exactly this code; wait for it; HTTP probe must answer < 500
          and the unit must still be active after settle_seconds
          -> else E_SANDBOX_CHECK_FAILED (fixable)
       c. re-hash the staging file after the check -> must still equal the
          intake hash, else E_ARTIFACT_CHANGED (fixable)
       d. write state/proofs/<request_id>.json (broker-owned)
  Pass -> status "dry_run_pass" when the target is not apply-enabled.
  8. B3 apply (apply_enabled targets only):
       a. destination = production_root/target_relpath (realpath must stay
          inside production_root; no symlink destination)
       b. snapshot the current file (or record that none existed)
       c. atomically replace it with the INTAKE COPY (never the staging file)
       d. restart the production unit (exact sudoers rule), wait, probe
          (optional expect_body_contains), still active after settle
       e. pass -> "promoted"; fail -> restore snapshot, restart, re-check:
          ok -> "failed_rolled_back"; not ok -> "failed_rollback_failed"
          (both escalate to the operator). A guard refusal before anything is
          written (bad destination, missing prod_check, write error) ->
          "failed_not_applied" (escalate).

B2 DECISION (2026-09-26): 's proof store (/srv/angkai/
sandbox_proofs) has no producer and its format carries no artifact hash, so
it cannot say WHICH code passed. Per the approved Q2 ("the broker re-runs a
fixed check itself rather than trusting Angkai's report"), the broker now
produces its own proof. proof_ref is optional and never trusted.
RESIDUAL (Layer A): the agent could change the staging file and change it
back between the pre-check and re-hash; the intake copy is what B3 applies,
so production can only ever receive bytes the broker hashed itself.

POLICY FORMAT: JSON (policy.json), not YAML as the design doc says -- keeps
the broker stdlib-only.

B4 (2026-09-26):
  - artifact_sha256 is OPTIONAL: Angkai has no hashing tool (no Bash). If
    given it must match; if absent the broker uses its intake copy's hash.
    Nothing is weakened: the sandbox proof and the apply always use the
    intake copy the broker hashed itself.
  - ntfy alert for every outcome that needs the operator (escalated,
    failed_rolled_back, failed_rollback_failed, failed_not_applied) and an
    info alert for promoted. Config /etc/kaiju-broker/ntfy.json (root:kaibroker
    0640). Best-effort: an alert failure never changes the decision.

PHASE G -- G1 (2026-10-09): schema_version "2", DRY RUN ONLY. Design:
.md section 8 + the G0 addendum.
G0's answer to Q-G1: the BROKER creates the commit, Angkai never touches git
(its headless tool list has no git tool and no Bash). DEVIATION from the
handoff's literal "commit hash" field, same way B1 deviated from the YAML
design and B2 deviated from trusting proof_ref: a v2 request names only
target/change_class, NOT a commit hash Angkai cannot produce. On a v2
request the broker mirrors target["staging_root"] into its OWN git checkout
(target["git"]["broker_checkout"], kaibroker-owned, outside every angkai MCP
root and outside validate-kaiju-relay-path.sh's allowlist -- angkai cannot
reach it), skipping target["git"]["ignore_patterns"] (build junk must never
enter a commit or trip the path policy), stages+commits, policy-checks EVERY
changed path against target["git"]["classes"][cls]["allowed_relpaths"] (the
multi-file generalization of v1's single target_relpath check), and on any
rejection resets the checkout back to the previous HEAD -- so checkout HEAD
only ever holds the last policy-passed, sandbox-proven snapshot. Sandbox proof
re-uses v1's restart_unit/service_ok against target["git"]["sandbox_check"]
(a twin unit whose WorkingDirectory must be repointed to broker_checkout --
host install, not built here) and additionally verifies HEAD is still the new
commit afterward (git analogue of B2's re-hash). G1 NEVER applies to
production: apply/rollback via `git revert` is G2. v1 (schema_version "1") is
completely unchanged -- same REQUIRED dict, same function body, dispatched to
before any v2-only code runs.

PHASE G -- G2 (2026-10-09): apply as a production commit + post-check +
automatic revert, DUMMY TARGET ONLY (same B3 pattern: apply is per-target
opt-in via target["git"]["apply_enabled"], exact-match sudoers, throwaway
units). The real a2a-gateway git target is NOT touched by G2 -- it has no
"apply_enabled" key under its (future) "git" block until a separate GO.
Production gets a fresh commit built the same content-addressed way B3
applies files (mirror the broker checkout's PROVEN tree into
target["git"]["production_root"] via sync_tree, the same function G1 uses to
build the checkout -- never the checkout's own foreign commit history, which
would overwrite production's lineage wholesale). This keeps production's
commit history its own (parent = production's own prior HEAD, captured
before anything is touched). Before touching anything, apply_change_v2
refuses outright (failed_not_applied) if production's working tree is not
clean: sync_tree mirrors by deleting as well as copying, so running it
against uncommitted tracked or untracked changes would silently destroy them
with no snapshot to recover from. Rollback on a failed post-check is a real
`git revert` of the fresh commit, not `git reset --hard`: revert creates a
new commit that is the inverse of the bad one, so the bad commit stays
reachable and visible in production's log (the design's "reviewable history"
goal) instead of becoming an unreferenced dangling object. reset --hard is
still used, but only for PRE-commit guard refusals (bad diff, disallowed
path, failed `git commit`) where nothing has landed in history yet and there
is nothing to revert; the no-op case (sync_tree produced zero diff, so no
commit was made) is guarded separately so a failed post-check there can never
attempt to revert an unrelated prior commit. Every terminal outcome
(promoted, failed_rolled_back, failed_rollback_failed) is recorded to
state/snapshots/<rid>.json with prev_head, applied_commit and (if any)
revert_commit, giving the ledger an auditable hash trail. production_root
must already be a baseline-committed git repo (the operator runs this by hand, once,
outside the broker -- the broker never auto-inits a production repo,
mirroring B3's refusal-not-silent-fix guard for a missing prod_check). Path
policy is re-checked independently against production's OWN diff before
committing (defense in depth: never assume the checkout-side check was
sufficient). Check order after G1's dry_run_pass:
target["git"]["apply_enabled"] is True -> apply_change_v2(); same statuses as
B3 (promoted, failed_rolled_back, failed_rollback_failed, failed_not_applied),
same ALERT_STATUSES, no new ntfy code needed.
"""
import hashlib
import shutil
import socket
import ssl
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import json
import os
import re
import stat
import sys
import time
import uuid
from datetime import datetime, timezone

MAX_REQUEST_BYTES = 64 * 1024
MAX_ATTEMPTS = 5            # original + 4 resubmits (the operator, 2026-09-26)
SCHEMA_VERSION = "1"
STATE_RANK = {"stage_0": 0, "graduated_window": 1, "fully_autonomous": 2}
REQ_NAME = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.json$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
REQUIRED = {
    "schema_version": str, "request_id": str, "task_id": str, "target": str,
    "change_class": str, "target_relpath": str, "artifact_path": str,
    "submitted_at": str,
}
REQUIRED_V2 = {
    "schema_version": str, "request_id": str, "task_id": str, "target": str,
    "change_class": str, "submitted_at": str,
}
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # git's well-known empty-tree hash
ESCALATE_CODES = {"E_OWNER", "E_REPLAY", "E_RESUBMIT_LIMIT"}


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Config:
    def __init__(self):
        e = os.environ.get
        self.ntfy_path = e("KAIBROKER_NTFY", "/etc/kaiju-broker/ntfy.json")
        self.spool = e("KAIBROKER_SPOOL", "/var/spool/kaiju-broker")
        self.state_dir = e("KAIBROKER_STATE", "/var/lib/kaiju-broker")
        self.policy_path = e("KAIBROKER_POLICY", "/etc/kaiju-broker/policy.json")
        self.checkpoint_path = e(
            "KAIBROKER_CHECKPOINT",
            "/srv/kaiju-governance/Health/a2a_checkpoint_state.json")
        uid = e("KAIBROKER_ALLOWED_UID")
        if uid is None:
            import pwd
            uid = pwd.getpwnam("angkai").pw_uid
        self.allowed_uid = int(uid)
        self.incoming = os.path.join(self.spool, "incoming")
        self.outcomes = os.path.join(self.spool, "outcomes")
        self.ledger = os.path.join(self.state_dir, "ledger.jsonl")


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def ledger_entries(cfg):
    try:
        with open(cfg.ledger, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except ValueError:
                        continue
    except FileNotFoundError:
        return


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def checkpoint_state(cfg):
    """Missing/unreadable state fails CLOSED (stage_0), never open."""
    try:
        s = load_json(cfg.checkpoint_path).get("checkpoint_state")
        return s if s in STATE_RANK else "stage_0"
    except (OSError, ValueError, AttributeError):
        return "stage_0"


def safe_relpath(rel):
    return (bool(rel) and not rel.startswith("/") and "\\" not in rel
            and ".." not in rel.split("/") and os.path.normpath(rel) == rel)


def glob_match(rel, patterns):
    import fnmatch
    return any(fnmatch.fnmatchcase(rel, p) for p in patterns)


def evaluate(cfg, policy, path, name):
    """Returns (request_id_or_None, task_id_or_None, codes, applied_or_None)."""
    try:
        st = os.lstat(path)
    except OSError:
        return None, None, ["E_OWNER"], None
    if not stat.S_ISREG(st.st_mode) or st.st_uid != cfg.allowed_uid:
        return None, None, ["E_OWNER"], None
    if not REQ_NAME.match(name):
        return None, None, ["E_BAD_REQUEST_NAME"], None
    if st.st_size > MAX_REQUEST_BYTES:
        return None, None, ["E_TOO_LARGE"], None
    try:
        req = load_json(path)
    except (OSError, ValueError):
        return None, None, ["E_BAD_JSON"], None
    if not isinstance(req, dict):
        return None, None, ["E_BAD_JSON"], None

    rid = req.get("request_id") if isinstance(req.get("request_id"), str) else None
    tid = req.get("task_id") if isinstance(req.get("task_id"), str) else None

    # Dispatch on schema_version BEFORE the v1 REQUIRED check, since v2
    # requests legitimately omit v1-only fields (target_relpath,
    # artifact_path). schema_version itself is validated here either way,
    # identically to how the v1 REQUIRED loop would have validated it.
    sv = req.get("schema_version")
    if "schema_version" not in req or sv in (None, ""):
        return rid, tid, ["E_FIELD_MISSING:schema_version"], None
    if not isinstance(sv, str):
        return rid, tid, ["E_FIELD_TYPE:schema_version"], None
    if sv == "2":
        return evaluate_v2(cfg, policy, req, rid, tid, name)
    if sv == "3":
        return evaluate_v3(cfg, policy, req, rid, tid, name)

    codes = []
    for f, t in REQUIRED.items():
        if f not in req or req[f] in (None, ""):
            codes.append("E_FIELD_MISSING:" + f)
        elif not isinstance(req[f], t):
            codes.append("E_FIELD_TYPE:" + f)
    if codes:
        return rid, tid, codes, None
    if req["schema_version"] != SCHEMA_VERSION:
        return rid, tid, ["E_SCHEMA_VERSION"], None
    try:
        if str(uuid.UUID(rid)) != rid or name != rid + ".json":
            return rid, tid, ["E_FIELD_TYPE:request_id"], None
    except ValueError:
        return rid, tid, ["E_FIELD_TYPE:request_id"], None
    claimed = req.get("artifact_sha256")
    if claimed is not None and (not isinstance(claimed, str) or not SHA_RE.match(claimed)):
        return rid, tid, ["E_FIELD_TYPE:artifact_sha256"], None

    prior = [x for x in ledger_entries(cfg)]
    if any(x.get("request_id") == rid for x in prior):
        return rid, tid, ["E_REPLAY"], None
    if sum(1 for x in prior if x.get("task_id") == tid) >= MAX_ATTEMPTS:
        return rid, tid, ["E_RESUBMIT_LIMIT"], None

    target = policy.get("targets", {}).get(req["target"])
    if target is None:
        return rid, tid, ["P_TARGET_NOT_ALLOWED"], None
    cls = target.get("classes", {}).get(req["change_class"])
    if cls is None:
        return rid, tid, ["P_CLASS_NOT_ALLOWED"], None
    rel = req["target_relpath"]
    if not safe_relpath(rel) or not glob_match(rel, target.get("allowed_relpaths", [])):
        return rid, tid, ["P_PATH_NOT_ALLOWED"], None
    need = cls.get("min_checkpoint_state", "fully_autonomous")
    if STATE_RANK.get(checkpoint_state(cfg), 0) < STATE_RANK.get(need, 2):
        return rid, tid, ["P_CHECKPOINT_STATE"], None

    staging_root = os.path.realpath(target["staging_root"])
    expected = os.path.join(staging_root, rel)
    art = req["artifact_path"]
    if not os.path.isabs(art) or os.path.realpath(art) != expected:
        return rid, tid, ["E_ARTIFACT_OUTSIDE_STAGING"], None
    try:
        ast = os.lstat(expected)
    except OSError:
        return rid, tid, ["E_ARTIFACT_MISSING"], None
    if not stat.S_ISREG(ast.st_mode):
        return rid, tid, ["E_ARTIFACT_OUTSIDE_STAGING"], None
    if claimed is not None and sha256_file(expected) != claimed:
        return rid, tid, ["E_HASH_MISMATCH"], None

    code = sandbox_proof(cfg, target, req, expected, rid)
    if code:
        return rid, tid, [code], None
    if target.get("apply_enabled") is not True:
        return rid, tid, [], None
    return rid, tid, [], apply_change(cfg, target, req, rid)


def restart_unit(unit):
    """Exact-match sudoers rule for kaibroker: systemctl restart <unit>."""
    r = subprocess.run(["sudo", "-n", "/usr/bin/systemctl", "restart", unit],
                       capture_output=True, timeout=120)
    return r.returncode == 0


def unit_active(unit):
    r = subprocess.run(["/usr/bin/systemctl", "is-active", unit],
                       capture_output=True, text=True, timeout=30)
    return r.stdout.strip() == "active"


def http_alive(url, timeout=5, expect=None):
    """True if the server answers with an HTTP status < 500 (and, when
    `expect` is given, a 2xx body containing that string). UNCHANGED since
    before the probe feature -- this is the path every sandbox_check/
    prod_check with no "probe" key still takes, byte-for-byte as before."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if expect is None:
                return resp.status < 500
            return 200 <= resp.status < 300 and expect in resp.read(65536).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return expect is None and exc.code < 500
    except (urllib.error.URLError, OSError, ValueError):
        return False


def validate_probe(probe):
    """Structural check for an OPTIONAL per-check "probe" object in policy
    (sandbox_check/prod_check). Same fail-closed style as every other
    policy field the broker consults (e.g. the isinstance(chk, dict) guards
    around sandbox_proof/apply_change): anything that doesn't match this
    exact shape is treated as an invalid policy, never guessed at or
    partially honored. method must be GET or POST; headers, if given, must
    be a flat string->string map (never logged beyond method+URL, so no
    header value the broker didn't already construct itself is ever
    written anywhere); body, if given, must already be a JSON string (the
    broker never serializes a body itself -- policy supplies exactly the
    bytes to send); expect_status and expect_body_contains are REQUIRED
    once a probe is present, since a probe with no success criteria would
    silently always pass; max_read_bytes, if given, must be a positive
    int."""
    if not isinstance(probe, dict):
        return False
    if probe.get("method", "GET") not in ("GET", "POST"):
        return False
    headers = probe.get("headers", {})
    if not isinstance(headers, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in headers.items()):
        return False
    body = probe.get("body")
    if body is not None and not isinstance(body, str):
        return False
    if not isinstance(probe.get("expect_status"), int):
        return False
    if not isinstance(probe.get("expect_body_contains"), str):
        return False
    mrb = probe.get("max_read_bytes", 65536)
    if not isinstance(mrb, int) or isinstance(mrb, bool) or mrb <= 0:
        return False
    return True


def probe_alive(url, probe, timeout=5):
    """Stricter liveness check for policy that opts in via a "probe" object.
    Sends exactly the request `probe` describes over a raw socket (not
    urllib: an MCP initialize response is `Content-Type: text/event-stream`
    with no Content-Length and the connection deliberately held open, which
    is indistinguishable from "still loading" to a client that insists on
    reading to EOF). Reads at most max_read_bytes and NEVER waits for the
    peer to close -- but once headers are complete it keeps reading (fixed
    2026-10-09: a single "headers + >=1 body byte" check was wrong for a
    chunked SSE reply, where the chunk-size line and the JSON payload can
    land in separate TCP segments, leaving the marker still unread on the
    first byte) until the body read so far contains expect_body_contains
    (re-checked after every recv, so a marker split across segments is
    still found once all its pieces have arrived), or max_read_bytes is
    reached, or the overall timeout expires, or the peer closes the
    connection -- whichever comes first. Never logs anything beyond the
    method and URL."""
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname
    if not host:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = (parsed.path or "/") + (("?" + parsed.query) if parsed.query else "")
    method = probe.get("method", "GET")
    # If this call site is ever extended to log, it must log ONLY
    # method + url (never headers/body) -- same discipline as every other
    # check in this file, which logs nothing from request content either.
    headers = dict(probe.get("headers", {}))
    body_bytes = (probe.get("body") or "").encode("utf-8")
    if body_bytes:
        headers.setdefault("Content-Length", str(len(body_bytes)))
    headers.setdefault("Host", host)
    headers.setdefault("Connection", "close")
    head = "%s %s HTTP/1.1\r\n" % (method, path)
    head += "".join("%s: %s\r\n" % (k, v) for k, v in headers.items())
    head += "\r\n"
    wire = head.encode("utf-8") + body_bytes
    max_bytes = probe.get("max_read_bytes", 65536)
    marker = probe["expect_body_contains"]
    deadline = time.time() + timeout
    data = b""
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            if parsed.scheme == "https":
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
            sock.sendall(wire)
            while len(data) < max_bytes:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                sock.settimeout(remaining)
                try:
                    chunk = sock.recv(max_bytes - len(data))
                except socket.timeout:
                    break
                if not chunk:
                    break  # peer closed -- fine, we just stop reading
                data += chunk
                head_end = data.find(b"\r\n\r\n")
                if head_end == -1:
                    continue  # headers not complete yet -- keep reading
                body_so_far = data[head_end + 4:]
                if marker in body_so_far.decode("utf-8", "replace"):
                    break  # marker found: enough to decide, don't wait for more
    except OSError:
        return False
    if not data:
        return False
    status_line = data.split(b"\r\n", 1)[0]
    try:
        status = int(status_line.split(b" ")[1])
    except (IndexError, ValueError):
        return False
    if status != probe["expect_status"]:
        return False
    body_so_far = data.partition(b"\r\n\r\n")[2]
    return marker in body_so_far.decode("utf-8", "replace")


def service_ok(chk):
    """Wait for the probe, settle, then require active + probe again. A
    "probe" object replaces ONLY the HTTP liveness test below -- the
    poll-until-timeout, settle, and final unit_active() + re-probe
    structure is identical either way. An invalid probe object fails
    closed immediately (no network call at all): a policy bug must never
    be mistaken for "server not up yet" and retried into a timeout."""
    probe = chk.get("probe")
    if probe is not None and not validate_probe(probe):
        return False
    if probe is not None:
        def alive():
            return probe_alive(chk["url"], probe)
    else:
        exp = chk.get("expect_body_contains")

        def alive():
            return http_alive(chk["url"], expect=exp)

    deadline = time.time() + int(chk.get("timeout_seconds", 60))
    while time.time() < deadline and not alive():
        time.sleep(1)
    time.sleep(int(chk.get("settle_seconds", 8)))
    return unit_active(chk["unit"]) and alive()


def sandbox_proof(cfg, target, req, staging_file, rid):
    chk = target.get("sandbox_check")
    if not isinstance(chk, dict):
        return "E_SANDBOX_CHECK_FAILED"
    work = os.path.join(cfg.state_dir, "work", rid)
    os.makedirs(work, exist_ok=True)
    intake = os.path.join(work, "artifact")
    shutil.copyfile(staging_file, intake)
    os.chmod(intake, 0o640)
    h = sha256_file(intake)
    if req.get("artifact_sha256") is not None and h != req["artifact_sha256"]:
        return "E_HASH_MISMATCH"
    if not restart_unit(chk["unit"]):
        return "E_SANDBOX_CHECK_FAILED"
    if not service_ok(chk):
        return "E_SANDBOX_CHECK_FAILED"
    if sha256_file(staging_file) != h:
        return "E_ARTIFACT_CHANGED"
    os.makedirs(os.path.join(cfg.state_dir, "proofs"), exist_ok=True)
    atomic_write(os.path.join(cfg.state_dir, "proofs", rid + ".json"), {
        "request_id": rid, "task_id": req["task_id"], "target": req["target"],
        "target_relpath": req["target_relpath"], "artifact_sha256": h,
        "intake_copy": intake, "sandbox_unit": chk["unit"], "probe_url": chk["url"],
        "result": "pass", "created_at": now_iso(),
    })
    return None


def apply_change(cfg, target, req, rid):
    """B3. Only reached for apply_enabled targets after a passing sandbox
    proof. Writes ONLY inside this target's production_root, and only the
    broker's own intake copy. Returns the final status string."""
    chk = target.get("prod_check")
    if not isinstance(chk, dict):
        return "failed_not_applied"  # misconfigured: refuse, escalate
    root = os.path.realpath(target["production_root"])
    dest = os.path.join(root, req["target_relpath"])
    parent = os.path.dirname(dest)
    if (not dest.startswith(root + os.sep) or not os.path.isdir(parent)
            or os.path.realpath(parent) != parent):
        return "failed_not_applied"
    if os.path.islink(dest) or (os.path.exists(dest) and not os.path.isfile(dest)):
        return "failed_not_applied"
    work = os.path.join(cfg.state_dir, "work", rid)
    intake = os.path.join(work, "artifact")
    snap = os.path.join(cfg.state_dir, "snapshots", rid)
    os.makedirs(snap, exist_ok=True)
    existed = os.path.isfile(dest)
    if existed:
        shutil.copy2(dest, os.path.join(snap, "original"))
    atomic_write(os.path.join(snap, "meta.json"), {
        "request_id": rid, "dest": dest, "existed": existed, "taken_at": now_iso()})

    def put(src):
        tmp = dest + ".broker-tmp-" + rid
        shutil.copyfile(src, tmp)
        os.chmod(tmp, 0o644)
        os.replace(tmp, dest)

    try:
        put(intake)
    except OSError:
        return "failed_not_applied"
    if restart_unit(chk["unit"]) and service_ok(chk):
        return "promoted"
    # automatic rollback
    try:
        if existed:
            put(os.path.join(snap, "original"))
        elif os.path.exists(dest):
            os.remove(dest)
    except OSError:
        return "failed_rollback_failed"
    if restart_unit(chk["unit"]) and service_ok(chk):
        return "failed_rolled_back"
    return "failed_rollback_failed"


# ---------------- G1: schema_version "2" (git commits, DRY RUN ONLY) ----------------

def run_git(cwd, *args, check=True):
    r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True,
                        text=True, timeout=60)
    if check and r.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), r.stderr.strip()))
    return r


def ensure_repo(path):
    os.makedirs(path, exist_ok=True)
    if not os.path.isdir(os.path.join(path, ".git")):
        run_git(path, "init", "-q", "-b", "main")


def git_head(path):
    r = run_git(path, "rev-parse", "HEAD", check=False)
    return r.stdout.strip() if r.returncode == 0 else None


def git_write_gitignore(path, patterns):
    """Defense in depth: even if sync_tree misses an ignored path (or the
    sandboxed process under test writes one at runtime), git never stages it."""
    content = ("\n".join(patterns) + "\n") if patterns else ""
    gi = os.path.join(path, ".gitignore")
    cur = None
    if os.path.exists(gi):
        with open(gi, encoding="utf-8") as fh:
            cur = fh.read()
    if cur != content:
        with open(gi, "w", encoding="utf-8") as fh:
            fh.write(content)


def should_ignore(rel, patterns):
    import fnmatch
    parts = rel.split("/")
    return any(fnmatch.fnmatchcase(part, p) for part in parts for p in patterns) or \
        any(fnmatch.fnmatchcase(rel, p) for p in patterns)


def _raise(err):
    raise err


def list_tree(root, patterns):
    """os.walk's default onerror=None silently skips any directory it can't
    scandir (e.g. an ACL that denies the broker's own user --x on a
    subtree), which makes an unreadable tree look identical to an empty one.
    Pass onerror so that case raises instead -- a caller that treats this as
    "nothing to mirror" has no way to tell unreadable apart from genuinely
    empty, and sync_tree below must not confuse the two."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root, onerror=_raise):
        dirnames[:] = [d for d in dirnames if d != ".git" and not should_ignore(d, patterns)]
        rel_dir = os.path.relpath(dirpath, root)
        for fn in filenames:
            rel = fn if rel_dir == "." else (rel_dir + "/" + fn)
            rel = rel.replace(os.sep, "/")
            if rel == ".gitignore" or should_ignore(rel, patterns):
                continue
            out[rel] = os.path.join(dirpath, fn)
    return out


def sync_tree(src_root, dst_root, patterns):
    """Mirror src_root into dst_root (copy changed/new, delete removed),
    skipping ignore_patterns on both sides. Never touches .git or .gitignore.
    Refuses outright if src_root comes back empty while dst_root is not: an
    unreadable source already raises inside list_tree above, but a source
    that is empty for some other reason (wrong path, not yet populated, an
    ACL quirk that returns zero entries without erroring) is just as
    dangerous to mirror onto a real tree, since sync_tree's delete pass would
    read that as "everything was removed" and wipe dst_root for real.
    Mode handling (fixed 2026-10-09 after two live P_PATH_NOT_ALLOWED
    escalations, ledger ids 36bed22c... and 11b693f9...): shutil.copyfile
    copies CONTENT ONLY, never the source's permission bits, so an
    unconditional os.chmod(dest, 0o644) after every copy was blowing away an
    existing destination file's executable bit every sync -- the real
    gateway checkout's release.sh is tracked as 100755, so every v2 sync
    showed a spurious mode-only diff on it and evaluate_v2 rejected the
    whole request as an unallowed path. A dest that already exists keeps
    its own executable state (0o755 if it had any x bit set, else 0o644);
    a dest that does not exist yet is always created 0o644. The SOURCE's
    mode is never consulted either way -- staging_root is angkai's sandbox,
    not something the broker should trust to decide what gets to be
    executable in production."""
    src = list_tree(src_root, patterns)
    dst = list_tree(dst_root, patterns)
    if not src and dst:
        raise RuntimeError(
            "sync_tree: refusing to mirror empty source %r onto non-empty "
            "destination %r" % (src_root, dst_root))
    for rel, abspath in src.items():
        dest = os.path.join(dst_root, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        keep_exec = os.path.exists(dest) and bool(os.stat(dest).st_mode & 0o111)
        shutil.copyfile(abspath, dest)
        os.chmod(dest, 0o755 if keep_exec else 0o644)
    for rel in dst:
        if rel not in src:
            os.remove(os.path.join(dst_root, rel))
    for dirpath, _dirnames, _filenames in os.walk(dst_root, topdown=False):
        rel_dir = os.path.relpath(dirpath, dst_root)
        if rel_dir == "." or ".git" in rel_dir.split(os.sep):
            continue  # never descend into .git's internals (e.g. empty refs/heads pre-first-commit)
        try:
            if not os.listdir(dirpath):
                os.rmdir(dirpath)
        except OSError:
            pass


def git_diff_staged_paths(path, old_ref):
    r = run_git(path, "diff", "--cached", "--name-only", old_ref or EMPTY_TREE, check=False)
    return [l for l in r.stdout.splitlines() if l]


def git_commit_all(path, message):
    env = dict(os.environ)
    env.update({"GIT_AUTHOR_NAME": "kaiju-broker", "GIT_AUTHOR_EMAIL": "kaibroker@localhost",
                "GIT_COMMITTER_NAME": "kaiju-broker", "GIT_COMMITTER_EMAIL": "kaibroker@localhost"})
    r = subprocess.run(["git", "-C", path, "commit", "-q", "--no-gpg-sign", "-m", message],
                        capture_output=True, text=True, timeout=30, env=env)
    return r.returncode == 0


def git_reset_hard(path, ref):
    """Discard any tentative staged/committed change, back to the last
    approved state (ref), or to a pristine empty tree if there was none yet.
    Only ever used PRE-commit (nothing has landed in reachable history yet);
    post-commit rollback uses git_revert_commit instead, see there."""
    if ref:
        run_git(path, "reset", "-q", "--hard", ref, check=False)
    else:
        run_git(path, "reset", "-q", check=False)
        run_git(path, "clean", "-q", "-fdx", check=False)


def git_is_clean(path):
    """True iff path's working tree has no uncommitted changes (tracked or
    untracked). sync_tree mirrors by copying AND deleting; against a dirty
    tree it would silently destroy whatever wasn't committed yet, with no
    snapshot to recover from -- so apply_change_v2 refuses outright instead."""
    r = run_git(path, "status", "--porcelain", check=False)
    return r.returncode == 0 and r.stdout.strip() == ""


def git_revert_commit(path, commit):
    """Create a new commit that is the inverse of commit, leaving commit
    itself intact and visible in history (unlike reset --hard, which would
    make it an unreachable dangling object). Used only for the post-commit
    rollback case, where the bad commit already landed in production."""
    env = dict(os.environ)
    env.update({"GIT_AUTHOR_NAME": "kaiju-broker", "GIT_AUTHOR_EMAIL": "kaibroker@localhost",
                "GIT_COMMITTER_NAME": "kaiju-broker", "GIT_COMMITTER_EMAIL": "kaibroker@localhost"})
    r = subprocess.run(["git", "-C", path, "revert", "--no-edit", "--no-gpg-sign", commit],
                        capture_output=True, text=True, timeout=30, env=env)
    return r.returncode == 0


def sandbox_proof_v2(cfg, gitcfg, checkout, new_head, rid, req):
    chk = gitcfg.get("sandbox_check")
    if not isinstance(chk, dict):
        return "E_SANDBOX_CHECK_FAILED"
    if not restart_unit(chk["unit"]):
        return "E_SANDBOX_CHECK_FAILED"
    if not service_ok(chk):
        return "E_SANDBOX_CHECK_FAILED"
    if git_head(checkout) != new_head:
        return "E_CHECKOUT_HEAD_CHANGED"
    os.makedirs(os.path.join(cfg.state_dir, "proofs"), exist_ok=True)
    atomic_write(os.path.join(cfg.state_dir, "proofs", rid + ".json"), {
        "request_id": rid, "task_id": req["task_id"], "target": req["target"],
        "schema_version": "2", "commit": new_head, "sandbox_unit": chk["unit"],
        "probe_url": chk["url"], "result": "pass", "created_at": now_iso(),
    })
    return None


def apply_change_v2(cfg, gitcfg, checkout, new_head, rid, req, patterns):
    """G2. Only reached for apply_enabled git targets after a passing sandbox
    proof. Mirrors with git commits what B3's apply_change does with files:
    production gets its OWN new commit (never the checkout's foreign history),
    content-addressed via sync_tree from the already-proven checkout tree, with
    an independent re-check of allowed_relpaths against production's own diff.
    Refuses outright (failed_not_applied) if production's working tree is not
    clean -- sync_tree mirrors by deleting as well as copying, and reset --hard
    cannot protect uncommitted work it was never told about. Pre-commit guard
    refusals use git_reset_hard (nothing has landed in history yet); a failed
    post-check instead uses git_revert_commit, so the bad commit stays visible
    in production's history rather than becoming a dangling object -- matching
    the design doc's "reviewable history" goal. Every terminal outcome is
    recorded to state/snapshots/<rid>.json with the relevant commit hashes.
    Returns the final status string, same vocabulary as B3's apply_change."""
    chk = gitcfg.get("prod_check")
    if not isinstance(chk, dict):
        return "failed_not_applied"
    prod = os.path.realpath(gitcfg["production_root"])
    prev_head = git_head(prod)
    if prev_head is None:
        return "failed_not_applied"  # must already be baseline-committed; never auto-init production
    if not git_is_clean(prod):
        return "failed_not_applied"  # refuse: sync_tree would silently overwrite/delete uncommitted work

    try:
        sync_tree(checkout, prod, patterns)
        run_git(prod, "add", "-A")
        changed = [p for p in git_diff_staged_paths(prod, prev_head) if p != ".gitignore"]
    except (OSError, RuntimeError, subprocess.SubprocessError):
        git_reset_hard(prod, prev_head)
        return "failed_not_applied"

    cls = gitcfg.get("classes", {}).get(req["change_class"]) or {}
    allowed = cls.get("allowed_relpaths", [])
    bad = [p for p in changed if not (safe_relpath(p) and glob_match(p, allowed))]
    if bad:
        git_reset_hard(prod, prev_head)
        return "failed_not_applied"

    if changed and not git_commit_all(prod, "kaiju-broker promote: task=%s request=%s" % (req["task_id"], rid)):
        git_reset_hard(prod, prev_head)
        return "failed_not_applied"
    new_prod_head = git_head(prod)

    def record(status, revert_head=None):
        os.makedirs(os.path.join(cfg.state_dir, "snapshots"), exist_ok=True)
        atomic_write(os.path.join(cfg.state_dir, "snapshots", rid + ".json"), {
            "request_id": rid, "task_id": req["task_id"], "target": req["target"],
            "schema_version": "2", "prev_head": prev_head, "applied_commit": new_prod_head,
            "revert_commit": revert_head, "status": status, "created_at": now_iso(),
        })

    if restart_unit(chk["unit"]) and service_ok(chk):
        record("promoted")
        return "promoted"

    # automatic rollback: git revert (not reset --hard), so the bad commit
    # stays reviewable in production's history instead of being discarded.
    if new_prod_head == prev_head:
        record("failed_rollback_failed")  # no-op apply: nothing committed, nothing to revert
        return "failed_rollback_failed"
    if not git_revert_commit(prod, new_prod_head):
        record("failed_rollback_failed")
        return "failed_rollback_failed"
    revert_head = git_head(prod)
    if restart_unit(chk["unit"]) and service_ok(chk):
        record("failed_rolled_back", revert_head)
        return "failed_rolled_back"
    record("failed_rollback_failed", revert_head)
    return "failed_rollback_failed"


def evaluate_v2(cfg, policy, req, rid, tid, name):
    """G1: schema_version "2". DRY RUN ONLY -- never writes to a
    production_root, regardless of any apply_enabled flag on the target."""
    codes = []
    for f, t in REQUIRED_V2.items():
        if f not in req or req[f] in (None, ""):
            codes.append("E_FIELD_MISSING:" + f)
        elif not isinstance(req[f], t):
            codes.append("E_FIELD_TYPE:" + f)
    if codes:
        return rid, tid, codes, None
    try:
        if str(uuid.UUID(rid)) != rid or name != rid + ".json":
            return rid, tid, ["E_FIELD_TYPE:request_id"], None
    except ValueError:
        return rid, tid, ["E_FIELD_TYPE:request_id"], None

    prior = list(ledger_entries(cfg))
    if any(x.get("request_id") == rid for x in prior):
        return rid, tid, ["E_REPLAY"], None
    if sum(1 for x in prior if x.get("task_id") == tid) >= MAX_ATTEMPTS:
        return rid, tid, ["E_RESUBMIT_LIMIT"], None

    target = policy.get("targets", {}).get(req["target"])
    if target is None:
        return rid, tid, ["P_TARGET_NOT_ALLOWED"], None
    gitcfg = target.get("git")
    if not isinstance(gitcfg, dict):
        return rid, tid, ["P_TARGET_NOT_ALLOWED"], None  # v2 not enabled for this target
    cls = gitcfg.get("classes", {}).get(req["change_class"])
    if cls is None:
        return rid, tid, ["P_CLASS_NOT_ALLOWED"], None
    need = cls.get("min_checkpoint_state", "fully_autonomous")
    if STATE_RANK.get(checkpoint_state(cfg), 0) < STATE_RANK.get(need, 2):
        return rid, tid, ["P_CHECKPOINT_STATE"], None

    staging_root = os.path.realpath(target["staging_root"])
    checkout = os.path.realpath(gitcfg["broker_checkout"])
    patterns = gitcfg.get("ignore_patterns", [])
    allowed = cls.get("allowed_relpaths", [])

    try:
        ensure_repo(checkout)
        prev_head = git_head(checkout)
        git_write_gitignore(checkout, patterns)
        sync_tree(staging_root, checkout, patterns)
        run_git(checkout, "add", "-A")
        changed = [p for p in git_diff_staged_paths(checkout, prev_head) if p != ".gitignore"]
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return rid, tid, ["E_GIT_OPERATION_FAILED"], None

    if not changed:
        git_reset_hard(checkout, prev_head)
        return rid, tid, [], None  # dry_run_pass: nothing changed, nothing to prove

    bad = [p for p in changed if not (safe_relpath(p) and glob_match(p, allowed))]
    if bad:
        git_reset_hard(checkout, prev_head)
        return rid, tid, ["P_PATH_NOT_ALLOWED"], None

    if not git_commit_all(checkout, "kaiju-broker snapshot: task=%s request=%s" % (tid, rid)):
        git_reset_hard(checkout, prev_head)
        return rid, tid, ["E_GIT_OPERATION_FAILED"], None
    new_head = git_head(checkout)

    code = sandbox_proof_v2(cfg, gitcfg, checkout, new_head, rid, req)
    if code:
        git_reset_hard(checkout, prev_head)
        return rid, tid, [code], None

    if gitcfg.get("apply_enabled") is not True:
        return rid, tid, [], None  # dry_run_pass; checkout HEAD stays at new_head
    return rid, tid, [], apply_change_v2(cfg, gitcfg, checkout, new_head, rid, req, patterns)


ALERT_STATUSES = {"escalated", "failed_rolled_back", "failed_rollback_failed", "failed_not_applied"}


# ---------------- : schema_version "3", change_class edit_brief ----------------
# The broker (not Angkai) applies a Kaiju Relay EDIT brief: exact-string edits from the brief's
# EDITS_JSON block, computed against the PRODUCTION file, written into the sandbox staging file,
# then the normal v1 sandbox proof + apply/rollback runs on that result. No LLM, no shell, nothing
# from the request is executed. Policy (per target): classes.edit_brief = {min_checkpoint_state,
# brief_dir}; the edited file must match target.allowed_relpaths and live under production_root.
MAX_BRIEF_BYTES = 256 * 1024
_EDIT_BLOCK = re.compile(r"EDITS_JSON[^\n]*\n```json\n(.*?)\n```", re.DOTALL)


def _plan_edits(text, edits):
    spans = []
    for i, e in enumerate(edits, 1):
        if not isinstance(e, dict):
            raise ValueError("edit %d not an object" % i)
        old, new = e.get("old_text"), e.get("new_text")
        if not isinstance(old, str) or not isinstance(new, str) or not old.strip() or old == new:
            raise ValueError("edit %d invalid" % i)
        if text.count(old) != 1:
            raise ValueError("edit %d old_text occurs %d times" % (i, text.count(old)))
        st = text.index(old)
        spans.append((st, st + len(old), new))
    spans.sort()
    for a, b in zip(spans, spans[1:]):
        if a[1] > b[0]:
            raise ValueError("edits overlap")
    out, cur = [], 0
    for st, en, new in spans:
        out.append(text[cur:st])
        out.append(new)
        cur = en
    out.append(text[cur:])
    return "".join(out)


def _write_text(path, text):
    tmp = path + ".brokertmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    try:
        os.chmod(tmp, os.stat(path).st_mode & 0o7777)
    except OSError:
        pass
    os.replace(tmp, path)


def evaluate_v3(cfg, policy, req, rid, tid, name):
    for f in ("request_id", "task_id", "target", "change_class", "submitted_at", "brief_path"):
        if f not in req or req[f] in (None, ""):
            return rid, tid, ["E_FIELD_MISSING:" + f], None
        if not isinstance(req[f], str):
            return rid, tid, ["E_FIELD_TYPE:" + f], None
    try:
        if str(uuid.UUID(rid)) != rid or name != rid + ".json":
            return rid, tid, ["E_FIELD_TYPE:request_id"], None
    except ValueError:
        return rid, tid, ["E_FIELD_TYPE:request_id"], None
    prior = [x for x in ledger_entries(cfg)]
    if any(x.get("request_id") == rid for x in prior):
        return rid, tid, ["E_REPLAY"], None
    if sum(1 for x in prior if x.get("task_id") == tid) >= MAX_ATTEMPTS:
        return rid, tid, ["E_RESUBMIT_LIMIT"], None
    target = policy.get("targets", {}).get(req["target"])
    if target is None:
        return rid, tid, ["P_TARGET_NOT_ALLOWED"], None
    cls = target.get("classes", {}).get(req["change_class"])
    if req["change_class"] != "edit_brief" or cls is None or not cls.get("brief_dir"):
        return rid, tid, ["P_CLASS_NOT_ALLOWED"], None
    need = cls.get("min_checkpoint_state", "fully_autonomous")
    if STATE_RANK.get(checkpoint_state(cfg), 0) < STATE_RANK.get(need, 2):
        return rid, tid, ["P_CHECKPOINT_STATE"], None
    # brief file: absolute, real path inside brief_dir, regular file, size cap
    brief = req["brief_path"]
    bdir = os.path.realpath(cls["brief_dir"])
    if not os.path.isabs(brief) or not os.path.realpath(brief).startswith(bdir + os.sep):
        return rid, tid, ["E_ARTIFACT_OUTSIDE_STAGING"], None
    try:
        bst = os.lstat(brief)
    except OSError:
        return rid, tid, ["E_ARTIFACT_MISSING"], None
    if not stat.S_ISREG(bst.st_mode) or bst.st_size > MAX_BRIEF_BYTES:
        return rid, tid, ["E_ARTIFACT_OUTSIDE_STAGING"], None
    try:
        with open(brief, encoding="utf-8") as fh:
            m = _EDIT_BLOCK.search(fh.read())
        payload = json.loads(m.group(1)) if m else None
    except (OSError, ValueError):
        payload = None
    if (not isinstance(payload, dict) or not isinstance(payload.get("edits"), list) or not payload["edits"]
            or not isinstance(payload.get("target_file"), str) or not SHA_RE.match(str(payload.get("base_sha256", "")))):
        return rid, tid, ["E_BRIEF_INVALID"], None
    prod_root = os.path.realpath(target["production_root"])
    staging_root = os.path.realpath(target["staging_root"])
    tf = payload["target_file"]
    if not os.path.isabs(tf) or not os.path.realpath(tf).startswith(prod_root + os.sep):
        return rid, tid, ["P_PATH_NOT_ALLOWED"], None
    rel = os.path.relpath(os.path.realpath(tf), prod_root)
    if not safe_relpath(rel) or not glob_match(rel, target.get("allowed_relpaths", [])):
        return rid, tid, ["P_PATH_NOT_ALLOWED"], None
    prod_file = os.path.join(prod_root, rel)
    stage_file = os.path.join(staging_root, rel)
    try:
        if not stat.S_ISREG(os.lstat(prod_file).st_mode) or not stat.S_ISREG(os.lstat(stage_file).st_mode):
            return rid, tid, ["E_ARTIFACT_MISSING"], None
        with open(prod_file, encoding="utf-8") as fh:
            base_text = fh.read()
    except (OSError, UnicodeDecodeError):
        return rid, tid, ["E_ARTIFACT_MISSING"], None
    if hashlib.sha256(base_text.encode("utf-8")).hexdigest() != payload["base_sha256"]:
        return rid, tid, ["E_BRIEF_DRIFT"], None
    if sha256_file(stage_file) != sha256_file(prod_file):
        return rid, tid, ["E_STAGING_NOT_CLEAN"], None
    try:
        updated = _plan_edits(base_text, payload["edits"])
    except ValueError:
        return rid, tid, ["E_BRIEF_INVALID"], None
    try:
        _write_text(stage_file, updated)
    except OSError:
        return rid, tid, ["E_STAGE_WRITE"], None
    v1 = dict(req, schema_version="1", target_relpath=rel, artifact_path=stage_file,
              artifact_sha256=hashlib.sha256(updated.encode("utf-8")).hexdigest())
    code = sandbox_proof(cfg, target, v1, stage_file, rid)
    applied = None
    if not code and target.get("apply_enabled") is True:
        applied = apply_change(cfg, target, v1, rid)
    if code or applied in (None, "failed_not_applied", "failed_rolled_back", "failed_rollback_failed"):
        if applied != "promoted" and code != "E_ARTIFACT_CHANGED":
            try:
                _write_text(stage_file, base_text)   # keep the sandbox in sync with production
            except OSError:
                pass
    if code:
        return rid, tid, [code], None
    return rid, tid, [], applied


def notify(cfg, entry, target_name=None):
    """Best-effort ntfy alert. Fixed-format text only (no request content)."""
    st = entry.get("status")
    if st not in ALERT_STATUSES and st != "promoted":
        return False
    try:
        conf = load_json(cfg.ntfy_path)
        url = conf["url"].rstrip("/") + "/" + conf["topic"]
        title = ("Kaiju broker: PROMOTED" if st == "promoted"
                 else "Kaiju broker: NEEDS OPERATOR (" + st + ")")
        body = "status=%s codes=%s target=%s task=%s request=%s" % (
            st, ",".join(entry.get("codes") or []) or "-", target_name or "-",
            entry.get("task_id") or "-", entry.get("request_id") or "-")
        req = urllib.request.Request(url, data=body.encode(), method="POST", headers={
            "Title": title, "Priority": "default" if st == "promoted" else "high",
            "Tags": "white_check_mark" if st == "promoted" else "warning"})
        if conf.get("user"):
            import base64
            tok = base64.b64encode(("%s:%s" % (conf["user"], conf.get("password", ""))).encode()).decode()
            req.add_header("Authorization", "Basic " + tok)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except Exception:  # noqa: BLE001 -- alerts must never change the decision
        return False


def status_for(codes, applied=None):
    if applied:
        return applied
    if not codes:
        return "dry_run_pass"
    c = codes[0]
    if c in ESCALATE_CODES or c.startswith("P_"):
        return "escalated"
    return "rejected_fixable"


def atomic_write(path, data, mode=0o640):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def process_one(cfg, policy, name):
    path = os.path.join(cfg.incoming, name)
    rid, tid, codes, applied = evaluate(cfg, policy, path, name)
    target_name = None
    try:
        if rid:
            target_name = load_json(os.path.join(cfg.state_dir, "proofs", rid + ".json")).get("target")
    except (OSError, ValueError):
        pass
    status = status_for(codes, applied)
    prior_for_task = sum(1 for x in ledger_entries(cfg) if tid and x.get("task_id") == tid)
    remaining = max(0, MAX_ATTEMPTS - prior_for_task - 1) if status == "rejected_fixable" else 0
    entry = {
        "at": now_iso(), "file": name, "request_id": rid, "task_id": tid,
        "status": status, "codes": codes, "attempts_remaining": remaining,
        "mode": "applied" if applied else "dry_run",
    }
    # Outcome only for a well-formed, non-replayed request id: a replay or a
    # forged/garbage file must never overwrite an earlier real outcome.
    if rid and REQ_NAME.match(name) and name == rid + ".json" and "E_REPLAY" not in codes:
        atomic_write(os.path.join(cfg.outcomes, rid + ".json"), entry)
    with open(cfg.ledger, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    notify(cfg, entry, target_name)
    try:
        os.remove(path)
    except OSError:
        pass
    return entry


def run_once(cfg):
    policy = load_json(cfg.policy_path)
    results = []
    for name in sorted(os.listdir(cfg.incoming)):
        if name.endswith(".tmp"):
            continue
        results.append(process_one(cfg, policy, name))
    return results


if __name__ == "__main__":
    if "--once" not in sys.argv:
        print("usage: kaiju_broker.py --once   (one pass over incoming/)", file=sys.stderr)
        sys.exit(2)
    for r in run_once(Config()):
        print(json.dumps(r))
