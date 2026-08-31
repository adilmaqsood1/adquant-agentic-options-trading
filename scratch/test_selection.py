from app.engine.contract_selector import select_contract
from app.engine.risk_gate_agent import evaluate_options_risk_gates

symbols = [('COO', 71.50, 'call'), ('HRL', 31.20, 'put'), ('IR', 78.40, 'call'), ('EXR', 142.0, 'call'), ('MAA', 132.50, 'call')]

for sym, px, ctype in symbols:
    sig = {'symbol': sym, 'strategy_id': 'liquidity_sweep_absorption', 'signal_type': 'ENTER_LONG' if ctype == 'call' else 'ENTER_SHORT', 'groq_confidence': 85}
    spec = select_contract(sig, underlying_price=px)
    gate = evaluate_options_risk_gates(spec, sig, open_positions=[], current_price=px)
    print(f"{sym}: OCC={spec['occ_symbol']} | Qty={gate.get('contracts_qty')} | Cost=${gate.get('total_cost')} | Approved={gate.get('approved')}")
