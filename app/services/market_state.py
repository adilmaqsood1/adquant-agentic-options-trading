import os
import time
import datetime
import pandas as pd
from typing import Dict, List, Optional, Any

try:
    from app.data.adapter import get_data
    from app.data.kaggle_source import POSSIBLE_PATHS
except ImportError:
    try:
        from data.adapter import get_data
        from data.kaggle_source import POSSIBLE_PATHS
    except ImportError:
        from ..data.adapter import get_data
        from ..data.kaggle_source import POSSIBLE_PATHS

# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# 1. MASTER UNIVERSE DEFINITIONS (100% Optionable US Equities & ETFs on Alpaca)
# ─────────────────────────────────────────────────────────────────────────────

# High-Liquidity Primary Options Universe (Tight Bid/Ask Spreads, High Open Interest)
OPTIONS_CORE_UNIVERSE: List[str] = [
    "SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "TSLA",
    "AMD", "PLTR", "ARM", "NFLX", "AVGO", "COST", "ADBE", "CRM", "NOW", "SNOW", "PANW",
    "CRWD", "MSTR", "COIN", "HON", "MU", "UBER", "SHOP", "NET", "DDOG", "ZS", "MRNA", "TEAM"
]

# Nasdaq 100 Component Universe
ALL_NASDAQ_SYMBOLS: List[str] = [
    "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "TSLA", "AVGO",
    "COST", "PEP", "CSCO", "TMUS", "ADBE", "NFLX", "TXN", "AMD", "QCOM", "INTC",
    "INTU", "AMAT", "CMCSA", "BKNG", "HON", "AMGN", "ISRG", "VRTX", "SBUX", "MDLZ",
    "LRCX", "ADI", "GILD", "REGN", "PANW", "KLAC", "SNPS", "CDNS", "CRWD", "MAR",
    "ORLY", "FTNT", "CTAS", "ASML", "MRVL", "PYPL", "NXPI", "WDAY", "ADSK", "PCAR",
    "ROP", "CPRT", "PAYX", "FAST", "ROST", "ODFL", "CHTR", "KDP", "EXC", "AEP",
    "CSX", "DXCM", "VRSK", "CTSH", "IDXX", "BIIB", "EA", "LULU", "GEHC", "MCHP",
    "FANG", "XEL", "CCEP", "TEAM", "ANSS", "KHC", "CDW", "ON", "TTD", "DLTR",
    "ZS", "GFS", "ILMN", "WBD", "WBA", "MRNA", "BMRN", "ALGN", "CEG", "ARM",
    "MDB", "PDD", "DASH", "TTWO", "SMCI", "MSTR", "COIN", "MU"
]

# Load All 500+ Local S&P 500 Symbols from CSV files
def get_all_sp500_symbols() -> List[str]:
    sp500_set = {"SPY"}
    for folder in POSSIBLE_PATHS:
        if os.path.exists(folder):
            for f in os.listdir(folder):
                if f.endswith(".csv"):
                    sp500_set.add(f.replace(".csv", "").upper())
    return sorted(list(sp500_set))

ALL_SP500_SYMBOLS: List[str] = get_all_sp500_symbols()

# Combined Optionable US Equities (S&P 500 + Nasdaq union)
ALL_US_EQUITIES: List[str] = sorted(list(set(ALL_SP500_SYMBOLS + ALL_NASDAQ_SYMBOLS + OPTIONS_CORE_UNIVERSE)))

# ─────────────────────────────────────────────────────────────────────────────
# 2. STRATEGY MARKET CONFIGURATION (Full Universe: 521 Optionable US Equities & ETFs)
# ─────────────────────────────────────────────────────────────────────────────
STRATEGY_MARKET_CONFIG: Dict[str, Dict[str, Any]] = {
    # 2H Fast Momentum: High-Beta Optionable Tech Equities & Indices
    "momentum_ema_rsi_adx": {
        "symbols": ALL_US_EQUITIES,
        "source": "alpaca",
        "timeframe": "2H",
        "bars_needed": 300
    },
    # 4H Microstructure: Liquidity Sweep & Stop-Hunt Absorption
    "liquidity_sweep_absorption": {
        "symbols": ALL_US_EQUITIES,
        "source": "alpaca",
        "timeframe": "4H",
        "bars_needed": 300
    },
    # 4H Statistical Lead-Lag: High-Beta Propagation
    "lead_lag_propagation": {
        "symbols": ALL_US_EQUITIES,
        "source": "alpaca",
        "timeframe": "4H",
        "bars_needed": 300
    },
    # 4H Regime Switching: Hurst Double Squeeze
    "hurst_double_squeeze": {
        "symbols": ALL_US_EQUITIES,
        "source": "alpaca",
        "timeframe": "4H",
        "bars_needed": 300
    },
    # 4H Institutional Benchmark: Anchored VWAP Deviation Snap
    "anchored_vwap_deviation": {
        "symbols": ALL_US_EQUITIES,
        "source": "alpaca",
        "timeframe": "4H",
        "bars_needed": 300
    },
    # 4H Order Flow: CVD Delta Divergence Short Squeeze
    "cvd_divergence_squeeze": {
        "symbols": ALL_US_EQUITIES,
        "source": "alpaca",
        "timeframe": "4H",
        "bars_needed": 300
    },
    # 4H Momentum / Reversal: RSI Oversold Bullish Hook Above 30
    "rsi_oversold_reversal": {
        "symbols": ALL_US_EQUITIES,
        "source": "alpaca",
        "timeframe": "4H",
        "bars_needed": 300
    },
    # 4H/1D Institutional Trend Pullback Continuation (TEAM-Style)
    "trend_pullback_continuation": {
        "symbols": ALL_US_EQUITIES,
        "source": "alpaca",
        "timeframe": "4H",
        "bars_needed": 300
    }
}



