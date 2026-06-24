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

Add this repo as a Claude Code plugin (or run `justokenmax install claude`). Now
when your agent **reads** `products.csv` / `build.log` / a PDF spec while
building the site, the `Read` hook transparently swaps in the cheap artifact —
you do nothing. Turn a lever off with `justokenmax config disable <kind>` and the
hook leaves that file untouched. Run `justokenmax stats` anytime to see the
lifetime savings.

## 5. In Codex CLI / OpenCode / Cursor

```bash
justokenmax install            # auto-detects and registers the MCP server
# ...then in that agent, the justokenmax_* tools are available.
justokenmax uninstall          # clean removal
```

That's it — the same tool, the same savings, your toggles. Liked it?
**[Sponsor ❤](https://github.com/sponsors/Kashi-KS)**.
