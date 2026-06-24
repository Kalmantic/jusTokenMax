# Installation

The canonical install is the Python package; it provides the `justokenmax` CLI.

## From the repo (works today)

```bash
git clone https://github.com/Kalmantic/jusTokenMax && cd jusTokenMax
pip install pypdf Pillow            # required codecs
pip install pdfplumber              # optional: better PDF tables
pip install ./python                # installs the `justokenmax` CLI
justokenmax --version
```

## From PyPI (once published)

```bash
pip install justokenmax
```

## Node-only (no Python)

The MCP server is registered as `npx -y @kalmantic/justokenmax mcp`. The Node
launcher auto-provisions a runtime: if no Python is on `PATH`, it falls back to
**`uvx justokenmax`** ([uv](https://astral.sh/uv) fetches an ephemeral Python +
the package) and bootstraps `uv` itself if needed. So a Claude Code user with
only Node gets the full toolset with zero manual setup.

## As a Claude Code plugin

From inside Claude Code:

```text
/plugin marketplace add https://github.com/Kalmantic/jusTokenMax.git
/plugin install justokenmax@justokenmax
/reload-plugins
```

The `Read` hook then optimizes PDFs / images / logs / JSON / notebooks / CSV /
diffs automatically, and the commands, skills, and MCP server become available.
The hook calls the `justokenmax` CLI, so install the Python package or have Node
(it auto-provisions via `npx`/`uv`).

## For any agent (one command)

```bash
justokenmax install            # auto-detect Codex / OpenCode / Cursor / Claude
justokenmax uninstall          # clean removal
```

See **[Cross-Agent Setup](Cross-Agent-Setup)** for details.
