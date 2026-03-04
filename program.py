"""Профессиональный интрадей-аналитик MOEX (учебный)."""

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
    "SBER", "GAZP", "LKOH", "ROSN", "NVTK", "GMKN", "TATN", "PLZL", "CHMF", "ALRS", "MAGN", "MOEX", "MTSS"
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
    mapping = {"BUY": "КУПИТЬ", "SELL": "ПРОДАТЬ/ЗАКРЫТЬ", "HOLD": "ОЖИДАТЬ"}
    return mapping.get((signal or "").upper(), "ОЖИДАТЬ")


def _fetch_json(url: str, ticker: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"HTTP ошибка для {ticker}: {error.code}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Ошибка сети для {ticker}: {error.reason}") from error


def moving_average(values: list[float], window: int) -> float:
    if len(values) < window:
        raise ValueError(f"Недостаточно данных для SMA{window}: {len(values)}")
    return statistics.fmean(values[-window:])


def compute_ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2 / (period + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append(alpha * value + (1 - alpha) * out[-1])
    return out


def compute_rsi(values: list[float], period: int = 14) -> float:
    if len(values) <= period:
        raise ValueError(f"Недостаточно данных для RSI{period}: {len(values)}")

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))

    avg_gain = statistics.fmean(gains[-period:])
    avg_loss = statistics.fmean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def compute_macd(values: list[float]) -> tuple[list[float], list[float], list[float]]:
    ema12 = compute_ema(values, 12)
    ema26 = compute_ema(values, 26)
    macd_line = [a - b for a, b in zip(ema12, ema26)]
    signal_line = compute_ema(macd_line, 9)
    hist = [m - s for m, s in zip(macd_line, signal_line)]
    return macd_line, signal_line, hist


def compute_bollinger(values: list[float], period: int = 20, num_std: float = 2.0) -> tuple[float, float, float]:
    if len(values) < period:
        raise ValueError("Недостаточно данных для Bollinger")
    window = values[-period:]
    mid = statistics.fmean(window)
    std = statistics.pstdev(window)
    return mid - num_std * std, mid, mid + num_std * std


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
    rows_all: list[list[object]] = []
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

        rows_all.extend(page_rows)
        offset += len(page_rows)

    if not columns or not rows_all:
        raise RuntimeError(f"Нет данных по тикеру {ticker}")

    closes = parse_close_prices(rows_all, columns)
    if len(closes) < 20:
        raise RuntimeError(f"Слишком мало данных по {ticker}: {len(closes)}")
    return closes


def analyze_ticker(ticker: str) -> list[Recommendation]:
    closes = fetch_close_prices(ticker, days=365)
    timeframes = {
        "Краткосрок (2-4 недели)": (5, 20),
        "Среднесрок (1-3 месяца)": (20, 50),
        "Долгосрок (6-12 месяцев)": (50, 150),
    }
    results: list[Recommendation] = []
    for timeframe, (fast, slow) in timeframes.items():
        last_price = closes[-1]
        if len(closes) < slow:
            results.append(
                Recommendation(ticker.upper(), timeframe, last_price, 0.0, 0.0, 0.0, "HOLD", f"Недостаточно данных: нужно {slow}, есть {len(closes)}")
            )
            continue

        sma_fast = moving_average(closes, fast)
        sma_slow = moving_average(closes, slow)
        rsi = compute_rsi(closes)

        if last_price > sma_fast > sma_slow and rsi < 70:
            signal, reason = "BUY", "Тренд вверх + RSI в рабочей зоне"
        elif last_price < sma_fast < sma_slow and rsi > 30:
            signal, reason = "SELL", "Тренд вниз"
        else:
            signal, reason = "HOLD", "Нейтральный фон"

        results.append(Recommendation(ticker.upper(), timeframe, last_price, sma_fast, sma_slow, rsi, signal, reason))
    return results


def fetch_tickers_list(limit: int = 300) -> list[str]:
    all_tickers: list[str] = []
    offset = 0
    while len(all_tickers) < limit:
        query = urllib.parse.urlencode({"start": offset})
        data = _fetch_json(f"{MOEX_SECURITIES_URL}?{query}", "TQBR")
        sec = data.get("securities", {})
        columns = sec.get("columns", [])
        rows = sec.get("data", [])
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
    uniq = sorted(set(all_tickers))
    return uniq or DEFAULT_TICKERS


