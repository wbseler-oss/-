import os
from flask import Flask, request, jsonify, render_template_string
import program

app = Flask(__name__)

PAGE = """
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MOEX Дневной Трейдер</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; margin: 0; background: #0b1220; color: #e6edf3; }
    .wrap { max-width: 1100px; margin: 0 auto; padding: 24px; }
    .card { background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10); border-radius: 16px; padding: 16px; margin-bottom: 12px; }
    .row { display: grid; grid-template-columns: 1.2fr 1fr; gap: 12px; }
    @media (max-width: 900px) { .row { grid-template-columns: 1fr; } }
    .controls { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
    select, button { padding: 10px 12px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.2); background: rgba(0,0,0,0.25); color: #e6edf3; }
    button { background: #2563eb; border: 0; cursor: pointer; font-weight: 600; }
    .pill { display:inline-block; padding: 6px 10px; border-radius: 999px; font-weight: 700; font-size: 12px; }
    .buy { background: rgba(16,185,129,.18); color:#a7f3d0; border:1px solid rgba(16,185,129,.35); }
    .sell { background: rgba(239,68,68,.18); color:#fecaca; border:1px solid rgba(239,68,68,.35); }
    .hold { background: rgba(234,179,8,.18); color:#fde68a; border:1px solid rgba(234,179,8,.35); }
    .muted { color: rgba(230,237,243,0.74); font-size: 13px; }
    ul { margin: 8px 0 0; padding-left: 18px; }
    li { margin-bottom: 6px; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Дневной трейдер MOEX 📈</h1>
      <p class="muted">Выберите акцию, нажмите «Анализ», и система покажет график + точки «Покупка» / «Закрытие сделки». Можно включить автообновление.</p>
      <div class="controls">
        <label for="ticker">Акция:</label>
        <select id="ticker"></select>
        <button id="analyzeBtn">Анализ</button>
        <label><input type="checkbox" id="autoRefresh" /> Обновлять в реальном времени (каждые 15 сек)</label>
      </div>
      <div class="muted" style="margin-top:8px;">API: <a style="color:#93c5fd" href="/api/daytrade/analyze?ticker=SBER">/api/daytrade/analyze?ticker=SBER</a></div>
    </div>

    <div class="row">
      <div class="card">
        <canvas id="priceChart" height="140"></canvas>
      </div>
      <div class="card">
        <h3>Текущий сигнал</h3>
        <div id="signalBlock" class="pill hold">Наблюдать</div>
        <p id="reason" class="muted">Нажмите «Анализ»</p>
        <div class="muted" id="lastPrice">Текущая цена: -</div>
        <div class="muted" id="source">Источник: -</div>
      </div>
    </div>

    <div class="card">
      <h3>Точки входа / выхода</h3>
      <ul id="points"></ul>
    </div>
  </div>

<script>
let chart;
let refreshTimer;

function signalClass(signal) {
  if (signal === 'BUY') return 'pill buy';
  if (signal === 'SELL') return 'pill sell';
  return 'pill hold';
}

async function loadTickers() {
  const res = await fetch('/api/tickers');
  const data = await res.json();
  const select = document.getElementById('ticker');
  select.innerHTML = '';
  (data.tickers || []).forEach(t => {
    const opt = document.createElement('option');
    opt.value = t;
    opt.textContent = t;
    if (t === 'SBER') opt.selected = true;
    select.appendChild(opt);
  });
}

function drawChart(labels, prices, buyPoints, sellPoints) {
  const ctx = document.getElementById('priceChart');

  const buyData = labels.map(() => null);
  buyPoints.forEach(p => { buyData[p.index] = p.price; });

  const sellData = labels.map(() => null);
  sellPoints.forEach(p => { sellData[p.index] = p.price; });

  if (chart) chart.destroy();
  chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'Цена', data: prices, borderColor: '#60a5fa', backgroundColor: 'rgba(96,165,250,.15)', tension: 0.25, pointRadius: 0 },
        { label: 'Покупка', data: buyData, borderColor: '#34d399', backgroundColor: '#34d399', pointRadius: 5, showLine: false },
        { label: 'Закрытие', data: sellData, borderColor: '#f87171', backgroundColor: '#f87171', pointRadius: 5, showLine: false }
      ]
    },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: '#e6edf3' } } },
      scales: {
        x: { ticks: { color: 'rgba(230,237,243,.75)' } },
        y: { ticks: { color: 'rgba(230,237,243,.75)' } }
      }
    }
  });
}

async function analyze() {
  const ticker = document.getElementById('ticker').value;
  const res = await fetch(`/api/daytrade/analyze?ticker=${encodeURIComponent(ticker)}`);
  const data = await res.json();

  if (!res.ok) {
    document.getElementById('reason').textContent = data.error || 'Ошибка анализа';
    return;
  }

  const signalBlock = document.getElementById('signalBlock');
  signalBlock.className = signalClass(data.signal);
  signalBlock.textContent = data.signal_ru || data.signal;

  document.getElementById('reason').textContent = data.reason || '-';
  document.getElementById('lastPrice').textContent = `Текущая цена: ${data['цена_сейчас']}`;
  document.getElementById('source').textContent = `Источник: ${data.source || '-'}`;

  drawChart(data.labels || [], data.prices || [], data.buy_points || [], data.sell_points || []);

  const points = document.getElementById('points');
  points.innerHTML = '';
  const lastPoints = (data.all_points || []).slice(-12);
  if (lastPoints.length === 0) {
    points.innerHTML = '<li>Точек входа/выхода пока нет.</li>';
  } else {
    lastPoints.forEach(p => {
      const li = document.createElement('li');
      li.textContent = `${p.time} — ${p.type_ru} по ${p.price} (${p.comment})`;
      points.appendChild(li);
    });
  }
}

function setupAutoRefresh() {
  const check = document.getElementById('autoRefresh');
  check.addEventListener('change', () => {
    if (check.checked) {
      analyze();
      refreshTimer = setInterval(analyze, 15000);
    } else {
      clearInterval(refreshTimer);
    }
  });
}

document.getElementById('analyzeBtn').addEventListener('click', analyze);
loadTickers().then(analyze);
setupAutoRefresh();
</script>
</body>
</html>
"""


@app.get("/")
def home():
    return render_template_string(PAGE)


@app.get("/api/tickers")
def api_tickers():
    try:
        tickers = program.fetch_tickers_list(limit=250)
    except Exception:
        tickers = program.DEFAULT_TICKERS
    return jsonify({"tickers": tickers})


@app.get("/api/daytrade/analyze")
def api_daytrade_analyze():
    ticker = (request.args.get("ticker") or "SBER").strip().upper()
    try:
        result = program.run_daytrade_analysis(ticker)
        return jsonify(result)
    except Exception as error:
        return jsonify({"ticker": ticker, "error": str(error)}), 500


# Совместимость со старым endpoint
@app.get("/api/analyze")
def api_analyze_legacy():
    ticker = (request.args.get("ticker") or "SBER").strip().upper()
    try:
        return jsonify(program.run_analysis(ticker))
    except Exception as error:
        return jsonify({"ticker": ticker, "error": str(error)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
