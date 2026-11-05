"""
kaiju_mokaima_a2a_adapter.py -- brief section 8.2's "Mokaima adapter":
"MCP tool letting Mokaima emit A2A task objects to Bakaidah directly, receive
Bakaidah's output, run verification (section 6), and either hold for
check-in or release per checkpoint state."

Written 2026-08-27 (Daikaiju AIOps/ part 7 continuation 3),
built with the operator's explicit go-ahead to build (not yet wire/deploy) the
Mokaima MCP server. Uses the mcp Python SDK's FastMCP, pinned to mcp==1.28.1
-- the EXACT version already proven live in this project's own git MCP
server (/srv/data), confirmed by direct inspection of
its dist-info rather than assumed, per build-from-existing + the standing
NO-ASSUMPTION RULE. mcp 2.x renamed FastMCP to MCPServer and changed other
APIs -- same class of breaking-version trap as's a2a-sdk<1.0 issue,
avoided here by matching the sibling server's own known-good pin instead
of guessing.

VERIFICATION, three layers, all passing (test_server_integration.py,
test_stdio_subprocess.py, both also deployed alongside this file):
  - Unit level: inherits the 27 tests already passing on the 4 modules
    this server wraps (schema, hard-stop filter, persistence, step5
    review).
  - Real MCP protocol level (5/5 pass): actual mcp.ClientSession calls
    against an in-process server transport -- exercises real JSON-RPC
    tool-call routing and schema validation, not direct Python calls.
  - Real stdio subprocess level (3/3 pass): the server spawned as an
    actual subprocess over stdio and driven via mcp.client.stdio --
    the EXACT mechanism claude_desktop_config.json's command/args
    launches every MCP server with. This is the closest verification
    available without registering it in the live config and
    restarting Claude Desktop.
call_gateway_tool is NOT exercised by any of the above -- see tool 4
below for why, and what would need to happen for it to be.

FOUR TOOLS EXPOSED:

  1. review_bakaidah_output -- wraps kaiju_mokaima_step5_review.review().
     Fully real, fully logic-tested (inherits the 5 tests already passing
     on that module). Loads/saves checkpoint state via VAULT
     Health/a2a_checkpoint_state.json on every call, so the graduation
     state machine is genuinely persistent across separate tool calls,
     not just within one Python process's lifetime.

     UPDATE 2026-08-30 follow-up, "Mokaima help 1.0"): gained an
     optional gateway_task_id parameter that, when provided and
     section6_warnings is not explicitly given, auto-fetches that task's
     real reply via the gateway's own get_task_result and parses out the
     "---\nwarning: ..."/"note: ..." banner bakaidah_executor.py's
     gate-check port now genuinely appends -- see parse_filter_warnings()
     and _gateway_call() below. Before this, section6_warnings had never
     once been populated for any real call's own origin finding);
     this closes that gap for callers willing to pass the gateway task_id
     instead of hand-copying warning text. Explicit section6_warnings
     still always takes priority when provided -- this is additive, not a
     replacement for manual review.

  2. get_checkpoint_state -- read-only view of current checkpoint state.

  3. create_a2a_task -- wraps kaiju_a2a_task_schema.new_task(), stamping
     the CURRENT persisted checkpoint state onto a new task object per
     brief section 8.3.

  4. call_gateway_tool -- a GENERIC pass-through to the real, already-
     deployed mcp-a2a-gateway (register_agent/send_message/get_task_
     result/unregister_agent/list_agents/get_task_list), connecting via
     the official MCP streamable_http client rather than hand-rolled
     JSON-RPC. Deliberately generic (tool_name + arguments dict) rather
     than one wrapper function per gateway tool: Mokaima never captured
     each gateway tool's exact parameter schema beyond its name (MCP
     Inspector showed the tools were "correctly schemed" but the actual
     schemas were never recorded to VAULT) -- writing named wrapper
     functions with guessed parameter names would violate the standing
     NO-ASSUMPTION RULE. This passthrough needs no such guess: it uses
     the SDK's own list_tools()/call_tool() machinery, which discovers
     the real schema from the gateway itself at call time.
     CONFIRMED LIVE 2026-08-30 session): this tool genuinely
     reaches the real gateway -- exercised repeatedly this session for
     both's own live tests and the gateway-timeout root-cause
     work. The "GENUINELY UNTESTED" note from this tool's original build
     no longer applies; kept below only as an accurate build-time record.
     Its own connection logic is now factored into _gateway_call() below,
     shared with review_bakaidah_output's new auto-fetch path -- one
     source of truth for how this server talks to the gateway, not two.
     ORIGINAL BUILD-TIME NOTE (2026-08-27, accurate as of that date only):
     Mokaima's sandbox had no network path to intake-host's LAN (192.0.2.45),
     only outbound access to a fixed public-package allowlist -- this
     tool was built correctly per the SDK's documented API but was, at
     build time, the very first real test of it once deployed on a host
     that could actually reach the gateway.

NOT YET DONE, deliberately out of scope for this build: registering this
server in Mokaima's own claude_desktop_config.json and restarting Claude
Desktop. Restarting Claude Desktop would end the current chat session
outright -- that action needs to happen in a moment the operator chooses, not
bundled into a build turn. See the deployment guide for the concrete
remaining steps.

STANDING GOTCHA, confirmed 2026-08-29 part 9) and still true for
THIS edit: editing this file's source on disk has NO effect on the
already-running Mokaima MCP subprocess -- same class as the GUI-session-
reboot gotcha. A Claude Desktop restart is required before this change
takes effect, and the only reliable way to confirm it actually took is an
independent disk read plus a live call showing the new behavior (a new
field's presence, not just an unchanged-looking success) -- never trust a
call's own return value alone to prove new code ran.
"""

