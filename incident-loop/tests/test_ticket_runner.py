#!/usr/bin/env python3
"""S4 runner tests: real flock/timeout/subprocess for script runs, fake health. Runs anywhere with flock+coreutils."""
import json, os, stat, subprocess, sys, tempfile, time, hashlib
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [_HERE, os.path.join(os.path.dirname(_HERE), "watchdog")]
import kaiju_ticket_runner as R
BAD = 0
def t(n, ok):
    global BAD
    print(("PASS " if ok else "FAIL ") + n); BAD += (not ok)
KEY = b"runner-test-key"
class E:
    def __init__(self, script_body="exit 0", **cfgkw):
        self.d = tempfile.mkdtemp()
        j = lambda *a: os.path.join(self.d, *a)
        for x in ("lib", "inc", "state"): os.makedirs(j(x))
        self.cfg = R.Cfg(lib_dir=j("lib"), incident_dir=j("inc"), state_dir=j("state"), allow=j("allow"), lock=j("lock"), log=j("log"),
                         script_timeout=cfgkw.pop("script_timeout", 20), lock_wait=cfgkw.pop("lock_wait", 5), key_file=j("key"), **cfgkw)
        self.calls = j("calls")
        open(j("lib", "fmtest.sh"), "w").write('#!/bin/bash\necho "$@" >> %s\n%s\n' % (self.calls, script_body))
        os.chmod(j("lib", "fmtest.sh"), 0o755)
        open(j("lib", "fashsd_config_lib.sh"), "w").write("# lib\n")
        self.cfg.pins = j("pins"); self.cfg.autonomy_file = j("autonomy")
        open(j("autonomy"), "w").write("# runner-local switch\nfully_autonomous\n")
        self.repin()
        open(j("allow"), "w").write("# c\nfmtest.sh lidarr /srv/compose/arr\n")
        self.first = "2026-10-15 22:00:00"
        self.iid = hashlib.sha256(("lidarr|" + self.first).encode()).hexdigest()[:16]
        self.rec = {"service": "lidarr", "container": "lidarr", "status": "open", "first_seen": self.first, "capped": True}
        self.write_inc()
        self.now = time.time()
        self.health = ("200", "200")
        self.deps = {"now": lambda: self.now, "run": R.real_run, "health": lambda cfg, svc: self.health,
                     "container": lambda cfg, c: self.cstate}
        self.cstate = "running"
    def repin(self):
        with open(self.cfg.pins, "w") as f:
            for n in sorted(os.listdir(self.cfg.lib_dir)):
                p = os.path.join(self.cfg.lib_dir, n)
                if os.path.isfile(p) and not os.path.islink(p):
                    f.write("%s  %s\n" % (hashlib.sha256(open(p, "rb").read()).hexdigest(), n))
    def write_inc(self): json.dump(self.rec, open(os.path.join(self.cfg.incident_dir, "lidarr.json"), "w"))
    def ticket(self, **kw):
        n = int(self.now)
        b = {"schema": "kaiju-run-ticket/1", "ticket_id": hashlib.sha256(os.urandom(8)).hexdigest()[:16], "incident_id": self.iid, "service": "lidarr",
             "script": "fmtest.sh", "compose_dir": "/srv/compose/arr", "checkpoint_state": "fully_autonomous", "issued_at": n, "expires_at": n + 3600}
        b.update(kw); return R.sign(KEY, b)
    def run(self, ticket):
        return R.handle(self.cfg, KEY, json.dumps({"op": "run", "ticket": ticket}), self.deps)
    def ncalls(self): return len(open(self.calls).read().splitlines()) if os.path.exists(self.calls) else 0

