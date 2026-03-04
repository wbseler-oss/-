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
  <title>MOEX Аналитик</title>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; margin: 0; background: #0b1220; color: #e6edf3; }
    .wrap { max-width: 980px; margin: 0 auto; padding: 28px; }
    .card { background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10); border-radius: 18px; padding: 18px; box-shadow: 0 10px 25px rgba(0,0,0,.25); }
    h1 { margin: 0 0 8px; font-size: 28px; }
    p { margin: 0 0 16px; color: rgba(230,237,243,0.80); }
    form { display: flex; gap: 10px; flex-wrap: wrap; }
    input { flex: 1; min-width: 220px; padding: 12px 14px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.18); background: rgba(0,0,0,0.25); color: #e6edf3; outline: none; }
    button { padding: 12px 14px; border-radius: 12px; border: 0; background: #3b82f6; color: white; cursor: pointer; font-weight: 600; }
    button:hover { filter: brightness(1.05); }
    .row { display: grid; grid-template-columns: 1fr; gap: 12px; margin-top: 14px; }
    .pill { display: inline-block; padding: 6px 10px; border-radius: 999px; font-weight: 700; font-size: 12px; letter-spacing: 0.4px; }
    .buy { background: rgba(16,185,129,.18); border: 1px solid rgba(16,185,129,.35); color: #a7f3d0; }
    .sell { background: rgba(239,68,68,.18); border: 1px solid rgba(239,68,68,.35); color: #fecaca; }
    .hold { background: rgba(234,179,8,.18); border: 1px solid rgba(234,179,8,.35); color: #fde68a; }
    .muted { color: rgba(230,237,243,0.72); font-size: 13px; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
    table { width: 100%; border-collapse: collapse; margin-top: 10px; }
    th, td { text-align: left; padding: 8px; border-bottom: 1px solid rgba(255,255,255,0.10); font-size: 14px; }
    th { color: #bfdbfe; font-weight: 600; }
    .bar-wrap { margin-top: 6px; }
    .bar-label { font-size: 12px; color: rgba(230,237,243,0.80); margin-bottom: 4px; }
    .bar-bg { background: rgba(255,255,255,0.10); border-radius: 999px; overflow: hidden; height: 10px; }
    .bar-fill { height: 10px; background: linear-gradient(90deg, #3b82f6, #60a5fa); }
    .legend { display:flex; gap:12px; flex-wrap:wrap; font-size:12px; color: rgba(230,237,243,0.82); margin-top:10px; }
    a { color: #93c5fd; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>MOEX Робот-аналитик 🚀</h1>
      <p>Введите тикер (например: <b>SBER</b>, <b>GAZP</b>, <b>LKOH</b>) и получите понятную рекомендацию и мини‑график.</p>

      <form method="get" action="/analyze">
        <input name="ticker" value="{{ ticker|e }}" placeholder="Тикер (SBER)" autocomplete="off" />
        <button type="submit">Анализировать</button>
      </form>

      {% if error %}
        <div class="row">
          <div class="card" style="background: rgba(239,68,68,.12); border-color: rgba(239,68,68,.35);">
            <b>Ошибка:</b> {{ error|e }}
          </div>
        </div>
      {% endif %}

      {% if result %}
        <div class="row">
          <div class="card">
            <div class="muted">Итог по тикеру {{ result.get("ticker", ticker)|e }}</div>
            {% set s = result.get("signal", "HOLD") %}
            {% set sru = result.get("signal_ru", "Держать") %}
            {% if "BUY" in s %}
              <span class="pill buy">{{ sru }}</span>
            {% elif "SELL" in s %}
              <span class="pill sell">{{ sru }}</span>
            {% else %}
              <span class="pill hold">{{ sru }}</span>
            {% endif %}

            <div class="grid" style="margin-top:12px;">
              <div>
                <table>
                  <thead>
                    <tr>
                      <th>Таймфрейм</th>
                      <th>Сигнал</th>
                      <th>Цена</th>
                      <th>RSI</th>
                    </tr>
                  </thead>
                  <tbody>
                    {% for item in result.get("items", []) %}
                      <tr>
                        <td>{{ item.get("timeframe") }}</td>
                        <td>{{ item.get("signal_ru", item.get("signal")) }}</td>
                        <td>{{ "%.2f"|format(item.get("last_price", 0)) }}</td>
                        <td>{{ "%.2f"|format(item.get("rsi", 0)) }}</td>
                      </tr>
                    {% endfor %}
                  </tbody>
                </table>
              </div>

              <div>
                <div class="muted">Визуальный график (цена по таймфреймам)</div>
                {% for item in result.get("items", []) %}
                  <div class="bar-wrap">
                    <div class="bar-label">{{ item.get("timeframe") }} — {{ "%.2f"|format(item.get("last_price", 0)) }}</div>
                    <div class="bar-bg">
                      <div class="bar-fill" style="width: {{ item.get('price_percent', 0) }}%;"></div>
                    </div>
                  </div>
                {% endfor %}
                <div class="legend">
                  <span>Источник: {{ result.get("source", "Мосбиржа ISS") }}</span>
                  <span>{{ result.get("note", "Не является индивидуальной инвестиционной рекомендацией.") }}</span>
                </div>
              </div>
            </div>

            <div class="muted" style="margin-top:10px;">
              API: <a href="/api/analyze?ticker={{ ticker|e }}">/api/analyze?ticker={{ ticker|e }}</a>
            </div>
          </div>
        </div>
      {% endif %}

      <div class="muted" style="margin-top: 14px;">
        Примечание: на бесплатном тарифе Render сервис может “засыпать” и просыпаться до ~60 сек.
      </div>
    </div>
  </div>
</body>
</html>
"""


def _signal_to_russian(signal: str) -> str:
    mapping = {"BUY": "Покупать", "SELL": "Продавать", "HOLD": "Держать"}
    return mapping.get((signal or "").upper(), "Держать")


def _enrich_result_for_ui(result: dict) -> dict:
    items = result.get("items", [])
    prices = [float(item.get("last_price", 0) or 0) for item in items]
    max_price = max(prices) if prices else 1.0

    enriched_items = []
    for item in items:
        price = float(item.get("last_price", 0) or 0)
        enriched = dict(item)
        enriched["signal_ru"] = _signal_to_russian(str(item.get("signal", "HOLD")))
        enriched["price_percent"] = round((price / max_price) * 100, 2) if max_price > 0 else 0
        enriched_items.append(enriched)

    enriched_result = dict(result)
    enriched_result["items"] = enriched_items
    enriched_result["signal_ru"] = _signal_to_russian(str(result.get("signal", "HOLD")))
    enriched_result["source"] = result.get("source", "Мосбиржа ISS")
    return enriched_result


def _analyze_with_fallback(ticker: str):
    """Совместимость: используем run_analysis, а если его нет — собираем ответ из analyze_ticker."""
    run_analysis = getattr(program, "run_analysis", None)
    if callable(run_analysis):
        return run_analysis(ticker)

    analyze_ticker = getattr(program, "analyze_ticker", None)
    if not callable(analyze_ticker):
        raise AttributeError("В модуле program нет функций run_analysis и analyze_ticker")

    recommendations = analyze_ticker(ticker)
    items = []
    for rec in recommendations:
        items.append(
            {
                "timeframe": rec.timeframe,
                "last_price": round(rec.last_price, 4),
                "sma_fast": round(rec.sma_fast, 4),
                "sma_slow": round(rec.sma_slow, 4),
                "rsi": round(rec.rsi, 2),
                "signal": rec.signal,
                "reason": rec.reason,
            }
        )

    priority = {"SELL": 3, "BUY": 2, "HOLD": 1}
    aggregate_signal = max((item["signal"] for item in items), key=lambda s: priority.get(s, 0), default="HOLD")
    return {
        "ticker": ticker,
        "signal": aggregate_signal,
        "items": items,
        "source": "Мосбиржа ISS",
        "note": "Не является индивидуальной инвестиционной рекомендацией.",
    }


@app.get("/")
def home():
    return render_template_string(PAGE, ticker="SBER", result=None, error=None)


@app.get("/analyze")
def analyze_page():
    ticker = (request.args.get("ticker") or "SBER").strip().upper()
    try:
        result = _analyze_with_fallback(ticker)
        ui_result = _enrich_result_for_ui(result if isinstance(result, dict) else {"ticker": ticker, "signal": "HOLD", "items": []})
        return render_template_string(PAGE, ticker=ticker, result=ui_result, error=None)
    except Exception as error:
        return render_template_string(PAGE, ticker=ticker, result=None, error=str(error)), 500


@app.get("/api/analyze")
def analyze_api():
    ticker = (request.args.get("ticker") or "SBER").strip().upper()
    result = _analyze_with_fallback(ticker)
    if isinstance(result, str):
        return jsonify({"тикер": ticker, "результат": result})
    return jsonify(result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
