# InvestWatch — build-from-scratch example

A worked example for measuring jusTokenMax on a **new project built from a PRD**.

1. **[`PRD.md`](PRD.md)** — the product requirements doc you hand to your agent
   (a news-indexed investment tracker), plus a measured **with vs without
   jusTokenMax** table.
2. **[`scaffold.sh`](scaffold.sh)** — generates the data the build consumes (a
   big news-feed JSON, holdings + market-history CSVs across a shared 60-ticker
   universe, a `package-lock.json`, a noisy `build.log`). Git-ignored; regenerate
   any time.
3. **[`app/`](app/)** — the **built reference implementation**: a vanilla
   HTML/CSS/JS dashboard (no build step) — sortable/searchable holdings, summary
   cards, per-ticker news + sentiment, sector filter, dark mode.

## Run the app

```bash
bash scaffold.sh                 # generate data/
python3 -m http.server           # serve this folder
# open  http://localhost:8000/app/
```

## Measure it

```bash
justokenmax optimize data/news-feed.json data/holdings.csv \
  data/market-history.csv package-lock.json build.log
justokenmax stats
```

Measured (real tokenizer, one pass over the data inputs):
**532,789 → 117,354 tokens (−77%)** — the PRD itself is left untouched. Full
breakdown + the on/off live-agent steps are in
[`PRD.md`](PRD.md#token-cost-with-vs-without-justokenmax).