import json
import os
import subprocess
import sys
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP

from kaiju_a2a_task_schema import (
    CheckpointState, load_checkpoint_state, save_checkpoint_state, new_task,
    KaijuA2ATask, record_governance_verdicts,
)
from hard_stop_credentials_installpath_filter import ExecutionContract
from kaiju_mokaima_step5_review import review as step5_review


VAULT_ROOT = os.environ.get("KAIJU_VAULT_ROOT", "/srv/vault")

# GOVERNANCE STATE OFF VAULT (2026-09-26, Full Auto part 13, Layer C
# prerequisite P2): VAULT is exFAT mounted gid=homelab with no per-file
# permissions, and angu is in homelab -- Angkai could write
# Health/a2a_checkpoint_state.json (e.g. set itself fully_autonomous) or the
# activity log. Checkpoint state + activity log now live on ext4 under
# /srv/governance/Health/ (svcuser:svcuser 0755, files 0644, angu
# write verified DENIED). Same relative "Health/..." paths, different root.
# VAULT_ROOT is still used for everything that is genuinely VAULT content.
GOVERNANCE_ROOT = os.environ.get("KAIJU_GOVERNANCE_ROOT", "/srv/governance")
# SEPARATE TOOL LADDER (2026-10-14,: tool-using Bakaidah tasks (read-only
# file reads) get their OWN checkpoint ladder, so their results never move the
# table-triage ladder (default) and the reverse. Same state machine, same file
# names, different root: <GOVERNANCE_ROOT>/tool_ladder/Health/. The Broker reads
# only the default checkpoint file, so this ladder cannot promote anything on
# its own. Callers choose it with ladder="tool"; "default" is unchanged.
TOOL_LADDER_ROOT = os.path.join(GOVERNANCE_ROOT, "tool_ladder")


def _ladder_root(ladder: str):
    """Returns the state root for a ladder name, or None if the name is unknown."""
    if ladder == "default":
        return GOVERNANCE_ROOT
    if ladder == "tool":
        return TOOL_LADDER_ROOT
    return None


# GATEWAY_URL FIX (2026-08-27, part 7 continuation 5): first live
# call_gateway_tool test failed with an opaque anyio TaskGroup error --
# root cause found via kajazilla7.txt's own Phase 3 entry,
# which documents the gateway as listening on 192.0.2.45:<port>
# "streamable-http, /mcp path" -- this default was missing the /mcp
# suffix entirely. Matches FastMCP's own default streamable-HTTP mount
# path convention, so this isn't a one-off quirk of this gateway.
GATEWAY_URL = os.environ.get("KAIJU_GATEWAY_URL", "http://192.0.2.45:<port>/mcp")

