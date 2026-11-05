"""Bakaidah A2A agent-server entry point. Wires BakaidahAgentExecutor into
the A2A protocol's Starlette app and serves it over HTTP on port 10001.
"""


import logging

import uvicorn
from a2a.server.apps.jsonrpc.starlette_app import A2AStarletteApplication
from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from bakaidah_executor import BakaidahAgentExecutor

# fix: without this, the root logger defaults to WARNING and
# every logger.info() call in bakaidah_executor.py/bakaidah_filter_check.py
# (including the diagnostic logging added to debug the empty-
# reply_text issue) is silently dropped before it ever reaches a
# handler. Absence of those INFO lines in journalctl across this
# session's prior live tests is therefore inconclusive on its own --
# could mean the logged condition was genuinely false, or could mean
# this gap. Fixing it now so the next test's diagnostic log is actually
# trustworthy either way. Does not touch uvicorn's own loggers
# (uvicorn/uvicorn.access/uvicorn.error), which configure themselves
# separately inside uvicorn.run() below.
logging.basicConfig(level=logging.INFO)

AGENT_CARD = AgentCard(
    name="Bakaidah",
    description=(
        "Daikaiju AIOps reasoning agent — drafts proposed fixes and "
        "analysis for Kaiju-GAIS/Angkai tasks."
    ),
    url="http://192.0.2.45:<port>/",
    version="1.0.0",
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    capabilities=AgentCapabilities(streaming=False, push_notifications=False),
    skills=[
        AgentSkill(
            id="reasoning-draft",
            name="Reasoning and Drafting",
            description=(
                "Analyzes a task brief and drafts a proposed fix or response."
            ),
            tags=["reasoning", "drafting", "daikaiju-aiops"],
        )
    ],
)

handler = DefaultRequestHandler(
    agent_executor=BakaidahAgentExecutor(),
    task_store=InMemoryTaskStore(),
)

app_builder = A2AStarletteApplication(agent_card=AGENT_CARD, http_handler=handler)
app = app_builder.build()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10001)