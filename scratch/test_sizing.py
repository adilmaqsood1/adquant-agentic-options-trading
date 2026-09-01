import os, sys
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from app.engine.risk_gate_agent import evaluate_options_risk_gates

test_signals = [
    {
        'contract': {'symbol': 'AAPL', 'underlying_symbol': 'AAPL', 'occ_symbol': 'AAPL261016C00230000', 'contract_type': 'call', 'strategy_type': 'long_call', 'strike_price': 230.0, 'expiry_date': '2026-10-16', 'dte_at_entry': 45, 'premium_paid': 4.50, 'iv_rank': 25.0, 'underlying_price': 225.0},
        'ai_decision': {'symbol': 'AAPL', 'strategy_id': 'cross_sectional_momentum', 'confidence': 92, 'conviction_tier': 'HIGH_ALPHA', 'recommended_capital_usd': 9000.0, 'suggested_size_pct': 100}
    },
    {
        'contract': {'symbol': 'NVDA', 'underlying_symbol': 'NVDA', 'occ_symbol': 'NVDA261016C00125000', 'contract_type': 'call', 'strategy_type': 'long_call', 'strike_price': 125.0, 'expiry_date': '2026-10-16', 'dte_at_entry': 45, 'premium_paid': 5.20, 'iv_rank': 30.0, 'underlying_price': 122.0},
        'ai_decision': {'symbol': 'NVDA', 'strategy_id': 'rsi_oversold_reversal', 'confidence': 85, 'conviction_tier': 'CONFLUENCE_CORE', 'recommended_capital_usd': 6500.0, 'suggested_size_pct': 100}
    },
    {
        'contract': {'symbol': 'MSFT', 'underlying_symbol': 'MSFT', 'occ_symbol': 'MSFT261016C00450000', 'contract_type': 'call', 'strategy_type': 'long_call', 'strike_price': 450.0, 'expiry_date': '2026-10-16', 'dte_at_entry': 45, 'premium_paid': 8.50, 'iv_rank': 28.0, 'underlying_price': 445.0},
        'ai_decision': {'symbol': 'MSFT', 'strategy_id': 'supertrend', 'confidence': 78, 'conviction_tier': 'TACTICAL', 'recommended_capital_usd': 5100.0, 'suggested_size_pct': 100}
    }
]

for s in test_signals:
    c = s['contract']
    sig = s['ai_decision']
    res = evaluate_options_risk_gates(contract_spec=c, signal_dict=sig, open_positions=[], atr_14=3.5, current_price=c['underlying_price'])
    app = res.get('approved')
    cnt = res.get('contracts_qty', 0)
    out = res.get('total_cost', 0)
    tier = sig['conviction_tier']
    rec = sig['recommended_capital_usd']
    print(f"[{tier:15s}] {c['symbol']:4s} -> AI Recommended: ${rec:,.2f} | Risk Approved: {app} | Final Contracts: {cnt:2d} | Outlay: ${out:,.2f}")