TIMEFRAME_HOURS = {
    "1D": 24,
    "1d": 24,
    "4H": 4,
    "4h": 4,
    "2H": 2,
    "2h": 2,
    "1H": 1,
    "1h": 1,
    "15m": 0.25,
    "5m": 0.0833
}


def fetch_symbol(
    symbol: str,
    source: str = "alpaca",
    timeframe: str = "1D",
    bars_needed: int = 300
) -> Optional[pd.DataFrame]:
    """
    Fetches fresh live bars for a single symbol from Alpaca (or local Kaggle cache for equities).
    - End date is always datetime.utcnow()
    - Start date calculated with market closure buffer
    """
    clean_sym = symbol.strip().upper()
    tf = timeframe.upper()
    hours_per_bar = TIMEFRAME_HOURS.get(tf, 24)

    # 100% Optionable US Equities & ETFs: use 2.8x buffer for market closures & weekends
    multiplier = 2.8
    total_hours_back = int(bars_needed * hours_per_bar * multiplier)

    end_dt = datetime.datetime.utcnow()
    start_dt = end_dt - datetime.timedelta(hours=total_hours_back)

    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = end_dt.strftime("%Y-%m-%d")
    interval = tf.lower()

    try:
        df = get_data(
            symbol=clean_sym,
            source="alpaca",
            start=start_str,
            end=end_str,
            interval=interval
        )

        if df is None or df.empty:
            print(f"[MarketState] WARNING: No data returned for {clean_sym} (alpaca, {tf})")
            return None

        # Take the most recent requested bars_needed
        df_sliced = df.tail(bars_needed).copy()
        print(f"[MarketState] SUCCESS: Fetched {clean_sym} (alpaca, {tf}) -> {len(df_sliced)} bars (Last: {df_sliced.index[-1]} | Close: ${df_sliced['close'].iloc[-1]:,.2f})")
        return df_sliced

    except Exception as e:
        print(f"[MarketState] ERROR: Failed to fetch {clean_sym} (alpaca, {tf}): {e}")
        return None


def fetch_all(
    strategy_ids: Optional[List[str]] = None
) -> Dict[str, Dict[str, pd.DataFrame]]:
    """
    Fetches live market state for all requested strategies across all Alpaca Crypto, S&P 500, and Nasdaq symbols.
    Returns nested dictionary:
    {
        "strategy_id": {
            "SYMBOL": pd.DataFrame,
            ...
        }
    }
    """
    if strategy_ids is None:
        strategy_ids = list(STRATEGY_MARKET_CONFIG.keys())

    market_state: Dict[str, Dict[str, pd.DataFrame]] = {}
    symbol_cache: Dict[str, pd.DataFrame] = {}

    print(f"\n[MarketState] Fetching Alpaca market state for {len(strategy_ids)} strategies: {strategy_ids}")

    for s_id in strategy_ids:
        cfg = STRATEGY_MARKET_CONFIG.get(s_id)
        if not cfg:
            print(f"[MarketState] WARNING: Strategy '{s_id}' not found in STRATEGY_MARKET_CONFIG. Skipping.")
            continue

        market_state[s_id] = {}
        tf = cfg["timeframe"]
        bars = cfg.get("bars_needed", 300)

        for sym in cfg["symbols"]:
            cache_key = f"{sym}_alpaca_{tf}_{bars}"

            if cache_key in symbol_cache:
                market_state[s_id][sym] = symbol_cache[cache_key].copy()
            else:
                df = fetch_symbol(sym, source="alpaca", timeframe=tf, bars_needed=bars)
                if df is not None and not df.empty:
                    symbol_cache[cache_key] = df
                    market_state[s_id][sym] = df
                else:
                    print(f"[MarketState] WARNING: Missing data for {sym} under strategy {s_id}")

    return market_state