def fetch_intraday_candles(ticker: str, interval: int = 10, lookback_hours: int = 12) -> tuple[list[str], list[float], list[float]]:
    from_dt = (date.today() - timedelta(days=1)).isoformat()
    params = urllib.parse.urlencode({"interval": interval, "from": from_dt})
    data = _fetch_json(MOEX_CANDLES_URL.format(ticker=ticker.upper()) + f"?{params}", ticker)

    candles = data.get("candles", {})
    columns = candles.get("columns", [])
    rows = candles.get("data", [])
    if not columns or not rows:
        raise RuntimeError(f"Нет интрадей-данных по {ticker}")

    close_idx = columns.index("close")
    begin_idx = columns.index("begin")
    volume_idx = columns.index("volume") if "volume" in columns else None

    labels, prices, volumes = [], [], []
    for row in rows:
        close = row[close_idx]
        begin = row[begin_idx]
        if close is None:
            continue
        labels.append(str(begin)[11:16] if begin else "")
        prices.append(float(close))
        volumes.append(float(row[volume_idx]) if volume_idx is not None and row[volume_idx] is not None else 0.0)

    max_points = max(36, int(lookback_hours * 60 / max(1, interval)))
    return labels[-max_points:], prices[-max_points:], volumes[-max_points:]


def _intraday_score(prices: list[float], volumes: list[float]) -> dict[str, Any]:
    if len(prices) < 35:
        raise RuntimeError("Недостаточно интрадей-данных для уверенного сигнала")

    ema9 = compute_ema(prices, 9)
    ema21 = compute_ema(prices, 21)
    rsi = compute_rsi(prices, 14)
    macd_line, signal_line, hist = compute_macd(prices)
    bb_low, bb_mid, bb_high = compute_bollinger(prices, 20, 2)

    last_price = prices[-1]
    prev_price = prices[-2]

    score = 0
    reasons: list[str] = []

    if ema9[-1] > ema21[-1]:
        score += 1
        reasons.append("EMA9 выше EMA21")
    else:
        score -= 1
        reasons.append("EMA9 ниже EMA21")

    if hist[-1] > 0 and macd_line[-1] > signal_line[-1]:
        score += 1
        reasons.append("MACD в бычьей фазе")
    elif hist[-1] < 0:
        score -= 1
        reasons.append("MACD в медвежьей фазе")

    if 45 <= rsi <= 68:
        score += 1
        reasons.append("RSI в рабочем диапазоне")
    elif rsi >= 75:
        score -= 1
        reasons.append("RSI показывает перегрев")
    elif rsi <= 30:
        score += 1
        reasons.append("RSI в зоне перепроданности")

    if last_price < bb_low:
        score += 1
        reasons.append("Цена ниже нижней Bollinger (потенциал отскока)")
    elif last_price > bb_high:
        score -= 1
        reasons.append("Цена выше верхней Bollinger (риск отката)")

    avg_volume = statistics.fmean(volumes[-20:]) if len(volumes) >= 20 else 0.0
    if avg_volume > 0 and volumes[-1] > 1.35 * avg_volume:
        if last_price > prev_price:
            score += 1
            reasons.append("Импульс подтвержден объемом")
        else:
            score -= 1
            reasons.append("Высокий объем при снижении")

    if score >= 2:
        signal = "BUY"
        core_reason = "Суммарно бычий набор индикаторов"
    elif score <= -2:
        signal = "SELL"
        core_reason = "Суммарно медвежий набор индикаторов"
    else:
        signal = "HOLD"
        core_reason = "Сигналы смешанные, лучше ждать"

    confidence = min(95, 50 + abs(score) * 12)

    return {
        "signal": signal,
        "signal_ru": signal_to_russian(signal),
        "confidence": confidence,
        "reason": core_reason,
        "details": reasons,
        "ema9": round(ema9[-1], 4),
        "ema21": round(ema21[-1], 4),
        "rsi": round(rsi, 2),
        "macd_hist": round(hist[-1], 5),
        "bb_low": round(bb_low, 4),
        "bb_mid": round(bb_mid, 4),
        "bb_high": round(bb_high, 4),
    }


