# A2A gateway (third-party, Apache-2.0)

Daikaiju AIOps uses the upstream project `mcp_a2a_gateway`
(https://github.com/yw0nam/mcp_a2a_gateway), licensed Apache-2.0. It is **not copied here**.
Install upstream, then apply `gateway-modifications.patch` (our changes to `agent_manager.py`,
`server.py`, `task_manager.py`; stated here as required by Apache-2.0 section 4).
