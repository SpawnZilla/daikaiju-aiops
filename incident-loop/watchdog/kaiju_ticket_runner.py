#!/usr/bin/env python3
"""
kaiju_ticket_runner.py (S4, 2026-10-16) -- NOT YET DEPLOYED. Runs on the edge-node as root.
Deploy to /opt/kaiju-spine/watchdog/ (root:root 755). Reached only through a dedicated SSH key whose authorized_keys line is
    command="sudo /opt/kaiju-spine/watchdog/kaiju_ticket_runner.py",restrict,from="192.0.2.45" ssh-ed25519 ...
(sudoers allows that one path with no arguments). stdin carries ONE JSON object:
    {"op":"run","ticket":{...signed ticket...}}   or   {"op":"result","ticket_id":"<16 hex>"}
stdout carries ONE JSON result line. It never runs anything the ticket merely names: every check below must pass first.
Checks for op=run, in order: size/shape, HMAC signature, stored result (replay returns it, never re-runs), validity window
(max ttl), checkpoint_state fully_autonomous, EXACT "<script> <service> <compose_dir>" line in the allowlist, the real
open+capped incident record for that service with a matching incident_id, one run per incident, script is an executable
file inside the lib dir. The script then runs under the watchdog flock with the same arguments the watchdog uses
(<container> <compose_dir>); the service health URL is re-checked; a signed result is stored and returned.
"""
import fcntl, hashlib, hmac, json, os, re, subprocess, sys, time

class Cfg:
    def __init__(self, **kw):
        e = lambda n, d: os.environ.get("KAIJU_RUN_" + n, d)
        self.key_file = e("KEY_FILE", "/etc/kaiju-os/runticket.key")
        self.allow = e("ALLOW", "/etc/kaiju-os/known-fix-run.allow")
        self.state_dir = e("STATE_DIR", "/var/lib/kaiju-watchdog/tickets")
        self.incident_dir = e("INCIDENT_DIR", "/var/lib/kaiju-watchdog/incidents")
        self.lib_dir = e("LIB_DIR", "/opt/kaiju-spine/watchdog")
        self.lock = e("LOCK", "/run/dd-watchdog.lock")
        self.log = e("LOG", "/var/log/kaiju-watchdog/ticket_runner.log")
        self.script_timeout = int(e("SCRIPT_TIMEOUT", "900"))
        self.lock_wait = int(e("LOCK_WAIT", "1800"))
        self.max_ttl = int(e("MAX_TTL", "7200"))
        self.skew = int(e("SKEW", "120"))
        self.health_wait = int(e("HEALTH_WAIT", "60"))        # S7: seconds to keep re-checking health after a script that exited 0
        self.health_interval = int(e("HEALTH_INTERVAL", "5"))
        for k, v in kw.items():
            setattr(self, k, v)

MAX_IN = 8192
ID_RE = re.compile(r"\A[0-9a-f]{16}\Z")
SVC_RE = re.compile(r"\A[A-Za-z0-9._-]{1,64}\Z")
SCRIPT_RE = re.compile(r"\A[A-Za-z0-9._-]{1,80}\Z")
DIR_RE = re.compile(r"\A/[A-Za-z0-9._/-]{1,200}\Z")
TICKET_KEYS = {"schema", "ticket_id", "incident_id", "service", "script", "compose_dir", "checkpoint_state", "issued_at", "expires_at", "sig"}

def canon(d):
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def sign(key, d):
    return dict(d, sig=hmac.new(key, canon(d).encode(), hashlib.sha256).hexdigest())

def verify(key, d):
    t = dict(d); sig = t.pop("sig", "")
    return isinstance(sig, str) and hmac.compare_digest(sig, hmac.new(key, canon(t).encode(), hashlib.sha256).hexdigest())

