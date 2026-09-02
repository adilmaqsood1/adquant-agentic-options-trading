import datetime
import pandas as pd
from typing import Dict, List, Tuple, Any, Optional

from app.services.registry import (
    signal_cross_sectional_momentum,
    signal_supertrend,
    signal_donchian_turtle_breakout,
    signal_momentum_ema_rsi_adx,
    signal_liquidity_sweep_absorption,
    signal_lead_lag_propagation,
    signal_hurst_double_squeeze,
    signal_anchored_vwap_deviation,
    signal_sharpe_residual_momentum,
    signal_cvd_divergence_squeeze,
    signal_rsi_oversold_reversal,
    signal_trend_pullback_continuation,
    signal_volatility_squeeze_breakout
)
from app.core.database import is_position_open


STRATEGY_EXECUTION_CONFIG: Dict[str, Dict[str, Any]] = {
    "volatility_squeeze_breakout": {
        "handler": signal_volatility_squeeze_breakout,
        "params": {
            "bb_period": 20,
            "bb_std": 2.0,
            "kc_period": 20,
            "kc_mult": 1.5
        },
        "allocated_capital": 25000.0,
        "timeframe": "4H"
    },
    "momentum_ema_rsi_adx": {
        "handler": signal_momentum_ema_rsi_adx,
        "params": {
            "fast_ema": 20,
            "slow_ema": 50,
            "rsi_filter": 50.0,
            "adx_filter": 20.0
        },
        "allocated_capital": 25000.0,
        "timeframe": "2H"
    },
    "liquidity_sweep_absorption": {
        "handler": signal_liquidity_sweep_absorption,
        "params": {"lookback": 20, "vol_mult": 1.3},
        "allocated_capital": 20000.0,
        "timeframe": "4H"
    },
    "lead_lag_propagation": {
        "handler": signal_lead_lag_propagation,
        "params": {"roc_period": 5},
        "allocated_capital": 15000.0,
        "timeframe": "4H"
    },
    "hurst_double_squeeze": {
        "handler": signal_hurst_double_squeeze,
        "params": {"period": 20},
        "allocated_capital": 20000.0,
        "timeframe": "4H"
    },
    "anchored_vwap_deviation": {
        "handler": signal_anchored_vwap_deviation,
        "params": {"window": 30, "dev_threshold": -1.8},
        "allocated_capital": 20000.0,
        "timeframe": "4H"
    },
    "cvd_divergence_squeeze": {

        "handler": signal_cvd_divergence_squeeze,
        "params": {"period": 14},
        "allocated_capital": 15000.0,
        "timeframe": "4H"
    },
    "rsi_oversold_reversal": {
        "handler": signal_rsi_oversold_reversal,
        "params": {"period": 14, "rsi_threshold": 30.0, "rsi_exit": 65.0},
        "allocated_capital": 25000.0,
        "timeframe": "4H"
    },
    "trend_pullback_continuation": {
        "handler": signal_trend_pullback_continuation,
        "params": {"sma_period": 200, "ema_fast": 20, "ema_slow": 50},
        "allocated_capital": 25000.0,
        "timeframe": "4H"
    }
}




def detect_signal(
    strategy_id: str,
    symbol: str,
    df: pd.DataFrame
) -> Dict[str, Any]:
    """
    Evaluates strategy handler over the DataFrame, checks the last bar's signal,
    cross-references current open position state in database, and returns a signal payload.
    """
    cfg = STRATEGY_EXECUTION_CONFIG.get(strategy_id)
    if not cfg:
        raise ValueError(f"Strategy '{strategy_id}' not found in STRATEGY_EXECUTION_CONFIG")

    handler = cfg["handler"]
    params = cfg["params"]
    timeframe = cfg["timeframe"]
    allocated_capital = float(cfg["allocated_capital"])

    if df is None or df.empty or len(df) < 5:
        return {
            "strategy_id": strategy_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "signal_raw": 0,
            "signal_type": "NONE",
            "fired": False,
            "last_close": 0.0,
            "last_bar_time": None,
            "allocated_capital": allocated_capital,
            "timestamp": datetime.datetime.utcnow()
        }

    # 1. Run strategy handler to compute bar-by-bar signals
    signal_series = handler(df, params)
    raw_val = int(signal_series.iloc[-1]) if not pd.isna(signal_series.iloc[-1]) else 0

    # 2. Check position state from database
    in_position = is_position_open(strategy_id, symbol)

    # 3. Exact state-machine decision logic
    # Raw 1: Bullish entry signal
    # Raw -1: Bearish exit signal
    # Raw 0: Neutral / Hold
    if raw_val == 1 and not in_position:
        signal_type = "ENTER_LONG"
        fired = True
    elif raw_val == -1 and not in_position:
        # Options allow two-way alpha: profit from downside moves via Bear Put Spreads / Puts
        signal_type = "ENTER_SHORT"
        fired = True
    elif raw_val == -1 and in_position:
        signal_type = "EXIT_LONG"
        fired = True
    elif raw_val == 1 and in_position:
        signal_type = "ALREADY_IN"
        fired = False
    else:
        signal_type = "NONE"
        fired = False

    last_close = float(df["close"].iloc[-1])
    last_bar_dt = df.index[-1]
    last_bar_time = last_bar_dt.isoformat() if hasattr(last_bar_dt, "isoformat") else str(last_bar_dt)

    return {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "signal_raw": raw_val,
        "signal_type": signal_type,
        "fired": fired,
        "last_close": round(last_close, 4),
        "last_bar_time": last_bar_time,
        "allocated_capital": allocated_capital,
        "timestamp": datetime.datetime.utcnow()
    }


def detect_all(
    fresh_bars: Dict[str, Dict[str, pd.DataFrame]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Accepts nested dictionary from Market State Builder:
    {
        "strategy_id": {
            "SYMBOL": DataFrame, ...
        }
    }
    Evaluates every strategy and symbol combination.
    Returns: (all_signals, fired_signals)
    """
    all_signals: List[Dict[str, Any]] = []
    fired_signals: List[Dict[str, Any]] = []

    print("\n" + "-" * 75)
    print(f"[SignalDetector] Running multi-strategy signal scan across {len(fresh_bars)} strategies...")
    print("-" * 75)

    for strategy_id, symbols_map in fresh_bars.items():
        if strategy_id not in STRATEGY_EXECUTION_CONFIG:
            continue

        for symbol, df in symbols_map.items():
            res = detect_signal(strategy_id, symbol, df)
            all_signals.append(res)

            if res["fired"]:
                fired_signals.append(res)
                print(f"  [FIRED] [{strategy_id.upper()}] {symbol} -> {res['signal_type']} @ ${res['last_close']} ({res['timeframe']})")
            else:
                print(f"  [HOLD]  [{strategy_id}] {symbol} -> {res['signal_type']} (raw={res['signal_raw']})")

    print("-" * 75)
    print(f"[SignalDetector] Scan complete: Scanned {len(all_signals)} assets | Fired Signals: {len(fired_signals)}")
    print("-" * 75)

    return all_signals, fired_signals