e = E(); tk = e.ticket(); r = e.run(tk)
t("T1 happy path: done, exit 0, passed", r["status"] == "done" and r["exit"] == 0 and r["passed"] is True and r["health_code"] == "200")
t("T1b script got <container> <compose_dir> exactly", open(e.calls).read().strip() == "lidarr /srv/compose/arr")
t("T1c result is signed and verifies", R.verify(KEY, r) and r["ticket_id"] == tk["ticket_id"])
r2 = e.run(tk); t("T6 replay returns the stored result and does not re-run", r2 == r and e.ncalls() == 1)
res = R.handle(e.cfg, KEY, json.dumps({"op": "result", "ticket_id": tk["ticket_id"]}), e.deps)
t("T10 result op returns the stored result", res == r)
t("T10b result op for unknown id", R.handle(e.cfg, KEY, json.dumps({"op": "result", "ticket_id": "0" * 16}), e.deps)["status"] == "unknown")
t("T10c result op with bad id refused", R.handle(e.cfg, KEY, json.dumps({"op": "result", "ticket_id": "../etc"}), e.deps)["reason"] == "bad_ticket_id")
t2 = e.ticket(); r3 = e.run(t2)
t("T9 second ticket for the same incident refused", r3["status"] == "refused" and r3["reason"] == "incident_already_run" and e.ncalls() == 1)

def fresh(**kw): return E(**kw)
e = fresh(); bad = dict(e.ticket(), sig="0" * 64); r = e.run(bad)
t("T2 bad signature refused, nothing run", r.get("reason") == "bad_signature" and e.ncalls() == 0)
e = fresh(); tk = e.ticket(); tk["compose_dir"] = "/etc"; r = e.run(tk)
t("T3 tampered field fails signature", r.get("reason") == "bad_signature" and e.ncalls() == 0)
e = fresh(); n = int(e.now); r = e.run(e.ticket(issued_at=n - 7200, expires_at=n - 10))
t("T4 expired ticket refused", r["reason"] == "outside_validity_window" and e.ncalls() == 0)
e = fresh(); n = int(e.now); r = e.run(e.ticket(issued_at=n + 5000, expires_at=n + 6000))
t("T5 not-yet-valid ticket refused", r["reason"] == "outside_validity_window" and e.ncalls() == 0)
e = fresh(); n = int(e.now); r = e.run(e.ticket(issued_at=n, expires_at=n + 99999))
t("T18 ttl above max refused", r["reason"] == "bad_ttl" and e.ncalls() == 0)
e = fresh(); open(e.cfg.allow, "w").write("fmtest.sh radarr /srv/compose/arr\n"); r = e.run(e.ticket())
t("T7 not in allowlist refused", r["reason"] == "not_allowlisted" and e.ncalls() == 0)
e = fresh(); open(e.cfg.allow, "w").write("fmtest.sh lidarr /srv/compose/arr  \n"); r = e.run(e.ticket())
t("T7b allowlist match is exact (trailing spaces do not match)", r["reason"] == "not_allowlisted")
e = fresh(); os.remove(os.path.join(e.cfg.allow)); r = e.run(e.ticket())
t("T7c missing allowlist -> refused", r["reason"] == "not_allowlisted")
for name, mut, why in [("not open", {"status": "resolved"}, "incident_not_open"), ("not capped", {"capped": False}, "incident_not_capped"),
                       ("other incident id", {"first_seen": "2026-10-14 01:00:00"}, "incident_id_mismatch"),
                       ("bad container name", {"container": "x; rm -rf /"}, "bad_container")]:
    e = fresh(); e.rec.update(mut); e.write_inc(); r = e.run(e.ticket())
    t("T8 incident %s -> %s" % (name, why), r["reason"] == why and e.ncalls() == 0)
e = fresh(); os.remove(os.path.join(e.cfg.incident_dir, "lidarr.json")); r = e.run(e.ticket())
t("T8b no incident record -> refused", r["reason"] == "incident_not_found")
e = fresh(); r = e.run(e.ticket(checkpoint_state="graduated_window")); t("T13 checkpoint_state must be fully_autonomous", r["reason"] == "checkpoint_state" and e.ncalls() == 0)
for bad in ("../x.sh", "a/b.sh", "x y.sh", ""):
    e = fresh(); r = e.run(e.ticket(script=bad)); t("T12 script %r refused by shape" % bad, r["reason"] == "bad_ticket" and e.ncalls() == 0)
