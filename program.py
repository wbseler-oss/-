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
    mapping = {
        "BUY": "КУПИТЬ (ЛОНГ)",
        "SELL": "ПРОДАТЬ (ШОРТ)",
        "CLOSE": "ЗАКРЫТЬ СДЕЛКУ",
    }
    return mapping.get((signal or "").upper(), "ЗАКРЫТЬ СДЕЛКУ")


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
    window = values[-period:]
    mid = statistics.fmean(window)
    std = statistics.pstdev(window)
    return mid - num_std * std, mid, mid + num_std * std


def compute_vwap(highs: list[float], lows: list[float], closes: list[float], volumes: list[float]) -> list[float]:
    pv_sum = 0.0
    vol_sum = 0.0
    out = []
    for h, l, c, v in zip(highs, lows, closes, volumes):
        tp = (h + l + c) / 3
        pv_sum += tp * max(v, 0.0)
        vol_sum += max(v, 0.0)
        out.append(pv_sum / vol_sum if vol_sum > 0 else c)
    return out


def compute_atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float]:
    trs = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    atr = [trs[0]]
    alpha = 1 / period
    for tr in trs[1:]:
        atr.append(atr[-1] + alpha * (tr - atr[-1]))
    return atr




def compute_adx(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float]:
    if not closes:
        return []

    tr_values = [highs[0] - lows[0]]
    plus_dm = [0.0]
    minus_dm = [0.0]
    for i in range(1, len(closes)):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)
        tr_values.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))

    alpha = 1 / period
    tr_smooth = [tr_values[0]]
    plus_smooth = [plus_dm[0]]
    minus_smooth = [minus_dm[0]]
    for i in range(1, len(closes)):
        tr_smooth.append(tr_smooth[-1] + alpha * (tr_values[i] - tr_smooth[-1]))
        plus_smooth.append(plus_smooth[-1] + alpha * (plus_dm[i] - plus_smooth[-1]))
        minus_smooth.append(minus_smooth[-1] + alpha * (minus_dm[i] - minus_smooth[-1]))

    plus_di, minus_di, dx = [0.0], [0.0], [0.0]
    for i in range(1, len(closes)):
        if tr_smooth[i] <= 0:
            plus_di.append(0.0)
            minus_di.append(0.0)
            dx.append(0.0)
            continue
        pdi = 100 * plus_smooth[i] / tr_smooth[i]
        mdi = 100 * minus_smooth[i] / tr_smooth[i]
        plus_di.append(pdi)
        minus_di.append(mdi)
        denom = pdi + mdi
        dx.append(100 * abs(pdi - mdi) / denom if denom else 0.0)

    adx = [dx[0]]
    for i in range(1, len(dx)):
        adx.append(adx[-1] + alpha * (dx[i] - adx[-1]))
    return adx

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
        data = _fetch_json(MOEX_HISTORY_URL.format(ticker=ticker.upper()) + "?" + urllib.parse.urlencode({"from": start_date, "start": offset}), ticker)
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
    out: list[Recommendation] = []
    for timeframe, (fast, slow) in timeframes.items():
        last = closes[-1]
        if len(closes) < slow:
            out.append(Recommendation(ticker.upper(), timeframe, last, 0.0, 0.0, 0.0, "CLOSE", f"Недостаточно данных: нужно {slow}, есть {len(closes)}"))
            continue
        sma_fast, sma_slow, rsi = moving_average(closes, fast), moving_average(closes, slow), compute_rsi(closes)
        if last > sma_fast > sma_slow and rsi < 70:
            sig, reason = "BUY", "Тренд вверх"
        elif last < sma_fast < sma_slow and rsi > 30:
            sig, reason = "SELL", "Тренд вниз"
        else:
            sig, reason = "CLOSE", "Сигналов для нового входа нет"
        out.append(Recommendation(ticker.upper(), timeframe, last, sma_fast, sma_slow, rsi, sig, reason))
    return out


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
        idx = columns.index("SECID")
        for row in rows:
            secid = row[idx]
            if secid:
                all_tickers.append(str(secid))
                if len(all_tickers) >= limit:
                    break
        offset += len(rows)
    return sorted(set(all_tickers)) or DEFAULT_TICKERS