#: the canonical single write-path for releasing a task to
# Angkai (see release_task.sh's own header comment for why it exists
# -- incident/#054's stale-manifest-pair bug). Path fixed, not
# configurable, since this is a specific known script on this specific
# host, not a general external dependency.
RELEASE_TASK_SCRIPT = "/srv/angkai/hooks/release_task.sh"

mcp = FastMCP("kaiju-mokaima-a2a-adapter")


async def _gateway_call(tool_name: str, arguments: Optional[dict] = None) -> dict:
    """ follow-up (2026-08-30): the real MCP streamable_http
    connection logic to mcp-a2a-gateway, factored out of call_gateway_tool
    (below) so review_bakaidah_output's new gateway_task_id auto-fetch path
    can reuse the exact same, already-proven-live connection code rather
    than a second hand-maintained copy -- same "one source of truth"
    discipline this project applied to's own Filter port, now
    applied here too, inside this same file, before it became a second
    real drift risk.
    """
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(GATEWAY_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments or {})
            return {
                "isError": getattr(result, "isError", False),
                "content": [
                    getattr(block, "text", str(block)) for block in result.content
                ],
            }


def parse_filter_warnings(reply_text: str) -> List[str]:
    """ follow-up (2026-08-30): parses the "---\nwarning: ..."/
    "note: ..." banner bakaidah_filter_check.py's run_all_gates() appends
    onto a raw Bakaidah reply (via bakaidah_executor.py, live since into a flat list of warning strings -- the exact shape
    review_bakaidah_output's own section6_warnings parameter already
    expects and has always expected, per its original docstring.

    Each real warning entry starts with a bare "warning:" or "note:"
    prefix at the start of a line -- the real Filters' own convention,
    faithfully carried over by the port. A entry can legitimately
    span multiple lines (bakaidah_citation_grounding_filter's port
    appends one quoted-source line per fabricated citation under a
    single leading "warning:" line) -- those continuation lines are
    folded into the SAME warning string, not split into separate list
    entries, by only starting a new entry when a line itself begins with
    one of the two prefixes.

    Returns [] if no "---\n" banner marker is present at all -- a clean
    response with nothing to flag, or non-Bakaidah text (a pending/error
    placeholder message from the gateway, which contains no such marker
    either) -- both correctly produce an empty list, not a guess.
    """
    marker = "\n\n---\n"
    idx = reply_text.find(marker)
    if idx == -1:
        return []
    banner_body = reply_text[idx + len(marker):]
    warnings: List[str] = []
    for line in banner_body.split("\n"):
        if line.startswith("warning:") or line.startswith("note:"):
            warnings.append(line)
        elif warnings:
            warnings[-1] = warnings[-1] + "\n" + line
    return [w for w in warnings if w.strip()]


def _attempt_auto_release(task_id: str, target_agent: str, payload_ref: str,
                           max_tool_calls: int) -> dict:
    """: calls release_task.sh so a genuinely graduated, clean
    review can hand a task to Angkai without a manual release step.
    Never raises -- a bug or failure here can only fail to release
    (task_released.json never gets written, and Angkai's existing
    PreToolUse hook fail-closes by default), never silently grant
    access it shouldn't. Every outcome (attempted, success, output/
    error) is returned rather than swallowed, so a caller can always
    tell whether the release actually happened.
    """
    try:
        proc = subprocess.run(
            [RELEASE_TASK_SCRIPT, task_id, target_agent, payload_ref, str(max_tool_calls)],
            capture_output=True, text=True, timeout=10,
        )
        return {
            "attempted": True,
            "success": proc.returncode == 0,
            "output": (proc.stdout or "") + (proc.stderr or ""),
        }
    except Exception as e:
        return {"attempted": True, "success": False, "error": str(e)}


