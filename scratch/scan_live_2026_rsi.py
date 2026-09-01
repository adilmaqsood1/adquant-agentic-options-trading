import os, sys, requests, json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)

headers = {
    "APCA-API-KEY-ID": os.getenv("ALPACA_API_KEY", ""),
    "APCA-API-SECRET-KEY": os.getenv("ALPACA_API_SECRET", "")
}

from app.services.market_state import ALL_US_EQUITIES

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

start_dt = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%dT00:00:00Z")
candidates = []

print(f"Scanning {len(ALL_US_EQUITIES)} symbols using LIVE 2026 Alpaca Market Data...\n", flush=True)

# Process in chunks of 50 via Alpaca multi-bars endpoint with feed=iex
for i in range(0, len(ALL_US_EQUITIES), 50):
    batch = ALL_US_EQUITIES[i:i+50]
    symbols_str = ",".join(batch)
    try:
        url = f"https://data.alpaca.markets/v2/stocks/bars?symbols={symbols_str}&timeframe=1Day&start={start_dt}&limit=65&adjustment=raw&feed=iex"
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            bars_dict = r.json().get("bars", {})
            for sym, bars in bars_dict.items():
                if not bars or len(bars) < 20:
                    continue
                df = pd.DataFrame(bars)
                df["c"] = df["c"].astype(float)
                df["rsi_14"] = compute_rsi(df["c"], 14)
                df["rsi_3"] = compute_rsi(df["c"], 3)
                df["ema_50"] = df["c"].ewm(span=min(50, len(df)), adjust=False).mean()
                
                last_c = float(df["c"].iloc[-1])
                rsi_14_val = float(df["rsi_14"].iloc[-1])
                rsi_3_val = float(df["rsi_3"].iloc[-1])
                ema_50_val = float(df["ema_50"].iloc[-1])
                
                if rsi_14_val <= 42.0 or rsi_3_val <= 25.0:
                    score = (100.0 - rsi_14_val)
                    if last_c >= ema_50_val:
                        score += 15
                    if rsi_3_val <= 20:
                        score += 10
                    candidates.append({
                        "symbol": sym,
                        "price": round(last_c, 2),
                        "rsi_14": round(rsi_14_val, 2),
                        "rsi_3": round(rsi_3_val, 2),
                        "ema_50": round(ema_50_val, 2),
                        "trend": "ABOVE_50EMA" if last_c >= ema_50_val else "BELOW_50EMA",
                        "score": round(score, 1)
                    })
    except Exception as e:
        print(f"Batch error: {e}", flush=True)

candidates = sorted(candidates, key=lambda x: x["score"], reverse=True)

print(f"{'#':2s} | {'Ticker':6s} | {'Live Price':10s} | {'RSI-14':7s} | {'RSI-3':7s} | {'Trend Filter':14s} | {'Score':10s}", flush=True)
print("-" * 75, flush=True)
for idx, c in enumerate(candidates[:20], 1):
    print(f"{idx:2d} | {c['symbol']:6s} | ${c['price']:9.2f} | {c['rsi_14']:6.2f}  | {c['rsi_3']:6.2f}  | {c['trend']:14s} | {c['score']:5.1f} / 100", flush=True)