def fetch_intraday_bars(ticker: str, interval: int = 10, lookback_hours: int = 12) -> dict[str, list[float | str]]:
    params = urllib.parse.urlencode({"interval": interval, "from": (date.today() - timedelta(days=1)).isoformat()})
    data = _fetch_json(MOEX_CANDLES_URL.format(ticker=ticker.upper()) + f"?{params}", ticker)
    candles = data.get("candles", {})
    columns = candles.get("columns", [])
    rows = candles.get("data", [])
    if not columns or not rows:
        raise RuntimeError(f"Нет интрадей-данных по {ticker}")

    idx = {k: columns.index(k) for k in ["open", "close", "high", "low", "begin", "volume"]}
    labels, opens, highs, lows, closes, volumes = [], [], [], [], [], []
    for row in rows:
        if row[idx["close"]] is None:
            continue
        labels.append(str(row[idx["begin"]])[11:16])
        opens.append(float(row[idx["open"]]))
        highs.append(float(row[idx["high"]]))
        lows.append(float(row[idx["low"]]))
        closes.append(float(row[idx["close"]]))
        volumes.append(float(row[idx["volume"]] or 0.0))

    keep = max(42, int(lookback_hours * 60 / max(interval, 1)))
    return {"labels": labels[-keep:], "open": opens[-keep:], "high": highs[-keep:], "low": lows[-keep:], "close": closes[-keep:], "volume": volumes[-keep:]}


