"""MCP compression proxy.

Sits between an agent and ONE downstream MCP server: it speaks MCP to the agent
over stdio and spawns the downstream server, forwarding every message. On the
way back it compresses the expensive parts so any agent's other MCP servers get
cheaper — universally, not just jusTokenMax's own tools:

  * tools/call results — large text content blocks routed through the right
    compressor (JSON / log / diff / generic) and redacted;
  * tools/list        — verbose tool descriptions trimmed.

Everything else passes through untouched.

Run:  justokenmax proxy -- npx -y some-mcp-server --flag

`transform_response` is a pure function so it can be unit-tested without any
subprocess plumbing.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from typing import List

# Below this a content block isn't worth routing through a compressor (but it is
# still redacted — secrets are cheap to mask and worth masking at any size).
_MIN_COMPRESS = 800


def _compress_text(text: str) -> str:
    from .redact import redact
    if len(text) < _MIN_COMPRESS:
        return redact(text)[0]
    from .diffcompress import compress_diff
    from .jsoncompress import compress_json, looks_like_json
    from .logs import compress_log
    stripped = text.lstrip()
    if looks_like_json(text):
        text = compress_json(text)[0]
    elif stripped.startswith("diff --git") or "\n@@ " in text:
        text = compress_diff(text)[0]
    elif text.count("\n") >= 30:
        text = compress_log(text)[0]
    return redact(text)[0]


def _trim_desc(desc: str, limit: int = 240) -> str:
    return desc if len(desc) <= limit else desc[:limit].rstrip() + " …"


def transform_response(msg: dict) -> dict:
    """Compress a downstream response (mutates and returns the dict)."""
    result = msg.get("result")
    if not isinstance(result, dict):
        return msg
    content = result.get("content")
    if isinstance(content, list):
        for block in content:
            if (isinstance(block, dict) and block.get("type") == "text"
                    and isinstance(block.get("text"), str)):
                block["text"] = _compress_text(block["text"])
    tools = result.get("tools")
    if isinstance(tools, list):
        for tool in tools:
            if isinstance(tool, dict) and isinstance(tool.get("description"), str):
                tool["description"] = _trim_desc(tool["description"])
    return msg


def _pump_up(agent_in, down_in) -> None:
    """agent -> downstream (requests pass through)."""
    try:
        for line in agent_in:
            down_in.write(line)
            down_in.flush()
    except (OSError, ValueError):
        return
    finally:
        try:
            down_in.close()
        except OSError:
            return


def _pump_down(down_out, agent_out) -> None:
    """downstream -> agent (responses compressed)."""
    for line in down_out:
        out = line
        stripped = line.strip()
        if stripped:
            try:
                out = json.dumps(transform_response(json.loads(stripped))) + "\n"
            except json.JSONDecodeError:
                out = line
        agent_out.write(out)
        agent_out.flush()


def run(downstream_argv: List[str]) -> int:
    if not downstream_argv:
        sys.stderr.write(
            "usage: justokenmax proxy -- <downstream-mcp-command ...>\n")
        return 2
    proc = subprocess.Popen(downstream_argv, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, text=True, bufsize=1)
    up = threading.Thread(target=_pump_up, args=(sys.stdin, proc.stdin),
                          daemon=True)
    down = threading.Thread(target=_pump_down, args=(proc.stdout, sys.stdout),
                            daemon=True)
    up.start()
    down.start()
    proc.wait()
    down.join(timeout=1)
    return proc.returncode or 0
