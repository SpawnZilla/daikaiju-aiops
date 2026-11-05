"""Bakaidah A2A AgentExecutor — bridges incoming A2A messages to Open
WebUI's chat-completions API, where Bakaidah (gemma4-bakaidah:31b) actually
runs. fix (option b, 2026-08-30): Open WebUI's own Filter chain never
executes on this raw /api/chat/completions path (confirmed root cause,
part 10; live-tested and ruled out on the chat_id-attached completions
flow and /api/chat/completed too, same session). This executor now
runs a faithful port of the 4 gate-shaped Filters (Reference
Existence, Incident Fabrication, Citation Grounding, Enforcement
Gate) directly against Bakaidah's raw response, via
bakaidah_filter_check.py, and appends the same "---\nwarning: ..."
banner convention those Filters use — so section6_warnings can finally
see real verdicts instead of an always-empty gap.

UPDATE 2026-08-30 (same session, fidelity-gap follow-up):
wires in citation grounding's soft inlet() steering instruction (the
real Filter's system-message nudge asking Bakaidah to include a
literal supporting quote when citing a web source), which was
deliberately left unwired when this file was first built -- see
CITATION_QUOTE_INSTRUCTION's own docstring note in
bakaidah_filter_check.py for why this was flagged as a known fidelity
gap rather than silently guessed into place. Gated behind the same
INJECT_CITATION_QUOTE_INSTRUCTION flag bakaidah_filter_check.py
already exposes -- default True, matching the real Filter's own
default. When present, this appends a NEW system message ahead of
the user turn rather than modifying the user's own message text, so
the trigger/message content contract this executor's callers already
depend on is unchanged.
"""


import logging
import os
import re
import time
import uuid

import httpx
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils import new_agent_text_message

from bakaidah_filter_check import (
    run_all_gates,
    INJECT_CITATION_QUOTE_INSTRUCTION,
    CITATION_QUOTE_INSTRUCTION,
    GROUNDING_INSTRUCTION,
    needs_grounding_instruction,
    postprocess_reply,
)
from bakaidah_stage_b import (
    should_retry as stage_b_should_retry,
    stage_b_retry,
    ask_bakaidah,
)
import bakaidah_direct as bdirect
import bakaidah_ledger_gate as bledger

logger = logging.getLogger(__name__)

# tool-ladder fix (2026-10-14): the citation-quote steering message is
# only for tasks that actually ask for citations or web sources. Injected into
# every task, it made a tool task's final reply answer the steering message
# ("Please provide the web source or URL...") instead of the task (TT-2, TT-2c).
_CITATION_TASK_RE = re.compile(
    r"\bcit(?:e|es|ed|ing|ation|ations)\b|https?://|\bweb\s+(?:search|source|sources|page)\b"
    r"|\bsearch\s+the\s+web\b",
    re.IGNORECASE,
)


def _wants_citation(user_text):
    return bool(_CITATION_TASK_RE.search(user_text or ""))


OPENWEBUI_BASE_URL = os.environ.get("OPENWEBUI_BASE_URL", "http://192.0.2.21:3000")
OPENWEBUI_API_KEY = os.environ["OPENWEBUI_API_KEY"]
BAKAIDAH_MODEL = os.environ.get("BAKAIDAH_MODEL", "gemma4-bakaidah:31b")

# fix, Path A (native/agentic mode) -- CORRECTED 2026-09-13 from
# an earlier same-session Path B (legacy function-calling) attempt.
# Path B was live-tested (real gateway round trip, agent_task_id
# populated, task completed) and produced NO tool call at all --
# confirmed via Open WebUI's own current docs: "Legacy Mode is legacy
# and no longer supported... Native (Agentic) Mode... is the only
# supported mode going forward." Path B is not a config problem to
# fix, it's an unsupported path. Path A is the only mode Open WebUI's
# own docs currently commit to actually working.
#
# Path A requires a real chat lifecycle per call (create -> completion
# with chat_id+id+stream:true -> read final message -> delete), since
# the native tool-execution loop only runs on that code path (it
# writes results into the chat record, not the raw HTTP response).
# Blocking variant used here (no session_id): the HTTP call blocks
# until Open WebUI's tool loop finishes and returns null, matching
# this executor's existing single-await-per-call shape. Built-in tools
# (web search, code interpreter, etc) are NOT available in blocking
# mode -- acceptable, since's scope is tool_ids (vault,
# sandbox_execute), not built-ins.
#
# BAKAIDAH_TOOL_IDS: comma-separated Open WebUI tool_ids, e.g.
# "server:0,server:mcp:sandbox_execute". Empty/unset sends no tool_ids
# at all (plain no-tools completion via Path A, still heavier than the
# old bare-completion call but harmless).
_BAKAIDAH_TOOL_IDS_RAW = os.environ.get("BAKAIDAH_TOOL_IDS", "")
BAKAIDAH_TOOL_IDS = [t.strip() for t in _BAKAIDAH_TOOL_IDS_RAW.split(",") if t.strip()]

