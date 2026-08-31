from app.engine.options_exit_guardian import evaluate_position_exit_with_ai

# Cycle 1: NVDA runner hits +70% profit with 28 DTE
pos_cycle_1 = {
    "symbol": "NVDA",
    "option_symbol": "NVDA261002C00125000",
    "strategy_id": "liquidity_sweep_absorption",
    "strategy_type": "long_call",
    "entry_price": 6.00,
    "strike_price": 125.0,
    "quantity": 3,
    "trail_stop_floor_pct": 0.0,
    "trail_stop_premium": 0.0
}
res1 = evaluate_position_exit_with_ai(pos_cycle_1, live_premium=10.20, underlying_price=132.0, current_dte=28)
print("--- CYCLE 1 (+70% RUNNER) ---")
print("  Action:", res1.get("action"))
print("  Should Close:", res1.get("should_close"))
print("  Reason:", res1.get("reasoning"))

# Simulate that the trailing stop floor (+45% -> $8.70) was written to the position record
pos_cycle_2 = dict(pos_cycle_1)
pos_cycle_2["trail_stop_floor_pct"] = 45.0
pos_cycle_2["trail_stop_premium"] = 8.70

# Cycle 2: Premium pulls back to $8.40 (+40% PnL, falling below the +45% / $8.70 floor)
res2 = evaluate_position_exit_with_ai(pos_cycle_2, live_premium=8.40, underlying_price=129.0, current_dte=27)
print("\n--- CYCLE 2 (PULLBACK BELOW +45% TRAILING FLOOR) ---")
print("  Action:", res2.get("action"))
print("  Should Close:", res2.get("should_close"))
print("  Reason:", res2.get("reasoning"))

# Test 3: Normal holding phase (+10% PnL, 30 DTE) -> Decision Point Filter verifies 0 LLM calls
pos_normal = {
    "symbol": "AAPL",
    "option_symbol": "AAPL261002C00215000",
    "strategy_id": "momentum_ema_rsi_adx",
    "strategy_type": "long_call",
    "entry_price": 5.00,
    "quantity": 2
}
res3 = evaluate_position_exit_with_ai(pos_normal, live_premium=5.50, underlying_price=212.0, current_dte=30)
print("\n--- TEST 3 (NORMAL HOLDING PHASE +10% PnL) ---")
print("  Action:", res3.get("action"))
print("  Should Close:", res3.get("should_close"))
print("  Reason:", res3.get("reasoning"))
