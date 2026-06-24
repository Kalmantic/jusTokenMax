# Cross-Agent Setup

jusTokenMax works with any agent over the open **MCP** standard, plus native
integrations where they exist.

## One command (recommended)

```bash
justokenmax install [codex|opencode|cursor|claude|gemini|qwen|cline|kilocode|omp]
justokenmax install                                  # omit to auto-detect
justokenmax uninstall [agent]
justokenmax install --dry-run                        # preview the change
```

Seamless and reversible: idempotent (never duplicates), merges JSON configs
without clobbering your other servers, and removes only our entry on uninstall.
The registered command is `npx -y @kalmantic/justokenmax mcp`, which works for
anyone with Node — even **no Python** (see [Installation](Installation)).

## What it writes

| Agent | Config file | Format |
| --- | --- | --- |
| Codex CLI | `~/.codex/config.toml` | `[mcp_servers.justokenmax]` |
| OpenCode | `~/.config/opencode/opencode.json` | `mcp` (type `local`) |
| Cursor | `~/.cursor/mcp.json` | `mcpServers` |
| Claude Code | project `.mcp.json` | `mcpServers` |
| Gemini CLI | `~/.gemini/settings.json` | `mcpServers` |
| Qwen | `~/.qwen/settings.json` | `mcpServers` (format assumed Gemini-compatible, not verified on a live Qwen instance) |
| Cline | `~/.cline/data/settings/cline_mcp_settings.json` | `mcpServers` |
| Kilo Code | `~/.config/kilo/kilo.jsonc` | `mcp` (type `local`) |
| oh-my-pi (omp) | `~/.omp/agent/mcp.json` | `mcpServers` (type `stdio`) |

## Manual (Codex example)

```toml
# ~/.codex/config.toml
[mcp_servers.justokenmax]
command = "npx"
args = ["-y", "@kalmantic/justokenmax", "mcp"]
# or, with Python: command = "python3", args = ["-m", "justokenmax.mcp_server"]
```

## OpenCode — transparent reads

Beyond the MCP tools, OpenCode can auto-compress heavy reads via a plugin — see
`integrations/opencode/` in the repo (copy `justokenmax.js` into
`.opencode/plugins/`).

## Tools exposed over MCP

`justokenmax_optimize`, `_compress_json`, `_compress_log`, `_compress_diff`,
`_query`, `_outline`, `_delta`, `_redact`, `_retrieve`, `_stats`.
