import os
from flask import Flask, jsonify, render_template_string, request
import program

app = Flask(__name__)

PAGE = """
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Проф. Дневной Трейдер MOEX</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body { font-family: Inter, system-ui, Arial; margin: 0; background:#0b1220; color:#e6edf3; }
    .wrap { max-width: 1200px; margin:0 auto; padding:20px; }
    .card { background: rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.12); border-radius:16px; padding:16px; margin-bottom:12px; }
    .row { display:grid; grid-template-columns: 1.2fr 1fr; gap:12px; }
    @media (max-width: 1000px){ .row{ grid-template-columns:1fr; } }
    .controls { display:flex; flex-wrap:wrap; gap:10px; align-items:center; }
    select, button { padding:10px 12px; border-radius:10px; border:1px solid rgba(255,255,255,.2); background: rgba(0,0,0,.25); color:#e6edf3; }
    button { background:#2563eb; border:0; cursor:pointer; font-weight:700; }
    .pill { display:inline-block; padding:6px 10px; border-radius:999px; font-weight:700; font-size:12px; }
    .buy { background: rgba(16,185,129,.18); border:1px solid rgba(16,185,129,.35); color:#a7f3d0; }
    .sell { background: rgba(239,68,68,.18); border:1px solid rgba(239,68,68,.35); color:#fecaca; }
    .hold { background: rgba(234,179,8,.18); border:1px solid rgba(234,179,8,.35); color:#fde68a; }
    table { width:100%; border-collapse: collapse; font-size:13px; }
    th, td { border-bottom:1px solid rgba(255,255,255,.1); padding:8px; text-align:left; }
    th { color:#bfdbfe; }
    .muted { color: rgba(230,237,243,.74); font-size:13px; }
    .scroll { max-height:460px; overflow:auto; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Профессиональный дневной трейдер MOEX ⚡</h1>
      <p class="muted">Интрадей-анализ по техиндикаторам (EMA, RSI, MACD, Bollinger, объёмы), точки входа/выхода, скринер по российским акциям.</p>
      <div class="controls">
        <label>Акция:</label>
        <select id="ticker"></select>
        <button id="analyzeBtn">Анализ по акции</button>
        <button id="scanBtn">Анализ всех акций (скринер)</button>
        <label><input type="checkbox" id="autoRefresh" /> Реальное время (15 сек)</label>
      </div>
      <div class="muted" style="margin-top:8px;">API: /api/daytrade/analyze?ticker=SBER | /api/daytrade/screener?limit=80</div>
    </div>

    <div class="row">
      <div class="card">
        <canvas id="chart" height="130"></canvas>
      </div>
      <div class="card">
        <h3>Сигнал по выбранной акции</h3>
        <div id="signalPill" class="pill hold">ОЖИДАТЬ</div>
        <p id="reason" class="muted">Нажмите «Анализ по акции»</p>
        <div id="price" class="muted">Цена: -</div>
        <div id="confidence" class="muted">Уверенность: -</div>
        <div id="stats" class="muted">Статистика: -</div>
        <div class="muted" id="note"></div>
        <ul id="details" class="muted"></ul>
      </div>
    </div>

    <div class="card">
      <h3>Скринер всех акций (интрадей)</h3>
      <div class="scroll">
        <table>
          <thead>
            <tr>
              <th>Тикер</th>
              <th>Сигнал</th>
              <th>Уверенность</th>
              <th>Цена</th>
              <th>Причина</th>
              <th>Winrate</th>
              <th>PF</th>
            </tr>
          </thead>
          <tbody id="screenerBody"></tbody>
        </table>
      </div>
    </div>
  </div>

<script>
let chart;
let timer;

function pillClass(signal) {
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
    const o = document.createElement('option');
    o.value = t;
    o.textContent = t;
    if (t === 'SBER') o.selected = true;
    select.appendChild(o);
  });
}

function drawChart(labels, prices, buyPoints, sellPoints) {
  const buyData = labels.map(() => null);
  buyPoints.forEach(p => buyData[p.index] = p.price);
  const sellData = labels.map(() => null);
  sellPoints.forEach(p => sellData[p.index] = p.price);

  if (chart) chart.destroy();
  chart = new Chart(document.getElementById('chart'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        {label:'Цена', data:prices, borderColor:'#60a5fa', tension:0.25, pointRadius:0},
        {label:'Покупка', data:buyData, borderColor:'#34d399', backgroundColor:'#34d399', pointRadius:5, showLine:false},
        {label:'Продажа/Закрытие', data:sellData, borderColor:'#f87171', backgroundColor:'#f87171', pointRadius:5, showLine:false}
      ]
    },
    options: {
      plugins: { legend: { labels: { color: '#e6edf3' } } },
      scales: {
        x: { ticks: { color: 'rgba(230,237,243,.75)' } },
        y: { ticks: { color: 'rgba(230,237,243,.75)' } }
      }
    }
  });
}

async function analyzeOne() {
  const ticker = document.getElementById('ticker').value;
  const res = await fetch(`/api/daytrade/analyze?ticker=${encodeURIComponent(ticker)}`);
  const data = await res.json();
  if (!res.ok) {
    document.getElementById('reason').textContent = data.error || 'Ошибка';
    return;
  }

  const pill = document.getElementById('signalPill');
  pill.className = pillClass(data.signal);
  pill.textContent = data.signal_ru || data.signal;

  document.getElementById('reason').textContent = data.reason || '-';
  document.getElementById('price').textContent = `Цена: ${data['цена_сейчас']}`;
  document.getElementById('confidence').textContent = `Уверенность: ${data.confidence || '-'}%`;
  const st = data.stats || {};
  document.getElementById('stats').textContent = `Статистика: сделок ${st.total_trades ?? '-'}, winrate ${st.winrate_pct ?? '-'}%, PF ${st.profit_factor ?? '-'}`;
  document.getElementById('note').textContent = data.note || '';

  const details = document.getElementById('details');
  details.innerHTML = '';
  (data.details || []).slice(0, 6).forEach(x => {
    const li = document.createElement('li');
    li.textContent = x;
    details.appendChild(li);
  });

  drawChart(data.labels || [], data.prices || [], data.buy_points || [], data.sell_points || []);
}

async function analyzeScreener() {
  const res = await fetch('/api/daytrade/screener?limit=80');
  const data = await res.json();
  const body = document.getElementById('screenerBody');
  body.innerHTML = '';

  (data.items || []).forEach(row => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${row.ticker}</td><td>${row.signal_ru}</td><td>${row.confidence}%</td><td>${row.price}</td><td>${row.reason}</td><td>${row.winrate ?? '-'}%</td><td>${row.profit_factor ?? '-'}</td>`;
    body.appendChild(tr);
  });
}

function initRealtime() {
  const check = document.getElementById('autoRefresh');
  check.addEventListener('change', () => {
    if (check.checked) {
      analyzeOne();
      timer = setInterval(analyzeOne, 15000);
    } else {
      clearInterval(timer);
    }
  });
}

document.getElementById('analyzeBtn').addEventListener('click', analyzeOne);
document.getElementById('scanBtn').addEventListener('click', analyzeScreener);

loadTickers().then(() => {
  analyzeOne();
  analyzeScreener();
  initRealtime();
});
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
        tickers = program.fetch_tickers_list(limit=300)
    except Exception:
        tickers = program.DEFAULT_TICKERS
    return jsonify({"tickers": tickers})


@app.get("/api/daytrade/analyze")
def api_daytrade_analyze():
    ticker = (request.args.get("ticker") or "SBER").strip().upper()
    try:
        return jsonify(program.run_daytrade_analysis(ticker))
    except Exception as error:
        return jsonify({"ticker": ticker, "error": str(error)}), 500


@app.get("/api/daytrade/screener")
def api_daytrade_screener():
    limit = int(request.args.get("limit") or 80)
    limit = min(max(limit, 10), 300)
    try:
        return jsonify(program.run_screener(limit=limit))
    except Exception as error:
        return jsonify({"error": str(error)}), 500


# Легаси endpoint
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
