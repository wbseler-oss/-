from flask import Flask, request, jsonify
import program

app = Flask(__name__)

@app.route("/")
def home():
    return "MOEX аналитик работает 🚀"

@app.route("/analyze")
def analyze():
    ticker = request.args.get("ticker", "SBER")
    result = program.run_analysis(ticker)  # если у вас другая функция — скажите
    return jsonify(result)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
