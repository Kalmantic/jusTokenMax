import json
from pathlib import Path

import pytest

from justokenmax import install as inst


@pytest.fixture(autouse=True)
def fake_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)          # for claude's project-local ./.mcp.json
    return tmp_path


# ---------------- JSON agents (cursor / opencode / claude) ----------------
def test_install_cursor_creates_entry(fake_home):
    r = inst.install("cursor")
    assert r["changed"] and r["status"] == "installed"
    data = json.loads(Path(r["path"]).read_text())
    assert data["mcpServers"]["justokenmax"]["command"] == "npx"
    assert data["mcpServers"]["justokenmax"]["args"] == [
        "-y", "@kalmantic/justokenmax", "mcp"]


def test_install_is_idempotent(fake_home):
    inst.install("cursor")
    r2 = inst.install("cursor")
    assert r2["changed"] is False and r2["status"] == "already configured"
    data = json.loads(Path(inst.config_path("cursor")).read_text())
    assert list(data["mcpServers"]).count("justokenmax") == 1


def test_install_preserves_other_servers(fake_home):
    path = inst.config_path("cursor")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({"mcpServers": {"other": {"command": "x"}},
                                      "misc": 1}))
    inst.install("cursor")
    data = json.loads(Path(path).read_text())
    assert "other" in data["mcpServers"] and "justokenmax" in data["mcpServers"]
    assert data["misc"] == 1


def test_uninstall_removes_only_our_entry(fake_home):
    path = inst.config_path("cursor")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))
    inst.install("cursor")
    r = inst.uninstall("cursor")
    assert r["changed"] and r["status"] == "removed"
    data = json.loads(Path(path).read_text())
    assert "justokenmax" not in data["mcpServers"]
    assert "other" in data["mcpServers"]


def test_uninstall_absent_is_noop(fake_home):
    r = inst.uninstall("cursor")
    assert r["changed"] is False and r["status"] == "not present"


def test_opencode_uses_local_type(fake_home):
    inst.install("opencode")
    entry = json.loads(Path(inst.config_path("opencode")).read_text())["mcp"]["justokenmax"]
    assert entry["type"] == "local"
    assert entry["command"] == ["npx", "-y", "@kalmantic/justokenmax", "mcp"]


# ---------------- TOML agent (codex) ----------------
def test_codex_toml_install_and_uninstall(fake_home):
    path = inst.config_path("codex")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text('model = "gpt-5"\n')         # pre-existing config
    inst.install("codex")
    text = Path(path).read_text()
    assert "[mcp_servers.justokenmax]" in text
    assert 'model = "gpt-5"' in text                   # preserved
    inst.install("codex")                              # idempotent
    assert text.count("[mcp_servers.justokenmax]") == 1
    r = inst.uninstall("codex")
    assert r["changed"]
    text2 = Path(path).read_text()
    assert "[mcp_servers.justokenmax]" not in text2
    assert 'model = "gpt-5"' in text2                  # other config intact


# ---------------- dry-run ----------------
def test_dry_run_writes_nothing(fake_home):
    r = inst.install("cursor", dry_run=True)
    assert r["changed"] and not Path(inst.config_path("cursor")).exists()


def test_detect_includes_claude(fake_home):
    assert "claude" in inst.detect()


def test_install_gemini(fake_home):
    inst.install("gemini")
    data = json.loads(Path(inst.config_path("gemini")).read_text())
    assert data["mcpServers"]["justokenmax"]["command"] == "npx"
    assert data["mcpServers"]["justokenmax"]["args"] == [
        "-y", "@kalmantic/justokenmax", "mcp"]


def test_install_qwen(fake_home):
    inst.install("qwen")
    data = json.loads(Path(inst.config_path("qwen")).read_text())
    assert data["mcpServers"]["justokenmax"]["command"] == "npx"


def test_install_cline(fake_home):
    inst.install("cline")
    p = inst.config_path("cline")
    assert p.endswith("cline_mcp_settings.json")
    data = json.loads(Path(p).read_text())
    assert data["mcpServers"]["justokenmax"]["command"] == "npx"


def test_install_kilocode(fake_home):
    inst.install("kilocode")
    entry = json.loads(Path(inst.config_path("kilocode")).read_text())["mcp"]["justokenmax"]
    assert entry["type"] == "local"
    assert entry["command"] == ["npx", "-y", "@kalmantic/justokenmax", "mcp"]


def test_install_omp(fake_home):
    inst.install("omp")
    p = inst.config_path("omp")
    assert p.endswith("/.omp/agent/mcp.json")
    data = json.loads(Path(p).read_text())
    assert data["mcpServers"]["justokenmax"]["command"] == "npx"


# ---------------- data-loss guards (JSONC + unparseable) ----------------
def test_install_kilocode_preserves_jsonc_with_comments(fake_home):
    # A real kilo.jsonc with a // comment, an existing mcp server, and a
    # top-level setting. stdlib json can't parse this directly — the installer
    # must strip comments, keep everything, and add our entry without clobbering.
    path = inst.config_path("kilocode")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        "{\n"
        '  // user preference\n'
        '  "theme": "dark",\n'
        '  "mcp": {\n'
        '    "other": {"type": "local", "command": ["other"]}\n'
        "  }\n"
        "}\n"
    )
    r = inst.install("kilocode")
    assert r["changed"] and r["status"] == "installed"
    data = json.loads(Path(path).read_text())
    assert data["theme"] == "dark"                      # top-level setting kept
    assert "other" in data["mcp"]                       # existing server kept
    entry = data["mcp"]["justokenmax"]                  # our entry added
    assert entry["type"] == "local"
    assert entry["command"] == ["npx", "-y", "@kalmantic/justokenmax", "mcp"]


def test_strip_json_comments_preserves_commas_inside_strings():
    # Trailing-comma stripping must be string-aware: a `,` inside a quoted value
    # that happens to be followed by ws + `}`/`]` is data, not a trailing comma.
    for src in ('{"s": "a,]"}', '{"s": "x,}y"}', '{"s": "1,  ]"}'):
        assert json.loads(inst._strip_json_comments(src)) == json.loads(src)
    # Genuine trailing commas (outside strings) are still removed, and a real
    # `//` comment alongside a comma-bearing string value both round-trip.
    src = '{\n  // c\n  "s": "a,]",\n  "arr": [1, 2,],\n}'
    assert json.loads(inst._strip_json_comments(src)) == {"s": "a,]", "arr": [1, 2]}


def test_install_kilocode_preserves_comma_in_string_value(fake_home):
    # End-to-end: a kilo.jsonc whose string value contains `,]` must survive the
    # JSONC parse path unchanged (regression for blind trailing-comma regex).
    path = inst.config_path("kilocode")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        "{\n"
        '  // user preference\n'
        '  "s": "a,]",\n'
        '  "mcp": {}\n'
        "}\n"
    )
    r = inst.install("kilocode")
    assert r["changed"] and r["status"] == "installed"
    data = json.loads(Path(path).read_text())
    assert data["s"] == "a,]"                           # comma inside value kept
    assert "justokenmax" in data["mcp"]


def test_install_aborts_on_unparseable_existing_file(fake_home):
    # Genuinely broken JSON (not just JSONC) must abort the write so we never
    # destroy the user's file by overwriting it with our minimal config.
    path = inst.config_path("cursor")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    original = "{bad"
    Path(path).write_text(original)
    r = inst.install("cursor")
    assert r["changed"] is False
    assert r["status"] == "parse error - left untouched"
    assert Path(path).read_text() == original           # bytes untouched
