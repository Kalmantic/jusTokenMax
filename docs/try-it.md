# Try jusTokenMax in 5 minutes

Get it running, then measure the savings on a realistic development task — once
with jusTokenMax **on**, once **off**.

---

## 1. Install in Claude Code (recommended)

From inside Claude Code, run these **one at a time** — Claude Code takes a single
slash command per prompt, so don't paste all three together:

1. `/plugin marketplace add https://github.com/Kalmantic/jusTokenMax.git`
2. `/plugin install justokenmax@justokenmax`
3. `/reload-plugins`

Now when your agent **reads** a PDF / log / JSON / CSV / notebook / diff, the
`Read` hook transparently swaps in jusTokenMax's cheap artifact — you do nothing.

The hook calls the `justokenmax` CLI, so you need it on your `PATH` (step 2
below), **or** just have Node (it auto-provisions Python via `npx`/`uv`).

**To uninstall** later (one at a time):

1. `/plugin uninstall justokenmax@justokenmax`
2. `/plugin marketplace remove justokenmax`
3. `/reload-plugins`

---

## 2. Or: the CLI and other agents

```bash
git clone https://github.com/Kalmantic/jusTokenMax && cd jusTokenMax
pip install pypdf Pillow ./python      # installs the `justokenmax` CLI
justokenmax --version
```

Register it with any MCP agent (auto-detects Codex / OpenCode / Cursor / Claude):

```bash
justokenmax install            # seamless + reversible
justokenmax uninstall          # clean removal
```

**Node but no Python?** The registered command is `npx -y @kalmantic/justokenmax
mcp`, which auto-provisions Python via `uv` — zero manual setup.

---

## 3. See it work — inputs, and a lever on vs off

```bash
export JUSTOKENMAX_HOME=$(mktemp -d)/.jtm     # throwaway cache for the demo

# a 5,000-row product catalog + a noisy build log
python - <<'PY'
import csv
with open("products.csv","w",newline="") as f:
    w=csv.writer(f); w.writerow(["id","name","price","in_stock"])
    for i in range(5000): w.writerow([i,f"Product {i}",round(i*1.99,2),i%2==0])
PY
{ for i in $(seq 1 4000); do echo "[12:00:0$((i%9))] DEBUG bundling chunk_$i"; done;
  echo "ERROR: build failed"; } > build.log

justokenmax optimize products.csv build.log     # -> ~ -99% each
justokenmax stats                                # running total of tokens saved

# turn a lever off — your project, your way
justokenmax config disable csv
justokenmax optimize products.csv                # -> skip (disabled by config)
justokenmax config enable csv
```

---

## 4. Measure it on a real dev task — extend a website codebase

The bigger use case is **day-to-day development on an existing website**, where
the token bill is dominated by the agent *reading* source files, the lockfile,
and build output — and **re-reading** them as it iterates. Here's a self-contained
project to prove it.

### Scaffold a small e-commerce website

```bash
mkdir -p shopsite/src shopsite/public shopsite/data && cd shopsite

cat > package.json <<'JSON'
{ "name":"shopsite","version":"1.0.0",
  "scripts":{"build":"node build.js","dev":"node server.js"},
  "dependencies":{"express":"^4.19.2","nanoid":"^5.0.7"} }
JSON

# a chunky package-lock.json — the classic token sink
python3 - <<'PY'
import json
d={f"node_modules/pkg-{i}":{"version":f"1.{i}.0",
   "resolved":f"https://registry.npmjs.org/pkg-{i}/-/pkg-{i}-1.{i}.0.tgz",
   "integrity":"sha512-"+"A"*86,
   "dependencies":{f"dep-{j}":"^1.0.0" for j in range(6)}} for i in range(800)}
json.dump({"name":"shopsite","lockfileVersion":3,"packages":d}, open("package-lock.json","w"), indent=2)
PY

# several source modules (so navigating the code costs real tokens)
for m in catalog cart filters render api utils format storage; do
  M="$(printf '%s' "${m:0:1}" | tr a-z A-Z)${m:1}"
  cat > "src/$m.js" <<JS
// $m module — part of the ShopSite frontend
export function ${m}Init(config) { return { ...config, ready: true }; }
export function ${m}Load(data) { return (data || []).map((x) => x); }
export class ${M}Manager {
  constructor(opts) { this.opts = opts || {}; }
  process(items) { return (items || []).filter(Boolean); }
  render(el) { if (el) el.innerHTML = ""; }
}
export const ${m}Defaults = { enabled: true, limit: 50 };
JS
done

# 5,000-row product catalog + a noisy build log with a real error
python3 - <<'PY'
import csv
with open("data/products.csv","w",newline="") as f:
    w=csv.writer(f); w.writerow(["id","name","price","category","in_stock"])
    for i in range(5000): w.writerow([i,f"Product {i}",round(i*1.99,2),f"cat{i%12}",i%2==0])
PY
{ for i in $(seq 1 3000); do echo "[12:00:0$((i%9))] bundling src/module_$i.js ok"; done;
  echo "ERROR: TypeError: cart is undefined (src/cart.js:42)"; } > build.log

printf '<!doctype html><html><body><div id="app"></div><script type="module" src="../src/render.js"></script></body></html>' > public/index.html
cd ..
```

