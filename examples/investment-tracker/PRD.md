# PRD — InvestWatch: a news-indexed investment tracker

> A worked, **build-from-scratch** example for measuring jusTokenMax. Hand this
> PRD to your coding agent, point it at the scaffolded data, and let it build the
> app — then compare the token cost **with** vs **without** jusTokenMax. See
> [Token cost](#token-cost-with-vs-without-justokenmax) at the bottom.

## 1. Overview

**InvestWatch** is a personal web app that tracks an investment portfolio and
**indexes financial news against each holding**, so a user can see — per ticker —
their position, recent price action, and the news (with sentiment) driving it.

It's a static + light-API web app: a build step ingests three local data files,
indexes news by ticker, and renders a dashboard.

## 2. Goals

- Show a portfolio at a glance: holdings, cost basis, current value, day change.
- For each holding, surface the **most relevant recent news** with a sentiment
  score, and a rolled-up "news sentiment" per ticker.
- Let the user filter by sector/account and search holdings and news.
- Be fast and fully client-renderable after a single build.

## 3. Users

- **Retail investor** tracking a multi-account portfolio.
- **Analyst** scanning news sentiment across a watchlist.

## 4. Data sources (provided — see `scaffold.sh`)

| File | Shape | Used for |
| --- | --- | --- |
| `data/news-feed.json` | `{ feed: [{id, ticker, headline, body, source, publishedAt, sentiment, url}], count }` | the news index, per-ticker sentiment |
| `data/holdings.csv` | `ticker, shares, cost_basis, sector, account` | the portfolio |
| `data/market-history.csv` | `date, ticker, open, high, low, close, volume` | price action / day change |

Run `bash scaffold.sh` to generate them.

## 5. Features

1. **Portfolio table** — holdings with shares, cost basis, latest close, market
   value, unrealized P/L, and day change. Sortable; filter by sector and account.
2. **News index** — for each ticker, the latest N articles (headline, source,
   time, sentiment). A per-ticker **sentiment badge** (avg of recent articles).
3. **Holding detail** — selecting a holding shows its price sparkline (from
   `market-history.csv`) and its news list.
4. **Search** — across tickers and news headlines.
5. **Summary cards** — total market value, total unrealized P/L, most-positive
   and most-negative tickers by news sentiment.
6. **Dark-mode toggle**, responsive layout.

## 6. Tech & build

- Vanilla **TypeScript + Vite** (no heavy framework). `npm install` then
  `npm run build` → static `dist/`.
- A small build script reads the three data files, builds an in-memory index
  (ticker → holdings, prices, news + sentiment), and emits `dist/index.json`
  consumed by the client.
- No external network calls at runtime; all data is local.

## 7. Pages / structure (target)

```
src/
  main.ts            app bootstrap
  portfolio/         holdings table + summary cards
  news/              news index + sentiment rollup
  market/            price history / sparklines
  search/            search across tickers + news
  ui/                table, cards, toggle, theme
build.ts             ingest data files -> dist/index.json
public/index.html
```

## 8. Acceptance criteria

- `npm run build` succeeds and produces `dist/` with no type errors.
- The portfolio table totals match the sum of holdings.
- Each ticker with news shows a sentiment badge equal to the average of its
  recent articles' `sentiment`.
- Search filters both holdings and news live.
- Dark mode persists in `localStorage`.

## 9. Build it (the prompt)

> Build **InvestWatch** per this PRD. Read the three data files in `data/` to
> learn their exact shapes first, then scaffold the `src/` structure above, write
> `build.ts` to produce `dist/index.json`, and implement the UI. Run the build,
> read `build.log` if it fails, fix the error, and re-check. Re-read each file you
> change to verify it.

---

## Token cost: with vs without jusTokenMax

Building from scratch, your agent doesn't compress the PRD (you want requirements
verbatim) — the cost is in the **data it ingests** and the build artifacts it
reads. Measured with a real tokenizer (tiktoken `cl100k`) over **one pass** of
those inputs:

| Input the agent reads | Without jusTokenMax | With jusTokenMax | Difference |
| --- | ---: | ---: | ---: |
| `data/news-feed.json` (800 articles) | 155,049 | 853 | **−99%** |
| `data/holdings.csv` (3,000 rows) | 51,011 | 295 | **−99%** |
| `data/market-history.csv` (6,000 rows) | 190,832 | 503 | **−99%** |
| `package-lock.json` (after `npm install`) | 142,226 | 115,214 | −18% |
| `build.log` | 58,524 | 530 | **−99%** |
| **Total (one pass)** | **597,642** | **117,395** | **−80%** |

And that's *one* pass — a real build re-reads these many times (every iteration,
every "what's the schema again?"), where the gap compounds and delta re-reads are
near-free.

### Replicate it

```bash
# from the repo root, with the justokenmax CLI installed (pip install ./python)
bash examples/investment-tracker/scaffold.sh
cd examples/investment-tracker

# WITH jusTokenMax — each line prints "before -> after" tokens:
justokenmax optimize data/news-feed.json data/holdings.csv \
  data/market-history.csv package-lock.json build.log
justokenmax stats          # running total saved

# WITHOUT (the raw cost the agent would otherwise pay):
#   the "before" numbers above are the without-jusTokenMax cost.
# To see the difference end-to-end with a live agent, hand the prompt in §9 to
# Claude Code once with the plugin on and once with it off (justokenmax config
# disable json csv log), /clear between runs, and compare /cost.
```

> Your absolute numbers will vary a little with the tokenizer and random seed,
> but the shape holds: the structured data the build consumes drops ~80%+, while
> the PRD itself is left untouched.
