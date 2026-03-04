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
  <title>Проф. интрадей-трейдер MOEX</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body { font-family: Inter, system-ui, Arial; margin:0; background:#0b1220; color:#e6edf3; }
    .wrap { max-width: 1200px; margin: 0 auto; padding: 20px; }
    .card { background: rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.12); border-radius:16px; padding:16px; margin-bottom:12px; }
    .controls { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
    input, button { padding:10px 12px; border-radius:10px; border:1px solid rgba(255,255,255,.2); background: rgba(0,0,0,.3); color:#e6edf3; }
    button { background:#2563eb; border:0; font-weight:700; cursor:pointer; }
    .row { display:grid; grid-template-columns: 1.2fr 1fr; gap:12px; }
    @media (max-width: 1000px) { .row { grid-template-columns:1fr; } }
    .pill { display:inline-block; padding:6px 10px; border-radius:999px; font-weight:700; font-size:12px; }
    .buy { background: rgba(16,185,129,.18); border:1px solid rgba(16,185,129,.35); color:#a7f3d0; }
    .sell { background: rgba(239,68,68,.18); border:1px solid rgba(239,68,68,.35); color:#fecaca; }
    .close { background: rgba(234,179,8,.18); border:1px solid rgba(234,179,8,.35); color:#fde68a; }
    table { width:100%; border-collapse: collapse; font-size:13px; }
    th, td { border-bottom:1px solid rgba(255,255,255,.1); padding:8px; text-align:left; }
    th { color:#bfdbfe; }
    tr.clickable { cursor:pointer; }
    tr.clickable:hover { background: rgba(59,130,246,.12); }
    .muted { color: rgba(230,237,243,.75); font-size:13px; }
    .scroll { max-height: 480px; overflow:auto; }
    .chips { display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; }
    .chip { padding:6px 10px; border-radius:999px; background:rgba(59,130,246,.18); border:1px solid rgba(59,130,246,.4); color:#bfdbfe; cursor:pointer; font-size:12px; }
    .chip:hover { filter: brightness(1.1); }
    .strength-wrap { margin-top:10px; }
    .strength-row { display:flex; height:12px; border-radius:999px; overflow:hidden; background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.14); }
    .bull-bar { background: linear-gradient(90deg,#10b981,#34d399); }
    .bear-bar { background: linear-gradient(90deg,#f87171,#ef4444); }

  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Профессиональный дневной трейдер MOEX</h1>
      <p class="muted">BUY = вход в лонг, SELL = вход в шорт, CLOSE = выйти из позиции.</p>
      <div class="controls">
        <input id="tickerInput" list="tickersList" placeholder="Поиск акции (например, SBER)" />
        <datalist id="tickersList"></datalist>
        <button id="analyzeBtn">Показать анализ</button>
        <button id="refreshRecoBtn">Обновить рекомендации 80%+</button>
        <label><input type="checkbox" id="autoRefresh" /> Автообновление (15 сек)</label>
      </div>
      <div class="muted" style="margin-top:8px;">API: /api/daytrade/analyze?ticker=SBER | /api/daytrade/recommended?limit=120&confidence=80</div>
    </div>

    <div class="row">
      <div class="card"><canvas id="chart" height="130"></canvas></div>
      <div class="card">
        <h3>Сигнал</h3>
        <div id="signalPill" class="pill close">ЗАКРЫТЬ СДЕЛКУ</div>
        <p id="reason" class="muted">Выберите акцию и нажмите анализ.</p>
        <div id="price" class="muted">Цена: -</div>
        <div id="confidence" class="muted">Уверенность: -</div>
        <div id="stats" class="muted">Статистика: -</div>
        <div id="regime" class="muted">Режим рынка: -</div>
        <div id="trendPhase" class="muted">Тренд-фаза: -</div>
        <div id="eodTarget" class="muted">Цель до конца дня: -</div>
        <div id="bias" class="muted">Сила рынка: -</div>
        <div class="strength-wrap">
          <div class="strength-row">
            <div id="bullBar" class="bull-bar" style="width:50%"></div>
            <div id="bearBar" class="bear-bar" style="width:50%"></div>
          </div>
          <div id="strengthText" class="muted" style="margin-top:6px;">Быки 50% / Медведи 50%</div>
        </div>
        <div id="note" class="muted"></div>
      </div>
    </div>

    <div class="card">
      <h3>Недавно анализировались</h3>
      <div id="recentList" class="chips"></div>
    </div>

    <div class="card">
      <h3>Рекомендуемые сейчас (уверенность 80%+)</h3>
      <div class="scroll">
        <table>
          <thead>
            <tr>
              <th>Тикер</th>
              <th>Сигнал</th>
              <th>Уверенность</th>
              <th>Цена</th>
              <th>Winrate</th>
              <th>PF</th>
              <th>Быки</th>
              <th>Медведи</th>
              <th>Режим рынка</th>
              <th>Причина</th>
            </tr>
          </thead>
          <tbody id="recoBody"></tbody>
        </table>
      </div>
    </div>
  </div>

<script>
let chart;
let timer;

const RECENT_KEY = 'recentTickersV1';

function getRecentTickers() {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch (e) {
    return [];
  }
}

function saveRecentTicker(ticker) {
  const t = (ticker || '').toUpperCase();
  if (!t) return;
  const list = getRecentTickers().filter(x => x !== t);
  list.unshift(t);
  localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, 12)));
}

function renderRecentTickers() {
  const wrap = document.getElementById('recentList');
  wrap.innerHTML = '';
  const list = getRecentTickers();
  if (!list.length) {
    wrap.innerHTML = '<span class="muted">Пока пусто — откройте анализ нескольких тикеров.</span>';
    return;
  }
  list.forEach(t => {
    const chip = document.createElement('button');
    chip.className = 'chip';
    chip.textContent = t;
    chip.addEventListener('click', () => analyzeTicker(t));
    wrap.appendChild(chip);
  });
}


function pillClass(signal) {
  if (signal === 'BUY') return 'pill buy';
  if (signal === 'SELL') return 'pill sell';
  return 'pill close';
}

async function loadTickers() {
  const res = await fetch('/api/tickers');
  const data = await res.json();
  const list = document.getElementById('tickersList');
  list.innerHTML = '';
  (data.tickers || []).forEach(t => {
    const o = document.createElement('option');
    o.value = t;
    list.appendChild(o);
  });
  document.getElementById('tickerInput').value = 'SBER';
}

function drawChart(labels, prices, forecastLabels, forecastPrices, eodTarget, eodLow, eodHigh, buyPoints, sellPoints, closePoints) {
  const histLabels = labels || [];
  const futureLabels = forecastLabels || [];
  const allLabels = histLabels.concat(futureLabels);
  const histLen = histLabels.length;

  const priceData = (prices || []).concat(futureLabels.map(() => null));
  const forecastData = histLabels.map(() => null).concat(forecastPrices || []);
  const eodLevelData = allLabels.map(() => (typeof eodTarget === "number" ? eodTarget : null));
  const eodLowData = allLabels.map(() => (typeof eodLow === "number" ? eodLow : null));
  const eodHighData = allLabels.map(() => (typeof eodHigh === "number" ? eodHigh : null));

  const buyData = allLabels.map(() => null);
  (buyPoints || []).forEach(p => { if (typeof p.index === 'number' && p.index < histLen) buyData[p.index] = p.price; });
  const sellData = allLabels.map(() => null);
  (sellPoints || []).forEach(p => { if (typeof p.index === 'number' && p.index < histLen) sellData[p.index] = p.price; });
  const closeData = allLabels.map(() => null);
  (closePoints || []).forEach(p => { if (typeof p.index === 'number' && p.index < histLen) closeData[p.index] = p.price; });

  if (chart) chart.destroy();
  chart = new Chart(document.getElementById('chart'), {
    type: 'line',
    data: {
      labels: allLabels,
      datasets: [
        {label:'Цена', data:priceData, borderColor:'#60a5fa', tension:0.25, pointRadius:0},
        {label:'Прогноз (тех-модель)', data:forecastData, borderColor:'#c084fc', borderDash:[6,6], tension:0.25, pointRadius:0},
        {label:'Цель до конца дня', data:eodLevelData, borderColor:'#f59e0b', borderDash:[10,6], tension:0, pointRadius:0},
        {label:'EOD нижняя граница', data:eodLowData, borderColor:'rgba(245,158,11,0.35)', borderDash:[3,5], tension:0, pointRadius:0},
        {label:'EOD верхняя граница', data:eodHighData, borderColor:'rgba(245,158,11,0.35)', borderDash:[3,5], tension:0, pointRadius:0},
        {label:'BUY (лонг)', data:buyData, borderColor:'#34d399', backgroundColor:'#34d399', pointRadius:5, showLine:false},
        {label:'SELL (шорт)', data:sellData, borderColor:'#f87171', backgroundColor:'#f87171', pointRadius:5, showLine:false},
        {label:'CLOSE (выход)', data:closeData, borderColor:'#fbbf24', backgroundColor:'#fbbf24', pointRadius:5, showLine:false},
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

async function analyzeTicker(ticker) {
  const t = (ticker || document.getElementById('tickerInput').value || 'SBER').trim().toUpperCase();
  if (!t) return;
  document.getElementById('tickerInput').value = t;

  const res = await fetch(`/api/daytrade/analyze?ticker=${encodeURIComponent(t)}`);
  const data = await res.json();
  if (!res.ok) {
    document.getElementById('reason').textContent = data.error || 'Ошибка анализа';
    return;
  }

  const pill = document.getElementById('signalPill');
  pill.className = pillClass(data.signal);
  pill.textContent = data.signal_ru || data.signal;

  document.getElementById('reason').textContent = data.reason || '-';
  document.getElementById('price').textContent = `Цена: ${data['цена_сейчас']}`;
  document.getElementById('confidence').textContent = `Уверенность: ${data.confidence || '-'}%`;
  const st = data.stats || {};
  document.getElementById('stats').textContent = `Сделок: ${st.total_trades ?? '-'} | Winrate: ${st.winrate_pct ?? '-'}% | PF: ${st.profit_factor ?? '-'}`;
  document.getElementById('regime').textContent = `Режим рынка: ${data.market_regime_ru || '-'}`;
  const ts = data.trend_start_time || '-';
  const te = data.trend_end_time || '-';
  const bulls = Number(data.bull_strength_pct ?? 50);
  const bears = Number(data.bear_strength_pct ?? 50);
  const eodTarget = Number(data.eod_target_price);
  const eodLow = Number(data.eod_target_low);
  const eodHigh = Number(data.eod_target_high);
  const eodBars = data.eod_remaining_bars ?? '-';
  document.getElementById('trendPhase').textContent = `Тренд-фаза: старт ${ts} | завершение ${te}`;
  document.getElementById('eodTarget').textContent = `Цель до конца дня: ${Number.isFinite(eodTarget) ? eodTarget.toFixed(2) : '-'} (диапазон ${Number.isFinite(eodLow) ? eodLow.toFixed(2) : '-'}–${Number.isFinite(eodHigh) ? eodHigh.toFixed(2) : '-'}, баров: ${eodBars})`;
  document.getElementById('bias').textContent = `Сила рынка: ${data.market_bias_ru || '-'}`;
  document.getElementById('bullBar').style.width = `${bulls}%`;
  document.getElementById('bearBar').style.width = `${bears}%`;
  document.getElementById('strengthText').textContent = `Быки ${bulls}% / Медведи ${bears}%`;
  document.getElementById('note').textContent = data.note || '';

  saveRecentTicker(t);
  renderRecentTickers();
  drawChart(data.labels || [], data.prices || [], data.forecast_labels || [], data.forecast_prices || [], data.eod_target_price, data.eod_target_low, data.eod_target_high, data.buy_points || [], data.sell_points || [], data.close_points || []);
}

async function loadRecommended() {
  const res = await fetch('/api/daytrade/recommended?limit=120&confidence=80');
  const data = await res.json();
  const body = document.getElementById('recoBody');
  body.innerHTML = '';

  (data.items || []).forEach(row => {
    const tr = document.createElement('tr');
    tr.className = 'clickable';
    tr.innerHTML = `<td>${row.ticker}</td><td>${row.signal_ru}</td><td>${row.confidence}%</td><td>${row.price}</td><td>${row.winrate}%</td><td>${row.profit_factor}</td><td>${row.bull_strength_pct ?? '-'}%</td><td>${row.bear_strength_pct ?? '-'}%</td><td>${row.market_regime_ru || '-'}</td><td>${row.reason}</td>`;
    tr.addEventListener('click', () => analyzeTicker(row.ticker));
    body.appendChild(tr);
  });
}

function initRealtime() {
  document.getElementById('autoRefresh').addEventListener('change', (e) => {
    if (e.target.checked) {
      analyzeTicker();
      loadRecommended();
      timer = setInterval(() => { analyzeTicker(); loadRecommended(); }, 15000);
    } else {
      clearInterval(timer);
    }
  });
}

document.getElementById('analyzeBtn').addEventListener('click', () => analyzeTicker());
document.getElementById('refreshRecoBtn').addEventListener('click', loadRecommended);

loadTickers().then(() => {
  renderRecentTickers();
  analyzeTicker('SBER');
  loadRecommended();
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
        return jsonify({"tickers": program.fetch_tickers_list(limit=300)})
    except Exception:
        return jsonify({"tickers": program.DEFAULT_TICKERS})


@app.get("/api/daytrade/analyze")
def api_daytrade_analyze():
    ticker = (request.args.get("ticker") or "SBER").strip().upper()
    try:
        return jsonify(program.run_daytrade_analysis(ticker))
    except Exception as error:
        return jsonify({"ticker": ticker, "error": str(error)}), 500


@app.get("/api/daytrade/recommended")
def api_daytrade_recommended():
    limit = min(max(int(request.args.get("limit") or 120), 10), 300)
    confidence = min(max(int(request.args.get("confidence") or 80), 50), 99)
    try:
        return jsonify(program.run_screener(limit=limit, confidence_threshold=confidence))
    except Exception as error:
        return jsonify({"error": str(error)}), 500


@app.get("/api/daytrade/screener")
def api_daytrade_screener_legacy():
    limit = min(max(int(request.args.get("limit") or 80), 10), 300)
    try:
        return jsonify(program.run_screener(limit=limit, confidence_threshold=80))
    except Exception as error:
        return jsonify({"error": str(error)}), 500


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
