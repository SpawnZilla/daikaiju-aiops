#!/usr/bin/env python3
"""
production_matcher.py -- shared production-signature matcher (,
2026-09-19). Stdlib only. Built to be REUSED by 's future snapshot
hook (the operator's decision 2026-09-19: the snapshot gate stays a separate
sibling hook, but both share this matcher and production_signatures.conf).

It does two jobs:
  1. NORMALIZE one PreToolUse tool call (Bash, Write/Edit, any mcp write-ish
     tool) into candidate targets: relative paths resolved against the
     call's cwd, symlinks and '..' resolved (os.path.realpath), '~' expanded.
     This is the fix for 's relative-path blind spot.
  2. MATCH the targets against production_signatures.conf.

CONFIG LINES ('#' comments and blank lines allowed):
  path|/abs/path|label       production file or dir. The path itself and
                             everything under it match; boundary aware
                             (/a/b does not match /a/bc or /a/b-sandbox).
  unit|name.service|label    systemd unit as a whole word.
  port|10000|label          TCP port, only in port-shaped context
                             (:PORT, port PORT, port=PORT, -p PORT).
  denypath|/abs/path|label   ALWAYS blocked, no proof can unlock it.
  option|block_unverifiable|yes|no
                             yes = also gate a mutating Bash command that
                             uses $VAR / backtick expansion we cannot
                             resolve. Default no (logged only).

BASH RULES: a single simple read-only command (ls, cat, grep, find without
-exec/-delete, systemctl status, docker ps, ...) is never gated. Anything
else is treated as mutating and is matched. Write tools are always matched
by their target path.
"""

import os
import re
import shlex


class ConfigError(Exception):
    pass


_WRITE_EXACT = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
_MCP_WRITEISH = re.compile(r"^mcp__.*(write|create|edit|move|delete|rename|remove|append)", re.I)
_PATH_KEYS = ("file_path", "path", "notebook_path", "source", "destination", "dest", "target")
_META = re.compile(r"[;&|`<>\n]|\$\(")
_RO_VERBS = {
    "ls", "cat", "head", "tail", "grep", "egrep", "fgrep", "stat", "wc", "file", "diff",
    "pwd", "journalctl", "date", "id", "df", "du", "readlink", "realpath", "basename",
    "dirname", "sha256sum", "md5sum", "which", "whoami", "hostname", "uname",
}
_FIND_MUTATORS = {"-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0", "-fprintf", "-fls"}
_SYSTEMCTL_RO = {"status", "is-active", "is-enabled", "is-failed", "show", "cat",
                 "list-units", "list-unit-files", "list-timers"}
_DOCKER_RO = {"ps", "logs", "inspect", "images", "version", "info", "top", "stats"}
_GIT_RO = {"status", "log", "diff", "show", "rev-parse"}


