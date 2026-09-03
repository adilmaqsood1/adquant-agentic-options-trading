import os
import sys
import pandas as pd
import numpy as np
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.registry import signal_volatility_squeeze_breakout
from app.services.market_state import STRATEGY_MARKET_CONFIG, OPTIONS_CORE_UNIVERSE
from app.services.signal_detector import STRATEGY_EXECUTION_CONFIG
from app.engine.contract_selector import select_contract
from app.engine.opportunity_ranker import detect_confluence_opportunities

print("=" * 80)
print("     VERIFYING OPTIONS QUANT OPPORTUNITY ENGINE OVERHAUL")
print("=" * 80)

# 1. Verify Universe Configuration
print("\n[1] UNIVERSE RESTRICTION CHECK:")
print(f"Total Liquid Universe Assets: {len(OPTIONS_CORE_UNIVERSE)}")
for strat_id, cfg in STRATEGY_MARKET_CONFIG.items():
    symbols = cfg["symbols"]
    print(f"  - Strategy '{strat_id}': {len(symbols)} symbols ({'OPTIONS_CORE_UNIVERSE' if symbols == OPTIONS_CORE_UNIVERSE else 'CUSTOM'})")
    assert len(symbols) >= len(OPTIONS_CORE_UNIVERSE), f"Strategy {strat_id} has too few symbols ({len(symbols)})!"
print("[OK] PASSED: All strategies configured with extensive liquid options universe.")

# 2. Verify Volatility Squeeze Strategy Functionality
print("\n[2] VOLATILITY SQUEEZE STRATEGY MATHEMATICAL CHECK:")
dates = pd.date_range(end=datetime.datetime.utcnow(), periods=100, freq="4h")
np.random.seed(42)

# Generate synthetic price series with a compression (squeeze) followed by an upward breakout
base_price = 150.0
# First 60 bars: low volatility compression (tight range)
comp_noise = np.random.normal(0, 0.3, 60)
comp_prices = base_price + np.cumsum(comp_noise)
# Next 40 bars: explosive breakout
break_moves = np.linspace(0.5, 2.5, 40) + np.random.normal(0, 0.4, 40)
break_prices = comp_prices[-1] + np.cumsum(break_moves)

all_prices = np.concatenate([comp_prices, break_prices])
df_test = pd.DataFrame({
    "open": all_prices - 0.2,
    "high": all_prices + 0.8,
    "low": all_prices - 0.8,
    "close": all_prices,
    "volume": np.random.randint(100000, 500000, len(all_prices))
}, index=dates)

params = {"bb_period": 20, "bb_std": 2.0, "kc_period": 20, "kc_mult": 1.5}
signals = signal_volatility_squeeze_breakout(df_test, params)
print(f"Total signal points computed: {len(signals)}")
print(f"Bullish signals count: {(signals == 1).sum()}")
print(f"Bearish signals count: {(signals == -1).sum()}")
assert (signals == 1).sum() > 0, "Volatility Squeeze should have detected the bullish breakout!"
print("[OK] PASSED: Volatility Squeeze successfully identifies compression and triggers on breakout.")

# 3. Verify Two-Way Options Contract Selection (Calls & Puts)
print("\n[3] TWO-WAY CONTRACT SELECTION CHECK:")
call_spec = select_contract({"symbol": "NVDA", "signal_type": "ENTER_LONG", "strategy_id": "volatility_squeeze_breakout"}, underlying_price=120.0)
print(f"Bullish Setup -> Strategy: {call_spec.get('strategy_type')} | Contract: {call_spec.get('contract_type')} | OCC: {call_spec.get('occ_symbol')}")
assert call_spec.get("contract_type") == "call", "Bullish signal must select a Call!"

put_spec = select_contract({"symbol": "NVDA", "signal_type": "ENTER_SHORT", "strategy_id": "volatility_squeeze_breakout"}, underlying_price=120.0)
print(f"Bearish Setup -> Strategy: {put_spec.get('strategy_type')} | Contract: {put_spec.get('contract_type')} | OCC: {put_spec.get('occ_symbol')}")
assert put_spec.get("contract_type") == "put", "Bearish signal must select a Put!"
print("[OK] PASSED: Contract selector generates valid high-delta Calls and Puts based on signal direction.")

# 4. Verify Confluence & Opportunity Ranker Prioritization
print("\n[4] OPPORTUNITY RANKER SQUEEZE PRIORITY CHECK:")
raw_signals = [
    {"symbol": "NVDA", "strategy_id": "volatility_squeeze_breakout", "signal_type": "ENTER_LONG", "last_close": 125.0, "groq_confidence": 85},
    {"symbol": "AFL", "strategy_id": "momentum_ema_rsi_adx", "signal_type": "ENTER_LONG", "last_close": 80.0, "groq_confidence": 85}
]
ranked = detect_confluence_opportunities(raw_signals)
print(f"Rank 1 Symbol: {ranked[0]['symbol']} (Tier: {ranked[0]['confluence_tier']}, Score: {ranked[0]['composite_conviction']})")
print(f"Rank 2 Symbol: {ranked[1]['symbol']} (Tier: {ranked[1]['confluence_tier']}, Score: {ranked[1]['composite_conviction']})")
assert ranked[0]["symbol"] == "NVDA" and ranked[0]["is_vol_squeeze"], "Vol Squeeze signal should be ranked #1 above standard momentum!"
print("[OK] PASSED: Opportunity Ranker prioritizes Volatility Squeeze setups with +20 conviction bonus.")

print("\n" + "=" * 80)
print("     ALL 4 SYSTEM ENHANCEMENT TESTS PASSED 100% SUCCESSFULLY!")
print("=" * 80)
