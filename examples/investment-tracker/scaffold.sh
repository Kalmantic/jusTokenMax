#!/usr/bin/env bash
# Scaffold the data inputs for the InvestWatch example (see PRD.md).
# These are the heavy files the build/app consumes — what jusTokenMax compresses.
# The reference app in ./app/ reads them; jusTokenMax compresses them for the agent.
set -e
cd "$(dirname "$0")"
mkdir -p data

# Shared ticker universe so holdings <-> market <-> news all join cleanly.
python3 - <<'PY'
import json
TICKERS = ("AAPL MSFT NVDA TSLA AMZN GOOGL META JPM XOM UNH BAC WMT PG KO PEP "
           "DIS NFLX ADBE CRM ORCL INTC AMD QCOM CSCO TXN IBM GE BA CAT MMM "
           "HON LMT RTX GS MS C WFC AXP V MA PYPL SQ SHOP UBER ABNB COIN PLTR "
           "SNOW NOW PANW CRWD DDOG ZS NET MDB TEAM WDAY OKTA TWLO HUBS").split()
json.dump(TICKERS, open("data/_tickers.json", "w"))
print(f"  {len(TICKERS)} tickers")
PY

# 1) news feed the tracker indexes on (big JSON array of articles)
python3 - <<'PY'
import json, random
random.seed(7)
T = json.load(open("data/_tickers.json"))
sources = ["Reuters","Bloomberg","WSJ","CNBC","FT","MarketWatch"]
body = ("Shares moved after the company reported results and updated guidance; "
        "analysts weighed the impact on margins, demand, and the broader sector. ") * 4
arts = [{
    "id": i, "ticker": random.choice(T),
    "headline": f"Markets react as update #{i} hits the wire",
    "body": body, "source": random.choice(sources),
    "publishedAt": f"2026-06-{(i%28)+1:02d}T1{i%9}:00:00Z",
    "sentiment": round(random.uniform(-1, 1), 3),
    "url": f"https://news.example.com/article/{i}",
} for i in range(800)]
json.dump({"feed": arts, "count": len(arts)}, open("data/news-feed.json","w"), indent=2)
PY

# 2) portfolio holdings (CSV) — one row per ticker per account
python3 - <<'PY'
import csv, json, random
random.seed(3)
T = json.load(open("data/_tickers.json"))
secs = ["Tech","Energy","Health","Finance","Consumer","Industrial"]
with open("data/holdings.csv","w",newline="") as f:
    w = csv.writer(f); w.writerow(["ticker","shares","cost_basis","sector","account"])
    for t in T:
        for a in range(random.randint(1,4)):
            w.writerow([t, random.randint(1,500), round(random.uniform(5,900),2),
                        random.choice(secs), f"acct-{a}"])
PY

# 3) daily market history (CSV) — 100 days per ticker
python3 - <<'PY'
import csv, json, random
random.seed(5)
T = json.load(open("data/_tickers.json"))
with open("data/market-history.csv","w",newline="") as f:
    w = csv.writer(f); w.writerow(["date","ticker","open","high","low","close","volume"])
    for t in T:
        price = random.uniform(20, 600)
        for d in range(100):
            price *= random.uniform(0.97, 1.03)
            o = round(price, 2)
            w.writerow([f"2026-{(d%12)+1:02d}-{(d%28)+1:02d}", t, o,
                        round(o*1.02,2), round(o*0.98,2), round(o*1.005,2),
                        random.randint(50_000, 9_000_000)])
PY

# 4) package-lock.json (after `npm install`) — the classic token sink
python3 - <<'PY'
import json
d={f"node_modules/pkg-{i}":{"version":f"1.{i}.0",
   "resolved":f"https://registry.npmjs.org/pkg-{i}/-/pkg-{i}-1.{i}.0.tgz",
   "integrity":"sha512-"+"A"*86,
   "dependencies":{f"dep-{j}":"^1.0.0" for j in range(6)}} for i in range(900)}
json.dump({"name":"investwatch","lockfileVersion":3,"packages":d}, open("package-lock.json","w"), indent=2)
PY

# 5) a noisy build log with a real error
{ for i in $(seq 1 3500); do echo "[12:00:0$((i%9))] vite: transforming src/module_$i.ts"; done;
  echo "ERROR: TS2345 in src/news/index.ts:88 — Argument of type 'Article' is not assignable"; } > build.log

echo "scaffolded InvestWatch inputs (run a static server to view ./app/):"
ls -la data/news-feed.json data/holdings.csv data/market-history.csv package-lock.json build.log 2>/dev/null | awk '{print "  "$9, $5" bytes"}'
