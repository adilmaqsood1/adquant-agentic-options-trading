from app.engine.options_exit_guardian import evaluate_position_exit_with_ai

# Test 1: Hard Stop Loss (-38%)
pos_loss = {
    "symbol": "AAPL",
    "option_symbol": "AAPL261002C00215000",
    "strategy_id": "momentum_ema_rsi_adx",
    "strategy_type": "long_call",
    "entry_price": 5.00,
    "strike_price": 215.0,
    "quantity": 2
}
res1 = evaluate_position_exit_with_ai(pos_loss, live_premium=3.10, underlying_price=210.0, current_dte=25)
print("Test 1 (Hard Stop Loss -38%):")
print("  Action:", res1.get("action"))
print("  Should Close:", res1.get("should_close"))
print("  Reason:", res1.get("reasoning"))

# Test 2: Hard Time Stop (5 DTE)
pos_time = {
    "symbol": "MSFT",
    "option_symbol": "MSFT260905C00440000",
    "strategy_id": "lead_lag_propagation",
    "strategy_type": "long_call",
    "entry_price": 6.00,
    "strike_price": 440.0,
    "quantity": 1
}
res2 = evaluate_position_exit_with_ai(pos_time, live_premium=6.20, underlying_price=442.0, current_dte=5)
print("\nTest 2 (Hard Time Stop 5 DTE):")
print("  Action:", res2.get("action"))
print("  Should Close:", res2.get("should_close"))
print("  Reason:", res2.get("reasoning"))

# Test 3: Profit Runner with 28 DTE (+70% profit)
pos_runner = {
    "symbol": "NVDA",
    "option_symbol": "NVDA261002C00125000",
    "strategy_id": "liquidity_sweep_absorption",
    "strategy_type": "long_call",
    "entry_price": 6.00,
    "strike_price": 125.0,
    "quantity": 3
}
res3 = evaluate_position_exit_with_ai(pos_runner, live_premium=10.20, underlying_price=132.0, current_dte=28)
print("\nTest 3 (+70% Profit Runner with 28 DTE):")
print("  Action:", res3.get("action"))
print("  Should Close:", res3.get("should_close"))
print("  Reason:", res3.get("reasoning"))
