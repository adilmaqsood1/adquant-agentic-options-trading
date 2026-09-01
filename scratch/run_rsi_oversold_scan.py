import os, sys
import pandas as pd
import numpy as np
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from data.data_loader import get_available_symbols, get_market_data

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

symbols_list = [s["symbol"] for s in get_available_symbols()]
print(f"Scanning {len(symbols_list)} S&P 500 US Equities for RSI Oversold Reversal setups...\n")

candidates = []

for sym in symbols_list:
    try:
        df = get_market_data(sym, interval="1d")
        if df is None or len(df) < 60:
            continue
        
        df["rsi_14"] = compute_rsi(df["close"], 14)
        df["rsi_3"] = compute_rsi(df["close"], 3)
        df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()
        df["ema_200"] = df["close"].ewm(span=200, adjust=False).mean()
        
        last_close = float(df["close"].iloc[-1])
        rsi_14_val = float(df["rsi_14"].iloc[-1])
        rsi_3_val = float(df["rsi_3"].iloc[-1])
        ema_50_val = float(df["ema_50"].iloc[-1])
        ema_200_val = float(df["ema_200"].iloc[-1])
        
        # Check Oversold conditions
        # RSI 14 <= 38 OR RSI 3 <= 18
        if rsi_14_val <= 38.0 or rsi_3_val <= 20.0:
            trend_state = "BULLISH_UPTREND" if last_close >= ema_200_val else "PULLBACK"
            score = 100 - rsi_14_val
            if last_close >= ema_200_val:
                score += 15 # Bonus for dip in macro uptrend
            if rsi_3_val <= 15:
                score += 10 # Extreme short term exhaustion
                
            candidates.append({
                "symbol": sym,
                "close": round(last_close, 2),
                "rsi_14": round(rsi_14_val, 2),
                "rsi_3": round(rsi_3_val, 2),
                "trend": trend_state,
                "ema_200": round(ema_200_val, 2),
                "score": round(score, 1)
            })
    except Exception:
        pass

# Rank by opportunity score
candidates = sorted(candidates, key=lambda x: x["score"], reverse=True)

print(f"{'#':2s} | {'Ticker':6s} | {'Price':8s} | {'RSI-14':7s} | {'RSI-3':7s} | {'Macro Trend':15s} | {'Opportunity Score':18s}")
print("-" * 80)
for i, c in enumerate(candidates[:15], 1):
    print(f"{i:2d} | {c['symbol']:6s} | ${c['close']:7.2f} | {c['rsi_14']:6.2f}  | {c['rsi_3']:6.2f}  | {c['trend']:15s} | {c['score']:6.1f} / 100")

