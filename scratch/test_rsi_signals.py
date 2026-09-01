import os, sys
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from app.services.market_state import fetch_symbol
from app.services.signal_detector import detect_signal

test_symbols = ["WELL", "VLO", "MPC", "DOC", "PSX", "LW", "IWM", "ORLY", "A", "DGX", "MMM", "EVRG", "BKR", "SMH", "KMB"]

print("Testing Agentic Signal Detector on RSI Oversold candidates...\n")

fired_count = 0
for sym in test_symbols:
    df = fetch_symbol(sym, source="alpaca", timeframe="1D", bars_needed=200)
    if df is not None and not df.empty:
        sig = detect_signal("rsi_oversold_reversal", sym, df)
        if sig.get("fired"):
            fired_count += 1
            print(f"[FIRED] {sym:6s} | Action: {sig['signal_type']:10s} | Price: ${sig['last_close']:7.2f} | Strategy: {sig['strategy_id']}")
        else:
            print(f"[IDLE]  {sym:6s} | Action: {sig['signal_type']:10s} | Price: ${sig['last_close']:7.2f}")

print(f"\nTotal Fired Signals: {fired_count}/{len(test_symbols)}")
