# jusTokenMax for Aider

Unlike Codex / Gemini / Cline / Cursor / OpenCode, **Aider has no MCP client or
file-read hook** (see its [config options](https://aider.chat/docs/config/options.html)),
so jusTokenMax can't auto-intercept Aider's reads — there's nothing for
`justokenmax install` to wire up. You still get the savings, explicitly:

## 1. Optimize heavy files, then add the cheap artifact

```bash
justokenmax optimize spec.pdf data.csv build.log --json
#   each result has an "output" path (the .md / digest / compressed file)
```

In Aider, `/add` the optimized artifact instead of the raw file — the model sees
the Markdown / digest at a fraction of the tokens. `justokenmax stats` shows what
you saved.

## 2. Navigate code by symbol instead of adding whole files

```bash
justokenmax index .                 # build the symbol map
justokenmax query handleCheckout    # -> file:line + signature
justokenmax outline src/app.ts      # a file's shape, no bodies
```

Use those to `/add` only the exact files/ranges you need, rather than dragging
whole modules into context.

## 3. Compress a diff before review / commit messages

```bash
git diff | justokenmax diff -        # keep code hunks, collapse lockfile noise
```

## If Aider adds MCP client support

If a future Aider version gains MCP, jusTokenMax already ships an MCP server
(`justokenmax mcp` / `npx -y @kalmantic/justokenmax mcp`) — point Aider at it and
the full tool set (`justokenmax_optimize`, `_query`, `_outline`, …) becomes
available. Track it and we'll add `justokenmax install aider`.