def _simulate_strategy(labels: list[str], closes: list[float], highs: list[float], lows: list[float], volumes: list[float]) -> dict[str, Any]:
    if len(closes) < 50:
        raise RuntimeError("Недостаточно свечей для надежного интрадей анализа")

    ema9, ema21, ema50 = compute_ema(closes, 9), compute_ema(closes, 21), compute_ema(closes, 50)
    rsi = compute_rsi_series(closes, 14)
    _, _, macd_hist = compute_macd(closes)
    vwap = compute_vwap(highs, lows, closes, volumes)
    atr = compute_atr(highs, lows, closes, 14)
    adx = compute_adx(highs, lows, closes, 14)

    # Параметры трендовой модели: в боковике не торгуем, в тренде держим позицию до явного разворота.
    min_hold_bars = 8
    reversal_confirm_bars = 3
    initial_stop_atr = 1.6
    trend_trail_atr = 2.3
    reversal_trail_atr = 1.4
    break_even_arm_atr = 3.0
    break_even_lock_atr = 0.25
    adx_entry_threshold = 22.0
    adx_trend_threshold = 20.0
    adx_range_threshold = 16.0
    ema_gap_threshold = 0.12
    trend_band_threshold = 0.38

    trades, points = [], []
    pos = "FLAT"  # FLAT/LONG/SHORT
    entry_price, entry_i, stop = 0.0, 0, 0.0
    best_price, worst_price = 0.0, 0.0
    reversal_count = 0
    break_even_armed = False

    for i in range(1, len(closes)):
        price = closes[i]
        atr_pct = (atr[i] / price) * 100 if price else 0.0
        volatility_ok = 0.10 <= atr_pct <= 2.4
        ema_gap_pct = abs(ema21[i] - ema50[i]) / price * 100 if price else 0.0

        trend_up = price > ema50[i] and ema50[i] >= ema50[i - 1]
        trend_down = price < ema50[i] and ema50[i] <= ema50[i - 1]
        adx_strong = adx[i] >= adx_entry_threshold
        trend_strength_ok = ema_gap_pct >= ema_gap_threshold

        long_setup = (
            ema9[i] > ema21[i]
            and macd_hist[i] > 0
            and 47 <= rsi[i] <= 72
            and price > vwap[i]
            and adx_strong
            and trend_strength_ok
        )
        short_setup = (
            ema9[i] < ema21[i]
            and macd_hist[i] < 0
            and 28 <= rsi[i] <= 53
            and price < vwap[i]
            and adx_strong
            and trend_strength_ok
        )

        cross_up = ema9[i - 1] <= ema21[i - 1] and ema9[i] > ema21[i]
        cross_dn = ema9[i - 1] >= ema21[i - 1] and ema9[i] < ema21[i]

        if pos == "FLAT":
            if cross_up and trend_up and long_setup and volatility_ok:
                pos, entry_price, entry_i = "LONG", price, i
                stop = price - initial_stop_atr * atr[i]
                best_price, worst_price = highs[i], lows[i]
                reversal_count = 0
                break_even_armed = False
                points.append({"type": "BUY", "type_ru": "Покупка (лонг)", "index": i, "time": labels[i], "price": round(price, 4), "comment": "Вход в лонг: сильный тренд подтвержден"})
            elif cross_dn and trend_down and short_setup and volatility_ok:
                pos, entry_price, entry_i = "SHORT", price, i
                stop = price + initial_stop_atr * atr[i]
                best_price, worst_price = highs[i], lows[i]
                reversal_count = 0
                break_even_armed = False
                points.append({"type": "SELL", "type_ru": "Продажа (шорт)", "index": i, "time": labels[i], "price": round(price, 4), "comment": "Вход в шорт: сильный тренд подтвержден"})
            continue

        if pos == "LONG":
            best_price = max(best_price, highs[i])
            mfe = best_price - entry_price
            if (not break_even_armed) and mfe >= break_even_arm_atr * atr[i]:
                break_even_armed = True
                stop = max(stop, entry_price + break_even_lock_atr * atr[i])

            reverse_signal = ema9[i] < ema21[i] and macd_hist[i] < 0 and price < vwap[i] and price < ema50[i]
            adx_weakening = adx[i] < adx_trend_threshold
            reversal_count = reversal_count + 1 if reverse_signal else 0
            enough_hold = (i - entry_i) >= min_hold_bars
            clear_reversal = enough_hold and reversal_count >= reversal_confirm_bars and adx_weakening

            trail_atr = reversal_trail_atr if clear_reversal else trend_trail_atr
            stop = max(stop, best_price - trail_atr * atr[i])

            exit_reason = None
            if lows[i] <= stop:
                exit_price = stop
                if clear_reversal:
                    exit_reason = "Закрытие лонга: явный разворот подтвержден"
                elif break_even_armed:
                    exit_reason = "Закрытие лонга: трейлинг по тренду"
                else:
                    exit_reason = "Закрытие лонга: защитный стоп"
            elif clear_reversal and rsi[i] < 48:
                exit_price = price
                exit_reason = "Закрытие лонга: подтвержденный разворот (3 бара)"
            else:
                continue
            pnl = (exit_price - entry_price) / entry_price * 100
        else:  # SHORT
            worst_price = min(worst_price, lows[i])
            mfe = entry_price - worst_price
            if (not break_even_armed) and mfe >= break_even_arm_atr * atr[i]:
                break_even_armed = True
                stop = min(stop, entry_price - break_even_lock_atr * atr[i])

            reverse_signal = ema9[i] > ema21[i] and macd_hist[i] > 0 and price > vwap[i] and price > ema50[i]
            adx_weakening = adx[i] < adx_trend_threshold
            reversal_count = reversal_count + 1 if reverse_signal else 0
            enough_hold = (i - entry_i) >= min_hold_bars
            clear_reversal = enough_hold and reversal_count >= reversal_confirm_bars and adx_weakening

            trail_atr = reversal_trail_atr if clear_reversal else trend_trail_atr
            stop = min(stop, worst_price + trail_atr * atr[i])

            exit_reason = None
            if highs[i] >= stop:
                exit_price = stop
                if clear_reversal:
                    exit_reason = "Закрытие шорта: явный разворот подтвержден"
                elif break_even_armed:
                    exit_reason = "Закрытие шорта: трейлинг по тренду"
                else:
                    exit_reason = "Закрытие шорта: защитный стоп"
            elif clear_reversal and rsi[i] > 52:
                exit_price = price
                exit_reason = "Закрытие шорта: подтвержденный разворот (3 бара)"
            else:
                continue
            pnl = (entry_price - exit_price) / entry_price * 100

        trades.append({
            "side": pos,
            "entry_index": entry_i,
            "exit_index": i,
            "entry_time": labels[entry_i],
            "exit_time": labels[i],
            "entry_price": round(entry_price, 4),
            "exit_price": round(exit_price, 4),
            "pnl_pct": round(pnl, 3),
            "result": "WIN" if pnl > 0 else "LOSS",
            "reason": exit_reason,
        })
        points.append({"type": "CLOSE", "type_ru": "Закрытие сделки", "index": i, "time": labels[i], "price": round(exit_price, 4), "comment": exit_reason})
        pos = "FLAT"

    wins = [t for t in trades if t["pnl_pct"] > 0]
    losses = [t for t in trades if t["pnl_pct"] <= 0]
    total = len(trades)
    winrate = (len(wins) / total * 100) if total else 0.0
    gross_profit = sum(t["pnl_pct"] for t in wins)
    gross_loss = abs(sum(t["pnl_pct"] for t in losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)

    ema_gap_last_pct = abs(ema21[-1] - ema50[-1]) / closes[-1] * 100 if closes[-1] else 0.0
    if adx[-1] < adx_range_threshold or ema_gap_last_pct < trend_band_threshold:
        market_regime = "RANGE"
        market_regime_ru = "Боковик"
    elif ema21[-1] >= ema50[-1]:
        market_regime = "TREND_UP"
        market_regime_ru = "Тренд вверх"
    else:
        market_regime = "TREND_DOWN"
        market_regime_ru = "Тренд вниз"

    long_score = int(closes[-1] > ema50[-1]) + int(ema9[-1] > ema21[-1]) + int(macd_hist[-1] > 0) + int(47 <= rsi[-1] <= 72) + int(closes[-1] > vwap[-1]) + int(adx[-1] >= adx_entry_threshold)
    short_score = int(closes[-1] < ema50[-1]) + int(ema9[-1] < ema21[-1]) + int(macd_hist[-1] < 0) + int(28 <= rsi[-1] <= 53) + int(closes[-1] < vwap[-1]) + int(adx[-1] >= adx_entry_threshold)

    if market_regime == "RANGE":
        signal, reason = "CLOSE", "Боковой рынок: сделок не открываем, ждём тренд"
    elif long_score >= 5 and long_score > short_score:
        signal, reason = "BUY", "Тренд вверх: ищем продолжение движения"
    elif short_score >= 5 and short_score > long_score:
        signal, reason = "SELL", "Тренд вниз: ищем продолжение движения"
    else:
        signal, reason = "CLOSE", "Нет явного трендового преимущества"

    confidence = min(95, 48 + max(long_score, short_score) * 9 + (10 if winrate >= 55 and total >= 3 else 0))

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
            "RSI14": round(rsi[-1], 2),
            "MACD_hist": round(macd_hist[-1], 5),
            "VWAP": round(vwap[-1], 4),
            "ATR14": round(atr[-1], 4),
            "ADX14": round(adx[-1], 2),
            "EMA21_50_gap_pct": round(ema_gap_last_pct, 3),
        },
        "strategy_params": {
            "min_hold_bars": min_hold_bars,
            "reversal_confirm_bars": reversal_confirm_bars,
            "initial_stop_atr": initial_stop_atr,
            "trend_trail_atr": trend_trail_atr,
            "reversal_trail_atr": reversal_trail_atr,
            "break_even_arm_atr": break_even_arm_atr,
            "break_even_lock_atr": break_even_lock_atr,
            "adx_entry_threshold": adx_entry_threshold,
            "adx_trend_threshold": adx_trend_threshold,
            "adx_range_threshold": adx_range_threshold,
            "ema_gap_threshold": ema_gap_threshold,
        },
        "market_regime": market_regime,
        "market_regime_ru": market_regime_ru,
    }


