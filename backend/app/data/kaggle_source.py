import os
import pandas as pd
from typing import Optional

POSSIBLE_PATHS = [
    os.path.join(os.path.dirname(__file__), "SP500_Data_10Y"),
    os.path.join(os.path.dirname(__file__), "raw"),
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "SP500_Data_10Y")
]


def load_kaggle_data(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    interval: str = "1d"
) -> pd.DataFrame:
    """
    Loads local S&P 500 10-year historical CSV data.
    Accepts symbol (e.g. AAPL, SPY, NVDA).
    """
    clean_sym = symbol.upper().replace("/", "-").strip()
    
    csv_path = None
    for folder in POSSIBLE_PATHS:
        candidate = os.path.join(folder, f"{clean_sym}.csv")
        if os.path.exists(candidate):
            csv_path = candidate
            break

    if not csv_path or not os.path.exists(csv_path):
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    try:
        # The Kaggle dataset has:
        # Row 1: Price,Close,High,Low,Open,Volume
        # Row 2: Ticker,AAPL,AAPL,AAPL,AAPL,AAPL
        # Row 3: Date,,,,,
        # Row 4+: 2015-12-21,close,high,low,open,vol
        df = pd.read_csv(
            csv_path,
            skiprows=3,
            header=None,
            names=["date", "close", "high", "low", "open", "volume"],
            parse_dates=["date"],
            index_col="date"
        )
        df.sort_index(inplace=True)

        # Ensure correct column ordering
        df = df[["open", "high", "low", "close", "volume"]]

        # Filter date range if provided
        if start:
            df = df[df.index >= pd.to_datetime(start)]
        if end:
            df = df[df.index <= pd.to_datetime(end)]

        return df
    except Exception as e:
        print(f"[KaggleSource] Error loading {clean_sym}: {e}")
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
