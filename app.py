from flask import Flask, request, render_template_string
import os
import program

app = Flask(__name__)

HTML = """
<!doctype html>
<html>
<head>
    <title>MOEX Аналитик</title>
</head>
<body>
    <h1>MOEX Робот-Аналитик 🚀</h1>
    <form method="get" action="/analyze">
        <input type="text" name="ticker" placeholder="Введите тикер (например SBER)">
        <button type="submit">Анализировать</button>
    </form>
</body>
</html>
"""

@app.route("/")
def home():
    return HTML

@app.route("/analyze")
def analyze():
    ticker = request.args.get("ticker", "SBER")
    result = program.run_analysis(ticker)
    return f"<pre>{result}</pre>"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
