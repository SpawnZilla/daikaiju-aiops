"""bakaidah_direct.py -- prompt-overflow fix (2026-10-10).

PROBLEM (measured 2026-10-10 in the Ollama journal): the executor's Open
WebUI path sends 30,872 tokens before the task itself (workspace system
prompt plus tool schemas). num_ctx is 24,576, so Ollama cuts every prompt
that is longer than that down to its LAST 12,291 tokens (limit = num_ctx/2+3,
keep=5), which drops the front of the system prompt and the tool schemas.
Open WebUI's own Filters never run on this path, so the 30k are
pure overhead for table tasks.

FIX: mechanical table tasks (drift and triage, recognised by the marker lines
their templates must contain) skip Open WebUI and its tools. They go straight
to Ollama's /api/chat with a short purpose-built system prompt
(bakaidah_compact_prompt.txt, about 400 tokens). Same model, same num_ctx,
same think setting. The executor's verdict/count/status post-processing, the
gates and Stage B run unchanged on the reply. If the first Ollama call fails,
the executor falls back to the Open WebUI path WITHOUT tool_ids and says so in
a visible [executor] footer.

Everything else (tasks without those markers) keeps the old path and the full
workspace prompt.

Switches (environment, all optional):
  BAKAIDAH_DIRECT=0             turn the direct path off
  BAKAIDAH_OLLAMA_URL           default http://127.0.0.1:11434
  BAKAIDAH_OLLAMA_MODEL         default gemma4-bakaidah:31b
  BAKAIDAH_NUM_CTX              default 24576 (must equal Open WebUI's value, or
                               Ollama reloads the model on every switch)
  BAKAIDAH_DIRECT_NUM_PREDICT   default 4096 (thinking tokens count too)
  BAKAIDAH_THINK                default 1 (0 = off)
  BAKAIDAH_COMPACT_PROMPT       path of the prompt file; it is re-read on every
                               call, so editing it needs no restart
  BAKAIDAH_DIRECT_CONFIG        path of the runtime config file (default
                               bakaidah_direct.json next to this file)

Runtime config (2026-10-10): bakaidah_direct.json is re-read on every call, so
these can be changed without restarting the service. Keys, all optional:
"enabled" (bool), "think" (bool), "num_predict" (int), "num_ctx" (int),
"ollama_url" (str), "model" (str). A key that is missing or has the wrong type
falls back to the environment value; a missing or unreadable file means no
overrides.
"""

import json
import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)

DIRECT_ENABLED = os.environ.get("BAKAIDAH_DIRECT", "1") != "0"
OLLAMA_URL = os.environ.get("BAKAIDAH_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("BAKAIDAH_OLLAMA_MODEL", "gemma4-bakaidah:31b")
NUM_CTX = int(os.environ.get("BAKAIDAH_NUM_CTX", "24576"))
NUM_PREDICT = int(os.environ.get("BAKAIDAH_DIRECT_NUM_PREDICT", "4096"))
THINK = os.environ.get("BAKAIDAH_THINK", "1") != "0"
PROMPT_PATH = os.environ.get(
    "BAKAIDAH_COMPACT_PROMPT",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "bakaidah_compact_prompt.txt"),
)

CONFIG_PATH = os.environ.get(
    "BAKAIDAH_DIRECT_CONFIG",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "bakaidah_direct.json"),
)


