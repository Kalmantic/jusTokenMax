import json
import subprocess
import sys

from justokenmax.proxy import transform_response


def _call_result(text):
    return {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": text}]}}


def test_compresses_large_json_tool_result():
    big = json.dumps({"items": list(range(2000))})
    msg = transform_response(_call_result(big))
    out = msg["result"]["content"][0]["text"]
    assert "items elided" in out
    assert len(out) < len(big)


def test_redacts_secret_in_result():
    secret = "s" + "k-" + "Z" * 22
    msg = transform_response(_call_result(f"using key {secret} now"))
    assert secret not in msg["result"]["content"][0]["text"]


def test_trims_verbose_tool_descriptions():
    msg = {"result": {"tools": [{"name": "x", "description": "D" * 500}]}}
    out = transform_response(msg)["result"]["tools"][0]["description"]
    assert out.endswith("…") and len(out) < 300


def test_passes_through_non_result():
    msg = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
    assert transform_response(dict(msg)) == msg


def test_small_text_untouched_but_present():
    msg = transform_response(_call_result("short and clean"))
    assert msg["result"]["content"][0]["text"] == "short and clean"


# --- end-to-end through the proxy with a fake downstream MCP server ---
_FAKE_DOWNSTREAM = (
    "import sys, json\n"
    "for line in sys.stdin:\n"
    "    line = line.strip()\n"
    "    if not line:\n"
    "        continue\n"
    "    req = json.loads(line)\n"
    "    big = json.dumps({'rows': list(range(3000))})\n"
    "    print(json.dumps({'jsonrpc':'2.0','id':req.get('id'),"
    "'result':{'content':[{'type':'text','text':big}]}}))\n"
    "    sys.stdout.flush()\n"
)


def test_end_to_end_proxy_compresses(tmp_path):
    down = tmp_path / "fake_server.py"
    down.write_text(_FAKE_DOWNSTREAM)
    req = json.dumps({"jsonrpc": "2.0", "id": 7,
                      "method": "tools/call", "params": {"name": "q"}}) + "\n"
    proc = subprocess.run(
        [sys.executable, "-m", "justokenmax", "proxy", "--",
         sys.executable, str(down)],
        input=req, capture_output=True, text=True, timeout=30,
    )
    resp = json.loads(proc.stdout.strip().splitlines()[0])
    text = resp["result"]["content"][0]["text"]
    assert "more of 3000 items elided" in text     # downstream output was compressed
    assert resp["id"] == 7
