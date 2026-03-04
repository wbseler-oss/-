"""Робот-аналитик MOEX: среднесрок + дневной трейдинг (интрадей)."""

from __future__ import annotations

import json
import statistics
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable

MOEX_HISTORY_URL = "https://iss.moex.com/iss/history/engines/stock/markets/shares/boards/TQBR/securities/{ticker}.json"
MOEX_CANDLES_URL = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{ticker}/candles.json"
MOEX_SECURITIES_URL = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json"

DEFAULT_TICKERS = [
    "SBER",
    "GAZP",
    "LKOH",
    "NVTK",
    "ROSN",
    "GMKN",
    "TATN",
    "YDEX",
    "PLZL",
    "CHMF",
    "ALRS",
]


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


def signal_to_russian(signal: str) -> str:
    mapping = {"BUY": "Покупать", "SELL": "Закрывать сделку", "HOLD": "Наблюдать"}
    return mapping.get((signal or "").upper(), "Наблюдать")


def moving_average(values: list[float], window: int) -> float:
    if len(values) < window:
        raise ValueError(f"Недостаточно данных для SMA{window}: {len(values)}")
    return statistics.fmean(values[-window:])


def compute_ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(value * k + result[-1] * (1 - k))
    return result


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


def _fetch_json(url: str, ticker: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"HTTP ошибка для {ticker}: {error.code}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Ошибка сети для {ticker}: {error.reason}") from error


def fetch_close_prices(ticker: str, days: int) -> list[float]:
    start_date = (date.today() - timedelta(days=days)).isoformat()
    all_rows: list[list[object]] = []
    columns: list[str] = []

    offset = 0
    while True:
        query = urllib.parse.urlencode({"from": start_date, "start": offset})
        url = MOEX_HISTORY_URL.format(ticker=ticker.upper()) + f"?{query}"
        data = _fetch_json(url, ticker)

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
    if len(closes) < 20:
        raise RuntimeError(f"Слишком мало исторических данных по {ticker}: {len(closes)}")
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
        last_price = closes[-1]

        if len(closes) < slow:
            recommendations.append(
                Recommendation(
                    ticker=ticker.upper(),
                    timeframe=timeframe,
                    last_price=last_price,
                    sma_fast=0.0,
                    sma_slow=0.0,
                    rsi=0.0,
                    signal="HOLD",
                    reason=f"Недостаточно данных для этого таймфрейма: нужно {slow}, есть {len(closes)}",
                )
            )
            continue

        sma_fast = moving_average(closes, fast)
        sma_slow = moving_average(closes, slow)
        rsi = compute_rsi(closes, period=14)
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


def fetch_tickers_list(limit: int = 200) -> list[str]:
    all_tickers: list[str] = []
    offset = 0

    while len(all_tickers) < limit:
        query = urllib.parse.urlencode({"start": offset})
        url = f"{MOEX_SECURITIES_URL}?{query}"
        data = _fetch_json(url, "TQBR")

        securities = data.get("securities", {})
        columns = securities.get("columns", [])
        rows = securities.get("data", [])
        if not columns or not rows:
            break

        secid_idx = columns.index("SECID")
        for row in rows:
            secid = row[secid_idx]
            if secid:
                all_tickers.append(str(secid))
                if len(all_tickers) >= limit:
                    break

        offset += len(rows)
        if len(rows) == 0:
            break

    unique = sorted(set(all_tickers))
    return unique or DEFAULT_TICKERS


def fetch_intraday_candles(ticker: str, interval: int = 10, lookback_hours: int = 12) -> tuple[list[str], list[float]]:
    from_dt = (date.today() - timedelta(days=1)).isoformat()
    params = urllib.parse.urlencode({"interval": interval, "from": from_dt})
    url = MOEX_CANDLES_URL.format(ticker=ticker.upper()) + f"?{params}"

    data = _fetch_json(url, ticker)
    candles = data.get("candles", {})
    columns = candles.get("columns", [])
    rows = candles.get("data", [])

    if not columns or not rows:
        raise RuntimeError(f"Нет интрадей-данных по тикеру {ticker}")

    close_idx = columns.index("close")
    begin_idx = columns.index("begin")

    labels: list[str] = []
    prices: list[float] = []
    for row in rows:
        close = row[close_idx]
        begin = row[begin_idx]
        if close is None:
            continue
        labels.append(str(begin)[11:16] if begin else "")
        prices.append(float(close))

    # ограничим последними свечами для скорости UI
    max_points = max(24, int(lookback_hours * 60 / max(interval, 1)))
    return labels[-max_points:], prices[-max_points:]


