"""Профессиональный интрадей-аналитик MOEX (учебный, без гарантий)."""

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

DEFAULT_TICKERS = ["SBER", "GAZP", "LKOH", "ROSN", "NVTK", "GMKN", "TATN", "PLZL", "CHMF", "ALRS", "MAGN", "MOEX", "MTSS"]


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


def compute_rsi_series(values: list[float], period: int = 14) -> list[float]:
    if len(values) < period + 1:
        return [50.0 for _ in values]
    out = [50.0]
    for i in range(1, len(values)):
        window = values[max(0, i - period): i + 1]
        if len(window) < 2:
            out.append(50.0)
            continue
        gains, losses = [], []
        for j in range(1, len(window)):
            diff = window[j] - window[j - 1]
            gains.append(max(diff, 0.0))
            losses.append(max(-diff, 0.0))
        avg_gain = statistics.fmean(gains) if gains else 0.0
        avg_loss = statistics.fmean(losses) if losses else 0.0
        if avg_loss == 0:
            out.append(100.0)
        else:
            rs = avg_gain / avg_loss
            out.append(100 - 100 / (1 + rs))
    return out


def compute_rsi(values: list[float], period: int = 14) -> float:
    return compute_rsi_series(values, period)[-1]


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


def compute_vwap(highs: list[float], lows: list[float], closes: list[float], volumes: list[float]) -> list[float]:
    cumulative_pv = 0.0
    cumulative_vol = 0.0
    vwap = []
    for h, l, c, v in zip(highs, lows, closes, volumes):
        typical = (h + l + c) / 3
        cumulative_pv += typical * max(v, 0.0)
        cumulative_vol += max(v, 0.0)
        vwap.append(cumulative_pv / cumulative_vol if cumulative_vol > 0 else c)
    return vwap


def compute_atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float]:
    if not closes:
        return []
    trs = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    atr = [trs[0]]
    alpha = 1 / period
    for tr in trs[1:]:
        atr.append(atr[-1] + alpha * (tr - atr[-1]))
    return atr


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
        data = _fetch_json(MOEX_HISTORY_URL.format(ticker=ticker.upper()) + f"?{query}", ticker)
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
    timeframes = {"Краткосрок (2-4 недели)": (5, 20), "Среднесрок (1-3 месяца)": (20, 50), "Долгосрок (6-12 месяцев)": (50, 150)}
    results: list[Recommendation] = []
    for timeframe, (fast, slow) in timeframes.items():
        last_price = closes[-1]
        if len(closes) < slow:
            results.append(Recommendation(ticker.upper(), timeframe, last_price, 0.0, 0.0, 0.0, "HOLD", f"Недостаточно данных: нужно {slow}, есть {len(closes)}"))
            continue
        sma_fast = moving_average(closes, fast)
        sma_slow = moving_average(closes, slow)
        rsi = compute_rsi(closes)
        if last_price > sma_fast > sma_slow and rsi < 70:
            signal, reason = "BUY", "Тренд вверх + RSI рабочий"
        elif last_price < sma_fast < sma_slow and rsi > 30:
            signal, reason = "SELL", "Тренд вниз"
        else:
            signal, reason = "HOLD", "Нейтрально"
        results.append(Recommendation(ticker.upper(), timeframe, last_price, sma_fast, sma_slow, rsi, signal, reason))
    return results


def fetch_tickers_list(limit: int = 250) -> list[str]:
    all_tickers: list[str] = []
    offset = 0
    while len(all_tickers) < limit:
        data = _fetch_json(f"{MOEX_SECURITIES_URL}?" + urllib.parse.urlencode({"start": offset}), "TQBR")
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


def fetch_intraday_bars(ticker: str, interval: int = 10, lookback_hours: int = 12) -> dict[str, list[float | str]]:
    from_dt = (date.today() - timedelta(days=1)).isoformat()
    params = urllib.parse.urlencode({"interval": interval, "from": from_dt})
    data = _fetch_json(MOEX_CANDLES_URL.format(ticker=ticker.upper()) + f"?{params}", ticker)
    candles = data.get("candles", {})
    columns = candles.get("columns", [])
    rows = candles.get("data", [])
    if not columns or not rows:
        raise RuntimeError(f"Нет интрадей-данных по {ticker}")

    idx = {name: columns.index(name) for name in ["open", "close", "high", "low", "begin", "volume"] if name in columns}
    labels, opens, highs, lows, closes, volumes = [], [], [], [], [], []

    for row in rows:
        if row[idx["close"]] is None:
            continue
        labels.append(str(row[idx["begin"]])[11:16] if row[idx["begin"]] else "")
        opens.append(float(row[idx["open"]]))
        highs.append(float(row[idx["high"]]))
        lows.append(float(row[idx["low"]]))
        closes.append(float(row[idx["close"]]))
        volumes.append(float(row[idx["volume"]]) if "volume" in idx and row[idx["volume"]] is not None else 0.0)

    max_points = max(42, int(lookback_hours * 60 / max(interval, 1)))
    return {
        "labels": labels[-max_points:],
        "open": opens[-max_points:],
        "high": highs[-max_points:],
        "low": lows[-max_points:],
        "close": closes[-max_points:],
        "volume": volumes[-max_points:],
    }