def build_trade_points(labels: list[str], prices: list[float]) -> list[dict[str, Any]]:
    ema9 = compute_ema(prices, 9)
    ema21 = compute_ema(prices, 21)
    points: list[dict[str, Any]] = []
    for i in range(1, len(prices)):
        if ema9[i - 1] <= ema21[i - 1] and ema9[i] > ema21[i]:
            points.append({"type": "BUY", "type_ru": "Покупка", "index": i, "time": labels[i], "price": round(prices[i], 4), "comment": "EMA9 пересекла EMA21 вверх"})
        elif ema9[i - 1] >= ema21[i - 1] and ema9[i] < ema21[i]:
            points.append({"type": "SELL", "type_ru": "Закрытие", "index": i, "time": labels[i], "price": round(prices[i], 4), "comment": "EMA9 пересекла EMA21 вниз"})
    return points


def run_daytrade_analysis(ticker: str) -> dict[str, Any]:
    ticker = ticker.strip().upper()
    if not ticker:
        raise ValueError("Тикер не должен быть пустым")

    labels, prices, volumes = fetch_intraday_candles(ticker, interval=10, lookback_hours=12)
    points = build_trade_points(labels, prices)
    scored = _intraday_score(prices, volumes)

    buy_points = [p for p in points if p["type"] == "BUY"]
    sell_points = [p for p in points if p["type"] == "SELL"]

    return {
        "ticker": ticker,
        "режим": "Дневной трейдинг (10 минут)",
        "signal": scored["signal"],
        "signal_ru": scored["signal_ru"],
        "confidence": scored["confidence"],
        "reason": scored["reason"],
        "details": scored["details"],
        "indicators": {
            "EMA9": scored["ema9"],
            "EMA21": scored["ema21"],
            "RSI14": scored["rsi"],
            "MACD_hist": scored["macd_hist"],
            "Bollinger_low": scored["bb_low"],
            "Bollinger_mid": scored["bb_mid"],
            "Bollinger_high": scored["bb_high"],
        },
        "цена_сейчас": round(prices[-1], 4),
        "labels": labels,
        "prices": prices,
        "buy_points": buy_points,
        "sell_points": sell_points,
        "all_points": points,
        "source": "Мосбиржа ISS",
        "note": "Учебная модель. Не является инвестиционной рекомендацией.",
    }


def run_screener(limit: int = 80) -> dict[str, Any]:
    tickers = fetch_tickers_list(limit=limit)
    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        try:
            result = run_daytrade_analysis(ticker)
            rows.append(
                {
                    "ticker": ticker,
                    "signal": result["signal"],
                    "signal_ru": result["signal_ru"],
                    "confidence": result["confidence"],
                    "price": result["цена_сейчас"],
                    "reason": result["reason"],
                }
            )
        except Exception:
            continue

    priority = {"BUY": 0, "HOLD": 1, "SELL": 2}
    rows.sort(key=lambda x: (priority.get(x["signal"], 3), -x["confidence"]))
    return {"count": len(rows), "items": rows, "source": "Мосбиржа ISS"}


def run_analysis(ticker: str) -> dict[str, Any]:
    """Совместимость со старым API."""
    ticker = ticker.strip().upper()
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
    aggregate = max((x["signal"] for x in items), key=lambda s: priority.get(s, 0), default="HOLD")
    return {
        "ticker": ticker,
        "signal": aggregate,
        "signal_ru": signal_to_russian(aggregate),
        "items": items,
        "source": "Мосбиржа ISS",
        "note": "Учебная модель. Не является инвестиционной рекомендацией.",
    }


def main() -> None:
    ticker = input("Введите тикер: ").strip().upper() or "SBER"
    result = run_daytrade_analysis(ticker)
    print(f"{result['ticker']} -> {result['signal_ru']} ({result['confidence']}%)")
    print(result["reason"])


if __name__ == "__main__":
    main()