def _config():
    """Runtime overrides from bakaidah_direct.json; {} if absent or unreadable."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}
    except Exception:
        logger.exception(" direct: cannot read %s; using environment values.", CONFIG_PATH)
        return {}
    return data if isinstance(data, dict) else {}


def _setting(key, default, kind):
    """Config-file value of the given type (bool/int/str), else the default."""
    value = _config().get(key)
    if kind is bool and isinstance(value, bool):
        return value
    if kind is int and isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    if kind is str and isinstance(value, str) and value.strip():
        return value.strip()
    return default


# The same marker lines the table gates key on: FIXED VERDICT VOCABULARY marks
# a drift task; EXECUTOR-FILLED COUNTS and EXECUTOR-CHECKED STATUS are the
# mandatory marker lines of the triage template (ROUND_PROCESS.md section 2b).
_MECHANICAL_RE = re.compile(
    r"FIXED\s+VERDICT\s+VOCABULARY|EXECUTOR-FILLED\s+COUNTS|EXECUTOR-CHECKED\s+STATUS",
    re.IGNORECASE,
)


def is_mechanical_task(user_text):
    """True for drift and triage table tasks (no tools needed)."""
    return bool(_MECHANICAL_RE.search(user_text or ""))


def should_use_direct(user_text):
    return _setting("enabled", DIRECT_ENABLED, bool) and is_mechanical_task(user_text)


def load_compact_prompt():
    with open(PROMPT_PATH, "r", encoding="utf-8") as fh:
        text = fh.read().strip()
    if not text:
        raise RuntimeError("compact prompt file is empty: " + PROMPT_PATH)
    return text


def build_messages(user_text, extra_system=None):
    """One system message (the compact prompt plus any extra instruction
    texts), then the task. Gemma-style templates take a single system turn."""
    system = load_compact_prompt()
    extras = [t.strip() for t in (extra_system or []) if t and t.strip()]
    if extras:
        system = system + "\n\n" + "\n\n".join(extras)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_text},
    ]


async def ask_direct(user_text, extra_system, timeout):
    """One Ollama /api/chat call. Returns (reply_text, note); note is "" or a
    visible [executor] line. Raises when the call fails or the reply is empty."""
    messages = build_messages(user_text, extra_system)
    num_ctx = _setting("num_ctx", NUM_CTX, int)
    num_predict = _setting("num_predict", NUM_PREDICT, int)
    url = _setting("ollama_url", OLLAMA_URL, str).rstrip("/")
    body = {
        "model": _setting("model", OLLAMA_MODEL, str),
        "messages": messages,
        "stream": False,
        "think": _setting("think", THINK, bool),
        "options": {"num_ctx": num_ctx, "num_predict": num_predict},
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url + "/api/chat", json=body)
        resp.raise_for_status()
        data = resp.json()
    msg = data.get("message") or {}
    reply = (msg.get("content") or "").strip()
    prompt_tokens = int(data.get("prompt_eval_count") or 0)
    out_tokens = int(data.get("eval_count") or 0)
    reason = data.get("done_reason") or ""
    logger.info(
        " direct: prompt_tokens=%d output_tokens=%d done_reason=%s "
        "reply_chars=%d thinking_chars=%d",
        prompt_tokens, out_tokens, reason, len(reply), len(msg.get("thinking") or ""),
    )
    if not reply:
        raise RuntimeError(
            "empty reply from Ollama (done_reason=%s, output_tokens=%d)" % (reason, out_tokens)
        )
    notes = []
    if reason == "length":
        notes.append("the reply hit the %d-token limit and was cut off" % num_predict)
    # Ollama cuts an over-long prompt to num_ctx/2+3 tokens and logs it. If the
    # counted prompt sits at that cut size but the text is clearly longer, say so.
    estimated = (len(messages[0]["content"]) + len(user_text)) // 4
    if prompt_tokens and prompt_tokens <= num_ctx // 2 + 8 and estimated > int(prompt_tokens * 1.3):
        notes.append(
            "the prompt may have been truncated by Ollama (counted %d tokens, estimated about %d)"
            % (prompt_tokens, estimated)
        )
    note = ("\n\n[executor] direct path: " + "; ".join(notes) + ".") if notes else ""
    return reply, note


async def run_direct(user_text, extra_system, timeout, postprocess_fn, gates_fn,
                     stage_b_should_retry, stage_b_retry):
    """Whole direct-path pipeline; returns the text to deliver. Raises only if
    the FIRST Ollama call fails (the caller then falls back). After that every
    step is fail-safe, like the executor's own path.

    postprocess_fn(user_text, reply) -> (reply, footer)       sync
    gates_fn(client, user_text, reply) -> (banner, warnings)  async
    stage_b_should_retry(user_text, reply, warnings) -> bool
    stage_b_retry(ask, gates, postprocess, user_text, reply, banner, pp_footer,
                  warnings) -> (reply, pp_footer, banner, sb_footer)   async
    """
    reply_text, direct_note = await ask_direct(user_text, extra_system, timeout)

    pp_footer = ""
    try:
        reply_text, pp_footer = postprocess_fn(user_text, reply_text)
    except Exception:
        logger.exception(" direct: verdict postprocess raised; reply left unmodified.")
        pp_footer = ""

    banner = ""
    gate_warnings = []
    sb_footer = ""
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            banner, gate_warnings = await gates_fn(client, user_text, reply_text)
        except Exception:
            logger.exception(" direct: gate check raised; reply delivered without gates.")
            banner = ""
            gate_warnings = []
        try:
            if stage_b_should_retry(user_text, reply_text, gate_warnings):
                async def _ask(msg):
                    text, _note = await ask_direct(msg, extra_system, timeout)
                    return text

                async def _gates(reply):
                    return await gates_fn(client, user_text, reply)

                reply_text, pp_footer, banner, sb_footer = await stage_b_retry(
                    _ask, _gates, postprocess_fn, user_text,
                    reply_text, banner, pp_footer, gate_warnings,
                )
        except Exception:
            logger.exception(" direct: Stage B raised; delivering the first reply.")
            sb_footer = ""

    return reply_text + pp_footer + sb_footer + direct_note + banner
