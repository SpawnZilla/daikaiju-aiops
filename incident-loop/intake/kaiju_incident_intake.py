#!/usr/bin/env python3
"""
kaiju_incident_intake.py -- intake-host side of the S3a incident hand-off.
NEW 2026-10-15 -- NOT YET DEPLOYED.

Reads the ntfy topic <incident-topic> (reader credentials), and for every message:
  1. parses it as JSON, checks schema "kaiju-incident/1" and every field's shape
  2. verifies the HMAC-SHA256 signature (shared key file)
  3. checks the service against an allowlist file (one service name per line)
  4. dedupes on (incident_id, event); every ntfy message id is remembered, so a message already
     handled (accepted, duplicate or rejected) is skipped silently on later polls
  (optional "evidence" object = container state + redacted log tail: strictly shape-checked,
   stored in the queue record only, never copied into a brief)
Accepted events are appended to its OWN queue (Incident_Candidates.jsonl).
A "capped" event (curl check failed AND 4 automatic fixes failed) also gets a
templated brief written to the briefs directory. An "opened" event is queued only.
Brief text is built from validated fields only; no free text from the message is copied.
Own track record (Incident_Intake_Track.json) is separate from the self-origination counters.
This script never calls Bakaidah, never executes anything, never edits the scope gate.

Usage:
  kaiju_incident_intake.py                    # fetch from ntfy, process
  kaiju_incident_intake.py --input-file F     # process ntfy JSON lines from file F (tests)
Env (all have defaults except credentials):
  KAIJU_INTAKE_URL, KAIJU_INTAKE_TOPIC, KAIJU_INTAKE_USER, KAIJU_INTAKE_PASS,
  KAIJU_INTAKE_KEY_FILE, KAIJU_INTAKE_ALLOWLIST, KAIJU_INTAKE_QUEUE,
  KAIJU_INTAKE_TRACK, KAIJU_INTAKE_STATE_DIR, KAIJU_INTAKE_BRIEFS_DIR, KAIJU_INTAKE_SINCE
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

E = os.environ.get
URL = E("KAIJU_INTAKE_URL", "http://192.0.2.45:<port>")
TOPIC = E("KAIJU_INTAKE_TOPIC", "<incident-topic>")
KEY_FILE = E("KAIJU_INTAKE_KEY_FILE", "/etc/kaiju-os/incident.key")
ALLOWLIST = E("KAIJU_INTAKE_ALLOWLIST", "/etc/kaiju-os/incident-services.allow")
VAULT = "/srv/vault"
QUEUE = E("KAIJU_INTAKE_QUEUE", VAULT + "/Health/Incident_Candidates.jsonl")
TRACK = E("KAIJU_INTAKE_TRACK", VAULT + "/Health/Incident_Intake_Track.json")
STATE_DIR = E("KAIJU_INTAKE_STATE_DIR", "/var/lib/kaiju-incident-intake")
BRIEFS_DIR = E("KAIJU_INTAKE_BRIEFS_DIR", VAULT + "/angkai/briefs")
SINCE = E("KAIJU_INTAKE_SINCE", "24h")

SERVICE_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}\Z")
SCRIPT_RE = re.compile(r"^[a-z0-9_]{1,64}\Z")
TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\Z")
CODE_RE = re.compile(r"^[0-9]{1,3}\Z")
IID_RE = re.compile(r"^[0-9a-f]{16}\Z")
MID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}\Z")
EVENTS = ("opened", "capped", "resolved")
TOP_KEYS = {"schema", "incident_id", "event", "service", "container", "first_seen",
            "last_seen", "flap", "attempts", "host", "sig"}
ATT_KEYS = {"time", "script", "fix_exit", "code", "result"}
EV_KEYS = {"collected_at", "state", "exit_code", "oom", "restarts", "health", "log_tail"}
EV_STATES = ("created", "running", "paused", "restarting", "removing", "exited", "dead", "absent")
EV_HEALTH = ("none", "starting", "healthy", "unhealthy")
LOG_LINE_RE = re.compile(r"^[\x20-\x7e]{0,200}\Z")


def fetch(user, password):
    req = urllib.request.Request("%s/%s/json?poll=1&since=%s" % (URL, TOPIC, SINCE))
    tok = base64.b64encode(("%s:%s" % (user, password)).encode()).decode()
    req.add_header("Authorization", "Basic " + tok)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace").splitlines()


def sign(payload_without_sig, key):
    canon = json.dumps(payload_without_sig, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hmac.new(key, canon.encode("utf-8"), hashlib.sha256).hexdigest()


def validate_evidence(e):
    """Strict shape check of the optional evidence object (container state + log tail)."""
    if not (isinstance(e, dict) and set(e) == EV_KEYS):
        return False
    if not (isinstance(e["collected_at"], str) and TIME_RE.match(e["collected_at"])):
        return False
    if e["state"] not in EV_STATES or e["health"] not in EV_HEALTH:
        return False
    for k in ("exit_code", "restarts"):
        if not (isinstance(e[k], int) and not isinstance(e[k], bool) and 0 <= e[k] <= 100000):
            return False
    if not isinstance(e["oom"], bool):
        return False
    lt = e["log_tail"]
    if not (isinstance(lt, list) and len(lt) <= 40):
        return False
    total = 0
    for line in lt:
        if not (isinstance(line, str) and LOG_LINE_RE.match(line)):
            return False
        total += len(line) + 1
    return total <= 4000


def validate(msg, key, allow):
    """Return (payload, None) or (None, reason)."""
    try:
        p = json.loads(msg)
    except Exception:
        return None, "not_json"
    if not isinstance(p, dict) or not (TOP_KEYS <= set(p) <= TOP_KEYS | {"evidence"}):
        return None, "bad_fields"
    if p["schema"] != "kaiju-incident/1":
        return None, "bad_schema"
    if p["event"] not in EVENTS:
        return None, "bad_event"
    if not (isinstance(p["incident_id"], str) and IID_RE.match(p["incident_id"])):
        return None, "bad_incident_id"
    for k in ("service", "container", "host"):
        if not (isinstance(p[k], str) and SERVICE_RE.match(p[k])):
            return None, "bad_" + k
    for k in ("first_seen", "last_seen"):
        if not (isinstance(p[k], str) and TIME_RE.match(p[k])):
            return None, "bad_" + k
    if not isinstance(p["flap"], bool):
        return None, "bad_flap"
    if not isinstance(p["attempts"], list) or len(p["attempts"]) > 20:
        return None, "bad_attempts"
    for a in p["attempts"]:
        if not (isinstance(a, dict) and set(a) == ATT_KEYS and isinstance(a["time"], str)
                and TIME_RE.match(a["time"]) and isinstance(a["script"], str)
                and SCRIPT_RE.match(a["script"]) and isinstance(a["fix_exit"], int)
                and not isinstance(a["fix_exit"], bool) and 0 <= a["fix_exit"] <= 255
                and isinstance(a["code"], str) and CODE_RE.match(a["code"])
                and a["result"] in ("pass", "fail")):
            return None, "bad_attempt"
    if "evidence" in p and not validate_evidence(p["evidence"]):
        return None, "bad_evidence"
    if not (isinstance(p["sig"], str) and re.match(r"^[0-9a-f]{64}\Z", p["sig"])):
        return None, "bad_sig_format"
    body = {k: v for k, v in p.items() if k != "sig"}
    if not hmac.compare_digest(sign(body, key), p["sig"]):
        return None, "bad_signature"
    if p["service"] not in allow:
        return None, "service_not_allowed"
    if p["event"] == "capped" and len(p["attempts"]) == 0 and not p["flap"]:
        return None, "capped_without_attempts"
    return p, None


def render_brief(brief_id, cand_id, p):
    lines = [
        "BRIEF %s" % brief_id,
        "ORIGIN: watchdog incident hand-off, candidate %s (edge-node watchdog verified: health check failed AND automatic fixes failed)" % cand_id,
        "SERVICE: %s (container %s) on host %s" % (p["service"], p["container"], p["host"]),
        "INCIDENT: %s   first seen %s   last seen %s   flap-guard: %s" % (
            p["incident_id"], p["first_seen"], p["last_seen"], "yes" if p["flap"] else "no"),
        "",
        "AUTOMATIC ATTEMPTS ON THE edge-node (%d):" % len(p["attempts"]),
    ]
    for a in p["attempts"]:
        lines.append("- %s  %s  exit=%d  health=%s  result=%s" % (
            a["time"], a["script"], a["fix_exit"], a["code"], a["result"]))
    if not p["attempts"]:
        lines.append("- none (flap guard: previous capped incident resolved less than 24h ago)")
    ev = p.get("evidence")
    if ev:
        lines += [
            "",
            "CONTAINER STATE (validated fields only): %s exit_code=%d oom=%s restarts=%d health=%s, collected %s" % (
                ev["state"], ev["exit_code"], "yes" if ev["oom"] else "no", ev["restarts"], ev["health"], ev["collected_at"]),
            "EVIDENCE: the container log tail is kept in the queue record only (untrusted text, never copied into briefs).",
        ]
    lines += [
        "",
        "REQUEST: diagnose read-only (Bakaidah), then act only through an allowlisted fm fix script via a",
        "signed run ticket for the edge-node runner. Human-only failure modes escalate. If no failure mode matches,",
        "draft a new fm script, runbook and mocked tests into staging for the operator to deploy.",
        "",
        "NOTE: This brief was generated from a signed, schema-validated watchdog message. It is subject to",
        "the same autonomy_scope_gate and Step 5 review as any other brief. It carries no elevated trust.",
    ]
    return "\n".join(lines) + "\n"


def load_track():
    try:
        with open(TRACK) as f:
            t = json.load(f)
    except Exception:
        t = {}
    for k in ("accepted", "rejected", "duplicates", "briefs_written"):
        t.setdefault(k, 0)
    t.setdefault("rejected_reasons", {})
    return t


def save_track(t):
    t["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = TRACK + ".tmp"
    with open(tmp, "w") as f:
        json.dump(t, f, indent=2, sort_keys=True)
    os.replace(tmp, TRACK)


def touch(path):
    if path:
        open(path, "w").close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-file")
    args = ap.parse_args()

    try:
        key = open(KEY_FILE, "rb").read().strip()
        if not key:
            raise ValueError("empty")
    except Exception as e:
        print("intake: cannot read key file %s: %s" % (KEY_FILE, e), file=sys.stderr)
        return 2
    try:
        allow = {l.strip() for l in open(ALLOWLIST) if l.strip() and not l.startswith("#")}
    except Exception:
        allow = set()  # no allowlist -> every message is rejected as service_not_allowed

    if args.input_file:
        lines = open(args.input_file).read().splitlines()
    else:
        user, pw = E("KAIJU_INTAKE_USER"), E("KAIJU_INTAKE_PASS")
        if not user or not pw:
            print("intake: KAIJU_INTAKE_USER / KAIJU_INTAKE_PASS not set", file=sys.stderr)
            return 2
        try:
            lines = fetch(user, pw)
        except Exception as e:
            print("intake: fetch failed: %s" % e, file=sys.stderr)
            return 1

    os.makedirs(STATE_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(QUEUE), exist_ok=True)
    track = load_track()
    out = {"accepted": 0, "rejected": 0, "duplicates": 0, "briefs": 0}

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            env = json.loads(line)
        except Exception:
            continue
        if not isinstance(env, dict) or env.get("event") != "message":
            continue  # open / keepalive lines
        mid = env.get("id")
        mmark = os.path.join(STATE_DIR, "msg-" + mid) if isinstance(mid, str) and MID_RE.match(mid) else None
        if mmark and os.path.exists(mmark):
            continue  # this ntfy message was already handled on an earlier poll
        p, reason = validate(env.get("message", ""), key, allow)
        if p is None:
            track["rejected"] += 1
            track["rejected_reasons"][reason] = track["rejected_reasons"].get(reason, 0) + 1
            out["rejected"] += 1
            touch(mmark)
            continue
        cand_id = hashlib.sha256(("%s|%s" % (p["incident_id"], p["event"])).encode()).hexdigest()[:12]
        marker = os.path.join(STATE_DIR, cand_id)
        if os.path.exists(marker):
            track["duplicates"] += 1
            out["duplicates"] += 1
            touch(mmark)
            continue
        brief_id = None
        if p["event"] == "capped":
            brief_id = "brief-inc-%s" % cand_id
            body = render_brief(brief_id, cand_id, p)
            path = os.path.join(BRIEFS_DIR, brief_id + ".txt")
            tmp = path + ".tmp"
            with open(tmp, "w") as f:
                f.write(body)
            os.replace(tmp, path)
        rec = {"candidate_id": cand_id, "received_at": datetime.now(timezone.utc).isoformat(),
               "origin": "watchdog_incident", "state": "pre_accepted" if brief_id else "recorded",
               "brief_id": brief_id,
               "payload": {k: v for k, v in p.items() if k != "sig"}}
        with open(QUEUE, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
        open(marker, "w").close()  # marker last: a crash before this re-processes, never loses
        touch(mmark)
        track["accepted"] += 1
        out["accepted"] += 1
        if brief_id:
            track["briefs_written"] += 1
            out["briefs"] += 1
    save_track(track)
    print("intake: accepted=%(accepted)d briefs=%(briefs)d duplicates=%(duplicates)d rejected=%(rejected)d" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
