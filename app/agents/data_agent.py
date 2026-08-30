"""
Layer 1: Data Agent
───────────────────
Pure Python. No LLM. Runs first every cycle.
Fetches fresh bars for all symbols, computes all 12 technical indicators,
and returns a FeatureSnapshot dict keyed by symbol.

All other agents read exclusively from this snapshot — single source of truth.
"""
import datetime
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List

from app.services.technical_indicators import (
    sma, ema, rsi, macd, bollinger_bands, atr, adx,
    donchian_channel, supertrend, kalman_filter_trend, volume_delta_imbalance
)

# ─── In-memory cache ──────────────────────────────────────────────────────────
_SNAPSHOT_CACHE: Dict[str, Any] = {}
_SNAPSHOT_TIMESTAMP: Optional[datetime.datetime] = None


def compute_feature_snapshot(symbol: str, df: pd.DataFrame, timeframe: str = "4H") -> Dict[str, Any]:
    """
    Computes all 12 technical indicator features for a single symbol DataFrame.
    Returns a flat dict with scalar values — safe to pass directly into Groq prompts.
    """
    if df is None or df.empty or len(df) < 20:
        return {"symbol": symbol, "timeframe": timeframe, "error": "insufficient_data", "bars": 0}

    close = df["close"]
    high  = df["high"]
    low   = df["low"]
    vol   = df["volume"]
    n     = len(df)

    # ── Core Price Context ────────────────────────────────────────────────────
    current_price = float(close.iloc[-1])
    prev_close    = float(close.iloc[-2]) if n >= 2 else current_price
    price_change_1b_pct = round((current_price - prev_close) / (prev_close + 1e-10) * 100, 3)

    # ── EMAs ─────────────────────────────────────────────────────────────────
    ema20  = float(ema(close, 20).iloc[-1])
    ema50  = float(ema(close, 50).iloc[-1])
    ema200 = float(ema(close, 200).iloc[-1])
    ema20_prev = float(ema(close, 20).iloc[-2]) if n >= 2 else ema20
    ema50_prev = float(ema(close, 50).iloc[-2]) if n >= 2 else ema50

    ema_bullish_cross  = bool(ema20 > ema50 and ema20_prev <= ema50_prev)
    ema_bearish_cross  = bool(ema20 < ema50 and ema20_prev >= ema50_prev)
    price_above_ema200 = bool(current_price > ema200)
    price_above_ema50  = bool(current_price > ema50)
    ema20_ema50_gap_pct = round((ema20 - ema50) / (ema50 + 1e-10) * 100, 3)

    # ── RSI ──────────────────────────────────────────────────────────────────
    rsi_val  = float(rsi(close, 14).iloc[-1])
    rsi_prev = float(rsi(close, 14).iloc[-2]) if n >= 2 else rsi_val
    rsi_3    = float(rsi(close, 3).iloc[-1]) if n >= 3 else rsi_val

    # ── ADX ──────────────────────────────────────────────────────────────────
    adx_val = float(adx(high, low, close, 14).iloc[-1])

    # ── ATR ──────────────────────────────────────────────────────────────────
    atr_val = float(atr(high, low, close, 14).iloc[-1])
    atr_pct = round(atr_val / (current_price + 1e-10) * 100, 3)

    # ── MACD ─────────────────────────────────────────────────────────────────
    macd_line, signal_line, histogram = macd(close, 12, 26, 9)
    macd_val     = float(macd_line.iloc[-1])
    macd_sig     = float(signal_line.iloc[-1])
    macd_hist    = float(histogram.iloc[-1])
    macd_hist_prev = float(histogram.iloc[-2]) if n >= 2 else macd_hist
    macd_bullish_cross = bool(macd_val > macd_sig and float(macd_line.iloc[-2]) <= float(signal_line.iloc[-2])) if n >= 2 else False
    macd_hist_turning_up = bool(macd_hist > macd_hist_prev)

    # ── Bollinger Bands ───────────────────────────────────────────────────────
    bb_upper, bb_middle, bb_lower = bollinger_bands(close, 20, 2.0)
    bb_upper_val  = float(bb_upper.iloc[-1])
    bb_lower_val  = float(bb_lower.iloc[-1])
    bb_mid_val    = float(bb_middle.iloc[-1])
    bb_width_pct  = round((bb_upper_val - bb_lower_val) / (bb_mid_val + 1e-10) * 100, 3)
    bb_pct_b      = round((current_price - bb_lower_val) / (bb_upper_val - bb_lower_val + 1e-10), 3)
    # Squeeze: band width below 20-bar average
    bb_widths = ((bb_upper - bb_lower) / (bb_middle + 1e-10) * 100)
    bb_width_avg20 = float(bb_widths.rolling(20, min_periods=5).mean().iloc[-1])
    bb_squeeze_active = bool(bb_width_pct < bb_width_avg20 * 0.7)

    # ── Donchian Channels ─────────────────────────────────────────────────────
    dc20_upper, dc20_mid, dc20_lower = donchian_channel(high, low, 20)
    dc10_upper, dc10_mid, dc10_lower = donchian_channel(high, low, 10)
    dc20_upper_val = float(dc20_upper.iloc[-1])
    dc20_lower_val = float(dc20_lower.iloc[-1])
    dc10_lower_val = float(dc10_lower.iloc[-1])
    donchian_breakout_up   = bool(current_price >= dc20_upper_val)
    donchian_breakout_down = bool(current_price <= dc20_lower_val)
    donchian_exit_down     = bool(current_price <= dc10_lower_val)

    # ── Supertrend ────────────────────────────────────────────────────────────
    st_line_s, st_direction = supertrend(high, low, close, period=10, multiplier=3.0)
    st_direction_val  = int(st_direction.iloc[-1])
    st_direction_prev = int(st_direction.iloc[-2]) if n >= 2 else st_direction_val
    st_bullish_flip = bool(st_direction_val == 1 and st_direction_prev == -1)
    st_bearish_flip = bool(st_direction_val == -1 and st_direction_prev == 1)
    st_is_bullish   = bool(st_direction_val == 1)

    # ── Kalman Trend ──────────────────────────────────────────────────────────
    kalman = kalman_filter_trend(close)
    kalman_val  = float(kalman.iloc[-1])
    kalman_prev = float(kalman.iloc[-2]) if n >= 2 else kalman_val
    kalman_trending_up = bool(kalman_val > kalman_prev)

    # ── Volume ────────────────────────────────────────────────────────────────
    vol_20_avg     = float(vol.rolling(20, min_periods=5).mean().iloc[-1])
    current_vol    = float(vol.iloc[-1])
    vol_ratio      = round(current_vol / (vol_20_avg + 1e-10), 3)
    vol_surge      = bool(vol_ratio > 1.5)
    vol_imbalance  = float(volume_delta_imbalance(close, high, low, vol, 14).iloc[-1])

    # ── Momentum ─────────────────────────────────────────────────────────────
    ret_5d  = round(close.pct_change(5).iloc[-1] * 100,  2) if n >= 5  else 0.0
    ret_20d = round(close.pct_change(20).iloc[-1] * 100, 2) if n >= 20 else 0.0
    ret_30d = round(close.pct_change(30).iloc[-1] * 100, 2) if n >= 30 else 0.0

    # ── Volatility Regime ─────────────────────────────────────────────────────
    returns        = close.pct_change().dropna()
    vol_30d_annual = round(float(returns.rolling(30, min_periods=10).std().iloc[-1]) * np.sqrt(365) * 100, 2) if n >= 10 else 0.0
    low_vol_regime = bool(vol_30d_annual < 40.0)

    # ── Last 5 bars summary ───────────────────────────────────────────────────
    last5 = df.tail(5)[["open","high","low","close","volume"]].round(4).to_dict("records")

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "bars": n,
        "timestamp_utc": datetime.datetime.utcnow().isoformat(),
        "last_bar_time": str(df.index[-1]),

        # Price
        "price": round(current_price, 4),
        "price_change_1b_pct": price_change_1b_pct,
        "ret_5d_pct": ret_5d,
        "ret_20d_pct": ret_20d,
        "ret_30d_pct": ret_30d,

        # EMAs
        "ema20": round(ema20, 4),
        "ema50": round(ema50, 4),
        "ema200": round(ema200, 4),
        "ema20_ema50_gap_pct": ema20_ema50_gap_pct,
        "ema_bullish_cross": ema_bullish_cross,
        "ema_bearish_cross": ema_bearish_cross,
        "price_above_ema200": price_above_ema200,
        "price_above_ema50": price_above_ema50,

        # RSI
        "rsi_14": round(rsi_val, 2),
        "rsi_3": round(rsi_3, 2),
        "rsi_prev": round(rsi_prev, 2),

        # ADX
        "adx_14": round(adx_val, 2),
        "strong_trend": bool(adx_val > 25),

        # ATR
        "atr_14": round(atr_val, 4),
        "atr_pct": atr_pct,

        # MACD
        "macd": round(macd_val, 6),
        "macd_signal": round(macd_sig, 6),
        "macd_histogram": round(macd_hist, 6),
        "macd_bullish_cross": macd_bullish_cross,
        "macd_hist_turning_up": macd_hist_turning_up,

        # Bollinger Bands
        "bb_upper": round(bb_upper_val, 4),
        "bb_lower": round(bb_lower_val, 4),
        "bb_width_pct": bb_width_pct,
        "bb_pct_b": bb_pct_b,
        "bb_squeeze_active": bb_squeeze_active,

        # Donchian
        "dc20_upper": round(dc20_upper_val, 4),
        "dc20_lower": round(dc20_lower_val, 4),
        "dc10_lower": round(dc10_lower_val, 4),
        "donchian_breakout_up": donchian_breakout_up,
        "donchian_breakout_down": donchian_breakout_down,
        "donchian_exit_down": donchian_exit_down,

        # Supertrend
        "supertrend_bullish": st_is_bullish,
        "supertrend_bullish_flip": st_bullish_flip,
        "supertrend_bearish_flip": st_bearish_flip,

        # Kalman
        "kalman_trending_up": kalman_trending_up,

        # Volume
        "volume_ratio_vs_20avg": vol_ratio,
        "volume_surge": vol_surge,
        "volume_imbalance": round(vol_imbalance, 4),

        # Volatility Regime
        "vol_30d_annual_pct": vol_30d_annual,
        "low_vol_regime": low_vol_regime,

        # Last 5 bars
        "last_5_bars": last5
    }


