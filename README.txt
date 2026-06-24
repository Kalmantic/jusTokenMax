==============================================================================
 jusTokenMax - token-reduction toolkit for Claude Code, OpenCode & other
 coding harnesses
==============================================================================

Keep your coding agent under a token (and cost) budget. jusTokenMax shrinks
every expensive thing before it reaches the model's context - attachments, logs,
JSON, notebooks, CSVs, diffs, and the files you read - so the same work costs a
fraction of the tokens.

Built by Kashi (https://www.linkedin.com/in/kashiks/) and
Rajan (https://www.linkedin.com/in/thiyagarajan/), founders of
Kalmantic (https://www.kalmantic.com) - jusCode.co. MIT licensed.

Sponsor: https://github.com/sponsors/Kashi-KS


TOKENMAX UNDER A BUDGET
------------------------------------------------------------------------------
Coding-agent bills are driven by INPUT tokens - the PDFs, logs, API responses,
diffs, and source files that pile into the context window. jusTokenMax caps
that: it intercepts each heavy input and replaces it with a faithful, far
cheaper equivalent, BEFORE it costs you a token.

- Compress everything that bloats context - PDFs -> Markdown, images downscaled,
  logs/JSON/notebooks/CSVs/diffs digested, whole-file reads replaced by symbol
  lookups. Typical reductions 56%-99% (measured, below).
- Stay under a budget - point it at what you feed your agent and per-task token
  cost drops by about the same; pair with terse output and chat-branch to also
  cap what the agent writes and re-reads.
- Reversible & safe - every original is cached by content hash
  (`justokenmax retrieve`); secrets and base64 blobs are masked on the way through.
- Works where you work - automatic in Claude Code (a Read hook swaps heavy files
  for cheap artifacts in place), and available to ANY MCP agent (Codex CLI,
  OpenCode, Cursor, ...) plus a plain `justokenmax` CLI.
- Zero dependencies, fully auditable - deterministic heuristics, no trained
  model, no network. Every transform is readable Python.

  What you feed it                          Typical reduction
  PDF spec / paper                          -56% (real PDFs)
  Verbose build/CI log                      -99%
  Large JSON / API response                 -99%
  Jupyter notebook                          -99%
  CSV (thousands of rows)                   -99%
  Git diff (lockfile churn)                 lockfile -> 1 line
  Finding a symbol vs reading the file      -97%


BUILT FOR CASUAL USERS *AND* ENTERPRISE - FROM DAY ONE
------------------------------------------------------------------------------
The same tool serves a solo developer and a regulated enterprise, by design -
not as an afterthought:

- Casual users get a one-command setup (`justokenmax install`) and then it just
  works, automatically: free, MIT, no account, no signup, sensible defaults.
  Your agent simply gets cheaper.
- Enterprise gets a tool that's safe to adopt: zero third-party services and no
  network calls (nothing leaves the machine - runs air-gapped and sidesteps
  data-egress / residency review); deterministic and fully auditable (readable
  Python, no black-box model) for security sign-off; built-in secret redaction
  (API keys/tokens masked before they reach context, logs, or the cache); an
  owner-only (0700) local cache; reversible (originals retained); open-MCP-
  standard integration; and MIT licensing for legal clearance.

That's why it's deliberately zero-dependency and deterministic from the first
commit - the properties enterprises require are the same ones that keep it small
and trustworthy for everyone.


COMPARISON  (Y = has it, ~ = partial/lighter, N = no)
------------------------------------------------------------------------------
Legend:  JO=jusTokenMax  HR=headroom  CV=caveman  CG=codegraph

PDF -> Markdown (drop page-image channel) ... JO:Y  HR:N  CV:N  CG:N
Image / log / JSON compression ............. JO:Y  HR:Y  CV:N  CG:N
Notebook (.ipynb) compression .............. JO:Y  HR:N  CV:N  CG:N
CSV / tabular sampling ..................... JO:Y  HR:N  CV:N  CG:N
Git-diff compression ....................... JO:Y  HR:N  CV:N  CG:N
Delta / incremental re-reads ............... JO:Y  HR:N  CV:N  CG:N
Secret + base64-blob redaction ............. JO:Y  HR:N  CV:N  CG:N
Code symbol index + outline ................ JO:Y  HR:N  CV:N  CG:Y
Output-token reduction (terse) ............. JO:Y  HR:Y  CV:Y  CG:N
Chat branching -> subagent + digest ........ JO:Y  HR:~  CV:N  CG:N
Reversible + retrieve original ............. JO:Y  HR:Y  CV:N  CG:N
Transparent in-place Read rewrite .......... JO:Y  HR:N  CV:N  CG:~
Content sniffer / auto-route ............... JO:Y  HR:Y  CV:N  CG:N
MCP server + one-command install ........... JO:Y  HR:~  CV:~  CG:~
HTTP proxy / wrap / middleware ............. JO:N  HR:Y  CV:N  CG:N
Trained compression model .................. JO:N  HR:Y  CV:N  CG:N
Cross-agent shared memory .................. JO:N  HR:Y  CV:N  CG:N
Zero-dependency / auditable ................ JO:Y  HR:N  CV:Y  CG:~
Single unified plugin (all levers) ......... JO:Y  HR:~  CV:N  CG:N

Distinct to jusTokenMax: a Claude-Code-native transparent rewrite (no proxy), a
queryable code symbol index + file outline, PDF->Markdown that drops the per-page
image channel, chat-branching as a first-class command, and zero-dependency
deterministic heuristics. Still headroom-only: a trained model, an HTTP proxy
mode, and a cross-agent shared-memory store.


INSTALL
------------------------------------------------------------------------------
The canonical install is the Python package; it provides the `justokenmax` CLI.

From this repo (works today, Python 3.9+):
  git clone https://github.com/Kalmantic/jusTokenMax && cd jusTokenMax
  pip install pypdf Pillow        # required codecs
  pip install pdfplumber          # optional: better PDF table extraction
  pip install ./python            # installs the `justokenmax` CLI
  justokenmax --version

From PyPI (once published):  pip install justokenmax
npm (optional thin shim):    npm install -g @kalmantic/justokenmax

One-command setup for any agent (seamless + reversible - idempotent, never
clobbers your other servers, removes cleanly):
  justokenmax install            # auto-detect Codex/OpenCode/Cursor/Claude
  justokenmax install codex      # or target one agent
  justokenmax install --dry-run  # preview the change first
  justokenmax uninstall          # remove it again, just as cleanly

Node but no Python? The registered command is `npx -y @kalmantic/justokenmax mcp`,
which works for anyone with Node: if no Python is on PATH it auto-provisions one
via uv (`uvx justokenmax`) - zero manual setup. (With Python, `python3 -m
justokenmax.mcp_server` also works and skips Node.)

As a Claude Code plugin: inside Claude Code run
  /plugin marketplace add https://github.com/Kalmantic/jusTokenMax.git
  /plugin install justokenmax@justokenmax
  /reload-plugins
Then the Read hook + commands +
skills + MCP server activate automatically.


USE
------------------------------------------------------------------------------
  justokenmax optimize report.pdf shot.png build.log api.json data.csv nb.ipynb
  justokenmax logs ci-output.log                 # compress a verbose log
  justokenmax json response.json                 # compress a JSON payload
  justokenmax diff < changes.diff                # compress a git diff
  justokenmax delta src/app.py                   # only what changed since last read
  justokenmax redact secrets.txt                 # mask secrets + elide blobs
  justokenmax index && justokenmax query parse   # build index, find a symbol
  justokenmax outline src/app.py                 # a file's shape, no bodies
  justokenmax retrieve <artifact>                # get the original back (reversible)
  justokenmax stats                              # lifetime token savings
  justokenmax config disable csv                 # turn a lever off (your way)
  justokenmax proxy -- npx -y some-mcp-server     # compress ANY other MCP server

New here? docs/try-it.md is a 5-minute copy-paste walkthrough (savings on vs off).

Configure - optimize your way (every lever on by default):
  justokenmax config                 # show what's on/off
  justokenmax config disable pdf     # persist: skip PDFs
  justokenmax config enable pdf      # back on
  JUSTOKENMAX_DISABLE=pdf,image ...  # one-off, via env
  Kinds: pdf image log json notebook csv diff redact

Plugin surface:
  Hook     PreToolUse(Read) rewrites PDF/image/.log/JSON/.ipynb/CSV/diff reads
           to the cheap artifact via updatedInput; never blocks a Read.
  MCP      stdlib stdio server: justokenmax_optimize, _compress_json,
           _compress_log, _compress_diff, _query, _outline, _delta, _redact,
           _retrieve, _stats - any MCP agent can call it.
  Commands /justokenmax:optimize, :logs, :json, :diff, :index, :query, :outline,
           :delta, :redact, :retrieve, :terse, :branch, :compress-memory,
           :learn, :stats
  Skills   attachments, code-index, chat-branch, terse-output, cache-align


RESULTS (regenerable: python benchmarks/benchmark.py --fetch)
------------------------------------------------------------------------------
PDF -> Markdown (real public PDFs):
  Attention Is All You Need (arXiv)   15 pages   37,074 -> 14,574   -60%
  IRS Form W-9                         6 pages   18,305 ->  9,305   -49%
  TOTAL                               21 pages   55,379 -> 23,879   -56%

Logs:            4,345 -> 21 lines    107,668 -> 396 tokens    -99%
JSON:            2,000-row payload    168,023 -> 374 tokens    -99%
Notebook:        20 cells w/ images  401,170 -> 610 tokens    -99%
CSV:             5,000 rows           57,340 -> 237 tokens    -99%
Delta re-read:   1 edit in 600 lines   2,407 ->  88 tokens    -96%
Code index:      locate a symbol       16,691 -> 486 tokens    -97%  (21 lookups)
Images:          3000x2000 -> 1568x1045   186 KB -> 107 KB     -42% bytes


LIMITS & HONESTY
------------------------------------------------------------------------------
- Why text, not image parsing? Almost every spec/design/test doc is born digital
  with a real text layer, and text is ~10x cheaper than a page-image (and
  searchable/diffable) - so text-first is the right default. Scanned/image-only
  PDFs are the exception (OCR is on the roadmap); or `config disable pdf`.
- No OCR: scanned/image-only PDFs -> empty Markdown; original passed through.
- PDF per-page tokens are a conservative model, not a billed number.
- Image token savings are base64-pipeline only; the always-real win is bytes.
- The code index is a snapshot, not live - re-run `justokenmax index` after changes.


SAFETY
------------------------------------------------------------------------------
Hooks run on untrusted files, so converters are bounded: PDFs capped at 2,000
pages / ~5M chars, Pillow decompression-bomb guard active, no shell execution,
content-hash output paths, owner-only (0700) cache, and the Read hook fails open.
Secrets and base64 blobs are masked inside every text digest.


TEST
------------------------------------------------------------------------------
  cd python && pip install -e . pytest pdfplumber
  pytest -q     # pdf, image, log, json, notebook, csv, diff, delta, redact,
                #          code-index, outline, optimize, cli, hook, mcp, install


SUPPORT
------------------------------------------------------------------------------
jusTokenMax is free and MIT-licensed. If it keeps your agent under budget,
please consider sponsoring -> https://github.com/sponsors/Kashi-KS


LICENSE
------------------------------------------------------------------------------
MIT - see LICENSE.
