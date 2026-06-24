#!/usr/bin/env bash
# Scaffold the data inputs for the InvestWatch example (see PRD.md).
# These are the heavy files the build consumes — what jusTokenMax compresses.
set -e
cd "$(dirname "$0")"
mkdir -p data

# 1) news feed the tracker indexes on (big JSON array of articles)
python3 - <<'PY'
import json, random
random.seed(7)
tickers = ["AAPL","MSFT","NVDA","TSLA","AMZN","GOOGL","META","JPM","XOM","UNH"]
sources = ["Reuters","Bloomberg","WSJ","CNBC","FT","MarketWatch"]
body = ("Shares moved after the company reported results and updated guidance; "
        "analysts weighed the impact on margins, demand, and the broader sector. ") * 4
articles = [{
    "id": i,
    "ticker": random.choice(tickers),
    "headline": f"Markets react as ticker update #{i} hits the wire",
    "body": body,
    "source": random.choice(sources),
    "publishedAt": f"2026-06-{(i%28)+1:02d}T1{i%9}:00:00Z",
    "sentiment": round(random.uniform(-1, 1), 3),
    "url": f"https://news.example.com/article/{i}",
} for i in range(800)]
json.dump({"feed": articles, "count": len(articles)}, open("data/news-feed.json", "w"), indent=2)
PY

# 2) portfolio holdings (CSV)
python3 - <<'PY'
import csv, random
random.seed(3)
with open("data/holdings.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["ticker","shares","cost_basis","sector","account"])
    secs = ["Tech","Energy","Health","Finance","Consumer"]
    for i in range(3000):
        w.writerow([f"TKR{i:04d}", random.randint(1,500),
                    round(random.uniform(5,900),2), random.choice(secs),
                    f"acct-{i%6}"])
PY

# 3) daily market history (CSV)
python3 - <<'PY'
import csv, random
random.seed(5)
with open("data/market-history.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["date","ticker","open","high","low","close","volume"])
    for i in range(6000):
        o = round(random.uniform(10,500),2)
        w.writerow([f"2026-{(i%12)+1:02d}-{(i%28)+1:02d}", f"TKR{i%300:04d}",
                    o, round(o*1.03,2), round(o*0.97,2), round(o*1.01,2),
                    random.randint(10_000, 5_000_000)])
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

echo "scaffolded InvestWatch inputs:"
ls -la data/*.json data/*.csv package-lock.json build.log 2>/dev/null | awk '{print "  "$9, $5" bytes"}'