def run_data_agent(bars_by_strategy: Dict[str, Dict[str, pd.DataFrame]]) -> Dict[str, Any]:
    """
    Layer 1 entry point.
    Accepts the nested bars dict from market_state.fetch_all(),
    deduplicates symbols, computes feature snapshots for every unique symbol,
    and stores them in the in-memory cache.

    Returns: {symbol: feature_snapshot_dict}
    """
    global _SNAPSHOT_CACHE, _SNAPSHOT_TIMESTAMP

    snapshots: Dict[str, Any] = {}
    symbols_processed = 0
    symbols_failed = 0

    print(f"\n[DataAgent] Building FeatureSnapshot for {sum(len(v) for v in bars_by_strategy.values())} symbol-strategy pairs...")

    try:
        from app.services.market_state import STRATEGY_MARKET_CONFIG
    except Exception:
        STRATEGY_MARKET_CONFIG = {}

    for strategy_id, sym_map in bars_by_strategy.items():
        cfg = STRATEGY_MARKET_CONFIG.get(strategy_id, {})
        tf = cfg.get("timeframe", "4H")
        for symbol, df in sym_map.items():
            if symbol in snapshots:
                continue  # deduplicate
            try:
                snap = compute_feature_snapshot(symbol, df, timeframe=tf)
                snapshots[symbol] = snap
                symbols_processed += 1
            except Exception as e:
                print(f"[DataAgent] ERROR computing snapshot for {symbol}: {e}")
                snapshots[symbol] = {"symbol": symbol, "timeframe": tf, "error": str(e), "bars": 0}
                symbols_failed += 1

    _SNAPSHOT_CACHE = snapshots
    _SNAPSHOT_TIMESTAMP = datetime.datetime.utcnow()

    print(f"[DataAgent] FeatureSnapshot complete: {symbols_processed} symbols OK | {symbols_failed} failed | Cache timestamp: {_SNAPSHOT_TIMESTAMP.isoformat()}")
    return snapshots


def get_snapshot(symbol: str) -> Optional[Dict[str, Any]]:
    """Returns the cached feature snapshot for a given symbol."""
    return _SNAPSHOT_CACHE.get(symbol)


def get_all_snapshots() -> Dict[str, Any]:
    """Returns the full snapshot cache."""
    return _SNAPSHOT_CACHE.copy()


def get_snapshot_timestamp() -> Optional[datetime.datetime]:
    return _SNAPSHOT_TIMESTAMP