def run_daytrade_analysis(ticker: str) -> dict[str, Any]:
    ticker = ticker.strip().upper()
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
            "Стратегия: только трендовый рынок (без сделок в боковике) + удержание до явного разворота",
            f"Сделок: {sim['stats']['total_trades']} | Winrate: {sim['stats']['winrate_pct']}%",
            f"Profit Factor: {sim['stats']['profit_factor']}",
        ],
        "indicators": sim["indicators"],
        "strategy_params": sim["strategy_params"],
        "market_regime": sim["market_regime"],
        "market_regime_ru": sim["market_regime_ru"],
        "stats": sim["stats"],
        "trades": sim["trades"][-15:],
        "цена_сейчас": round(closes[-1], 4),
        "labels": labels,
        "prices": closes,
        "buy_points": [p for p in points if p["type"] == "BUY"],
        "sell_points": [p for p in points if p["type"] == "SELL"],
        "close_points": [p for p in points if p["type"] == "CLOSE"],
        "all_points": points,
        "source": "Мосбиржа ISS",
        "note": "Учебная модель. 70-80% прибыльных сделок не гарантируются на реальном рынке.",
    }


def run_screener(limit: int = 80, confidence_threshold: int = 80) -> dict[str, Any]:
    tickers = fetch_tickers_list(limit=limit)
    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        try:
            r = run_daytrade_analysis(ticker)
            if r["signal"] not in {"BUY", "SELL"}:
                continue
            if r["confidence"] < confidence_threshold:
                continue
            st = r.get("stats", {})
            rows.append(
                {
                    "ticker": ticker,
                    "signal": r["signal"],
                    "signal_ru": r["signal_ru"],
                    "confidence": r["confidence"],
                    "price": r["цена_сейчас"],
                    "reason": r["reason"],
                    "market_regime": r.get("market_regime"),
                    "market_regime_ru": r.get("market_regime_ru"),
                    "winrate": st.get("winrate_pct", 0.0),
                    "profit_factor": st.get("profit_factor", 0.0),
                }
            )
        except Exception:
            continue

    priority = {"BUY": 0, "SELL": 1}
    rows.sort(key=lambda x: (priority.get(x["signal"], 9), -x["confidence"], -x["profit_factor"]))
    return {"count": len(rows), "items": rows, "confidence_threshold": confidence_threshold, "source": "Мосбиржа ISS"}


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
    return {"ticker": ticker, "items": items, "source": "Мосбиржа ISS"}


def main() -> None:
    ticker = input("Введите тикер: ").strip().upper() or "SBER"
    res = run_daytrade_analysis(ticker)
    print(f"{res['ticker']} -> {res['signal_ru']} ({res['confidence']}%)")


if __name__ == "__main__":
    main()
