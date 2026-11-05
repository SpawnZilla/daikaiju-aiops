"""
test_server_integration.py -- real end-to-end MCP protocol test of
kaiju_mokaima_a2a_adapter.py's 3 fully-local tools (get_checkpoint_state,
review_bakaidah_output, create_a2a_task), using the actual mcp.ClientSession
against an in-process server transport -- not just direct Python function
calls. call_gateway_tool is NOT exercised here (needs the real gateway,
unreachable from this sandbox) -- see the module's own docstring.

Run with: python3 test_server_integration.py (requires mcp==1.28.1
installed -- see the deployment guide for the venv setup step still
needed on intake-host).
"""

import asyncio
import json
import os
import tempfile

os.environ["KAIJU_VAULT_ROOT"] = tempfile.mkdtemp()

import kaiju_mokaima_a2a_adapter as srv
from mcp.shared.memory import create_connected_server_and_client_session


async def main():
    async with create_connected_server_and_client_session(srv.mcp._mcp_server) as client:
        # TEST 1: get_checkpoint_state on a fresh VAULT root -> stage_0
        result = await client.call_tool("get_checkpoint_state", {})
        state = json.loads(result.content[0].text)
        assert state["checkpoint_state"] == "stage_0", state
        print("TEST 1 (fresh checkpoint state via real MCP call): PASS", state)

        # TEST 2: review_bakaidah_output on a clean contract -> holds for check-in
        result = await client.call_tool("review_bakaidah_output", {
            "target_path": "/srv/vault/notes/example.md",
            "command_type": "write",
            "command": "write a script",
            "justification": "ordinary task",
        })
        review = json.loads(result.content[0].text)
        assert review["route"] == "hold_for_checkin", review
        print("TEST 2 (clean review via real MCP call): PASS", review["route"])

        # TEST 3: state persisted -- a second get_checkpoint_state call sees
        # the updated clean_run_count from TEST 2's review
        result = await client.call_tool("get_checkpoint_state", {})
        state2 = json.loads(result.content[0].text)
        assert state2["clean_run_count"] == 1, state2
        print("TEST 3 (state persisted across separate tool calls): PASS", state2)

        # TEST 4: dangerous contract -> escalates AND resets, over real MCP
        result = await client.call_tool("review_bakaidah_output", {
            "target_path": "/srv/vault/notes/example.md",
            "command_type": "execute",
            "command": "sudo systemctl restart mcp-a2a-gateway",
            "justification": "restart",
        })
        review2 = json.loads(result.content[0].text)
        assert review2["route"] == "escalate_to_operator", review2
        assert review2["checkpoint_state_after"]["checkpoint_state"] == "stage_0"
        print("TEST 4 (hard-stop escalates + resets via real MCP call): PASS", review2["route"])

        # TEST 5: create_a2a_task via real MCP call, stamped with current checkpoint
        result = await client.call_tool("create_a2a_task", {
            "origin_agent": "mokaima",
            "target_agent": "bakaidah",
            "task_type": "brief",
            "payload_ref": "angkai/briefs/test.md",
        })
        task = json.loads(result.content[0].text)
        assert task["status"] == "queued"
        assert task["checkpoint_state"] == "stage_0"
        assert "task_id" in task
        print("TEST 5 (create_a2a_task via real MCP call): PASS", task["task_id"])

    print("\nALL 5 REAL-MCP-PROTOCOL INTEGRATION TESTS PASS")

asyncio.run(main())
