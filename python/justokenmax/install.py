"""Cross-agent install / uninstall.

Registers (or removes) the jusTokenMax MCP server in a coding agent's config so
the compressors are available to Codex CLI, OpenCode, Cursor, and Claude Code —
not just the Claude Code plugin. Both directions are idempotent and reversible:
install never duplicates or clobbers other servers; uninstall removes only our
entry and leaves the rest of the file intact.

JSON configs are merged with the stdlib `json`; the Codex TOML config is edited
as text (stdlib has no TOML writer) by adding/removing a single block. No
dependencies.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Tuple

SERVER = "justokenmax"
# Registered command works for anyone with Node — `npx` runs the published
# package's bin, which bootstraps Python (or uv) under the hood. So a Claude Code
# user who has Node but no Python still gets the MCP server.
_NPX_ARGS = ["-y", "@kalmantic/justokenmax", "mcp"]

# agent -> how to register it
_AGENTS = {
    "codex": {
        "path": "~/.codex/config.toml", "fmt": "toml",
    },
    "opencode": {
        "path": "~/.config/opencode/opencode.json", "fmt": "json",
        "root": "mcp",
        "entry": {"type": "local", "command": ["npx"] + _NPX_ARGS,
                  "enabled": True},
    },
    "cursor": {
        "path": "~/.cursor/mcp.json", "fmt": "json",
        "root": "mcpServers",
        "entry": {"command": "npx", "args": _NPX_ARGS},
    },
    "claude": {
        "path": "./.mcp.json", "fmt": "json",
        "root": "mcpServers",
        "entry": {"command": "npx", "args": _NPX_ARGS},
    },
    "gemini": {
        "path": "~/.gemini/settings.json", "fmt": "json",
        "root": "mcpServers",
        "entry": {"command": "npx", "args": _NPX_ARGS},
    },
    "qwen": {
        "path": "~/.qwen/settings.json", "fmt": "json",
        "root": "mcpServers",
        "entry": {"command": "npx", "args": _NPX_ARGS},
    },
    "cline": {
        "path": "~/.cline/data/settings/cline_mcp_settings.json", "fmt": "json",
        "root": "mcpServers",
        "entry": {"command": "npx", "args": _NPX_ARGS},
    },
    "kilocode": {
        # Kilo Code (v7.0.33+) uses a CLI-style config with an `mcp` key. The
        # file is `.jsonc`, so it may contain // comments and trailing commas —
        # we parse it by stripping those (see `_strip_json_comments`) and never
        # clobber an existing config we can't parse.
        "path": "~/.config/kilo/kilo.jsonc", "fmt": "json",
        "root": "mcp",
        "entry": {"type": "local", "command": ["npx"] + _NPX_ARGS},
    },
    "omp": {
        # Pi / oh-my-pi (the `omp` binary) — user-level MCP config.
        "path": "~/.omp/agent/mcp.json", "fmt": "json",
        "root": "mcpServers",
        "entry": {"command": "npx", "args": _NPX_ARGS},
    },
}
AGENTS = tuple(_AGENTS)

_TOML_BLOCK = (
    f"[mcp_servers.{SERVER}]\n"
    'command = "npx"\n'
    'args = ["-y", "@kalmantic/justokenmax", "mcp"]\n'
)


def config_path(agent: str) -> str:
    return os.path.abspath(os.path.expanduser(_AGENTS[agent]["path"]))


def detect() -> List[str]:
    """Agents that look installed on this machine (their config dir exists);
    `claude` is always included since its config is project-local."""
    found = []
    for agent in _AGENTS:
        if agent == "claude" or os.path.isdir(os.path.dirname(config_path(agent))):
            found.append(agent)
    return found


def _strip_json_comments(text: str) -> str:
    """Make JSONC parseable by stdlib `json`: drop `//` line-comments and any
    trailing commas before `}`/`]`. Walks the text tracking in-string/escape
    state so a `//` (or comma) inside a quoted value is left untouched — both the
    comment-stripping and the trailing-comma removal run inside this single state
    machine, never a blind regex over the whole text. Dependency-free."""
    out = []
    in_str = False
    esc = False
    # Index into `out` of a pending `,` emitted outside any string. It becomes a
    # *trailing* comma only if the next significant char (scanning over
    # out-of-string whitespace) is `}` or `]`; until then we keep it.
    pending_comma = -1
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            # A string opens, so any pending comma was followed by a value, not
            # a closer: it is not trailing.
            pending_comma = -1
            in_str = True
            out.append(ch)
            i += 1
            continue
        # `//` outside a string starts a comment that runs to end of line. The
        # comment is whitespace-equivalent, so a pending comma stays pending.
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == ",":
            pending_comma = len(out)
            out.append(ch)
            i += 1
            continue
        if ch in "}]" and pending_comma != -1:
            # The pending comma is trailing: drop it before emitting the closer.
            out[pending_comma] = ""
            pending_comma = -1
            out.append(ch)
            i += 1
            continue
        if not ch.isspace():
            # Any other significant char clears the pending comma.
            pending_comma = -1
        out.append(ch)
        i += 1
    return "".join(out)


# Sentinel: file exists but neither strict JSON nor JSONC parsing succeeded.
# Callers must treat this as "leave the file untouched" rather than {}.
_UNPARSEABLE = object()


def _load_json(path: str):
    """Return the parsed config dict, `{}` for a missing/fresh file, or the
    `_UNPARSEABLE` sentinel for a present file we can't parse (so callers abort
    instead of overwriting — never silently clobber a user's config)."""
    if not os.path.exists(path):
        return {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return _UNPARSEABLE
    if not text.strip():
        return {}
    try:
        return json.loads(text)
    except ValueError:
        pass
    try:
        return json.loads(_strip_json_comments(text))
    except ValueError:
        return _UNPARSEABLE


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------- #
# JSON agents
# --------------------------------------------------------------------------- #
def _json_install(agent: str, path: str, dry: bool) -> Tuple[str, bool]:
    spec = _AGENTS[agent]
    data = _load_json(path)
    if data is _UNPARSEABLE:
        # Present-but-unparseable config: refuse to write so we never destroy
        # the user's existing settings (protects every json agent, not kilocode
        # alone). The user can fix the file by hand and re-run.
        return "parse error - left untouched", False
    section = data.setdefault(spec["root"], {})
    if section.get(SERVER) == spec["entry"]:
        return "already configured", False
    existed = SERVER in section
    section[SERVER] = spec["entry"]
    if not dry:
        _write(path, json.dumps(data, indent=2) + "\n")
    return ("reconfigured" if existed else "installed"), True


def _json_uninstall(agent: str, path: str, dry: bool) -> Tuple[str, bool]:
    root = _AGENTS[agent]["root"]
    data = _load_json(path)
    if data is _UNPARSEABLE:
        return "parse error - left untouched", False
    section = data.get(root, {})
    if SERVER not in section:
        return "not present", False
    del section[SERVER]
    if not section:
        data.pop(root, None)
    if not dry:
        _write(path, json.dumps(data, indent=2) + "\n")
    return "removed", True


# --------------------------------------------------------------------------- #
# Codex TOML (text-based, no TOML writer in the stdlib)
# --------------------------------------------------------------------------- #
def _toml_install(path: str, dry: bool) -> Tuple[str, bool]:
    text = Path(path).read_text(encoding="utf-8") if os.path.exists(path) else ""
    if f"[mcp_servers.{SERVER}]" in text:
        return "already configured", False
    new = (text.rstrip() + "\n\n" + _TOML_BLOCK) if text.strip() else _TOML_BLOCK
    if not dry:
        _write(path, new)
    return "installed", True


def _toml_uninstall(path: str, dry: bool) -> Tuple[str, bool]:
    if not os.path.exists(path):
        return "not present", False
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    header = f"[mcp_servers.{SERVER}]"
    out, i, removed = [], 0, False
    while i < len(lines):
        if lines[i].strip() == header:
            removed = True
            i += 1
            while i < len(lines) and not lines[i].lstrip().startswith("["):
                i += 1
        else:
            out.append(lines[i])
            i += 1
    if not removed:
        return "not present", False
    if not dry:
        _write(path, "\n".join(out).rstrip() + "\n")
    return "removed", True


# --------------------------------------------------------------------------- #
# public
# --------------------------------------------------------------------------- #
def install(agent: str, dry_run: bool = False) -> dict:
    path = config_path(agent)
    if _AGENTS[agent]["fmt"] == "toml":
        status, changed = _toml_install(path, dry_run)
    else:
        status, changed = _json_install(agent, path, dry_run)
    return {"agent": agent, "path": path, "status": status, "changed": changed}


def uninstall(agent: str, dry_run: bool = False) -> dict:
    path = config_path(agent)
    if _AGENTS[agent]["fmt"] == "toml":
        status, changed = _toml_uninstall(path, dry_run)
    else:
        status, changed = _json_uninstall(agent, path, dry_run)
    return {"agent": agent, "path": path, "status": status, "changed": changed}