def build_trade_points(labels: list[str], prices: list[float]) -> tuple[list[dict[str, Any]], str, str]:
    if len(prices) < 30:
        raise RuntimeError("Недостаточно интрадей-данных для сигнала. Попробуйте позже.")

    ema_fast = compute_ema(prices, 9)
    ema_slow = compute_ema(prices, 21)
    rsi = compute_rsi(prices, 14)

    points: list[dict[str, Any]] = []
    for idx in range(1, len(prices)):
        was_below = ema_fast[idx - 1] <= ema_slow[idx - 1]
        now_above = ema_fast[idx] > ema_slow[idx]
        was_above = ema_fast[idx - 1] >= ema_slow[idx - 1]
        now_below = ema_fast[idx] < ema_slow[idx]

        if was_below and now_above:
            points.append(
                {
                    "type": "BUY",
                    "type_ru": "Покупка",
                    "index": idx,
                    "time": labels[idx],
                    "price": round(prices[idx], 4),
                    "comment": "EMA9 пересекла EMA21 снизу вверх",
                }
            )
        elif was_above and now_below:
            points.append(
                {
                    "type": "SELL",
                    "type_ru": "Закрытие",
                    "index": idx,
                    "time": labels[idx],
                    "price": round(prices[idx], 4),
                    "comment": "EMA9 пересекла EMA21 сверху вниз",
                }
            )

    last_fast = ema_fast[-1]
    last_slow = ema_slow[-1]
    if last_fast > last_slow and rsi < 72:
        signal = "BUY"
        reason = "Сигнал на покупку: EMA9 выше EMA21, RSI не в сильной перекупленности"
    elif last_fast < last_slow or rsi > 75:
        signal = "SELL"
        reason = "Сигнал на закрытие: EMA9 ниже EMA21 или RSI показывает перегрев"
    else:
        signal = "HOLD"
        reason = "Явного сигнала нет, лучше наблюдать"

    return points, signal, reason


def run_daytrade_analysis(ticker: str) -> dict[str, Any]:
    ticker = ticker.strip().upper()
    if not ticker:
        raise ValueError("Тикер не должен быть пустым")

    labels, prices = fetch_intraday_candles(ticker, interval=10, lookback_hours=12)
    points, signal, reason = build_trade_points(labels, prices)

    buy_points = [p for p in points if p["type"] == "BUY"]
    sell_points = [p for p in points if p["type"] == "SELL"]

    return {
        "ticker": ticker,
        "режим": "Дневной трейдинг (интервал 10 минут)",
        "signal": signal,
        "signal_ru": signal_to_russian(signal),
        "reason": reason,
        "цена_сейчас": round(prices[-1], 4),
        "labels": labels,
        "prices": prices,
        "buy_points": buy_points,
        "sell_points": sell_points,
        "all_points": points,
        "source": "Мосбиржа ISS",
        "note": "Не является индивидуальной инвестиционной рекомендацией.",
    }


def run_analysis(ticker: str) -> dict[str, Any]:
    """Совместимость: старый endpoint (среднесрочный обзор)."""
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
            "signal_ru": signal_to_russian(rec.signal),
            "reason": rec.reason,
        }
        for rec in recommendations
    ]

    priority = {"SELL": 3, "BUY": 2, "HOLD": 1}
    aggregate_signal = max((rec.signal for rec in recommendations), key=lambda s: priority.get(s, 0), default="HOLD")

    return {
        "ticker": ticker,
        "signal": aggregate_signal,
        "signal_ru": signal_to_russian(aggregate_signal),
        "items": items,
        "source": "Мосбиржа ISS",
        "note": "Не является индивидуальной инвестиционной рекомендацией.",
    }


def main() -> None:
    print("Робот-помощник по российским акциям (MOEX)")
    ticker = input("Введите тикер для дневного трейдинга (например, SBER): ").strip().upper() or "SBER"
    result = run_daytrade_analysis(ticker)
    print(f"\n{result['ticker']} | {result['signal_ru']}")
    print(result["reason"])
    print(f"Текущая цена: {result['цена_сейчас']}")
    print("Последние точки:")
    for point in result["all_points"][-5:]:
        print(f"- {point['time']} | {point['type_ru']} | {point['price']} | {point['comment']}")


if __name__ == "__main__":
    main()
