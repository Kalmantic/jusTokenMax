// InvestWatch — reference implementation (vanilla, no build step).
// Reads the scaffolded data, joins holdings <-> latest close <-> news per ticker.

const fmt = (n) => n.toLocaleString(undefined, { maximumFractionDigits: 0 });
const usd = (n) => "$" + n.toLocaleString(undefined, { maximumFractionDigits: 0 });

function parseCSV(text) {
  const [head, ...lines] = text.trim().split("\n");
  const cols = head.split(",");
  return lines.filter(Boolean).map((line) => {
    const cells = line.split(",");
    return Object.fromEntries(cols.map((c, i) => [c, cells[i]]));
  });
}

async function load() {
  const [news, holdingsCsv, marketCsv] = await Promise.all([
    fetch("../data/news-feed.json").then((r) => r.json()),
    fetch("../data/holdings.csv").then((r) => r.text()),
    fetch("../data/market-history.csv").then((r) => r.text()),
  ]);

  const holdings = parseCSV(holdingsCsv);
  const market = parseCSV(marketCsv);

  // latest close per ticker (later rows overwrite earlier)
  const lastClose = {};
  for (const row of market) lastClose[row.ticker] = parseFloat(row.close);

  // news + average sentiment per ticker
  const newsByTicker = {};
  for (const a of news.feed) (newsByTicker[a.ticker] ||= []).push(a);
  const sentiment = {};
  for (const [t, arr] of Object.entries(newsByTicker))
    sentiment[t] = arr.reduce((s, a) => s + a.sentiment, 0) / arr.length;

  // enrich holdings
  const rows = holdings.map((h) => {
    const shares = +h.shares, cost = +h.cost_basis, close = lastClose[h.ticker] || 0;
    const value = shares * close, pl = value - shares * cost;
    return { ticker: h.ticker, shares, cost, close, value, pl,
             sector: h.sector, account: h.account,
             sentiment: sentiment[h.ticker] ?? 0 };
  });

  return { rows, news: news.feed, sectors: [...new Set(rows.map((r) => r.sector))].sort() };
}

function badge(s) {
  const cls = s > 0.05 ? "pos" : s < -0.05 ? "neg" : "";
  return `<span class="badge ${cls}">${s >= 0 ? "+" : ""}${s.toFixed(2)}</span>`;
}

function renderCards(rows) {
  const value = rows.reduce((s, r) => s + r.value, 0);
  const pl = rows.reduce((s, r) => s + r.pl, 0);
  const avgSent = rows.length ? rows.reduce((s, r) => s + r.sentiment, 0) / rows.length : 0;
  const tickers = new Set(rows.map((r) => r.ticker)).size;
  const cards = [
    ["Market value", usd(value)],
    ["Unrealized P/L", `<span class="${pl >= 0 ? "pos" : "neg"}">${pl >= 0 ? "+" : ""}${usd(pl)}</span>`],
    ["Positions", fmt(rows.length) + ` · ${tickers} tickers`],
    ["Avg news sentiment", badge(avgSent)],
  ];
  document.getElementById("cards").innerHTML = cards
    .map(([l, v]) => `<div class="card"><div class="label">${l}</div><div class="value">${v}</div></div>`)
    .join("");
}

function renderTable(rows) {
  document.querySelector("#holdings tbody").innerHTML = rows.map((r) => `
    <tr>
      <td>${r.ticker}</td>
      <td class="num">${fmt(r.shares)}</td>
      <td class="num">$${r.cost.toFixed(2)}</td>
      <td class="num">$${r.close.toFixed(2)}</td>
      <td class="num">${usd(r.value)}</td>
      <td class="num ${r.pl >= 0 ? "pos" : "neg"}">${r.pl >= 0 ? "+" : ""}${usd(r.pl)}</td>
      <td>${r.sector}</td>
      <td class="num">${badge(r.sentiment)}</td>
    </tr>`).join("");
}

function renderNews(news, q) {
  const items = news
    .filter((a) => !q || a.ticker.toLowerCase().includes(q) || a.headline.toLowerCase().includes(q))
    .slice(0, 30);
  document.getElementById("news").innerHTML = items.map((a) => `
    <li>
      <strong>${a.ticker}</strong> · ${badge(a.sentiment)}<br>
      ${a.headline}
      <div class="meta">${a.source} · ${a.publishedAt.slice(0, 10)}</div>
    </li>`).join("");
}

(async function main() {
  // theme
  const themeBtn = document.getElementById("theme");
  const setTheme = (t) => { document.documentElement.dataset.theme = t;
    themeBtn.textContent = t === "dark" ? "☀️" : "🌙"; localStorage.iwTheme = t; };
  setTheme(localStorage.iwTheme || "light");
  themeBtn.onclick = () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");

  let data;
  try { data = await load(); }
  catch (e) {
    document.querySelector("main").innerHTML =
      `<div class="panel">Couldn't load data — run <code>bash ../scaffold.sh</code> and serve this folder over http.<br><small>${e}</small></div>`;
    return;
  }

  // sector filter
  const sectorSel = document.getElementById("sector");
  for (const s of data.sectors) sectorSel.add(new Option(s, s));

  let sort = { k: "value", dir: -1 };
  function apply() {
    const q = document.getElementById("search").value.toLowerCase().trim();
    const sec = sectorSel.value;
    let rows = data.rows.filter((r) =>
      (!sec || r.sector === sec) &&
      (!q || r.ticker.toLowerCase().includes(q) || r.sector.toLowerCase().includes(q)));
    rows.sort((a, b) => {
      const x = a[sort.k], y = b[sort.k];
      return (typeof x === "string" ? x.localeCompare(y) : x - y) * sort.dir;
    });
    renderCards(rows); renderTable(rows); renderNews(data.news, q);
  }

  document.querySelectorAll("#holdings th").forEach((th) => {
    th.onclick = () => { const k = th.dataset.k;
      sort = { k, dir: sort.k === k ? -sort.dir : (k === "ticker" || k === "sector" ? 1 : -1) }; apply(); };
  });
  document.getElementById("search").oninput = apply;
  sectorSel.onchange = apply;
  apply();
})();
