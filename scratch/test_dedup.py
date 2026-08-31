from app.core.database import get_open_positions
from app.engine.contract_selector import select_contract
from app.engine.risk_gate_agent import evaluate_options_risk_gates

open_items = get_open_positions()
print(f"Active positions & working orders count: {len(open_items)}")
for item in open_items:
    print(f"  - {item['symbol']} ({item['option_symbol']}) | Status: {item['status']} | Working: {item.get('is_working_order')}")

# Test duplicate signal on ABT
sig = {'symbol': 'ABT', 'strategy_id': 'momentum_ema_rsi_adx', 'confidence': 90}
spec = select_contract(sig, underlying_price=108.0)
gate = evaluate_options_risk_gates(spec, sig, open_positions=open_items, current_price=108.0)
print("\nDuplicate ABT Gate Evaluation:")
print(f"  Approved: {gate.get('approved')}")
print(f"  Failed Gate: {gate.get('gate_failed')}")
print(f"  Reason: {gate.get('reason')}")