def _log(cfg, msg):
    try:
        os.makedirs(os.path.dirname(cfg.log), exist_ok=True)
        with open(cfg.log, "a") as f:
            f.write("%s | %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except OSError:
        pass

def _atomic(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)

def shape_ok(t):
    try:
        return (isinstance(t, dict) and set(t) == TICKET_KEYS and t["schema"] == "kaiju-run-ticket/1"
                and all(isinstance(t[k], str) for k in ("ticket_id", "incident_id", "service", "script", "compose_dir", "checkpoint_state", "sig"))
                and ID_RE.match(t["ticket_id"]) and ID_RE.match(t["incident_id"]) and SVC_RE.match(t["service"])
                and SCRIPT_RE.match(t["script"]) and DIR_RE.match(t["compose_dir"]) and ".." not in t["compose_dir"]
                and all(isinstance(t[k], int) and not isinstance(t[k], bool) for k in ("issued_at", "expires_at")))
    except (KeyError, TypeError):
        return False

def _allowed(cfg, line):
    try:
        with open(cfg.allow, encoding="utf-8") as f:
            return any(l.rstrip("\n") == line for l in f if l.strip() and not l.startswith("#"))
    except OSError:
        return False

def _incident(cfg, t):
    """-> (container, None) or (None, reason): the real open+capped record must match this ticket."""
    try:
        with open(os.path.join(cfg.incident_dir, t["service"] + ".json")) as f:
            r = json.load(f)
    except (OSError, ValueError):
        return None, "incident_not_found"
    if r.get("status") != "open":
        return None, "incident_not_open"
    if r.get("capped") is not True:
        return None, "incident_not_capped"
    if hashlib.sha256(("%s|%s" % (r.get("service"), r.get("first_seen"))).encode()).hexdigest()[:16] != t["incident_id"] or r.get("service") != t["service"]:
        return None, "incident_id_mismatch"
    c = r.get("container")
    if not isinstance(c, str) or not re.match(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z", c):
        return None, "bad_container"
    return c, None

def real_run(cfg, argv):
    """-> (exit_code, timed_out). argv runs under the watchdog flock (exit 200 = lock not obtained) and under `timeout` (124 = timed out)."""
    cmd = ["flock", "-E", "200", "-w", str(cfg.lock_wait), cfg.lock, "timeout", "-k", "10", str(cfg.script_timeout)] + argv
    env = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "KAIJU_LIB_DIR": cfg.lib_dir, "HOME": "/root"}
    try:
        p = subprocess.run(cmd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           timeout=cfg.script_timeout + cfg.lock_wait + 60)
    except subprocess.TimeoutExpired:
        return -1, True
    tail = (p.stdout or "").strip().splitlines()[-3:]
    _log(cfg, "script exit=%s output tail: %s" % (p.returncode, " / ".join(tail)[:300]))
    return p.returncode, p.returncode == 124


def real_health(cfg, service):
    """-> (code, expected) strings from the same config the watchdog uses; ('none','') if unavailable."""
    try:
        r = subprocess.run(["bash", "-c", 'source "$1/fashsd_config_lib.sh"; i=$(kaiju_service_index_by_name "$2"); [ -n "$i" ] || exit 3; '
                            'for f in health_url expected_code timeout_seconds; do kaiju_service_field "$i" "$f"; done', "x", cfg.lib_dir, service],
                           capture_output=True, text=True, timeout=30)
        url, exp, tmo = (r.stdout.split("\n") + ["", "", ""])[:3]
        if r.returncode != 0 or not url or url == "null":
            return "none", ""
        c = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", str(tmo or 10), url],
                           capture_output=True, text=True, timeout=60)
        return c.stdout.strip() or "none", exp
    except (OSError, subprocess.SubprocessError):
        return "none", ""

