# InvestWatch — build-from-scratch example

A worked example for measuring jusTokenMax on a **new project built from a PRD**.

1. **[`PRD.md`](PRD.md)** — the product requirements doc you hand to your agent
   (a news-indexed investment tracker), plus a measured **with vs without
   jusTokenMax** table at the bottom.
2. **[`scaffold.sh`](scaffold.sh)** — generates the data the build consumes (a
   big news-feed JSON, holdings + market-history CSVs, a `package-lock.json`, a
   noisy `build.log`). These are git-ignored; regenerate any time.

```bash
bash scaffold.sh
justokenmax optimize data/news-feed.json data/holdings.csv \
  data/market-history.csv package-lock.json build.log
```

Measured result (real tokenizer, one pass over the data inputs):
**597,642 → 117,395 tokens (−80%)** — the PRD itself is left untouched. Full
breakdown and the on/off live-agent steps are in [`PRD.md`](PRD.md#token-cost-with-vs-without-justokenmax).
