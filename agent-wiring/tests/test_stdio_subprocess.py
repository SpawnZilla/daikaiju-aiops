"""
test_stdio_subprocess.py -- spawns kaiju_mokaima_a2a_adapter.py as an
actual subprocess over stdio, exactly the way Claude Desktop's
claude_desktop_config.json "command"/"args" mechanism would launch it
(matching the existing filesystem/mem0/git server pattern). This is the
closest available verification to the real deployment shape, short of
actually registering it in claude_desktop_config.json and restarting.

Run with: python3 test_stdio_subprocess.py (requires mcp==1.28.1
installed -- see the deployment guide for the venv setup step still
needed on intake-host).
"""

import asyncio
import json
import os
import sys
import tempfile

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

VAULT_TMP = tempfile.mkdtemp()
PYTHON = sys.executable
SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kaiju_mokaima_a2a_adapter.py")


async def main():
    params = StdioServerParameters(
        command=PYTHON,
        args=[SCRIPT],
        env={**os.environ, "KAIJU_VAULT_ROOT": VAULT_TMP},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            assert names == sorted([
                "get_checkpoint_state", "review_bakaidah_output",
                "create_a2a_task", "call_gateway_tool",
            ]), names
            print("TEST 1 (real stdio subprocess, list_tools): PASS", names)

            result = await session.call_tool("get_checkpoint_state", {})
            state = json.loads(result.content[0].text)
            assert state["checkpoint_state"] == "stage_0"
            print("TEST 2 (real stdio subprocess, get_checkpoint_state): PASS", state)

            result = await session.call_tool("create_a2a_task", {
                "origin_agent": "mokaima", "target_agent": "angkai",
                "task_type": "execute", "payload_ref": "angkai/briefs/x.md",
                "priority": "high", "max_tool_calls": 1,
            })
            task = json.loads(result.content[0].text)
            assert task["priority"] == "high"
            assert task["max_tool_calls"] == 1
            print("TEST 3 (real stdio subprocess, create_a2a_task): PASS", task["task_id"])

    print("\nALL 3 REAL STDIO-SUBPROCESS TESTS PASS -- this is the actual launch shape Claude Desktop would use")

asyncio.run(main())