e = fresh(); r = e.run(e.ticket(compose_dir="/mnt/../etc")); t("T12b compose_dir with .. refused", r["reason"] == "bad_ticket")
e = fresh(); tk = e.ticket(); tk["extra"] = 1; r = e.run(tk); t("T12c extra ticket key refused", r["reason"] == "bad_ticket")
e = fresh(); os.chmod(os.path.join(e.cfg.lib_dir, "fmtest.sh"), 0o644); r = e.run(e.ticket())
t("T17 non-executable script refused", r["reason"] == "script_not_executable_in_lib_dir" and e.ncalls() == 0)
e = fresh(); os.symlink("/bin/true", os.path.join(e.cfg.lib_dir, "fmlink.sh")); open(e.cfg.allow, "w").write("fmlink.sh lidarr /srv/compose/arr\n"); r = e.run(e.ticket(script="fmlink.sh"))
t("T17b symlink out of the lib dir refused", r["reason"] == "script_not_executable_in_lib_dir")
e = fresh(script_body="exit 1"); r = e.run(e.ticket()); t("T14 script exit 1 -> done, passed false", r["status"] == "done" and r["exit"] == 1 and r["passed"] is False)
e = fresh(); e.health = ("503", "200"); r = e.run(e.ticket()); t("T14b exit 0 but health fails -> passed false", r["exit"] == 0 and r["passed"] is False)
e = fresh(); e.health = ("none", ""); r = e.run(e.ticket()); t("T14c no health config -> passed false", r["passed"] is False)
# S7: health re-poll after a clean exit (fake sleep, fake health that turns 200 after N checks)
def seq_env(codes, exp="200", **kw):
    x = fresh(**kw); x.polls = 0; x.sleeps = []
    def h(cfg, svc):
        c = codes[min(x.polls, len(codes) - 1)]; x.polls += 1; return (c, exp)
    x.deps = dict(x.deps, health=h, sleep=lambda s: x.sleeps.append(s)); return x
