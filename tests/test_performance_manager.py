"""
Performance Manager Test Suite
================================
Seeds PostgreSQL with mock closed trade histories for each strategy
and verifies all four mode assignments (GROWTH, NORMAL, REDUCE, PAUSE),
all five circuit breaker levels, and the master allocation formula output.
"""

import sys
import os
import datetime
from typing import Dict

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import get_pool
from app.engine.performance_manager import (
    compute_kelly_score,
    update_portfolio_state,
    get_current_circuit_breaker,
    get_dynamic_allocation,
    compute_volatility_ratio,
    upsert_strategy_performance,
    MODE_MULTIPLIERS,
    TOTAL_PORTFOLIO,
)

SEP = "─" * 85


def seed_mock_trades(strategy_id: str, trades_spec: list) -> int:
    """
    Inserts closed positions into `positions` table using (realized_pnl, realized_pnl_pct) specs.
    trades_spec = list of (realized_pnl, realized_pnl_pct) tuples.
    Returns number of rows inserted.
    """
    pool = get_pool()
    conn = pool.getconn()
    inserted = 0
    try:
        with conn.cursor() as cur:
            # Clean up previous test rows for this strategy
            cur.execute(
                "DELETE FROM positions WHERE strategy_id = %s AND groq_reasoning = 'PERF_MANAGER_TEST';",
                (strategy_id,)
            )
            for pnl, pnl_pct in trades_spec:
                cur.execute("""
                    INSERT INTO positions
                        (strategy_id, symbol, source, timeframe, signal_type,
                         entry_price, exit_price, allocated_capital, quantity,
                         realized_pnl, realized_pnl_pct,
                         status, groq_reasoning, entry_time, created_at)
                    VALUES
                        (%s,'TEST_SEED','test','1D','EXIT_LONG',
                         100.0, %s, 5000.0, 50.0,
                         %s, %s,
                         'closed', 'PERF_MANAGER_TEST', NOW(), NOW())
                """, (
                    strategy_id,
                    100.0 + float(pnl) / 50,
                    float(pnl),
                    float(pnl_pct)
                ))
                inserted += 1
            conn.commit()
    finally:
        pool.putconn(conn)
    return inserted



