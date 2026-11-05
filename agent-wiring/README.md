# Agent wiring

Reference code that connects the planning, reasoning and execution agents.

- `mokaima-adapter/`: the planning-agent adapter (MCP server) with the checkpoint ladder, autonomy scope gate, review step and hard-stop filter.
- `bakaidah-a2a/`: the reasoning agent's A2A server and executor.
- `gateway/`: NOT a copy. The A2A gateway is the upstream Apache-2.0 project `mcp_a2a_gateway`; install it and apply `gateway-modifications.patch` (see `NOTICE.md`).
- `mcpo/`: Docker compose file and example config for the mcpo tool bridge.
- `tests/`: 9 tests. Run from a copy of `mokaima-adapter/` plus `tests/` in one folder, with `pip install pytest mcp==1.28.1 httpx` and `KAIJU_VAULT_ROOT` / `KAIJU_GOVERNANCE_ROOT` pointed at empty temp folders.

Paths, addresses and ports are placeholders. Not yet part of `install.sh`.