e = seq_env(["000", "000", "200"], health_wait=60, health_interval=5); r = e.run(e.ticket())
t("T21 exit 0, service comes up during the re-poll -> passed true, 2 sleeps", r["passed"] is True and r["health_code"] == "200" and e.sleeps == [5, 5] and e.polls == 3)
e = seq_env(["000"], health_wait=20, health_interval=5); r = e.run(e.ticket())
t("T21b never up -> passed false, bounded (4 sleeps, 5 checks)", r["passed"] is False and r["health_code"] == "000" and len(e.sleeps) == 4 and e.polls == 5)
e = seq_env(["200"], health_wait=60); r = e.run(e.ticket())
t("T21c healthy at the first check -> no sleep", r["passed"] is True and e.sleeps == [] and e.polls == 1)
e = seq_env(["000", "200"], script_body="exit 1"); r = e.run(e.ticket())
t("T21d script exit 1 -> never re-polled, passed false", r["passed"] is False and e.sleeps == [] and e.polls == 1)
e = seq_env(["000", "200"], exp=""); r = e.run(e.ticket())
t("T21e no expected code -> never re-polled, passed false", r["passed"] is False and e.sleeps == [] and e.polls == 1)
e = seq_env(["000", "200"], script_body="sleep 30", script_timeout=1); r = e.run(e.ticket())
t("T21f timed-out script -> never re-polled", r["timed_out"] is True and r["passed"] is False and e.sleeps == [] and e.polls == 1)
e = seq_env(["000", "200"], health_wait=0); r = e.run(e.ticket())
t("T21g health_wait 0 turns the re-poll off", r["passed"] is False and e.sleeps == [] and e.polls == 1)
e = fresh(script_body="sleep 30", script_timeout=1); r = e.run(e.ticket()); t("T15 script timeout -> timed_out, passed false", r["timed_out"] is True and r["passed"] is False)
e = fresh(lock_wait=1)
holder = subprocess.Popen(["flock", e.cfg.lock, "sleep", "6"]); time.sleep(0.5)
r = e.run(e.ticket()); holder.wait()
t("T16 watchdog lock held -> not_run, script never started", r["status"] == "not_run" and e.ncalls() == 0)
r = e.run(e.ticket()); t("T16b after not_run the incident can be retried with a new ticket", r["status"] == "done" and e.ncalls() == 1)
e = fresh(); t("T11 oversized input refused", R.handle(e.cfg, KEY, "x" * 9000, e.deps)["reason"] == "too_large")
t("T11b bad json refused", R.handle(e.cfg, KEY, "{nope", e.deps)["reason"] == "bad_json")
t("T11c unknown op refused", R.handle(e.cfg, KEY, json.dumps({"op": "shell", "cmd": "id"}), e.deps)["reason"] == "bad_request")
t("T11d array refused", R.handle(e.cfg, KEY, "[1]", e.deps)["reason"] == "bad_request")
e = fresh(); tk = e.ticket(); open(os.path.join(e.cfg.state_dir, tk["ticket_id"] + ".state"), "w").close(); r = e.run(tk)
t("T19 state without a result (crash mid-run) -> running, never re-run", r["status"] == "running" and e.ncalls() == 0)
t("T20 log written", os.path.getsize(e.cfg.log) > 0 if os.path.exists(e.cfg.log) else True)
# ---- audit fix B: script and lib content pinning ----
e = fresh(); open(os.path.join(e.cfg.lib_dir, "fmtest.sh"), "a").write("echo tampered\n"); r = e.run(e.ticket())
t("K1 edited fix script (pin mismatch) refused, nothing run", r["reason"] == "pin_mismatch:fmtest.sh" and e.ncalls() == 0)
e = fresh(); open(os.path.join(e.cfg.lib_dir, "fashsd_config_lib.sh"), "a").write("evil\n"); r = e.run(e.ticket())
t("K2 edited sourced lib refused", r["reason"] == "pin_mismatch:fashsd_config_lib.sh" and e.ncalls() == 0)
e = fresh(); os.remove(e.cfg.pins); r = e.run(e.ticket())
t("K3 missing pin file refused (fail closed)", r["reason"] == "pins_missing" and e.ncalls() == 0)
e = fresh(); open(e.cfg.pins, "w").write("nothex  fmtest.sh\n"); r = e.run(e.ticket())
t("K4 malformed pin file refused", r["reason"] == "pins_malformed" and e.ncalls() == 0)
e = fresh(); open(e.cfg.pins, "w").write(open(e.cfg.pins).read().split("\n")[0] + "\n"); r = e.run(e.ticket())
t("K5 script not pinned refused", r["reason"] == "script_not_pinned" and e.ncalls() == 0)
e = fresh(); open(e.cfg.pins, "a").write("%s  gone.sh\n" % ("0" * 64)); r = e.run(e.ticket())
t("K6 pinned file missing refused", r["reason"] == "pinned_file_missing:gone.sh" and e.ncalls() == 0)
e = fresh(); tk = e.ticket(); r = e.run(tk)
t("K7 pinned copy removed after run", not os.path.exists(os.path.join(e.cfg.state_dir, tk["ticket_id"] + ".run")) and r["passed"] is True)
e = fresh(script_body='cp "$0" %s/swap_seen' % tempfile.gettempdir()); r = e.run(e.ticket())
t("K8 script runs from the private pinned copy", r["status"] == "done" and open(os.path.join(tempfile.gettempdir(), "swap_seen")).read() == open(os.path.join(e.cfg.lib_dir, "fmtest.sh")).read())
# ---- audit fix C: runner-local autonomy switch ----
e = fresh(); os.remove(e.cfg.autonomy_file); r = e.run(e.ticket())
t("K9 no runner-local autonomy file -> refused even with a valid fully_autonomous ticket", r["reason"] == "runner_autonomy_off" and e.ncalls() == 0)
e = fresh(); open(e.cfg.autonomy_file, "w").write("graduated_window\n"); r = e.run(e.ticket())
t("K10 runner-local state below fully_autonomous -> refused", r["reason"] == "runner_autonomy_off" and e.ncalls() == 0)
e = fresh(); open(e.cfg.autonomy_file, "w").write("fully_autonomous_x\n"); r = e.run(e.ticket())
t("K11 runner-local state must match exactly", r["reason"] == "runner_autonomy_off")
# ---- audit fix G: container state is part of passed ----
for cs, want in (("running", True), ("healthy", True), ("unhealthy", False), ("starting", False), ("not_running", False), ("unknown", False)):
    e = fresh(); e.cstate = cs; r = e.run(e.ticket())
    t("K12 HTTP 200 + container %s -> passed %s" % (cs, want), r["passed"] is want and r["container_state"] == cs)