def handle(cfg, key, raw, deps):
    if len(raw) > MAX_IN:
        return {"status": "refused", "reason": "too_large"}
    try:
        req = json.loads(raw)
    except ValueError:
        return {"status": "refused", "reason": "bad_json"}
    if not isinstance(req, dict):
        return {"status": "refused", "reason": "bad_request"}
    os.makedirs(cfg.state_dir, exist_ok=True)
    if req.get("op") == "result" and set(req) == {"op", "ticket_id"}:
        tid = req["ticket_id"]
        if not isinstance(tid, str) or not ID_RE.match(tid):
            return {"status": "refused", "reason": "bad_ticket_id"}
        p = os.path.join(cfg.state_dir, tid + ".result.json")
        if os.path.exists(p):
            return json.load(open(p))
        return {"status": "unknown" if not os.path.exists(os.path.join(cfg.state_dir, tid + ".state")) else "running", "ticket_id": tid}
    if req.get("op") != "run" or set(req) != {"op", "ticket"}:
        return {"status": "refused", "reason": "bad_request"}
    t = req["ticket"]
    if not shape_ok(t):
        return {"status": "refused", "reason": "bad_ticket"}
    if not verify(key, t):
        return {"status": "refused", "reason": "bad_signature"}
    tid, iid, svc = t["ticket_id"], t["incident_id"], t["service"]
    resp = os.path.join(cfg.state_dir, tid + ".result.json")
    if os.path.exists(resp):
        return json.load(open(resp))
    if os.path.exists(os.path.join(cfg.state_dir, tid + ".state")):
        return sign(key, {"schema": "kaiju-run-result/1", "ticket_id": tid, "incident_id": iid, "service": svc, "script": t["script"], "status": "running"})
    def result(status, reason="", store=True, **kw):
        d = {"schema": "kaiju-run-result/1", "ticket_id": tid, "incident_id": iid, "service": svc, "script": t["script"], "status": status,
             "reason": reason, "finished_at": int(deps["now"]())}
        d.update(kw)
        d = sign(key, d)
        if store:
            _atomic(resp, json.dumps(d, sort_keys=True))
        _log(cfg, "ticket %s %s/%s -> %s %s" % (tid, svc, t["script"], status, reason))
        return d
    now = deps["now"]()
    if t["expires_at"] - t["issued_at"] > cfg.max_ttl or t["expires_at"] <= t["issued_at"]:
        return result("refused", "bad_ttl", store=False)
    if now > t["expires_at"] or now < t["issued_at"] - cfg.skew:
        return result("refused", "outside_validity_window", store=False)
    if t["checkpoint_state"] != "fully_autonomous":
        return result("refused", "checkpoint_state")
    line = "%s %s %s" % (t["script"], svc, t["compose_dir"])
    if not _allowed(cfg, line):
        return result("refused", "not_allowlisted")
    container, why = _incident(cfg, t)
    if container is None:
        return result("refused", why)
    spath = os.path.join(cfg.lib_dir, t["script"])
    if not (os.path.isfile(spath) and os.access(spath, os.X_OK) and os.path.realpath(spath) == os.path.join(os.path.realpath(cfg.lib_dir), t["script"])):
        return result("refused", "script_not_executable_in_lib_dir")
    inc_mark = os.path.join(cfg.state_dir, "incident-%s.ran" % iid)
    try:
        os.close(os.open(inc_mark, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    except FileExistsError:
        return result("refused", "incident_already_run")
    try:
        os.close(os.open(os.path.join(cfg.state_dir, tid + ".state"), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    except FileExistsError:
        return sign(key, {"schema": "kaiju-run-result/1", "ticket_id": tid, "incident_id": iid, "service": svc, "script": t["script"], "status": "running"})
    _log(cfg, "ticket %s accepted: running %s %s %s" % (tid, spath, container, t["compose_dir"]))
    code, timed_out = deps["run"](cfg, [spath, container, t["compose_dir"]])
    if code == 200 and not timed_out:
        os.remove(inc_mark)
        return result("not_run", "watchdog_lock_not_obtained", exit=None)
    hc, exp = deps["health"](cfg, svc)
    if code == 0 and not timed_out and exp and hc != exp:
        # S7 (2026-10-16): a script that returns right after `docker compose up -d` leaves the service still starting; the first check
        # read 000 on a lidarr that was healthy seconds later. Re-poll for at most health_wait seconds, only for a clean exit with a known
        # expected code; an exit != 0, a timeout or a missing health config is never retried.
        sleep = deps.get("sleep", time.sleep)
        waited = 0
        while hc != exp and waited < cfg.health_wait:
            sleep(cfg.health_interval)
            waited += cfg.health_interval
            hc, exp = deps["health"](cfg, svc)
        _log(cfg, "ticket %s health re-poll: waited %ss, last code %s, expected %s" % (tid, waited, hc, exp))
    return result("done", "", exit=code, timed_out=timed_out, health_code=hc, passed=bool(code == 0 and not timed_out and exp and hc == exp))

def main():
    cfg = Cfg()
    try:
        key = open(cfg.key_file, "rb").read().strip()
    except OSError:
        print(json.dumps({"status": "refused", "reason": "runner_not_configured"})); return 0
    raw = sys.stdin.read(MAX_IN + 1)
    out = handle(cfg, key, raw, {"now": time.time, "run": real_run, "health": real_health})
    print(json.dumps(out, sort_keys=True))
    return 0

if __name__ == "__main__":
    sys.exit(main())