def load_signatures(conf_path):
    """Returns (signatures, options). Raises ConfigError on anything odd so
    the gate can fail closed instead of guessing."""
    try:
        with open(conf_path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        raise ConfigError("cannot read %s: %s" % (conf_path, exc))
    sigs = []
    options = {"block_unverifiable": False}
    for num, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        kind = parts[0].lower()
        if kind == "option":
            if len(parts) != 3 or parts[1] != "block_unverifiable" or parts[2].lower() not in ("yes", "no"):
                raise ConfigError("line %d: bad option line: %r" % (num, line))
            options["block_unverifiable"] = parts[2].lower() == "yes"
            continue
        if kind not in ("path", "unit", "port", "denypath") or len(parts) < 3 or not parts[1] or not parts[2]:
            raise ConfigError("line %d: bad signature line: %r" % (num, line))
        if kind in ("path", "denypath") and not parts[1].startswith("/"):
            raise ConfigError("line %d: %s needs an absolute path: %r" % (num, kind, line))
        if kind == "port" and not parts[1].isdigit():
            raise ConfigError("line %d: port must be a number: %r" % (num, line))
        sigs.append({"kind": kind, "value": parts[1], "label": parts[2]})
    if not sigs:
        raise ConfigError("%s holds no signatures" % conf_path)
    return sigs, options


def tool_kind(tool_name):
    name = tool_name or ""
    if name == "Bash":
        return "bash"
    if name in _WRITE_EXACT or _MCP_WRITEISH.match(name):
        return "write"
    return "other"


def resolve_path(path, cwd):
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        path = os.path.join(cwd, path)
    return os.path.realpath(path)


def _under(path, root):
    root = root.rstrip("/") or "/"
    return path == root or path.startswith(root + "/")


def _first_arg(tokens):
    for tok in tokens[1:]:
        if not tok.startswith("-"):
            return tok
    return ""


def is_read_only(command):
    """True only for ONE simple read-only command (no ; & | ` < > or $( )."""
    if _META.search(command):
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if not tokens:
        return True
    verb = os.path.basename(tokens[0])
    if verb in _RO_VERBS:
        return True
    if verb == "find":
        return not any(t in _FIND_MUTATORS for t in tokens)
    if verb == "systemctl":
        return _first_arg(tokens) in _SYSTEMCTL_RO
    if verb == "docker":
        return _first_arg(tokens) in _DOCKER_RO
    if verb == "git":
        return _first_arg(tokens) in _GIT_RO
    return False


def _bash_candidates(command, cwd):
    """Resolved candidate paths from every token + whether any token used an
    expansion we cannot resolve ($VAR, backtick)."""
    cands = set()
    unresolved = False
    for segment in re.split(r"&&|\|\||[;|&\n]", command):
        try:
            tokens = shlex.split(segment)
        except ValueError:
            tokens = segment.split()
        for tok in tokens:
            if "$" in tok or "`" in tok:
                unresolved = True
            tok = re.sub(r"^[0-9]*[<>]+", "", tok)
            if tok.startswith("-"):
                if "=" not in tok:
                    continue
                tok = tok.split("=", 1)[1]
            else:
                name, sep, val = tok.partition("=")
                if sep and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
                    tok = val
            if not tok or "$" in tok or "`" in tok:
                continue
            cands.add(resolve_path(tok, cwd))
    return cands, unresolved


def _raw_path_hit(command, sig_path):
    return re.search(re.escape(sig_path) + r"(?![A-Za-z0-9_.-])", command) is not None


def _unit_hit(command, unit):
    pattern = r"(?<![A-Za-z0-9_.-])" + re.escape(unit) + r"(?![A-Za-z0-9_-])"
    return re.search(pattern, command) is not None


def _port_hit(command, port):
    return re.search(r"(?:[:=]|\bport\s|--port\s|-p\s)" + re.escape(port) + r"(?![0-9])", command) is not None


def match_tool_call(tool_call, sigs, options, default_cwd):
    """Returns {kind, gated, deny, labels, unverifiable, read_only}."""
    tool = tool_call.get("tool_name") or ""
    tool_input = tool_call.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}
    cwd = tool_call.get("cwd") or default_cwd
    kind = tool_kind(tool)
    result = {"kind": kind, "gated": False, "deny": False, "labels": [],
              "unverifiable": False, "read_only": False}
    if kind == "other":
        return result

    command = ""
    if kind == "write":
        cands = {resolve_path(v, cwd) for k in _PATH_KEYS
                 for v in [tool_input.get(k)] if isinstance(v, str) and v}
    else:
        command = tool_input.get("command")
        command = command if isinstance(command, str) else ""
        if is_read_only(command):
            result["read_only"] = True
            return result
        cands, result["unverifiable"] = _bash_candidates(command, cwd)

    labels = []
    for sig in sigs:
        hit = False
        if sig["kind"] in ("path", "denypath"):
            roots = {sig["value"], os.path.realpath(sig["value"])}
            hit = any(_under(c, r) for c in cands for r in roots)
            if not hit and kind == "bash":
                hit = _raw_path_hit(command, sig["value"])
        elif kind == "bash" and sig["kind"] == "unit":
            hit = _unit_hit(command, sig["value"])
        elif kind == "bash" and sig["kind"] == "port":
            hit = _port_hit(command, sig["value"])
        if hit:
            labels.append(sig["label"])
            if sig["kind"] == "denypath":
                result["deny"] = True
    if (kind == "bash" and result["unverifiable"] and options.get("block_unverifiable")
            and not labels):
        labels.append("UNVERIFIABLE shell expansion in a mutating command")
    result["labels"] = labels
    result["gated"] = bool(labels)
    return result