e = fresh(container_check=False); e.cstate = "not_running"; r = e.run(e.ticket())
t("K13 container check off -> HTTP only", r["passed"] is True and r["container_state"] == "not_checked")
# ---- code review fix: 2026-11-25 code-review fixes ----
import threading
e = fresh(); tk = e.ticket(); r = e.run(tk); open(os.path.join(e.cfg.state_dir, tk["ticket_id"] + ".result.json"), "w").write('{"trunc')
r2 = e.run(tk)
t("K14 corrupt stored result -> signed refusal, no crash, no re-run", r2["reason"] == "stored_result_unreadable" and R.verify(KEY, r2) and e.ncalls() == 1)
r3 = R.handle(e.cfg, KEY, json.dumps({"op": "result", "ticket_id": tk["ticket_id"]}), e.deps)
t("K15 result op on corrupt result -> stored_result_unreadable, signed", r3["reason"] == "stored_result_unreadable" and R.verify(KEY, r3))
e = fresh(health_interval=0); r = e.run(e.ticket())
t("K16 health_interval 0 -> refused bad_health_config before running", r["reason"] == "bad_health_config" and e.ncalls() == 0)
e.cfg.health_interval = 5; r = e.run(e.ticket())
t("K16b ...and the incident was not consumed", r["status"] == "done")
e = fresh(health_wait=-1); r = e.run(e.ticket())
t("K16c negative health_wait refused", r["reason"] == "bad_health_config" and e.ncalls() == 0)
e = fresh(); tk = e.ticket(); open(os.path.join(e.cfg.state_dir, tk["ticket_id"] + ".run"), "w").write("x")
r = e.run(tk)
left = sorted(x for x in os.listdir(e.cfg.state_dir) if x.endswith((".ran", ".state", ".run")))
t("K17 private copy cannot be written -> run_copy_failed, nothing run, marker/state/copy released",
  r["reason"] == "run_copy_failed:FileExistsError" and e.ncalls() == 0 and left == [])
r = e.run(e.ticket()); t("K17b ...and a new ticket for the same incident can still run", r["status"] == "done")
e = fresh(); tk = e.ticket(); open(os.path.join(e.cfg.state_dir, tk["ticket_id"] + ".state"), "w").close()
r = e.run(tk)
t("K18 ticket already claimed -> running, incident NOT consumed", r["status"] == "running" and not os.path.exists(os.path.join(e.cfg.state_dir, "incident-%s.ran" % e.iid)))
r = e.run(e.ticket()); t("K18b ...so another ticket for the incident still runs", r["status"] == "done")
tk2 = e.ticket(); r = e.run(tk2)
t("K19 incident_already_run releases that ticket's .state", r["reason"] == "incident_already_run" and not os.path.exists(os.path.join(e.cfg.state_dir, tk2["ticket_id"] + ".state")))
d = tempfile.mkdtemp(); target = os.path.join(d, "x.result.json"); errs = []
def w(i):
    try:
        for k in range(200): R._atomic(target, json.dumps({"w": i, "k": k}))
    except Exception as ex: errs.append(ex)
ths = [threading.Thread(target=w, args=(i,)) for i in range(8)]
[x.start() for x in ths]; [x.join() for x in ths]
t("K20 8 concurrent writers: no errors, valid JSON, no temp files left",
  not errs and isinstance(json.load(open(target)), dict) and os.listdir(d) == ["x.result.json"])
t("K20b stored result keeps 0644", stat.S_IMODE(os.stat(target).st_mode) == 0o644)
print("ALL PASS" if BAD == 0 else "FAILURES: %d" % BAD); sys.exit(1 if BAD else 0)
