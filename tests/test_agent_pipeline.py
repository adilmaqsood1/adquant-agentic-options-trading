"""
Quick test: validates all 3 agent layer imports and runs one mini-cycle.
Run from backend/ directory:
  python test_agent_pipeline.py
"""
import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

print("=" * 70)
print("AUTONOMOUS 3-LAYER AGENT PIPELINE -- IMPORT & SMOKE TEST")
print("=" * 70)

# -- Layer 1 
print("\n[1] Testing Data Agent imports...")
try:
    from app.agents.data_agent import run_data_agent, compute_feature_snapshot, get_all_snapshots
    print("    [OK] data_agent.py loaded successfully")
except Exception as e:
    print(f"    [FAIL] data_agent.py: {e}")
    sys.exit(1)

# -- Layer 2 
print("\n[2] Testing Strategy Agents imports...")
try:
    from app.agents.strategy_agents import STRATEGY_AGENTS, run_strategy_agent, run_all_strategy_agents
    print(f"    [OK] strategy_agents.py loaded -- {len(STRATEGY_AGENTS)} strategies registered")
    for a in STRATEGY_AGENTS:
        print(f"       - [{a['timeframe']}] {a['id']}: {a['name']}")
except Exception as e:
    print(f"    [FAIL] strategy_agents.py: {e}")
    sys.exit(1)

# -- Layer 3 
print("\n[3] Testing Research Agent imports...")
try:
    from app.agents.research_agent import run_research_agent, get_latest_insights
    print("    [OK] research_agent.py loaded successfully")
except Exception as e:
    print(f"    [FAIL] research_agent.py: {e}")
    sys.exit(1)

# -- Orchestrator 
print("\n[4] Testing Orchestrator imports...")
try:
    from app.services.orchestrator import build_graph, run_cycle, AgentState
    graph = build_graph()
    print("    [OK] orchestrator.py loaded and graph compiled successfully")
except Exception as e:
    print(f"    [FAIL] orchestrator.py: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

# -- Mini FeatureSnapshot test 
print("\n[5] Testing FeatureSnapshot computation with synthetic data...")
try:
    import pandas as pd
    import numpy as np

    np.random.seed(42)
    n = 100
    close = 80000.0 + np.cumsum(np.random.randn(n) * 500)
    high  = close + np.abs(np.random.randn(n) * 200)
    low   = close - np.abs(np.random.randn(n) * 200)
    vol   = np.random.uniform(1e6, 5e6, n)
    dates = pd.date_range("2025-01-01", periods=n, freq="4h")

    df = pd.DataFrame({
        "open": close * 0.999,
        "high": high,
        "low": low,
        "close": close,
        "volume": vol
    }, index=dates)

    snap = compute_feature_snapshot("BTC/USD", df)
    print(f"    [OK] FeatureSnapshot computed: {len(snap)} fields")
    print(f"       Price:               ${snap['price']:,.2f}")
    print(f"       RSI-14:              {snap['rsi_14']:.1f}")
    print(f"       ADX-14:              {snap['adx_14']:.1f}")
    print(f"       EMA Bullish Cross:   {snap['ema_bullish_cross']}")
    print(f"       Supertrend Bullish:  {snap['supertrend_bullish']}")
    print(f"       BB Squeeze Active:   {snap['bb_squeeze_active']}")
    print(f"       Volume Ratio 20avg:  {snap['volume_ratio_vs_20avg']:.2f}x")
    print(f"       30D Return:          {snap['ret_30d_pct']:+.1f}%")
except Exception as e:
    print(f"    [FAIL] FeatureSnapshot: {e}")
    import traceback; traceback.print_exc()

print("\n" + "=" * 70)
print("ALL IMPORTS PASSED")
print("=" * 70)
print("\nTo run a full live cycle, call:")
print("  from app.services.orchestrator import run_cycle")
print("  result = run_cycle('4H', ['supertrend', 'donchian_turtle'])")
print()
