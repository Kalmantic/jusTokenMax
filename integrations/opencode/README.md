# jusTokenMax for OpenCode

Two integration layers — use either or both:

## 1. MCP tools (recommended, one command)

Gives OpenCode the full jusTokenMax tool set (`optimize`, `compress_json`,
`compress_log`, `compress_diff`, `query`, `outline`, `delta`, `redact`,
`retrieve`, `stats`):

```bash
justokenmax install opencode      # registers the MCP server in opencode.json
justokenmax uninstall opencode    # remove it
```

## 2. Transparent read compression (this plugin)

`justokenmax.js` mirrors the Claude Code `Read` hook: when OpenCode is about to
read a heavy file (PDF / log / JSON / notebook / CSV / diff), it swaps in
jusTokenMax's cheap artifact automatically.

Install by copying the file into an OpenCode plugins directory:

```bash
# project-local
mkdir -p .opencode/plugins && cp justokenmax.js .opencode/plugins/
# or global
mkdir -p ~/.config/opencode/plugins && cp justokenmax.js ~/.config/opencode/plugins/
```

Requires the `justokenmax` CLI (`pip install justokenmax`); it falls back to
`npx -y @kalmantic/justokenmax`, which bootstraps Python via `uv` if needed. The
plugin **never blocks a read** — any failure leaves the original read untouched.

> Status: community integration. OpenCode's plugin/tool API is young; if your
> OpenCode version names the read tool or its path argument differently, adjust
> `input.tool` / `ARG_KEYS` at the top of `justokenmax.js`. PRs welcome.
