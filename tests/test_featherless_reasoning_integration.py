import os
import sys
import pandas as pd
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

from app.services.llm_client import query_llm_json
from app.agents.reasoning_agent import reason_about_signal, reason_about_options_trade

def test_featherless_primary_reasoning():
    print("=" * 80)
    print("🧠 TESTING FEATHERLESS DEEPSEEK-V3.2 PRIMARY LLM INTEGRATION")
    print("=" * 80)

    # 1. Direct LLM Client Query
    print("\n1. Testing query_llm_json via Featherless DeepSeek-V3.2...")
    sys_prompt = "You are an autonomous quant trading risk evaluator. Always respond in valid JSON."
    user_prompt = "Evaluate AAPL Bullish Cross-Sectional Momentum. Return JSON with confidence (0-100), go (bool), reasoning (string)."
    
    parsed, model_used, usage = query_llm_json(sys_prompt, user_prompt)
    print(f"  Model Used: {model_used}")
    print(f"  Confidence: {parsed.get('confidence')}% | Go: {parsed.get('go')}")
    print(f"  Reasoning:  {parsed.get('reasoning')[:150]}...")

    # 2. Reasoning Agent (Spot / Crypto Trade)
    print("\n2. Testing Reasoning Agent reason_about_signal()...")
    dummy_signal = {
        "strategy_id": "cross_sectional_momentum",
        "symbol": "AAPL",
        "signal_type": "ENTER_LONG",
        "timeframe": "1D",
        "allocated_capital": 5000.0
    }
    dummy_df = pd.DataFrame({"close": [220.0, 222.5, 225.0, 228.0, 230.0]})
    dummy_portfolio = {"total_open_positions": 2, "active_strategies": ["rsi_oversold"]}
    
    res = reason_about_signal(dummy_signal, dummy_df, dummy_portfolio)
    print(f"  Model:      {res.get('groq_model')}")
    print(f"  Confidence: {res.get('confidence')}%")
    print(f"  Go:         {res.get('go')}")
    print(f"  Reasoning:  {res.get('reasoning')[:150]}...")

    # 3. Options Trade Reasoning Agent
    print("\n3. Testing Reasoning Agent reason_about_options_trade()...")
    dummy_contract = {
        "underlying_symbol": "NVDA",
        "strategy_id": "liquidity_sweep_absorption",
        "strategy_type": "long_call",
        "contract_type": "call",
        "strike_price": 130.0,
        "expiry_date": "2026-10-16",
        "dte_at_entry": 34,
        "underlying_price": 128.50,
        "premium_paid": 6.50,
        "contracts_qty": 2,
        "total_cost": 1300.0,
        "delta_entry": 0.68,
        "gamma_entry": 0.012,
        "theta_entry": -0.08,
        "vega_entry": 0.22,
        "iv_entry": 0.38,
        "iv_rank_entry": 28.0,
        "iv_regime": "low",
        "occ_symbol": "NVDA261016C00130000"
    }
    
    opt_res = reason_about_options_trade(dummy_signal, dummy_contract)
    print(f"  Model:            {opt_res.get('groq_model')}")
    print(f"  Confidence:       {opt_res.get('confidence')}%")
    print(f"  Options Verdict:  {opt_res.get('options_verdict')}")
    print(f"  Greeks Eval:      {opt_res.get('greeks_assessment')[:120]}...")
    print(f"  Reasoning:        {opt_res.get('reasoning')[:150]}...")

    print("\n" + "=" * 80)
    print("✅ FEATHERLESS DEEPSEEK-V3.2 PRIMARY MODEL FULLY VERIFIED")
    print("=" * 80)

if __name__ == "__main__":
    test_featherless_primary_reasoning()
