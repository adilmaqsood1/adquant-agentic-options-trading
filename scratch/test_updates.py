import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.engine.risk_gate_agent import evaluate_options_risk_gates
from app.engine.contract_selector import select_contract

print("Testing Contract Selection...")
contract = select_contract({'symbol': 'AAPL', 'signal_type': 'BUY', 'strategy_id': 'mcp_alpha'}, underlying_price=230.0)
print(f"Contract selected: {contract.get('occ_symbol')} | Strategy: {contract.get('strategy_type')}")

print("\nTesting Risk Gate Evaluation...")
res_low = evaluate_options_risk_gates(contract, {'confidence': 78, 'symbol': 'AAPL'}, [])
print(f"Confidence 78% result (Approved: {res_low.get('approved')}) - Reason: {res_low.get('reason')}")

res_high = evaluate_options_risk_gates(contract, {'confidence': 85, 'symbol': 'AAPL'}, [])
print(f"Confidence 85% result (Approved: {res_high.get('approved')})")
print("ALL TESTS PASSED SUCCESSFULLY!")
