"""Minimal MCP server exposing jusTokenMax to any MCP-capable agent.

This makes the compressors provider-agnostic: not just Claude Code, but any
client that speaks the Model Context Protocol can call them. It implements the
MCP stdio transport (newline-delimited JSON-RPC 2.0) by hand with only the
standard library — no SDK dependency.

Run:  python -m justokenmax.mcp_server      (or point an MCP client's command at it)

The request handling lives in `handle_request`, a pure function, so it can be
unit-tested without any stdio plumbing.
"""

from __future__ import annotations

import json
import os
import sys

# Allow running as a bare script (MCP clients invoke by path).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from justokenmax import __version__  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "justokenmax_optimize",
        "description": "Optimize a file by path (PDF->Markdown, image/log/JSON "
                       "compression). Returns the optimized artifact path and "
                       "token savings.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "justokenmax_compress_json",
        "description": "Compress a JSON string (elide long arrays/strings, "
                       "minify) and return the compact form.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "justokenmax_compress_log",
        "description": "Compress verbose log text into a digest (strip ANSI, "
                       "collapse repeats, fold stack traces, keep errors).",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "justokenmax_compress_diff",
        "description": "Compress a git diff: keep real code hunks, collapse "
                       "lockfile/generated/minified file diffs to one-line "
                       "summaries.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "justokenmax_query",
        "description": "Look up a code symbol in the index -> file:line + "
                       "signature. Build the index first with justokenmax index.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "term": {"type": "string"},
                "root": {"type": "string"},
                "kind": {"type": "string"},
            },
            "required": ["term"],
        },
    },
    {
        "name": "justokenmax_delta",
        "description": "Return only what changed in a file since the last read "
                       "(unified diff). First read returns the full file.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "justokenmax_redact",
        "description": "Strip base64 blobs/data-URIs and mask secrets in text.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "justokenmax_outline",
        "description": "Return a source file's shape — every function/class/"
                       "method with its signature, line number, and docstring, "
                       "no bodies. Far cheaper than reading the whole file.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "justokenmax_retrieve",
        "description": "Given an optimized artifact path, return the original "
                       "file it was produced from (reverses compression).",
        "inputSchema": {
            "type": "object",
            "properties": {"artifact": {"type": "string"}},
            "required": ["artifact"],
        },
    },
    {
        "name": "justokenmax_unmask",
        "description": "Audited reversible redaction: recover the original "
                       "secrets in a masked digest using its stored map "
                       "(opt-in; requires the digest to have been written with "
                       "audited-reversible redaction). Every unmask is recorded "
                       "to the redaction audit log.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string",
                        "description": "cache key the redaction map is stored under"},
                "text": {"type": "string",
                         "description": "the masked digest text to restore"},
                "actor": {"type": "string",
                          "description": "who is performing the unmask (audited)"},
            },
            "required": ["key", "text"],
        },
    },
    {
        "name": "justokenmax_stats",
        "description": "Lifetime token-savings ledger.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "justokenmax_discover",
        "description": "Survey Claude Code history for recoverable tokens: which "
                       "already-read files jusTokenMax could have compressed, "
                       "bucketed by kind/path, plus the most frequent unsupported "
                       "extensions (the compressor backlog).",
        "inputSchema": {
            "type": "object",
            "properties": {"root": {"type": "string"}},
        },
    },
]


def _tool_optimize(args):
    from justokenmax import optimize
    r = optimize(args["path"])
    return json.dumps(r.to_dict())


def _tool_outline(args):
    from justokenmax.outline import file_outline
    text, st = file_outline(args["path"])
    return text if st.get("ok") else f"outline unavailable: {st.get('note')}"


def _tool_compress_json(args):
    from justokenmax.jsoncompress import compress_json
    digest, _ = compress_json(args["text"])
    return digest


def _tool_compress_log(args):
    from justokenmax.logs import compress_log
    digest, _ = compress_log(args["text"])
    return digest


def _tool_compress_diff(args):
    from justokenmax.diffcompress import compress_diff
    digest, _ = compress_diff(args["text"])
    return digest


def _tool_query(args):
    from justokenmax.codeindex import query, format_hits
    hits = query(args.get("root", "."), args["term"], kind=args.get("kind"))
    return format_hits(hits)


def _tool_delta(args):
    from justokenmax.delta import delta
    artifact, _ = delta(args["path"])
    return artifact


def _tool_redact(args):
    from justokenmax.redact import redact
    return redact(args["text"])[0]


def _tool_retrieve(args):
    from justokenmax import cache
    origin = cache.lookup_origin(args["artifact"])
    return origin or "no recorded original for that artifact"


def _tool_unmask(args):
    from justokenmax import cache
    return cache.unmask(args["key"], args["text"], audit_actor=args.get("actor"))


def _tool_stats(args):
    from justokenmax import cache
    return json.dumps(cache.read_ledger())


def _tool_discover(args):
    from justokenmax.discover import discover
    return json.dumps(discover(root=args.get("root")))


DISPATCH = {
    "justokenmax_optimize": _tool_optimize,
    "justokenmax_compress_json": _tool_compress_json,
    "justokenmax_compress_log": _tool_compress_log,
    "justokenmax_compress_diff": _tool_compress_diff,
    "justokenmax_query": _tool_query,
    "justokenmax_outline": _tool_outline,
    "justokenmax_delta": _tool_delta,
    "justokenmax_redact": _tool_redact,
    "justokenmax_retrieve": _tool_retrieve,
    "justokenmax_unmask": _tool_unmask,
    "justokenmax_stats": _tool_stats,
    "justokenmax_discover": _tool_discover,
}


def _ok(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle_request(req: dict):
    """Handle one JSON-RPC request. Returns a response dict, or None for
    notifications (which get no reply)."""
    method = req.get("method")
    req_id = req.get("id")

    if method == "initialize":
        return _ok(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "justokenmax", "version": __version__},
        })
    if method == "ping":
        return _ok(req_id, {})
    if method and method.startswith("notifications/"):
        return None
    if method == "tools/list":
        return _ok(req_id, {"tools": TOOLS})
    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        fn = DISPATCH.get(name)
        if not fn:
            return _err(req_id, -32602, f"unknown tool: {name}")
        try:
            text = fn(args)
        except Exception as e:  # surface tool errors per MCP convention
            return _ok(req_id, {"content": [{"type": "text",
                       "text": f"error: {e}"}], "isError": True})
        return _ok(req_id, {"content": [{"type": "text", "text": text}]})
    if req_id is None:
        return None
    return _err(req_id, -32601, f"method not found: {method}")


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle_request(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