def _simulate_strategy(labels: list[str], closes: list[float], highs: list[float], lows: list[float], volumes: list[float]) -> dict[str, Any]:
    if len(closes) < 50:
        raise RuntimeError("Недостаточно свечей для надежного интрадей анализа")

    ema9 = compute_ema(closes, 9)
    ema21 = compute_ema(closes, 21)
    ema50 = compute_ema(closes, 50)
    rsi_s = compute_rsi_series(closes, 14)
    macd, macd_sig, macd_hist = compute_macd(closes)
    vwap = compute_vwap(highs, lows, closes, volumes)
    atr = compute_atr(highs, lows, closes, 14)

    trades = []
    points = []
    in_pos = False
    entry_price = 0.0
    entry_i = 0
    stop = 0.0
    take = 0.0

    for i in range(1, len(closes)):
        price = closes[i]
        trend_ok = price > ema50[i] and ema50[i] >= ema50[i - 1]
        momentum_ok = ema9[i] > ema21[i] and macd_hist[i] > 0 and 45 <= rsi_s[i] <= 68
        location_ok = price > vwap[i]
        atr_pct = (atr[i] / price) * 100 if price > 0 else 0
        volatility_ok = 0.10 <= atr_pct <= 2.0

        if not in_pos:
            cross_up = ema9[i - 1] <= ema21[i - 1] and ema9[i] > ema21[i]
            if cross_up and trend_ok and momentum_ok and location_ok and volatility_ok:
                in_pos = True
                entry_price = price
                entry_i = i
                stop = price - 1.2 * atr[i]
                take = price + 2.2 * atr[i]
                points.append({"type": "BUY", "type_ru": "Покупка", "index": i, "time": labels[i], "price": round(price, 4), "comment": "Вход: тренд+импульс+объём/волатильность"})
            continue

        # trailing stop
        stop = max(stop, price - 1.0 * atr[i])

        exit_reason = None
        if lows[i] <= stop:
            exit_reason = "Стоп-лосс/трейлинг"
            exit_price = stop
        elif highs[i] >= take:
            exit_reason = "Тейк-профит"
            exit_price = take
        elif ema9[i] < ema21[i] and rsi_s[i] > 55:
            exit_reason = "Сигнал разворота EMA"
            exit_price = price
        elif rsi_s[i] > 76 and macd_hist[i] < macd_hist[i - 1]:
            exit_reason = "Фиксация прибыли (перекупленность)"
            exit_price = price
        else:
            continue

        pnl_pct = ((exit_price - entry_price) / entry_price) * 100 if entry_price else 0.0
        trades.append(
            {
                "entry_index": entry_i,
                "exit_index": i,
                "entry_time": labels[entry_i],
                "exit_time": labels[i],
                "entry_price": round(entry_price, 4),
                "exit_price": round(exit_price, 4),
                "pnl_pct": round(pnl_pct, 3),
                "result": "WIN" if pnl_pct > 0 else "LOSS",
                "reason": exit_reason,
            }
        )
        points.append({"type": "SELL", "type_ru": "Закрытие", "index": i, "time": labels[i], "price": round(exit_price, 4), "comment": exit_reason})
        in_pos = False

    wins = [t for t in trades if t["pnl_pct"] > 0]
    losses = [t for t in trades if t["pnl_pct"] <= 0]
    total = len(trades)
    winrate = (len(wins) / total * 100) if total else 0.0
    gross_profit = sum(t["pnl_pct"] for t in wins)
    gross_loss = abs(sum(t["pnl_pct"] for t in losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)

    # текущий сигнал
    score = 0
    if closes[-1] > ema50[-1]:
        score += 1
    if ema9[-1] > ema21[-1]:
        score += 1
    if macd_hist[-1] > 0:
        score += 1
    if 45 <= rsi_s[-1] <= 68:
        score += 1
    if closes[-1] > vwap[-1]:
        score += 1

    if score >= 4:
        signal = "BUY"
        reason = "Сильный бычий набор фильтров (тренд/импульс/RSI/VWAP)"
    elif score <= 1:
        signal = "SELL"
        reason = "Преобладают медвежьи/слабые сигналы, лучше закрывать риск"
    else:
        signal = "HOLD"
        reason = "Нужны дополнительные подтверждения, сейчас лучше ждать"

    confidence = min(93, 45 + score * 10 + (8 if winrate >= 60 and total >= 3 else 0))

    return {
        "signal": signal,
        "signal_ru": signal_to_russian(signal),
        "reason": reason,
        "confidence": int(max(5, confidence)),
        "points": points,
        "trades": trades,
        "stats": {
            "total_trades": total,
            "wins": len(wins),
            "losses": len(losses),
            "winrate_pct": round(winrate, 2),
            "avg_trade_pct": round(statistics.fmean([t["pnl_pct"] for t in trades]), 3) if trades else 0.0,
            "profit_factor": round(profit_factor, 3),
        },
        "indicators": {
            "EMA9": round(ema9[-1], 4),
            "EMA21": round(ema21[-1], 4),
            "EMA50": round(ema50[-1], 4),
            "RSI14": round(rsi_s[-1], 2),
            "MACD_hist": round(macd_hist[-1], 5),
            "VWAP": round(vwap[-1], 4),
            "ATR14": round(atr[-1], 4),
        },
    }


def run_daytrade_analysis(ticker: str) -> dict[str, Any]:
    ticker = ticker.strip().upper()
    if not ticker:
        raise ValueError("Тикер не должен быть пустым")

    bars = fetch_intraday_bars(ticker, interval=10, lookback_hours=12)
    labels = [str(x) for x in bars["labels"]]
    closes = [float(x) for x in bars["close"]]
    highs = [float(x) for x in bars["high"]]
    lows = [float(x) for x in bars["low"]]
    volumes = [float(x) for x in bars["volume"]]

    sim = _simulate_strategy(labels, closes, highs, lows, volumes)
    points = sim["points"]

    return {
        "ticker": ticker,
        "режим": "Дневной трейдинг (10 минут)",
        "signal": sim["signal"],
        "signal_ru": sim["signal_ru"],
        "confidence": sim["confidence"],
        "reason": sim["reason"],
        "details": [
            "Стратегия: trend filter + momentum + VWAP + ATR risk-management",
            f"Сделок в окне: {sim['stats']['total_trades']}, winrate: {sim['stats']['winrate_pct']}%",
            f"Profit Factor: {sim['stats']['profit_factor']}",
        ],
        "indicators": sim["indicators"],
        "stats": sim["stats"],
        "trades": sim["trades"][-15:],
        "цена_сейчас": round(closes[-1], 4),
        "labels": labels,
        "prices": closes,
        "buy_points": [p for p in points if p["type"] == "BUY"],
        "sell_points": [p for p in points if p["type"] == "SELL"],
        "all_points": points,
        "source": "Мосбиржа ISS",
        "note": "Это учебная модель теханализа. Гарантировать 70-80% прибыльных сделок нельзя на реальном рынке.",
    }


def run_screener(limit: int = 60) -> dict[str, Any]:
    tickers = fetch_tickers_list(limit=limit)
    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        try:
            r = run_daytrade_analysis(ticker)
            st = r.get("stats", {})
            rows.append(
                {
                    "ticker": ticker,
                    "signal": r["signal"],
                    "signal_ru": r["signal_ru"],
                    "confidence": r["confidence"],
                    "price": r["цена_сейчас"],
                    "reason": r["reason"],
                    "winrate": st.get("winrate_pct", 0.0),
                    "profit_factor": st.get("profit_factor", 0.0),
                }
            )
        except Exception:
            continue

    priority = {"BUY": 0, "HOLD": 1, "SELL": 2}
    rows.sort(key=lambda x: (priority.get(x["signal"], 3), -x["confidence"], -x["winrate"]))
    return {"count": len(rows), "items": rows, "source": "Мосбиржа ISS"}


def run_analysis(ticker: str) -> dict[str, Any]:
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
    res = run_daytrade_analysis(ticker)
    print(f"{res['ticker']} -> {res['signal_ru']} ({res['confidence']}%)")
    print(res["reason"])


if __name__ == "__main__":
    main()
