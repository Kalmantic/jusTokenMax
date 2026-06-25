import json

from justokenmax import mcp_server as mcp


def _call(name, arguments):
    req = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
           "params": {"name": name, "arguments": arguments}}
    resp = mcp.handle_request(req)
    return resp["result"]


def test_initialize_advertises_server():
    resp = mcp.handle_request({"jsonrpc": "2.0", "id": 0, "method": "initialize"})
    assert resp["result"]["serverInfo"]["name"] == "justokenmax"
    assert resp["result"]["capabilities"]["tools"] == {}


def test_tools_list_has_expected_tools():
    resp = mcp.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert {"justokenmax_optimize", "justokenmax_compress_json", "justokenmax_compress_log",
            "justokenmax_query", "justokenmax_retrieve", "justokenmax_stats"} <= names


def test_compress_json_tool():
    src = json.dumps({"items": list(range(200))})
    result = _call("justokenmax_compress_json", {"text": src})
    text = result["content"][0]["text"]
    assert "items elided" in text
    assert "isError" not in result


def test_compress_log_tool():
    raw = "\n".join(["INFO x"] * 100 + ["ERROR boom"])
    text = _call("justokenmax_compress_log", {"text": raw})["content"][0]["text"]
    assert "ERROR boom" in text


def test_stats_tool_returns_ledger():
    text = _call("justokenmax_stats", {})["content"][0]["text"]
    assert "total_tokens_saved" in json.loads(text)


def test_unmask_tool_restores_and_audits():
    from justokenmax import cache
    from justokenmax.redact import redact_with_map
    secret = "s" + "k-" + "Z" * 22
    masked, mapping = redact_with_map(f"token={secret}")
    cache.save_redaction_map("mcpkey", mapping)
    text = _call("justokenmax_unmask",
                 {"key": "mcpkey", "text": masked, "actor": "agent"})
    restored = text["content"][0]["text"]
    assert secret in restored and "isError" not in text
    assert cache.read_audit_log()[-1]["actor"] == "agent"


def test_tools_list_includes_unmask():
    resp = mcp.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert "justokenmax_unmask" in names


def test_unknown_tool_is_error():
    resp = mcp.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                               "params": {"name": "nope", "arguments": {}}})
    assert "error" in resp


def test_notifications_get_no_reply():
    assert mcp.handle_request({"jsonrpc": "2.0",
                               "method": "notifications/initialized"}) is None


def test_unknown_method_errors():
    resp = mcp.handle_request({"jsonrpc": "2.0", "id": 3, "method": "bogus"})
    assert resp["error"]["code"] == -32601


def test_discover_tool_returns_report(monkeypatch, tmp_path):
    monkeypatch.setenv("JUSTOKENMAX_HISTORY", str(tmp_path / "absent"))
    text = _call("justokenmax_discover", {})["content"][0]["text"]
    rep = json.loads(text)
    assert "recoverable_tokens" in rep and rep["note"] == "no history dir"


def test_cli_mcp_subcommand_runs(monkeypatch):
    import io
    from justokenmax.cli import main
    monkeypatch.setattr("sys.stdin", io.StringIO(""))   # EOF -> server exits
    assert main(["mcp"]) == 0
