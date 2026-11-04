"""Offline tests for kaiju_relay_mcp_server.py. Run: python3 -I test_kaiju_relay_mcp.py (needs: pip install mcp starlette uvicorn for the wiring test)"""
import os, sys, tempfile, threading, unittest
root = tempfile.mkdtemp()
os.environ["VAULT_ROOT"] = root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kaiju_relay_mcp_server as s

target = os.path.join(root, "cfg.txt")
open(target, "w").write("a=1\n")
OK = {"stage_c_verdict": "PASS", "checkpoint_mandatory": False, "rendered": "BRIEF TEXT\nEDITS_JSON\n{}"}


class T(unittest.TestCase):
    def test_ok(self):
        out = s.draft_edit_brief_text("change a to 2", target, runner=lambda t, p: OK)
        self.assertTrue(out.startswith("EDIT BRIEF DRAFT (read-only; nothing was changed)"))
        self.assertIn("Stage C verdict: PASS", out)
        self.assertIn("BRIEF TEXT", out)

    def test_runner_gets_real_path_and_stripped_task(self):
        seen = {}
        s.draft_edit_brief_text("  do x  ", target, runner=lambda t, p: seen.update(t=t, p=p) or OK)
        self.assertEqual(seen, {"t": "do x", "p": os.path.realpath(target)})

    def test_checkpoint_text(self):
        r = dict(OK, checkpoint_mandatory=True, checkpoint_reason="stage C warning")
        self.assertIn("Checkpoint needed: True (stage C warning)", s.draft_edit_brief_text("t", target, runner=lambda a, b: r))

    def test_error_and_not_applicable(self):
        self.assertTrue(s.draft_edit_brief_text("t", target, runner=lambda a, b: {"error": "boom"}).startswith("NO BRIEF: boom"))
        out = s.draft_edit_brief_text("t", target, runner=lambda a, b: {"error": "NOT APPLICABLE x", "not_applicable": True})
        self.assertIn("not applicable", out)

    def test_runner_exception_and_bad_return(self):
        def boom(a, b): raise RuntimeError("ollama down")
        self.assertIn("ollama down", s.draft_edit_brief_text("t", target, runner=boom))
        self.assertTrue(s.draft_edit_brief_text("t", target, runner=lambda a, b: None).startswith("ERROR"))

    def test_path_checks(self):
        for bad in ("", None, "/etc/passwd", root + "/../etc/passwd", root + "/missing.txt", root):
            self.assertTrue(s.draft_edit_brief_text("t", bad, runner=lambda a, b: OK).startswith("ERROR"), bad)

    def test_symlink_escape_blocked(self):
        link = os.path.join(root, "evil")
        os.symlink("/etc/hostname", link)
        self.assertTrue(s.draft_edit_brief_text("t", link, runner=lambda a, b: OK).startswith("ERROR"))

    def test_empty_task(self):
        for t in ("", "   ", None):
            self.assertTrue(s.draft_edit_brief_text(t, target, runner=lambda a, b: OK).startswith("ERROR"))

    def test_busy_lock(self):
        go, started = threading.Event(), threading.Event()
        def slow(a, b):
            started.set(); go.wait(5); return OK
        res = {}
        th = threading.Thread(target=lambda: res.update(first=s.draft_edit_brief_text("t", target, runner=slow)))
        th.start(); started.wait(5)
        self.assertTrue(s.draft_edit_brief_text("t", target, runner=lambda a, b: OK).startswith("BUSY"))
        go.set(); th.join()
        self.assertTrue(res["first"].startswith("EDIT BRIEF"))
        self.assertTrue(s.draft_edit_brief_text("t", target, runner=lambda a, b: OK).startswith("EDIT BRIEF"))  # lock released

    def test_mcp_wiring(self):
        try:
            import asyncio
            from mcp.types import ListToolsRequest, CallToolRequest
        except ImportError:
            self.skipTest("mcp not installed")
        app = s.build_app()
        self.assertEqual([r.path for r in app.routes], ["/sse", "/messages"])

if __name__ == "__main__":
    unittest.main(verbosity=1)
