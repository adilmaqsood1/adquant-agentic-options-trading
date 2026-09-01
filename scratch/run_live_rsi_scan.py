import os, sys, requests, json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
load_dotenv(os.path.join(BASE_DIR, ".env"))

API_KEY = os.getenv("ALPACA_API_KEY", "")
API_SECRET = os.getenv("ALPACA_SECRET_KEY", "")

headers = {
    "APCA-API-KEY-ID": API_KEY,
    "APCA-API-SECRET-KEY": API_SECRET
}

WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AMD", "NFLX",
    "CRM", "INTC", "PYPL", "NKE", "SBUX", "BA", "DIS", "UBER", "COIN",
    "PLTR", "SHOP", "MRNA", "UNH", "JNJ", "PFE", "CVX", "XOM", "JPM", "GS",
    "BAC", "WMT", "TGT", "COST", "HD", "LOW", "CAT", "DE", "HON", "GE"
]

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

start_dt = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%dT00:00:00Z")
candidates = []

print(f"Scanning {len(WATCHLIST)} liquid US equities via Alpaca live market data for RSI Oversold setups...\n", flush=True)

for sym in WATCHLIST:
    try:
        url = f"https://data.alpaca.markets/v2/stocks/{sym}/bars"
        params = {"timeframe": "1Day", "start": start_dt, "limit": 65, "adjustment": "raw"}
        r = requests.get(url, headers=headers, params=params, timeout=5)
        if r.status_code != 200:
            continue
        bars = r.json().get("bars", [])
        if not bars or len(bars) < 30:
            continue
            
        df = pd.DataFrame(bars)
        df["c"] = df["c"].astype(float)
        df["rsi_14"] = compute_rsi(df["c"], 14)
        df["rsi_3"] = compute_rsi(df["c"], 3)
        df["ema_50"] = df["c"].ewm(span=min(50, len(df)), adjust=False).mean()
        
        last_close = float(df["c"].iloc[-1])
        rsi_14_val = float(df["rsi_14"].iloc[-1])
        rsi_3_val = float(df["rsi_3"].iloc[-1])
        ema_50_val = float(df["ema_50"].iloc[-1])
        
        # Check Oversold conditions
        # RSI 14 <= 42 OR RSI 3 <= 25
        if rsi_14_val <= 45.0 or rsi_3_val <= 25.0:
            trend = "ABOVE_50EMA" if last_close >= ema_50_val else "BELOW_50EMA"
            score = 100 - rsi_14_val
            if last_close >= ema_50_val:
                score += 15
            if rsi_3_val <= 20:
                score += 10
                
            candidates.append({
                "symbol": sym,
                "price": round(last_close, 2),
                "rsi_14": round(rsi_14_val, 2),
                "rsi_3": round(rsi_3_val, 2),
                "trend": trend,
                "score": round(score, 1)
            })
    except Exception as e:
        pass

candidates = sorted(candidates, key=lambda x: x["score"], reverse=True)

print(f"{'#':2s} | {'Ticker':6s} | {'Price':8s} | {'RSI-14':7s} | {'RSI-3':7s} | {'Trend Filter':14s} | {'Opportunity Score':18s}", flush=True)
print("-" * 80, flush=True)
for i, c in enumerate(candidates[:15], 1):
    print(f"{i:2d} | {c['symbol']:6s} | ${c['price']:7.2f} | {c['rsi_14']:6.2f}  | {c['rsi_3']:6.2f}  | {c['trend']:14s} | {c['score']:6.1f} / 100", flush=True)