@mcp.tool()
def get_checkpoint_state(ladder: str = "default") -> dict:
    """
    Return the current, persisted section 7 checkpoint/graduation
    state (checkpoint_state, clean_run_count, graduated_run_count), read
    fresh from VAULT Health/a2a_checkpoint_state.json. Read-only -- does
    not modify state.

    `ladder` (NEW 2026-10-14): "default" (table triage, unchanged) or "tool"
    (the separate tool-task ladder). Any other value returns an error and
    touches nothing. Non-default ladders add a "ladder" key to the result.
    """
    root = _ladder_root(ladder)
    if root is None:
        return {"error": "unknown ladder %r; use 'default' or 'tool'" % ladder}
    state = load_checkpoint_state(root).to_dict()
    if ladder != "default":
        state["ladder"] = ladder
    return state


@mcp.tool()
async def review_bakaidah_output(
    target_path: str,
    command_type: str,
    command: str,
    justification: str = "",
    evidence_references: Optional[list] = None,
    section6_warnings: Optional[list] = None,
    gateway_task_id: Optional[str] = None,
    task_id: Optional[str] = None,
    target_agent: Optional[str] = None,
    payload_ref: Optional[str] = None,
    max_tool_calls: Optional[int] = None,
    confirm_auto_release: bool = False,
    stage_errored: bool = False,
    task_json: Optional[dict] = None,
    manual_review_findings: Optional[List[str]] = None,
    ladder: str = "default",
) -> dict:
    """ brief section 4's Step 5 review, run for real: evaluates one
    Bakaidah-proposed action (as a structured execution contract, section
    12.1) against the section 6.1 hard-stop filter and the section 7
    checkpoint graduation state machine, persisting the resulting state
    transition back to VAULT before returning.

    `section6_warnings` should carry the ALREADY-FIRED results of
    Bakaidah's live filters. As of (2026-08-30), this tool can
    fetch and parse those itself -- see `gateway_task_id` below -- so
    passing this explicitly is now optional rather than the only path.

    `manual_review_findings` (optional, NEW 2026-09-30,
    follow-up/ tooling gap): a list of finding strings from
    MOKAIMA'S OWN independent line-by-line check of a Bakaidah reply
    against its source material -- distinct from `section6_warnings`,
    which is exclusively for Bakaidah's own live filter output. Before
    this parameter existed, a manual finding had no way to affect
    is_clean_run or the checkpoint ladder at all: it could only be
    written into `justification` for the audit record, while the actual
    governance math ran as if nothing had been found. Found live
    2026-09-30 re-climb task 2/9): a real cross-date value
    misattribution passed as a clean run because no existing filter was
    built to catch that specific defect shape. Pass real findings here
    whenever your own check of Bakaidah's reply against its source turns
    up something no filter flagged -- each entry gets exactly the same
    non-clean, ladder-resetting consequence a section6 warning has, and
    is tagged in governance_checks as filter_name="mokaima_manual_review"
    (never conflated with "section6_existing_filter") so the audit trail
    always shows whether Bakaidah's own filters or your own check caught
    a given defect. Do not use this for a call that simply failed
    outright -- that is `stage_errored`, a different concept.

    `gateway_task_id` (optional, NEW 2026-08-30, follow-up):
    when provided and `section6_warnings` is NOT explicitly given, this
    tool calls the real mcp-a2a-gateway's own get_task_result itself
    (same connection call_gateway_tool uses, via the shared _gateway_
    call() helper) to fetch that task's real stored reply, then parses
    any "---\nwarning: ..."/"note: ..." banner it carries into
    section6_warnings automatically via parse_filter_warnings() --
    genuinely populated now that bakaidah_executor.py runs the
    gate-check port against every raw Bakaidah reply, where before this
    parameter existed section6_warnings had never once been populated
    for any real call. FAILS SAFE: if the gateway call errors for any
    reason (unreachable, task not found, task still pending, malformed
    response), the exception is caught and section6_warnings falls back
    to whatever was explicitly passed (or [] if nothing was) -- a fetch
    failure here must never block a real review from completing, and
    never raises past this point. Explicit `section6_warnings`, when
    provided, ALWAYS takes priority and skips this auto-fetch entirely
    -- this is additive to manual review, not a replacement for it.

    `task_id` (optional) is threaded through to section 10's activity
    log so a logged entry can be tied back to a real A2A task object
    (create_a2a_task's task_id) -- omit it for ad hoc/manual reviews
    not tied to a task. Distinct from `gateway_task_id` above: this one
    is the create_a2a_task task_id used for logging, that one is the
    real mcp-a2a-gateway task_id used to fetch a stored reply -- they
    are often the same value for a real automated call, but the
    parameters serve different purposes and are not interchangeable.

    `stage_errored` (default False): pass True when the CALL to Bakaidah
    itself failed outright (backend timeout, unreachable, malformed
    response) rather than Bakaidah producing a real but flawed output.
    Per checkpoint_gate.should_checkpoint(), this always forces a
    mandatory checkpoint AND counts as a non-clean run -- it resets
    checkpoint_state/clean_run_count to stage_0/0, same as any other
    non-clean run. Use this to correctly log/count real infra failures
    (e.g. the gateway-dispatch timeouts seen 2026-08-29, now fixed as
    of 2026-08-30 -- see AIOPS_PENDING.md update) instead of
    silently treating them as ordinary clean runs, which is what every
    prior call to this tool did before this parameter existed. auto-release: when the review clears as route=='release_to_
    angkai', this does NOT automatically call release_task.sh just
    because checkpoint_state has reached graduated_window. The caller
    must ALSO pass confirm_auto_release=True, plus target_agent/
    payload_ref/max_tool_calls -- an explicit, deliberate extra gate
    beyond what section 7 itself requires, per the operator's decision
    (2026-08-29) that graduation state alone should never be
    sufficient to trigger a real release. Omit confirm_auto_release
    (or leave any of the three release fields unset) to get the
    review's verdict without any release attempt -- the safe default.

    Returns route ("release_to_angkai" | "hold_for_checkin" |
    "escalate_to_operator"), the governance_checks verdicts, the checkpoint
    transition description, any blocking/hold reasons, an auto_release
    field (None if not applicable/not confirmed, otherwise {attempted,
    success, output/error} from release_task.sh -- see
    _attempt_auto_release's docstring; failures are surfaced, never
    swallowed), a task field, and a NEW warnings_source field ("explicit"
    | "gateway_auto_fetch" | "none") so a caller can always tell where
    section6_warnings actually came from, not just what it contains.
    Every call now also appends one entry to Health/A2A_Activity_Log.jsonl
    (best-effort -- see append_activity_log's docstring in
    kaiju_mokaima_step5_review.py).

    `task_json` (optional): pass the exact dict create_a2a_task returned
    for this task. When provided, this reconstructs the real KaijuA2ATask
    object and calls kaiju_a2a_task_schema.record_governance_verdicts()
    on it for real (previously an unused import -- governance_checks
    were computed and logged, but never attached to a task object per
    section 12.4's own schema). Returns the enriched task (with
    governance_checks now populated) under the `task` key. This tool
    does NOT persist task objects itself -- create_a2a_task never has
    either -- so the caller is responsible for carrying the returned
    `task` forward if continuity across calls matters. Omit task_json
    to skip this entirely (task will be None in the response, same as
    every call before this parameter existed). A malformed task_json
    never breaks the real review result -- reconstruction failure is
    caught and reported under task.error instead of raising.
    """
    # `ladder` (NEW 2026-10-14): "default" = table-triage ladder (unchanged);
    # "tool" = the separate tool-task ladder. An unknown name returns an
    # error BEFORE any state is read or written.
    ladder_root = _ladder_root(ladder)
    if ladder_root is None:
        return {"error": "unknown ladder %r; use 'default' or 'tool'" % ladder}
    effective_warnings = section6_warnings
    warnings_source = "none"
    if section6_warnings:
        warnings_source = "explicit"
    elif gateway_task_id:
        try:
            gw_result = await _gateway_call(
                "get_task_result", {"task_id": gateway_task_id}
            )
            if not gw_result.get("isError"):
                raw = (gw_result.get("content") or [""])[0]
                task_obj = json.loads(raw)
                reply_text = (task_obj.get("result") or {}).get("message", "") or ""
                fetched = parse_filter_warnings(reply_text)
                effective_warnings = fetched
                warnings_source = "gateway_auto_fetch"
        except Exception:
            # Fetch failure must never block a real review -- fall back
            # to whatever was explicitly passed (already None/[] here
            # since this branch only runs when section6_warnings was
            # falsy to begin with), same fail-open principle's
            # own gate-check port uses in bakaidah_executor.py.
            effective_warnings = section6_warnings
            warnings_source = "none"

    if manual_review_findings:
        warnings_source = warnings_source + "+manual_review"

    contract = ExecutionContract(
        target_path=target_path,
        command_type=command_type,
        command=command,
        justification=justification,
        evidence_references=evidence_references or [],
    )
    checkpoint = load_checkpoint_state(ladder_root)
    result = step5_review(
        contract, effective_warnings or [], checkpoint,
        stage_errored=stage_errored,
        task_id=task_id, vault_root=ladder_root,
        manual_review_findings=manual_review_findings,
    )
    save_checkpoint_state(ladder_root, checkpoint)

    auto_release = None
    if result.route == "release_to_angkai":
        if confirm_auto_release and task_id and target_agent and payload_ref and max_tool_calls:
            auto_release = _attempt_auto_release(task_id, target_agent, payload_ref, max_tool_calls)
        elif confirm_auto_release:
            auto_release = {
                "attempted": False,
                "reason": "confirm_auto_release was set but task_id/target_agent/payload_ref/max_tool_calls were not all provided",
            }
        else:
            auto_release = {
                "attempted": False,
                "reason": "route is release_to_angkai but confirm_auto_release was not set -- explicit opt-in required, graduation state alone is not sufficient",
            }

    task_with_governance = None
    if task_json is not None:
        try:
            task_obj = KaijuA2ATask(**task_json)
            record_governance_verdicts(task_obj, result.governance_checks)
            task_with_governance = json.loads(task_obj.to_json())
        except Exception as e:
            task_with_governance = {"error": f"could not attach governance_checks to task_json: {e}"}

    response = {
        "route": result.route,
        "is_clean_run": result.is_clean_run,
        "checkpoint_transition": result.checkpoint_transition,
        "checkpoint_state_after": checkpoint.to_dict(),
        "reasons": result.reasons,
        "governance_checks": [
            {"filter_name": v.filter_name, "passed": v.passed, "detail": v.detail}
            for v in result.governance_checks
        ],
        "auto_release": auto_release,
        "task": task_with_governance,
        "warnings_source": warnings_source,
    }
    if ladder != "default":
        response["ladder"] = ladder
    return response