### The prompt (paste into your agent, working inside `shopsite/`)

> **I'm building an e-commerce product website. Add three features to this
> existing codebase:**
> 1. a **product search + category filter** bar,
> 2. a **shopping cart** that persists in `localStorage`,
> 3. a **dark-mode toggle**.
>
> Work like a real engineer: first **explore the codebase** to see how the
> modules fit together (catalog, cart, filters, render, api, utils, format,
> storage) before changing anything; check `package.json` and the dependency tree
> (skim `package-lock.json` if needed); wire the data from `data/products.csv`
> into the catalog; implement across the relevant `src/*.js` modules and update
> `public/index.html`; read `build.log` to see the current build error and make
> sure your changes address it; and after each edit, re-read the file you changed
> to verify it.

### Reproduce the numbers

Without an agent, you can reproduce the input savings directly:

```bash
justokenmax index shopsite                     # 32 symbols across 8 files
justokenmax optimize shopsite/package-lock.json shopsite/build.log shopsite/data/products.csv
for f in shopsite/src/*.js; do justokenmax outline "$f" >/dev/null; done
```

Summed with a real tokenizer, **one pass through these inputs**:

| Input the agent reads | Before | After | Reduction |
| --- | ---: | ---: | ---: |
| 8 source modules (read → outline) | 872 | 520 | −40% |
| `package-lock.json` | 126,426 | 102,414 | −18% |
| `products.csv` (5,000 rows) | 82,506 | 290 | −99% |
| `build.log` | 50,015 | 521 | −98% |
| **Total** | **259,819** | **103,745** | **−60%** |

(The source-module saving is small only because these demo modules are tiny — on
real files it's far larger, and every **re-read** while editing is near-free via
delta.)

### The on/off A/B (with a live agent)

1. **jusTokenMax ON** — run the prompt, then check Claude Code's context/cost with
   **`/cost`** and **`justokenmax stats`**.
2. **Turn it OFF**, `/clear`, and run the **identical** prompt:
   ```bash
   justokenmax config disable json diff csv log      # or uninstall the plugin
   ```
3. **Compare `/cost`.** The "off" run drags whole files, the full lockfile, the
   raw CSV, and the noisy log into context — and pays again on every re-read.
   Re-enable with `justokenmax config enable json diff csv log`.

> Tip: keep the task identical and `/clear` between runs so the only variable is
> jusTokenMax on vs off.

---

## 5. Build-from-scratch example — a PRD you can measure

Prefer a *new project from a spec*? [`examples/investment-tracker/`](../examples/investment-tracker/PRD.md)
has a full **PRD** for a news-indexed investment tracker, a `scaffold.sh` that
generates the data the build consumes, and a **built reference app**
([`app/`](../examples/investment-tracker/app/index.html), vanilla HTML/CSS/JS).
Measured, one pass over those inputs: **532,789 → 117,354 tokens (−77%)** with
jusTokenMax vs without — the PRD itself left untouched.

```bash
bash examples/investment-tracker/scaffold.sh
cd examples/investment-tracker
justokenmax optimize data/news-feed.json data/holdings.csv \
  data/market-history.csv package-lock.json build.log
```

---

That's it — the same tool, the same savings, your toggles. Liked it?
**[Sponsor ❤](https://github.com/sponsors/Kashi-KS)**.