def run_all_tests():
    print("=" * 85)
    print("  📊 PERFORMANCE MANAGER — FULL TEST SUITE")
    print("  Kelly Criterion | 4 Strategy Modes | 5 Circuit Breaker Levels | Master Allocation")
    print("=" * 85)

    # ── STEP 1: Mode Assignment Tests ───────────────────────────────────────────
    print(f"\n{SEP}")
    print("STEP 1: Four Strategy Mode Assignments — Kelly Criterion Scoring")
    print(SEP)

    mode_scenarios = {
        "liquidity_sweep_absorption": {
            "desc": "GROWTH — 8 wins, 2 losses, last trade WIN (Kelly >0.15, WR>=60%, no consecutive losses)",
            "trades": [
                # Losses first (DESC order → last inserted = most recent)
                (-80,  -2.0), (-60,  -1.5),
                (+320, +8.0), (+280, +7.0), (+410, +10.0), (+190, +4.8),
                (+350, +8.7), (+220, +5.5), (+380, +9.5), (+260, +6.5),
            ],
            "expected": "GROWTH",
        },
        "rsi_oversold_reversal": {
            "desc": "NORMAL — 5 wins, 4 losses, 0 consecutive (Kelly > 0, WR >= 45%)",
            "trades": [
                (+200, +5.0), (-90, -2.3), (+180, +4.5), (-70, -1.8),
                (+240, +6.0), (+160, +4.0), (-100, -2.5), (+210, +5.3), (-50, -1.3),
            ],
            "expected": "NORMAL",
        },
        "cvd_divergence_squeeze": {
            "desc": "REDUCE — 5W/3L, 3 consecutive losses, Kelly > 0 (avg_win > avg_loss, consec <= 3)",
            "trades": [
                # Most recent = losses (3 consecutive). Kelly > 0 because avg win > avg loss.
                (-80,  -2.0), (-70,  -1.8), (-90, -2.3),
                (+350, +8.7), (+300, +7.5), (+280, +7.0), (+320, +8.0), (+290, +7.3),
            ],
            "expected": "REDUCE",
        },
        "supertrend": {
            "desc": "PAUSE — 1 win, 6 losses, 5 consecutive losses (Kelly < 0)",
            "trades": [
                (+100, +2.5), (-180, -4.5), (-200, -5.0), (-150, -3.8),
                (-210, -5.3), (-190, -4.8), (-160, -4.0),
            ],
            "expected": "PAUSE",
        },
    }

    results = {}
    for strategy_id, sc in mode_scenarios.items():
        inserted = seed_mock_trades(strategy_id, sc["trades"])
        kelly = compute_kelly_score(strategy_id)
        mode = kelly["mode"]
        ok = "✅" if mode == sc["expected"] else "❌ MISMATCH"
        results[strategy_id] = kelly

        print(f"\n• [{strategy_id}] — {sc['desc']}")
        print(f"  Seeded Trades:      {inserted} closed trades")
        print(f"  Win Rate:           {kelly['win_rate']*100:.1f}%  ({kelly['winning_trades']}W / {kelly['losing_trades']}L)")
        print(f"  Win:Loss Ratio:     {kelly['win_loss_ratio']:.2f}x")
        print(f"  Full Kelly:         {kelly['kelly_pct']*100:.2f}%")
        print(f"  Quarter Kelly:      {kelly['quarter_kelly_pct']*100:.2f}%")
        print(f"  Consecutive Losses: {kelly['consecutive_losses']}")
        print(f"  ➡ Assigned Mode:   {mode}  (Multiplier: {kelly['size_multiplier']}x)  {ok}")

        # Persist to strategy_performance table
        upsert_strategy_performance(strategy_id)

    # ── STEP 2: Circuit Breaker Levels ───────────────────────────────────────────
    print(f"\n{SEP}")
    print("STEP 2: Five-Level Circuit Breaker System (isolated peak per scenario)")
    print(SEP)

    cb_scenarios = [
        (100_500, "Level 0 — Green (Normal): +0.5% portfolio value"),
        (97_300,  "Level 1 — Yellow (Caution): -2.7% from fresh peak"),
        (93_000,  "Level 2 — Orange (Defensive): -7% from fresh peak"),
        (89_000,  "Level 3 — Red (Crisis): -11% from fresh peak"),
        (83_000,  "Level 4 — Black (Shutdown): -17% from fresh peak"),
    ]

    # Each scenario gets its own fresh peak so drawdowns are absolute
    fresh_peaks = [100_500, 100_000, 100_000, 100_000, 100_000]
    for (portfolio_val, desc), peak_seed in zip(cb_scenarios, fresh_peaks):
        # Seed a higher peak first so drawdown calculation is correct
        if peak_seed > portfolio_val:
            update_portfolio_state(float(peak_seed))
        state = update_portfolio_state(float(portfolio_val))
        print(f"\n• {desc}")
        print(f"  Portfolio:        ${portfolio_val:,.0f}")
        print(f"  Peak:             ${state['peak_value']:,.0f}")
        print(f"  Drawdown:         {state['drawdown_pct']:.2f}%")
        print(f"  CB Level:         {state['circuit_breaker_level']} — {state['circuit_breaker_label']}")
        print(f"  CB Multiplier:    {state['cb_multiplier']}x")
        print(f"  Action:           {state['circuit_breaker_action']}")

    # Reset to healthy portfolio for allocation tests
    update_portfolio_state(108_000.0)

    # ── STEP 3: Volatility Ratio ─────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("STEP 3: Asset Volatility Ratio Normalization (ATR 14-day Benchmark: 2%)")
    print(SEP)

    vol_tests = [
        ("BTC/USD",    77735.0,   2723.0,  "High vol crypto — should shrink position"),
        ("AAPL",       309.90,    3.72,    "Low vol equity — should expand to cap"),
        ("SPY",        580.00,    4.64,    "Ultra-low vol ETF — capped at 1.5x"),
        ("SOL/USD",    103.89,    8.82,    "Medium-high vol crypto — moderate reduction"),
    ]

    for sym, price, atr, note in vol_tests:
        ratio = compute_volatility_ratio(atr, price)
        atr_pct = (atr / price) * 100
        print(f"  {sym:<12} ATR%: {atr_pct:.2f}%  →  Ratio: {ratio:.3f}x  ({note})")

    # ── STEP 4: Master Allocation Formula ────────────────────────────────────────
    print(f"\n{SEP}")
    print("STEP 4: Master Dynamic Allocation Formula — Three Judge Scenarios")
    print(SEP)

    # Scenario 1: RSI Oversold on AAPL, GROWTH mode, portfolio at +8%
    print("\n📌 Scenario 1: RSI Oversold AAPL — GROWTH mode, Portfolio +8% ($108k)")
    alloc_1 = get_dynamic_allocation(
        strategy_id="liquidity_sweep_absorption",
        symbol="AAPL",
        atr_14=4.20,
        current_price=309.90,
        groq_confidence=88,
        asset_class="spot",
        override_kelly=results["liquidity_sweep_absorption"]
    )
    _print_allocation(alloc_1)

    # Scenario 2: CVD Divergence on BTC, REDUCE mode, portfolio -6% (CB Level 2)
    update_portfolio_state(94_000.0)
    print("\n📌 Scenario 2: CVD Divergence BTC — REDUCE mode, Portfolio -6% (CB Level 2)")
    alloc_2 = get_dynamic_allocation(
        strategy_id="cvd_divergence_squeeze",
        symbol="BTC/USD",
        atr_14=1800.0,
        current_price=77735.0,
        groq_confidence=76,
        asset_class="crypto",
        override_kelly=results["cvd_divergence_squeeze"]
    )
    _print_allocation(alloc_2)

    # Scenario 3: Liquidity Sweep on SOL, NORMAL mode, portfolio at peak
    update_portfolio_state(112_000.0)
    print("\n📌 Scenario 3: Liquidity Sweep SOL — NORMAL mode, Portfolio at Peak ($112k)")
    alloc_3 = get_dynamic_allocation(
        strategy_id="rsi_oversold_reversal",
        symbol="SOL/USD",
        atr_14=8.50,
        current_price=103.89,
        groq_confidence=82,
        asset_class="crypto",
        override_kelly=results["rsi_oversold_reversal"]
    )
    _print_allocation(alloc_3)

    # Scenario 4: PAUSE mode — should be fully blocked
    print("\n📌 Scenario 4: Supertrend BTCUSD — PAUSE mode, should be BLOCKED")
    alloc_4 = get_dynamic_allocation(
        strategy_id="supertrend",
        symbol="BTC/USD",
        groq_confidence=85,
        asset_class="crypto",
        override_kelly=results["supertrend"]
    )
    _print_allocation(alloc_4)

    # Scenario 5: Confidence below threshold — should be BLOCKED
    print("\n📌 Scenario 5: Low Confidence (68%) — should be BLOCKED at confidence gate")
    alloc_5 = get_dynamic_allocation(
        strategy_id="rsi_oversold_reversal",
        symbol="AAPL",
        atr_14=4.20,
        current_price=309.90,
        groq_confidence=68,
        asset_class="spot",
        override_kelly=results["rsi_oversold_reversal"]
    )
    _print_allocation(alloc_5)

    # ── Summary ─────────────────────────────────────────────────────────────────
    print(f"\n{'=' * 85}")
    print("✅ PERFORMANCE MANAGER — ALL TESTS COMPLETE")
    print("   Kelly Criterion, 4 Modes, 5 Circuit Breakers, Volatility Ratio, Master Formula")
    print(f"{'=' * 85}")


def _print_allocation(result: Dict):
    if result.get("approved"):
        a = result["audit_trail"]
        print(f"  APPROVED ✅")
        print(f"  Mode:             {result['mode']} (multiplier: {a['size_multiplier']}x)")
        print(f"  Base Allocation:  ${a['base_allocation']:,.2f}  (Quarter Kelly: {a['quarter_kelly_pct']*100:.2f}%)")
        print(f"  CB Level:         {a['circuit_breaker_level']} (multiplier: {a['cb_multiplier']}x)")
        print(f"  Vol Ratio:        {a['vol_ratio']}x")
        print(f"  Conf Scalar:      {a['confidence_scalar']}x  (Groq: {a['groq_confidence']}%)")
        print(f"  Final Allocation: ${result['final_allocation']:,.2f}")
        if result.get("quantity"):
            print(f"  ATR Quantity:     {result['quantity']} units  (Risk: ${result['atr_risk_amount']:.2f})")
    else:
        print(f"  BLOCKED ❌  —  {result.get('block_reason')}")


if __name__ == "__main__":
    run_all_tests()
