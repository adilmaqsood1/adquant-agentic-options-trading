import sys
import os
import json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.engine.contract_selector import select_contract
from app.engine.iv_calculator import compute_iv_rank
from app.agents.reasoning_agent import reason_about_options_trade

def test_bs_autonomous_reasoning():
    print("=" * 80)
    print("🧠 TESTING BLACK-SCHOLES + AUTONOMOUS AI REASONING AGENT")
    print("=" * 80)

    test_assets = [
        {"symbol": "AAPL", "strategy": "rsi_oversold_reversal", "price": 309.90, "signal": "BUY"},
        {"symbol": "NVDA", "strategy": "cvd_divergence_squeeze", "price": 128.50, "signal": "BUY"},
        {"symbol": "TEAM", "strategy": "liquidity_sweep_absorption", "price": 185.20, "signal": "BUY"}
    ]

    for asset in test_assets:
        sym = asset["symbol"]
        print(f"\n" + "─" * 80)
        print(f"📊 ASSET: {sym} | Price: ${asset['price']:.2f} | Strategy: {asset['strategy']}")
        print("─" * 80)

        # 1. Step 1: IV & Volatility Rank
        iv_data = compute_iv_rank(sym)
        print(f"1. IV Analysis: 20d HV = {iv_data['hv_20']*100:.1f}%, IV Rank = {iv_data['iv_rank']:.1f}% ({iv_data['regime'].upper()} IV Regime)")

        # 2. Step 2: Black-Scholes Contract Selection
        contract_spec = select_contract(
            signal_dict={"symbol": sym, "strategy_id": asset["strategy"], "signal_type": asset["signal"]},
            underlying_price=asset["price"],
            hv_data=iv_data,
            allocated_capital=5000.0
        )
        print(f"2. Option Selected: {contract_spec['occ_symbol']} (${contract_spec['strike_price']:.2f} Strike, {contract_spec['dte_at_entry']} DTE)")
        print(f"   Premium: ${contract_spec['premium_paid']:.2f} | Qty: {contract_spec['contracts_qty']} contracts | Total Cost: ${contract_spec['total_cost']:.2f}")
        print(f"   Greeks: Delta={contract_spec['delta_entry']:.4f} | Gamma={contract_spec['gamma_entry']:.6f} | Theta=${contract_spec['theta_entry']:.4f}/day | Vega=${contract_spec['vega_entry']:.4f}")

        # 3. Step 3: Groq Autonomous Reasoning Agent Evaluation
        print(f"\n3. 🤖 Invoking Autonomous Reasoning Agent (Groq / LLM)...")
        reasoning_res = reason_about_options_trade(
            signal_dict={"symbol": sym, "strategy_id": asset["strategy"], "signal_type": asset["signal"]},
            contract_spec=contract_spec
        )

        print(f"   • Agent Verdict:          {reasoning_res.get('options_verdict', 'N/A')}")
        print(f"   • Decision:               {'✅ GO (APPROVED)' if reasoning_res.get('go') else '❌ NO-GO (REJECTED)'}")
        print(f"   • Conviction Confidence:  {reasoning_res.get('confidence')}%")
        print(f"   • Greeks Assessment:     {reasoning_res.get('greeks_assessment')}")
        print(f"   • IV Regime Rationale:    {reasoning_res.get('iv_regime_rationale')}")
        print(f"   • Size Modifier:          {reasoning_res.get('suggested_size_modifier')}x")
        print(f"   • Synthesized Rationale:  {reasoning_res.get('reasoning')}")

    print("\n" + "=" * 80)
    print("✅ BLACK-SCHOLES + AUTONOMOUS REASONING INTEGRATION VERIFIED")
    print("=" * 80)

if __name__ == "__main__":
    test_bs_autonomous_reasoning()
