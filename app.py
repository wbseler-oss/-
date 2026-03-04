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
    .wrap { max-width: 900px; margin: 0 auto; padding: 28px; }
    .card { background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10); border-radius: 18px; padding: 18px; box-shadow: 0 10px 25px rgba(0,0,0,.25); }
    h1 { margin: 0 0 8px; font-size: 28px; }
    p { margin: 0 0 16px; color: rgba(230,237,243,0.75); }
    form { display: flex; gap: 10px; flex-wrap: wrap; }
    input { flex: 1; min-width: 220px; padding: 12px 14px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.18); background: rgba(0,0,0,0.25); color: #e6edf3; outline: none; }
    button { padding: 12px 14px; border-radius: 12px; border: 0; background: #3b82f6; color: white; cursor: pointer; font-weight: 600; }
    button:hover { filter: brightness(1.05); }
    .row { display: grid; grid-template-columns: 1fr; gap: 12px; margin-top: 14px; }
    .pill { display: inline-block; padding: 6px 10px; border-radius: 999px; font-weight: 700; font-size: 12px; letter-spacing: 0.4px; }
    .buy { background: rgba(16,185,129,.18); border: 1px solid rgba(16,185,129,.35); color: #a7f3d0; }
    .sell { background: rgba(239,68,68,.18); border: 1px solid rgba(239,68,68,.35); color: #fecaca; }
    .hold { background: rgba(234,179,8,.18); border: 1px solid rgba(234,179,8,.35); color: #fde68a; }
    pre { white-space: pre-wrap; background: rgba(0,0,0,.25); border: 1px solid rgba(255,255,255,0.12); padding: 12px; border-radius: 14px; overflow: auto; }
    .muted { color: rgba(230,237,243,0.70); font-size: 13px; }
    a { color: #93c5fd; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>MOEX Робот-аналитик 🚀</h1>
      <p>Введите тикер (например: <b>SBER</b>, <b>GAZP</b>, <b>LKOH</b>) и получите сигналы.</p>

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
            <div class="muted">Результат</div>
            {% if result.get("signal") %}
              {% set s = result.get("signal","").upper() %}
              {% if "BUY" in s %}
                <span class="pill buy">BUY</span>
              {% elif "SELL" in s %}
                <span class="pill sell">SELL</span>
              {% else %}
                <span class="pill hold">HOLD</span>
              {% endif %}
            {% endif %}
            <pre>{{ result_text|e }}</pre>
            <div class="muted">
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


def _result_to_pretty_text(result) -> str:
    # Красивый вывод в <pre>
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        lines = []
        for k, v in result.items():
            lines.append(f"{k}: {v}")
        return "\n".join(lines)
    return str(result)


@app.get("/")
def home():
    return render_template_string(PAGE, ticker="SBER", result=None, result_text="", error=None)


@app.get("/analyze")
def analyze_page():
    ticker = (request.args.get("ticker") or "SBER").strip().upper()
    try:
        result = program.run_analysis(ticker)
        return render_template_string(
            PAGE,
            ticker=ticker,
            result=result if isinstance(result, dict) else {"signal": ""},
            result_text=_result_to_pretty_text(result),
            error=None,
        )
    except Exception as e:
        return render_template_string(PAGE, ticker=ticker, result=None, result_text="", error=str(e)), 500


@app.get("/api/analyze")
def analyze_api():
    ticker = (request.args.get("ticker") or "SBER").strip().upper()
    result = program.run_analysis(ticker)
    # Если результат строка — завернем в JSON
    if isinstance(result, str):
        return jsonify({"ticker": ticker, "output": result})
    return jsonify(result)


# Важно для Render:
# Gunicorn будет импортировать app:app, а этот блок нужен только для локального запуска.
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