# (2026-09-18): one ceiling for the whole blocking Open WebUI
# round trip (create chat -> completion/tool loop -> read -> delete).
# Was hardcoded 180.0, too short for tool-using prompts (confirmed live
# 2026-09-18: httpx.ReadTimeout at the completion call). Must stay BELOW
# the gateway's MCP_REQUEST_TIMEOUT (mcp-a2a-gateway.service.d/
# override.conf) or the gateway gives up first and the original
# stacked-ceiling mismatch returns.
EXECUTOR_TIMEOUT_SECONDS = float(os.environ.get("BAKAIDAH_EXECUTOR_TIMEOUT", "300"))


class BakaidahAgentExecutor(AgentExecutor):
    """Executes A2A requests by forwarding them to Bakaidah via Open WebUI,
    then running the 4 gate-shaped Filter ports against the
    raw reply before returning it."""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        user_text = context.get_user_input()

        messages = []
        if INJECT_CITATION_QUOTE_INSTRUCTION and _wants_citation(user_text):
            # Faithful port of bakaidah_citation_grounding_filter's own
            # inlet(): a soft, non-enforced steering instruction, sent
            # as its own system message ahead of the user turn rather
            # than altering user_text itself. Raises how often the
            # citation-grounding gate check (outlet-equivalent, in
            # run_all_gates below) has an actual quoted span to verify
            # -- without this, that check simply finds fewer checkable
            # quotes (the same "unverifiable" bucket the real Filter
            # itself uses for that case), never a false negative on a
            # genuine fabrication that IS present.
            messages.append({"role": "system", "content": CITATION_QUOTE_INSTRUCTION})
        # (2026-09-27): when the task restricts analysis to the
        # provided material, add the grounding rule as its own system
        # message (same mechanism as the citation-quote instruction).
        if needs_grounding_instruction(user_text):
            messages.append({"role": "system", "content": GROUNDING_INSTRUCTION})
        if bledger.needs_ledger(user_text):
            messages.append({"role": "system", "content": bledger.LEDGER_INSTRUCTION})
        messages.append({"role": "user", "content": user_text})

        # prompt-overflow fix (2026-10-10): drift and triage table
        # tasks skip Open WebUI and its tools. Through Open WebUI every
        # prompt carried 30,872 tokens of workspace prompt plus tool schemas,
        # more than num_ctx 24,576, so Ollama cut the front off (see
        # bakaidah_direct.py). The direct path sends a ~400-token system prompt
        # straight to Ollama and runs the same post-processing, gates and
        # Stage B on the reply. If the direct call fails, fall through to the
        # Open WebUI path below, without tool_ids, and say so in a footer.
        fallback_note = ""
        mechanical = bdirect.is_mechanical_task(user_text)
        if bdirect.should_use_direct(user_text) and not bledger.needs_ledger(user_text):
            try:
                direct_final = await bdirect.run_direct(
                    user_text,
                    [GROUNDING_INSTRUCTION] if needs_grounding_instruction(user_text) else [],
                    EXECUTOR_TIMEOUT_SECONDS,
                    postprocess_reply,
                    run_all_gates,
                    stage_b_should_retry,
                    stage_b_retry,
                )
            except Exception as exc:
                logger.exception(
                    " direct path failed; falling back to the Open WebUI path."
                )
                fallback_note = (
                    "\n\n[executor] direct Ollama path failed (%s); this reply came "
                    "from the Open WebUI path without tools." % type(exc).__name__
                )
            else:
                await event_queue.enqueue_event(
                    new_agent_text_message(direct_final, context.context_id, context.task_id)
                )
                return

        # Table tasks never need tools (their schemas were about 15k tokens).
        tool_ids = [] if mechanical else BAKAIDAH_TOOL_IDS

        request_body = {
            "model": BAKAIDAH_MODEL,
            "messages": messages,
        }
        if tool_ids:
            request_body["tool_ids"] = tool_ids

        async with httpx.AsyncClient(timeout=EXECUTOR_TIMEOUT_SECONDS) as client:
            headers = {"Authorization": f"Bearer {OPENWEBUI_API_KEY}"}

            # --- Path A, step 1: create the chat + assistant placeholder ---
            # Native mode's tool-execution loop only runs when the
            # completion request identifies a real chat_id + assistant
            # message id -- there is no way around creating
            # one first, even for a one-shot bridge like this.
            user_msg_id = str(uuid.uuid4())
            assistant_msg_id = str(uuid.uuid4())
            now = int(time.time())
            chat_resp = await client.post(
                f"{OPENWEBUI_BASE_URL}/api/v1/chats/new",
                headers=headers,
                json={
                    "chat": {
                        "title": "Bakaidah A2A",
                        "models": [BAKAIDAH_MODEL],
                        "history": {
                            "currentId": assistant_msg_id,
                            "messages": {
                                user_msg_id: {
                                    "id": user_msg_id,
                                    "role": "user",
                                    "content": user_text,
                                    "timestamp": now,
                                    "models": [BAKAIDAH_MODEL],
                                    "childrenIds": [assistant_msg_id],
                                },
                                assistant_msg_id: {
                                    "id": assistant_msg_id,
                                    "role": "assistant",
                                    "content": "",
                                    "parentId": user_msg_id,
                                    "childrenIds": [],
                                    "model": BAKAIDAH_MODEL,
                                    "modelName": BAKAIDAH_MODEL,
                                    "modelIdx": 0,
                                    "done": False,
                                    "timestamp": now + 1,
                                },
                            },
                        },
                    }
                },
            )
            chat_resp.raise_for_status()
            chat_id = chat_resp.json()["id"]

            reply_text = ""
            try:
                # --- Path A, step 2: fire the completion (blocking) ---
                # No session_id -> blocking variant: this call itself
                # waits for Open WebUI's full native tool loop to
                # finish and returns null: the real answer has to be
                # read back from the chat record afterward (step 3),
                # not from this response body.
                request_body["chat_id"] = chat_id
                request_body["id"] = assistant_msg_id
                request_body["stream"] = True
                request_body["background_tasks"] = {
                    "title_generation": False,
                    "tags_generation": False,
                    "follow_up_generation": False,
                }
                completion_resp = await client.post(
                    f"{OPENWEBUI_BASE_URL}/api/chat/completions",
                    headers=headers,
                    json=request_body,
                )
                completion_resp.raise_for_status()

                # --- Path A, step 3: read the finished answer ---
                final_resp = await client.get(
                    f"{OPENWEBUI_BASE_URL}/api/v1/chats/{chat_id}", headers=headers
                )
                final_resp.raise_for_status()
                final_message = final_resp.json()["chat"]["history"]["messages"][
                    assistant_msg_id
                ]

                # diagnostic finding (2026-09-13): native/
                # agentic tool-calling turns on this Open WebUI version
                # leave the legacy top-level `content` field empty --
                # the real answer text lives in the LAST `output` item
                # of type "message" (itself a list of {"type":
                # "output_text", "text": ...} parts). Confirmed via a
                # real raw-response capture showing genuine tool calls
                # (tool_search_files_post, tool_list_directory_post)
                # and a correct final answer that this simpler read
                # was silently missing. Fall back to top-level content
                # first since that's still what a plain no-tool-ids
                # completion (BAKAIDAH_TOOL_IDS unset) populates.
                reply_text = final_message.get("content", "")
                output_items = final_message.get("output") or []
                has_tool_calls = any(
                    item.get("type") == "function_call" for item in output_items
                )
                last_message_text = ""
                for item in reversed(output_items):
                    if item.get("type") == "message":
                        last_message_text = "".join(
                            part.get("text", "")
                            for part in (item.get("content") or [])
                            if part.get("type") == "output_text"
                        )
                        break
                # diag (2026-09-18): lengths + first 80 chars only.
                # A tool-using reply delivered the model's acknowledgment of
                # the injected system message instead of its final answer;
                # this shows which field held what.
                logger.info(
                    " diag: content_len=%d last_message_len=%d "
                    "has_tool_calls=%s output_types=%s content_head=%r "
                    "last_message_head=%r",
                    len(reply_text),
                    len(last_message_text),
                    has_tool_calls,
                    [item.get("type") for item in output_items],
                    reply_text[:80],
                    last_message_text[:80],
                )
                # On a tool-using turn the final answer is the LAST message
                # item; top-level content can hold earlier text. Without
                # tool calls, keep the original behavior (content first).
                if last_message_text and (has_tool_calls or not reply_text):
                    reply_text = last_message_text

                # Real tool-call activity lives as function_call/
                # function_call_output items in `output` on this Open
                # WebUI version -- there is no populated top-level
                # `sources` field for native-mode tool calls the way
                # Path B's docs described for legacy mode. Logged here
                # so acceptance criteria #2/#3 ("confirm real
                # tool output, not fabrication") stay verifiable without
                # re-adding the earlier full-record diagnostic dump.
                tool_calls = [
                    item for item in output_items if item.get("type") == "function_call"
                ]
                if tool_calls:
                    logger.info(
                        ": %d real tool call(s) executed: %s",
                        len(tool_calls),
                        [call.get("name") for call in tool_calls],
                    )
            finally:
                # --- Path A, step 4: delete the ephemeral chat ---
                # Per the doc's own A5 pattern for API-only callers --
                # `temporary:<uuid>` only works for real socket.io
                # clients, not plain HTTP, so create+delete is the
                # correct approach here, not an optional cleanup step.
                # Best-effort: a delete failure must never mask
                # whatever reply_text was already obtained above (or
                # propagate past a real completion-call failure, which
                # this finally-block would otherwise shadow).
                try:
                    del_resp = await client.delete(
                        f"{OPENWEBUI_BASE_URL}/api/v1/chats/{chat_id}", headers=headers
                    )
                    del_resp.raise_for_status()
                except Exception:
                    logger.exception(
                        ": failed to delete ephemeral chat %s; "
                        "leaving it in Bakaidah's chat list.",
                        chat_id,
                    )

            # fix: run the 4 gate ports against the raw reply.
            # Best-effort by design -- a gate-check failure (e.g. mcpo
            # unreachable) must never block delivering Bakaidah's actual
            # answer, same fail-open-on-infra-error principle the
            # originals use for their own network timeouts
            # (_path_exists returns None -> "unverifiable", not a
            # warning, on a connection failure).
            # gate 5k (2026-10-02): in FIXED VERDICT VOCABULARY
            # mode the executor computes each Verdict by the written rule
            # and overwrites the model's word; pp_footer is a visible
            # [executor] line listing every change. Fail-safe: any error
            # leaves the reply untouched.
            ledger_raw_reply = reply_text
            try:
                reply_text, _ledger_lines = bledger.split_facts(reply_text)
            except Exception:
                logger.exception(" split failed; leaving the reply whole.")
                reply_text = ledger_raw_reply
            pp_footer = ""
            try:
                reply_text, pp_footer = postprocess_reply(user_text, reply_text)
            except Exception:
                logger.exception(
                    " verdict postprocess raised; delivering Bakaidah's "
                    "reply unmodified."
                )
                pp_footer = ""

            gate_warnings = []
            try:
                banner, gate_warnings = await run_all_gates(client, user_text, reply_text)
            except Exception:
                logger.exception(
                    " gate-check port raised; delivering Bakaidah's "
                    "reply unmodified rather than blocking on it."
                )
                banner = ""

            # Stage B (2026-10-03): for a drift reply that came back
            # with real gate warnings, ask Bakaidah once to self-check its
            # table against the source. The retried reply is delivered only
            # if it has the same rows and fewer warning items; a visible
            # [executor] footer says what happened. Fail-safe: any error
            # delivers the first reply.
            sb_footer = ""
            try:
                if stage_b_should_retry(user_text, reply_text, gate_warnings):
                    sys_msgs = [m for m in messages if m.get("role") == "system"]

                    async def _ask(msg):
                        # Experiment (2026-10-03): the first live retry hung
                        # for the whole 240 s on the shared client, so the
                        # retry gets its own connection pool.
                        async with httpx.AsyncClient(
                            timeout=EXECUTOR_TIMEOUT_SECONDS
                        ) as retry_client:
                            return await ask_bakaidah(
                                retry_client, OPENWEBUI_BASE_URL,
                                OPENWEBUI_API_KEY, BAKAIDAH_MODEL,
                                tool_ids, sys_msgs, msg,
                            )

                    async def _gates(r):
                        return await run_all_gates(client, user_text, r)

                    reply_text, pp_footer, banner, sb_footer = await stage_b_retry(
                        _ask, _gates, postprocess_reply, user_text,
                        reply_text, banner, pp_footer, gate_warnings,
                    )
            except Exception:
                logger.exception(
                    " Stage B raised; delivering the first reply."
                )
                sb_footer = ""

        ledger_footer = ""
        if bledger.needs_ledger(user_text):
            async def _ledger_ask(msg):
                async with httpx.AsyncClient(timeout=EXECUTOR_TIMEOUT_SECONDS) as lc:
                    return await ask_bakaidah(
                        lc, OPENWEBUI_BASE_URL, OPENWEBUI_API_KEY, BAKAIDAH_MODEL,
                        [], [], msg,
                    )
            _unused, ledger_footer = await bledger.ledger_stage(
                user_text, ledger_raw_reply, _ledger_ask
            )
        final_text = reply_text + pp_footer + sb_footer + fallback_note + banner + ledger_footer

        await event_queue.enqueue_event(
            new_agent_text_message(final_text, context.context_id, context.task_id)
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("Bakaidah agent-server does not support cancellation")
