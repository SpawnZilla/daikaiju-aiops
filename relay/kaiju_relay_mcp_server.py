#!/usr/bin/env python3
"""
kaiju_relay_mcp_server.py  (v0.1, staged 2026-11-01, NOT installed)
Native SSE MCP server on dokaisho, port 8301, served to Open WebUI / Mokaima through mcpo.
One tool, draft_edit_brief(task, target_path): runs the Kaiju Relay edit pipeline
(relay_edit_brief.run_edit_pipeline: verify excerpts, draft, Stage C review) and returns the
rendered edit brief plus its EDITS_JSON block. READ-ONLY: it never applies an edit and never
writes a file; apply_edit_brief.py and the  broker stay the only way a brief becomes a change.
Same pattern as graphify_mcp_server.py (port 8300). No Pipe.
Deploy: /srv/mcpo/kaiju_relay_mcp_server.py ; managed by kaiju-relay-mcp.service.
"""

import asyncio
import os
import sys
import threading
import logging

RELAY_DIR = os.environ.get("RELAY_DIR", "/srv/kaiju-vault/kaiju-relay")
VAULT_ROOT = os.environ.get("VAULT_ROOT", "/srv/kaiju-vault")
MODEL_TAG = os.environ.get("RELAY_MODEL", "gemma4-bakaidah:31b")
NUM_CTX = int(os.environ.get("RELAY_NUM_CTX", "24576"))  # same as the loaded model, so Ollama does not reload it
TIMEOUT_S = int(os.environ.get("RELAY_TIMEOUT_S", "180"))
PORT = int(os.environ.get("RELAY_MCP_PORT", "8301"))

log = logging.getLogger("kaiju-relay-mcp")
_LOCK = threading.Lock()  # one pipeline run at a time: the model has a single slot


def check_target(target_path: str):
    """Returns (ok, message). The target must be a file inside vault (the relay reads it through mcpo's vault server)."""
    if not isinstance(target_path, str) or not target_path.strip():
        return False, "target_path is required"
    real = os.path.realpath(target_path)
    root = os.path.realpath(VAULT_ROOT)
    if not (real == root or real.startswith(root + os.sep)):
        return False, "target_path must be inside %s" % VAULT_ROOT
    if not os.path.isfile(real):
        return False, "target file not found: %s" % target_path
    return True, real


def _default_runner(task, target_path):
    if RELAY_DIR not in sys.path:
        sys.path.insert(0, RELAY_DIR)
    import relay_edit_brief  # noqa: E402
    return relay_edit_brief.run_edit_pipeline(MODEL_TAG, task, target_path, timeout=TIMEOUT_S, num_ctx=NUM_CTX)


def draft_edit_brief_text(task, target_path, runner=None):
    """Plain function (testable without MCP). Returns the text the tool sends back. Never raises."""
    if not isinstance(task, str) or not task.strip():
        return "ERROR: task is required (describe the exact change, e.g. which line and the new value)"
    ok, msg = check_target(target_path)
    if not ok:
        return "ERROR: " + msg
    if not _LOCK.acquire(blocking=False):
        return "BUSY: another edit brief is being drafted; try again in a minute"
    try:
        res = (runner or _default_runner)(task.strip(), msg)
    except Exception as exc:  # fail closed with a readable message
        log.warning("pipeline error: %r", exc)
        return "ERROR: the relay pipeline failed: %s" % exc
    finally:
        _LOCK.release()
    if not isinstance(res, dict):
        return "ERROR: the relay pipeline returned nothing usable"
    if res.get("error"):
        return ("NO BRIEF: %s" % res["error"]) + ("\n(not applicable: nothing in the target would change)" if res.get("not_applicable") else "")
    head = ["EDIT BRIEF DRAFT (read-only; nothing was changed)",
            "Stage C verdict: %s" % res.get("stage_c_verdict"),
            "Checkpoint needed: %s%s" % (bool(res.get("checkpoint_mandatory")), (" (" + str(res.get("checkpoint_reason")) + ")") if res.get("checkpoint_mandatory") else ""),
            "Review this brief before it is applied. It is applied only by apply_edit_brief.py or the  edit_brief broker class.",
            ""]
    return "\n".join(head) + (res.get("rendered") or "(no rendered brief)")


# ------------------------------------------------------------------ MCP wiring (same shape as graphify_mcp_server.py)
def build_app():
    from mcp.server import Server
    from mcp.server.sse import SseServerTransport
    from mcp.types import Tool, TextContent
    from starlette.applications import Starlette
    from starlette.routing import Route, Mount

    app = Server("kaiju-relay")

    @app.list_tools()
    async def list_tools():
        return [Tool(
            name="draft_edit_brief",
            description=("Draft a verified EDIT BRIEF for ONE file in the Kaidosho library (vault). Give the exact change wanted and the absolute path of the file. "
                         "Returns a brief with verbatim excerpts, the proposed edits and an EDITS_JSON block, plus a review verdict. It only DRAFTS: it never changes the file. "
                         "Takes 1 to 3 minutes. Use it when asked to prepare a change to a config or script; do not use it to read or search files."),
            inputSchema={"type": "object", "properties": {
                "task": {"type": "string", "description": "The exact change, e.g. 'On the feed line for r/homelab, replace the URL with X and change nothing else.'"},
                "target_path": {"type": "string", "description": "Absolute path of the file inside /srv/kaiju-vault"}},
                "required": ["task", "target_path"]})]

    @app.call_tool()
    async def call_tool(name: str, arguments: dict):
        if name != "draft_edit_brief":
            return [TextContent(type="text", text="Unknown tool: %s" % name)]
        text = await asyncio.to_thread(draft_edit_brief_text, arguments.get("task"), arguments.get("target_path"))
        return [TextContent(type="text", text=text)]

    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await app.run(streams[0], streams[1], app.create_initialization_options())

    return Starlette(routes=[Route("/sse", endpoint=handle_sse), Mount("/messages/", app=sse.handle_post_message)])


if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(build_app(), host="0.0.0.0", port=PORT)
