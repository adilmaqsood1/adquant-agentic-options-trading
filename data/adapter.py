import os
import datetime
import pandas as pd
import numpy as np
from typing import Optional

from data.kaggle_source import load_kaggle_data, POSSIBLE_PATHS
from data.alpaca_source import fetch_alpaca_stock_bars  


CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# Precompute known Kaggle S&P 500 symbols
KAGGLE_SYMBOLS = set()
for folder in POSSIBLE_PATHS:
    if os.path.exists(folder):
        for f in os.listdir(folder):
            if f.endswith(".csv"):
                KAGGLE_SYMBOLS.add(f.replace(".csv", "").upper())


def resolve_source(symbol: str, start: Optional[str] = None, end: Optional[str] = None) -> str:
    """
    Auto-routing logic for US Optionable Equities & ETFs:
    - In Kaggle S&P 500 list (for long historical backtesting up to 2025) -> 'kaggle'
    - Default for live / real-time US optionable equities & ETFs -> 'alpaca'
    """
    orig_clean = symbol.upper().replace("/", "-").strip()
    if orig_clean in KAGGLE_SYMBOLS:
        if end and pd.to_datetime(end).year > 2025:
            return "alpaca"
        return "kaggle"
        
    return "alpaca"


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Master normalizer:
    - Column names: open, high, low, close, volume (lowercase)
    - Index: pd.DatetimeIndex, timezone-naive
    - Dtypes: float64 for all 5 columns
    - Sort ascending by date
    - Drop rows where close is NaN or <= 0
    - Forward-fill remaining NaN in OHLC
    - Fill NaN in volume with 0.0
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    df = df.copy()

    # Column name lowercase mapping
    df.columns = [str(c).lower().strip() for c in df.columns]

    # Ensure required columns present
    required_cols = ["open", "high", "low", "close", "volume"]
    for col in required_cols:
        if col not in df.columns:
            if col == "open":
                df["open"] = df.get("close", 0.0)
            elif col == "high":
                df["high"] = df[["open", "close"]].max(axis=1) if "close" in df.columns else 0.0
            elif col == "low":
                df["low"] = df[["open", "close"]].min(axis=1) if "close" in df.columns else 0.0
            elif col == "volume":
                df["volume"] = 0.0

    df = df[required_cols]

    # Timezone-naive DatetimeIndex
    if not isinstance(df.index, pd.DatetimeIndex):
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df.set_index("date", inplace=True)
        else:
            df.index = pd.to_datetime(df.index)

    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    df.index.name = "date"

    # Sort ascending
    df.sort_index(inplace=True)

    # Cast to float64
    for col in required_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype(np.float64)

    # Drop rows where close is NaN or <= 0
    df = df[df["close"].notna() & (df["close"] > 0)]

    # Forward fill OHLC
    df[["open", "high", "low", "close"]] = df[["open", "high", "low", "close"]].ffill().bfill()
    df["volume"] = df["volume"].fillna(0.0)

    return df


def get_data(
    symbol: str,
    source: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    interval: str = "1d"
) -> pd.DataFrame:
    """
    Master unified data entry point:
    - Fetches from Alpaca (live/historical) or Kaggle (historical)
    - Seamlessly caches responses in data/cache/
    - Returns standardized 5-column DataFrame (open, high, low, close, volume) with DatetimeIndex
    """
    sym = symbol.strip().upper()
    
    # Auto-route source if not provided or 'auto'
    if not source or source.lower() == "auto":
        src = resolve_source(sym, start, end)
    else:
        src = source.lower().strip()

    # Normalize dates for filename
    start_tag = str(start)[:10] if start else "all"
    end_tag = str(end)[:10] if end else "all"
    clean_sym_tag = sym.replace("/", "-").replace("^", "")
    cache_file = os.path.join(CACHE_DIR, f"{clean_sym_tag}_{src}_{interval}_{start_tag}_{end_tag}.csv")

    # 1. Check cache first
    today_str = datetime.date.today().isoformat()
    if os.path.exists(cache_file):
        try:
            mtime = datetime.date.fromtimestamp(os.path.getmtime(cache_file)).isoformat()
            if mtime == today_str:
                cached_df = pd.read_csv(cache_file, parse_dates=["date"], index_col="date")
                return normalize_dataframe(cached_df)
        except Exception as e:
            print(f"[Adapter] Cache read error: {e}")

    # 2. Fetch from source (Alpaca primary, Kaggle fallback)
    raw_df = None
    if src == "kaggle":
        raw_df = load_kaggle_data(sym, start=start, end=end, interval=interval)
        if raw_df is None or raw_df.empty:
            raw_df = fetch_alpaca_stock_bars(sym, start=start, end=end, interval=interval)
    elif src == "alpaca":
        raw_df = fetch_alpaca_stock_bars(sym, start=start, end=end, interval=interval)
        if raw_df is None or raw_df.empty:
            raw_df = load_kaggle_data(sym, start=start, end=end, interval=interval)
    else:
        # Fallback cascade: Alpaca -> Kaggle
        raw_df = fetch_alpaca_stock_bars(sym, start=start, end=end, interval=interval)
        if raw_df is None or raw_df.empty:
            raw_df = load_kaggle_data(sym, start=start, end=end, interval=interval)

    # 3. Master normalization
    norm_df = normalize_dataframe(raw_df)

    # 4. Save to cache if valid data received
    if not norm_df.empty:
        try:
            norm_df.to_csv(cache_file)
        except Exception as e:
            print(f"[Adapter] Cache write error: {e}")

    return norm_df
