"""Консольный робот-аналитик по российским акциям (MOEX)."""

from __future__ import annotations

import json
import statistics
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

MOEX_HISTORY_URL = "https://iss.moex.com/iss/history/engines/stock/markets/shares/boards/TQBR/securities/{ticker}.json"


@dataclass
class Recommendation:
    ticker: str
    timeframe: str
    last_price: float
    sma_fast: float
    sma_slow: float
    rsi: float
    signal: str
    reason: str


def moving_average(values: list[float], window: int) -> float:
    if len(values) < window:
        raise ValueError(f"Недостаточно данных для SMA{window}: {len(values)}")
    return statistics.fmean(values[-window:])


def compute_rsi(values: list[float], period: int = 14) -> float:
    if len(values) <= period:
        raise ValueError(f"Недостаточно данных для RSI{period}: {len(values)}")

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        if delta >= 0:
            gains.append(delta)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(-delta)

    avg_gain = statistics.fmean(gains[-period:])
    avg_loss = statistics.fmean(losses[-period:])

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def classify_signal(last_price: float, sma_fast: float, sma_slow: float, rsi: float) -> tuple[str, str]:
    trend_up = last_price > sma_fast > sma_slow
    trend_down = last_price < sma_fast < sma_slow

    if trend_up and rsi < 70:
        return "BUY", "Восходящий тренд и RSI без перекупленности"
    if trend_down and rsi > 30:
        return "SELL", "Нисходящий тренд, слабая структура цены"
    return "HOLD", "Смешанные сигналы — лучше подождать"


def parse_close_prices(rows: Iterable[list[object]], columns: list[str]) -> list[float]:
    close_idx = columns.index("CLOSE")
    legal_close_idx = columns.index("LEGALCLOSEPRICE")

    closes: list[float] = []
    for row in rows:
        value = row[close_idx] if row[close_idx] is not None else row[legal_close_idx]
        if value is not None:
            closes.append(float(value))
    return closes


def fetch_close_prices(ticker: str, days: int) -> list[float]:
    start_date = (date.today() - timedelta(days=days)).isoformat()
    all_rows: list[list[object]] = []
    columns: list[str] = []

    offset = 0
    while True:
        query = urllib.parse.urlencode({"from": start_date, "start": offset})
        url = MOEX_HISTORY_URL.format(ticker=ticker.upper()) + f"?{query}"

        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"HTTP ошибка для {ticker}: {error.code}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Ошибка сети для {ticker}: {error.reason}") from error

        history = data.get("history", {})
        page_columns = history.get("columns", [])
        page_rows = history.get("data", [])

        if not page_columns:
            break
        if not columns:
            columns = page_columns

        if not page_rows:
            break

        all_rows.extend(page_rows)
        offset += len(page_rows)

    if not columns or not all_rows:
        raise RuntimeError(f"Нет данных по тикеру {ticker}. Проверьте символ на MOEX.")

    closes = parse_close_prices(all_rows, columns)
    if len(closes) < 150:
        raise RuntimeError(f"Недостаточно данных для долгосрочного анализа (SMA150): {len(closes)}")
    return closes


def analyze_ticker(ticker: str) -> list[Recommendation]:
    closes = fetch_close_prices(ticker, days=365)

    timeframes = {
        "Краткосрок (2-4 недели)": (5, 20),
        "Среднесрок (1-3 месяца)": (20, 50),
        "Долгосрок (6-12 месяцев)": (50, 150),
    }

    recommendations: list[Recommendation] = []
    for timeframe, (fast, slow) in timeframes.items():
        sma_fast = moving_average(closes, fast)
        sma_slow = moving_average(closes, slow)
        rsi = compute_rsi(closes, period=14)
        last_price = closes[-1]
        signal, reason = classify_signal(last_price, sma_fast, sma_slow, rsi)

        recommendations.append(
            Recommendation(
                ticker=ticker.upper(),
                timeframe=timeframe,
                last_price=last_price,
                sma_fast=sma_fast,
                sma_slow=sma_slow,
                rsi=rsi,
                signal=signal,
                reason=reason,
            )
        )

    return recommendations


def print_recommendations(recommendations: list[Recommendation]) -> None:
    for rec in recommendations:
        print(f"\n[{rec.ticker}] {rec.timeframe}")
        print(f"Цена: {rec.last_price:.2f}")
        print(f"SMA fast: {rec.sma_fast:.2f} | SMA slow: {rec.sma_slow:.2f} | RSI14: {rec.rsi:.2f}")
        print(f"Рекомендация: {rec.signal} — {rec.reason}")


def main() -> None:
    print("Робот-помощник по российским акциям (MOEX)")
    print("Это не индивидуальная инвестиционная рекомендация.")
    raw = input(
        "Введите тикеры через запятую (пример: SBER,GAZP,LKOH) или Enter для списка по умолчанию: "
    ).strip()

    tickers = ["SBER", "GAZP", "LKOH", "ROSN", "NVTK"] if not raw else [x.strip().upper() for x in raw.split(",") if x.strip()]

    for ticker in tickers:
        try:
            recommendations = analyze_ticker(ticker)
            print_recommendations(recommendations)
        except Exception as error:
            print(f"\n[{ticker}] Ошибка анализа: {error}")


def run_analysis(ticker: str):
    """
    Обертка для веб-сервиса.
    Возвращает dict с агрегированным сигналом и деталями по таймфреймам.
    """
    ticker = ticker.strip().upper()
    if not ticker:
        raise ValueError("Тикер не должен быть пустым")

    recommendations = analyze_ticker(ticker)
    items = [
        {
            "timeframe": rec.timeframe,
            "last_price": round(rec.last_price, 4),
            "sma_fast": round(rec.sma_fast, 4),
            "sma_slow": round(rec.sma_slow, 4),
            "rsi": round(rec.rsi, 2),
            "signal": rec.signal,
            "reason": rec.reason,
        }
        for rec in recommendations
    ]

    priority = {"SELL": 3, "BUY": 2, "HOLD": 1}
    aggregate_signal = max((rec.signal for rec in recommendations), key=lambda s: priority.get(s, 0), default="HOLD")

    return {
        "ticker": ticker,
        "signal": aggregate_signal,
        "items": items,
        "source": "MOEX ISS",
        "note": "Не является индивидуальной инвестиционной рекомендацией.",
    }


if __name__ == "__main__":
    main()
