# Try jusTokenMax in 5 minutes — see the savings, on vs off

A hands-on walkthrough you can copy-paste. Scenario: you're asking your agent to
**"build a website that lists these products"** — and you're feeding it a big
product **CSV**, a **PDF spec**, and a noisy **build log**. Those three inputs
are what blow up the token bill. Here's jusTokenMax shrinking them, and what
happens when you turn it off.

## 0. Install

```bash
git clone https://github.com/Kalmantic/jusTokenMax && cd jusTokenMax
pip install pypdf Pillow ./python
justokenmax --version
export JUSTOKENMAX_HOME=$(mktemp -d)/.jtm     # use a throwaway cache for this demo
```

## 1. Make the sample inputs

```bash
# a 5,000-row product catalog (CSV)
python - <<'PY'
import csv
with open("products.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["id","name","price","in_stock"])
    for i in range(5000):
        w.writerow([i, f"Product {i}", round(i*1.99,2), i%2==0])
PY

# a noisy build log
{ for i in $(seq 1 4000); do echo "[12:00:0$((i%9))] DEBUG bundling chunk_$i"; done;
  printf 'fetching dep\n%.0s' {1..200}; echo "ERROR: build failed"; } > build.log
```

## 2. Feature ON — watch it shrink

```bash
justokenmax optimize products.csv build.log
```

You'll see something like:

```
ok    products.csv
      -> .../<hash>.csv.md
      57,340 -> 237 tokens (-57,103, -99%)  [csv]  5000 rows x 4 cols
ok    build.log
      -> .../<hash>.log.txt
      44,160 -> 230 tokens (-43,930, -99%)  [log]  ...
```

The CSV became a schema + sample rows; the log became a digest. Your agent gets
all the **shape** it needs to build the site, at ~1% of the tokens. Check the
running total:

```bash
justokenmax stats
# justokenmax: 100,000+ tokens saved across 2 runs
```

## 3. Feature OFF — optimize your way

Don't want CSV touched (maybe you need every row)? Turn that lever off:

```bash
justokenmax config disable csv
justokenmax optimize products.csv     # -> skip  products.csv  (disabled by config)
justokenmax config                    #  csv  OFF   (everything else still on)
justokenmax config enable csv         # back on
```

Same with `JUSTOKENMAX_DISABLE=pdf,image justokenmax optimize ...` for a one-off.

## 4. In Claude Code — it's automatic

Install it as a Claude Code plugin. From inside Claude Code, run these three
slash commands **one at a time** — Claude Code takes a single slash command per
prompt, so don't paste all three together:

1. `/plugin marketplace add https://github.com/Kalmantic/jusTokenMax.git`
2. `/plugin install justokenmax@justokenmax`
3. `/reload-plugins`

(Non-interactive equivalent in a terminal: `claude plugin marketplace add
https://github.com/Kalmantic/jusTokenMax.git` then `claude plugin install
justokenmax@justokenmax`.)

The plugin's hook needs the `justokenmax` CLI on your `PATH` — if you cloned and
`pip install ./python`'d in step 0 you're set; otherwise `pip install justokenmax`
(or just have Node, and it auto-provisions via `npx`/`uv`).

Now when your agent **reads** `products.csv` / `build.log` / a PDF spec while
building the site, the `Read` hook transparently swaps in the cheap artifact —
you do nothing. Turn a lever off with `justokenmax config disable <kind>` and the
hook leaves that file untouched. Run `justokenmax stats` anytime to see the
lifetime savings.

Prefer just the tools (no auto-hook)? `justokenmax install claude` registers the
MCP server in a project `.mcp.json` instead (remove it with `justokenmax
uninstall claude`).

**To uninstall the plugin** later, run these one at a time:

1. `/plugin uninstall justokenmax@justokenmax`
2. `/plugin marketplace remove justokenmax`
3. `/reload-plugins`

## 5. In Codex CLI / OpenCode / Cursor

```bash
justokenmax install            # auto-detects and registers the MCP server
# ...then in that agent, the justokenmax_* tools are available.
justokenmax uninstall          # clean removal
```

## 6. A realistic end-to-end test — build a dashboard, then measure

Want a real, repeatable measurement of token utilization? Give your agent a
task that **reads several heavy files**, run it once with jusTokenMax **on** and
once **off**, and compare. This is the kind of task that normally burns tokens.

### Set up the inputs

You already have `products.csv` and `build.log` from step 1. Add a real PDF spec
so the PDF lever is exercised too:

```bash
curl -L -o spec.pdf https://arxiv.org/pdf/1706.03762    # any real PDF works
```

### The prompt (paste this into your agent)

> **Build a product analytics dashboard, end to end.**
>
> 1. Read `products.csv` (5,000 rows: id, name, price, in_stock). Summarize:
>    total products, price min/max/avg, and how many are in stock vs out.
> 2. Read `build.log` and tell me whether the last build passed or failed —
>    quote the exact error line(s) if any.
> 3. Read `spec.pdf` and list, in 5 bullets, what it's about (treat it as the
>    "requirements doc").
> 4. Create a single-file static site `dashboard.html` (vanilla HTML/CSS/JS, no
>    frameworks) that loads `products.csv` client-side and renders: summary cards
>    (total products, total in-stock, average price, most-expensive product); a
>    sortable, searchable products table; a price-range slider; and an
>    "in-stock only" toggle. Clean, responsive, light theme.
> 5. Write a short `dashboard-README.md` explaining how to run it and how the
>    filters work.
> 6. Re-read `products.csv` once more and confirm your table's column order
>    matches the CSV header exactly.
>
> Read each file fully before you use it, and work step by step.

This makes the agent read the CSV (twice → the **delta** lever kicks in), the
log, and the PDF — exactly the inputs jusTokenMax compresses.

### Measure it (on vs off)

1. **With jusTokenMax ON** (plugin installed, or `justokenmax install`), run the
   prompt. When it finishes, check Claude Code's context/cost with **`/cost`**
   (or the context indicator), and run **`justokenmax stats`** — it prints the
   tokens it saved on those reads.
2. **Turn it OFF** and repeat on a fresh conversation:
   ```bash
   justokenmax config disable csv log pdf      # or uninstall the plugin
   ```
   Run the exact same prompt again and check **`/cost`** once more.
3. **Compare.** The "off" run carries the raw 5,000-row CSV, the full noisy log,
   and the page-image PDF into context; the "on" run carries digests. The
   difference is the token utilization jusTokenMax buys you — typically the
   inputs alone drop ~90%+. (Re-enable with `justokenmax config enable csv log
   pdf`.)

> Tip: keep the task identical and start each run from a cleared conversation
> (`/clear`) so the only variable is jusTokenMax on vs off.

---

That's it — the same tool, the same savings, your toggles. Liked it?
**[Sponsor ❤](https://github.com/sponsors/Kashi-KS)**.