@mcp.tool()
def create_a2a_task(
    origin_agent: str,
    target_agent: str,
    task_type: str,
    payload_ref: str,
    priority: str = "normal",
    max_tool_calls: Optional[int] = None,
) -> dict:
    """
    Build a new section 8.3 task object, stamped with the CURRENT
    persisted checkpoint state. Does NOT submit it to the gateway --
    pair with call_gateway_tool("send_message", ...) once that tool's
    real argument shape is confirmed live, or construct the gateway
    call payload around this task object's fields directly.
    """
    checkpoint = load_checkpoint_state(GOVERNANCE_ROOT)
    task = new_task(
        origin_agent=origin_agent,
        target_agent=target_agent,
        task_type=task_type,
        payload_ref=payload_ref,
        checkpoint=checkpoint,
        priority=priority,
        max_tool_calls=max_tool_calls,
    )
    return json.loads(task.to_json())


@mcp.tool()
async def call_gateway_tool(tool_name: str, arguments: Optional[dict] = None) -> dict:
    """
    Generic pass-through to the real mcp-a2a-gateway (register_agent,
    list_agents, unregister_agent, send_message, get_task_result,
    get_task_list), connecting via the official MCP streamable_http
    client to KAIJU_GATEWAY_URL (default http://192.0.2.45:<port>).

    CONFIRMED LIVE 2026-08-30 session) -- genuinely reaches the
    real gateway, exercised repeatedly this session. Connection logic now
    lives in the shared _gateway_call() helper (above), reused by
    review_bakaidah_output's own gateway_task_id auto-fetch path -- this
    function is now a thin wrapper over that shared helper, not a second
    copy of the connection code.

    Pass arguments exactly as the gateway's own tool schema expects --
    call with no `arguments` and an unknown tool_name first if you need
    to discover the real schema (this function returns the gateway's
    error response verbatim rather than swallowing it).
    """
    return await _gateway_call(tool_name, arguments)


if __name__ == "__main__":
    mcp.run()
