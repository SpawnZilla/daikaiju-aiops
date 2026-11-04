#!/usr/bin/env python3
"""Tests for schema_version 3 / edit_brief. Runs as current user; unit restart + probes faked. python3 test_kaiju_broker_v3.py"""
import hashlib, json, os, sys, tempfile, uuid
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.dont_write_bytecode = True
T = tempfile.mkdtemp()
os.environ.update({"KAIBROKER_SPOOL": T+"/spool", "KAIBROKER_STATE": T+"/state", "KAIBROKER_POLICY": T+"/policy.json",
  "KAIBROKER_CHECKPOINT": T+"/cp.json", "KAIBROKER_ALLOWED_UID": str(os.getuid()), "KAIBROKER_NTFY": T+"/none.json"})
import kaiju_broker as kb
for d in ("spool/incoming","spool/outcomes","state","stage/pkg","prod/pkg","briefs"): os.makedirs(os.path.join(T,d))
OK = {"restart": True, "alive": True}
kb.restart_unit = lambda u: OK["restart"]
kb.service_ok = lambda chk: OK["alive"]
kb.unit_active = lambda u: True
kb.notify = lambda *a, **k: False
json.dump({"checkpoint_state": "fully_autonomous"}, open(T+"/cp.json","w"))
def policy(apply=True, state="fully_autonomous", brief_dir=None):
    json.dump({"version":1,"targets":{"gw":{"staging_root":T+"/stage","production_root":T+"/prod","apply_enabled":apply,
      "allowed_relpaths":["pkg/*.py"],
      "sandbox_check":{"unit":"s.service","url":"http://127.0.0.1:1/x","timeout_seconds":1,"settle_seconds":0},
      "prod_check":{"unit":"p.service","url":"http://127.0.0.1:1/x","timeout_seconds":1,"settle_seconds":0},
      "classes":{"code_file_replace":{"min_checkpoint_state":"fully_autonomous"},
                 "edit_brief":{"min_checkpoint_state":state,"brief_dir":brief_dir or T+"/briefs"}}}}}, open(T+"/policy.json","w"))
sha = lambda t: hashlib.sha256(t.encode()).hexdigest()
BASE = "a = 1\nb = 2\n"
def setup(base=BASE, stage=None):
    open(T+"/prod/pkg/m.py","w").write(base); open(T+"/stage/pkg/m.py","w").write(base if stage is None else stage)
def brief(edits=None, base_sha=None, target=None, name="b.md"):
    p = {"target_file": target or T+"/prod/pkg/m.py", "base_sha256": base_sha or sha(BASE),
         "edits": edits or [{"old_text":"b = 2","new_text":"b = 3"}]}
    path = os.path.join(T,"briefs",name); open(path,"w").write("EDITS_JSON\n```json\n"+json.dumps(p)+"\n```\n"); return path
def submit(brief_path, cls="edit_brief", tid=None, **over):
    rid = str(uuid.uuid4()); req = {"schema_version":"3","request_id":rid,"task_id":tid or "t-"+rid[:6],"target":"gw",
      "change_class":cls,"submitted_at":"x","brief_path":brief_path}; req.update(over)
    json.dump(req, open(T+"/spool/incoming/"+rid+".json","w"))
    return kb.run_once(kb.Config())[0]
fails = []
def check(name, cond):
    print(("PASS " if cond else "FAIL ")+name);
    if not cond: fails.append(name)
policy(); setup()
r = submit(brief()); check("promoted applies edit to production", r["status"]=="promoted" and open(T+"/prod/pkg/m.py").read()=="a = 1\nb = 3\n")
check("staging stays in sync after promote", open(T+"/stage/pkg/m.py").read()==open(T+"/prod/pkg/m.py").read())
setup(); policy(apply=False); r = submit(brief())
check("dry run: pass, production untouched, staging restored", r["status"]=="dry_run_pass" and open(T+"/prod/pkg/m.py").read()==BASE and open(T+"/stage/pkg/m.py").read()==BASE)
policy(); setup(); OK["alive"]=False; r = submit(brief())
check("failed sandbox proof -> rejected_fixable, prod+staging unchanged", r["status"]=="rejected_fixable" and open(T+"/prod/pkg/m.py").read()==BASE and open(T+"/stage/pkg/m.py").read()==BASE)
OK["alive"]=True; setup(); r = submit(brief(base_sha="0"*64)); check("drift (wrong base sha) rejected", "E_BRIEF_DRIFT" in r["codes"])
setup(); r = submit(brief(edits=[{"old_text":"zzz","new_text":"y"}])); check("old_text not found rejected", "E_BRIEF_INVALID" in r["codes"])
setup(); r = submit(brief(edits=[{"old_text":"=","new_text":"-"}])); check("ambiguous old_text rejected", "E_BRIEF_INVALID" in r["codes"])
setup(stage="a = 9\n"); r = submit(brief()); check("dirty staging rejected, staging untouched", "E_STAGING_NOT_CLEAN" in r["codes"] and open(T+"/stage/pkg/m.py").read()=="a = 9\n")
setup(); r = submit(brief(target="/etc/passwd")); check("target outside production_root escalated", "P_PATH_NOT_ALLOWED" in r["codes"] and r["status"]=="escalated")
os.makedirs(T+"/prod/other",exist_ok=True); open(T+"/prod/other/x.sh","w").write("x"); setup()
r = submit(brief(target=T+"/prod/other/x.sh")); check("path not in allowed_relpaths escalated", "P_PATH_NOT_ALLOWED" in r["codes"])
setup(); open("/tmp/outside_brief.md","w").write("x"); r = submit("/tmp/outside_brief.md"); check("brief outside brief_dir rejected", "E_ARTIFACT_OUTSIDE_STAGING" in r["codes"])
setup(); r = submit(brief(), cls="code_file_replace"); check("wrong class escalated", "P_CLASS_NOT_ALLOWED" in r["codes"])
policy(state="graduated_window"); json.dump({"checkpoint_state":"stage_0"}, open(T+"/cp.json","w")); setup()
r = submit(brief()); check("checkpoint below minimum escalated", "P_CHECKPOINT_STATE" in r["codes"])
json.dump({"checkpoint_state":"fully_autonomous"}, open(T+"/cp.json","w")); policy(); setup()
rid = str(uuid.uuid4()); json.dump({"schema_version":"3","request_id":rid,"task_id":"rp","target":"gw","change_class":"edit_brief","submitted_at":"x","brief_path":brief()}, open(T+f"/spool/incoming/{rid}.json","w")); kb.run_once(kb.Config())
setup(); json.dump({"schema_version":"3","request_id":rid,"task_id":"rp","target":"gw","change_class":"edit_brief","submitted_at":"x","brief_path":brief()}, open(T+f"/spool/incoming/{rid}.json","w"))
r = kb.run_once(kb.Config())[0]; check("replay escalated", "E_REPLAY" in r["codes"] and r["status"]=="escalated")
setup(); rid2=str(uuid.uuid4()); json.dump({"schema_version":"3","request_id":rid2,"task_id":"mf","target":"gw","change_class":"edit_brief","submitted_at":"x"}, open(T+f"/spool/incoming/{rid2}.json","w"))
r = kb.run_once(kb.Config())[0]; check("missing brief_path rejected", "E_FIELD_MISSING:brief_path" in r["codes"])
for i in range(5): setup(); r = submit(brief(base_sha="1"*64), tid="same")
setup(); r = submit(brief(), tid="same"); check("resubmit limit enforced", "E_RESUBMIT_LIMIT" in r["codes"])
print("\n%d failed" % len(fails)); sys.exit(1 if fails else 0)
