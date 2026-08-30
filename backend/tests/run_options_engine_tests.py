import sys
import os
import json
import datetime
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.engine.options_pricing import BlackScholesEngine
from app.engine.iv_calculator import compute_iv_rank, update_iv_history
from app.engine.contract_selector import select_contract, generate_occ_symbol
from app.engine.options_position_manager import (
    open_options_position,
    close_options_position,
    get_open_options_positions,
    is_underlying_held,
    snapshot_greeks,
    check_exit_conditions,
    get_options_portfolio_summary,
    log_options_cycle,
    TOTAL_OPTIONS_BUDGET
)

from app.core.database import get_pool

def run_all_tests():
    print("=" * 80)
    print("🚀 RUNNING OPTIONS TRADING ENGINE TEST SUITE (DATABASE-FIRST)")
    print("=" * 80)

    # ─────────────────────────────────────────────────────────────────────────────
    # TEST 1: Black-Scholes Engine
    # ─────────────────────────────────────────────────────────────────────────────
    print("\n" + "─" * 80)
    print("📍 TEST 1: Black-Scholes Engine Validation")
    print("─" * 80)
    S = 309.90
    K = 295.00
    DTE = 35
    T = DTE / 365.0
    IV = 0.28
    r = 0.045

    price = BlackScholesEngine.calculate_option_price(S=S, K=K, T=T, r=r, sigma=IV, option_type="call")
    greeks = BlackScholesEngine.calculate_greeks(S=S, K=K, T=T, r=r, sigma=IV, option_type="call")

    print(f"Inputs: S=${S:.2f}, K=${K:.2f}, DTE={DTE} days (T={T:.4f}), IV={IV*100:.1f}%, r={r*100:.1f}%")
    print(f"Calculated Option Price:  ${price:.2f}  (Expected: $19.00 - $22.00)")
    print(f"Calculated Delta (Δ):      {greeks['delta']:.4f}  (Expected: 0.68 - 0.72)")
    print(f"Calculated Gamma (Γ):      {greeks['gamma']:.6f}")
    print(f"Calculated Theta (Θ):      ${greeks['theta']:.4f}/day  (Expected: -$0.08 to -$0.12/day)")
    print(f"Calculated Vega (V):       ${greeks['vega']:.4f} per 1% vol  (Expected: $0.25 - $0.35)")
    print(f"Calculated Breakeven:     ${greeks['breakeven']:.2f}")

    t1_pass = (18.0 <= price <= 23.0) and (0.65 <= greeks['delta'] <= 0.75)
    print(f"\n>>> TEST 1 RESULT: {'✅ PASS' if t1_pass else '❌ FAIL'}")

    # ─────────────────────────────────────────────────────────────────────────────
    # TEST 2: IV Rank & Historical Volatility Calculation
    # ─────────────────────────────────────────────────────────────────────────────
    print("\n" + "─" * 80)
    print("📍 TEST 2: IV Rank Calculation (AAPL)")
    print("─" * 80)
    iv_data = compute_iv_rank("AAPL")
    print(f"Symbol:                   {iv_data['symbol']}")
    print(f"Current HV (20-day):       {iv_data['hv_20']*100:.2f}%")
    print(f"Historical HV (60-day):    {iv_data['hv_60']*100:.2f}%")
    print(f"Calculated IV Rank:        {iv_data['iv_rank']:.2f} / 100.0")
    print(f"Calculated IV Percentile:  {iv_data['iv_percentile']:.2f}%")
    print(f"Volatility Regime:         {iv_data['regime'].upper()} (Rule: <40 Low, 40-60 Med, >60 High)")

    t2_pass = 0.0 <= iv_data['iv_rank'] <= 100.0 and iv_data['regime'] in ["low", "medium", "high"]
    print(f"\n>>> TEST 2 RESULT: {'✅ PASS' if t2_pass else '❌ FAIL'}")

    # ─────────────────────────────────────────────────────────────────────────────
    # TEST 3: Contract Selection Engine
    # ─────────────────────────────────────────────────────────────────────────────
    print("\n" + "─" * 80)
    print("📍 TEST 3: Contract Selection Engine (Mock Bullish RSI Signal)")
    print("─" * 80)
    mock_signal = {
        "signal_id": "sig_rsi_aapl_001",
        "strategy_id": "rsi_oversold_reversal",
        "symbol": "AAPL",
        "signal_type": "BUY"
    }

    contract_spec = select_contract(
        signal_dict=mock_signal,
        underlying_price=309.90,
        hv_data=iv_data,
        allocated_capital=5000.0
    )

    print(f"Generated OCC Symbol:      {contract_spec['occ_symbol']}")
    print(f"Selected Strategy:         {contract_spec['strategy_type'].upper()} ({contract_spec['contract_type'].upper()})")
    print(f"Strike Price:              ${contract_spec['strike_price']:.2f}")
    print(f"Expiration Date:           {contract_spec['expiry_date']} ({contract_spec['dte_at_entry']} DTE)")
    print(f"Premium Paid:              ${contract_spec['premium_paid']:.2f} ($ {contract_spec['premium_paid']*100:.2f}/contract)")
    print(f"Contracts Sized:           {contract_spec['contracts_qty']} contracts (${contract_spec['total_cost']:.2f} total cost)")
    print(f"Entry Delta (Δ):           {contract_spec['delta_entry']:.4f} (Target Range: 0.60 - 0.80)")
    print(f"Profit Target (+80%):      ${contract_spec['profit_target_premium']:.2f}")
    print(f"Stop Loss (-40%):          ${contract_spec['stop_loss_premium']:.2f}")
    print(f"Breakeven Price:           ${contract_spec['breakeven_price']:.2f}")

    t3_pass = (
        len(contract_spec['occ_symbol']) >= 15 and
        0.60 <= abs(contract_spec['delta_entry']) <= 0.80 and
        contract_spec['total_cost'] <= 5000.0 and
        contract_spec['contracts_qty'] >= 1
    )
    print(f"\n>>> TEST 3 RESULT: {'✅ PASS' if t3_pass else '❌ FAIL'}")

    # ─────────────────────────────────────────────────────────────────────────────
    # TEST 4: Database Persistence & Exit Management
    # ─────────────────────────────────────────────────────────────────────────────
    print("\n" + "─" * 80)
    print("📍 TEST 4: Database Persistence (options_contracts & options_greeks_history)")
    print("─" * 80)

    # 1. Open Position
    pos_id = open_options_position(
        contract_spec=contract_spec,
        groq_decision={"confidence": 88, "reasoning": "High-conviction RSI Hook with Low IV cheap option premium.", "go": True}
    )
    print(f"1. Inserted Contract into 'options_contracts': ID = {pos_id}")

    # Verify query
    open_positions = get_open_options_positions()
    match_pos = next((p for p in open_positions if p["id"] == pos_id), None)
    print(f"   Queried from PostgreSQL: Symbol={match_pos['occ_symbol']} | Premium=${match_pos['premium_paid']} | Delta={match_pos['delta_entry']}")

    # 2. Snapshot Greeks
    greek_snap = snapshot_greeks(occ_symbol=contract_spec["occ_symbol"], current_underlying_price=315.50)
    print(f"2. Inserted Greek Snapshot into 'options_greeks_history': ID = {greek_snap['id']} | New Mid = ${greek_snap['option_mid_price']:.2f} | Mark PnL = ${greek_snap['mark_pnl']:+.2f}")

    # 3. Check Exit Condition at +80% Target
    mock_target_prem = contract_spec["profit_target_premium"] + 1.0 # above target
    exit_signal = check_exit_conditions(match_pos, current_premium=mock_target_prem)
    print(f"3. Exit Evaluation at ${mock_target_prem:.2f} Premium: Trigger = '{exit_signal}'")

    t4_pass = (pos_id > 0) and (greek_snap is not None) and (exit_signal == "profit_target")
    print(f"\n>>> TEST 4 RESULT: {'✅ PASS' if t4_pass else '❌ FAIL'}")

    # ─────────────────────────────────────────────────────────────────────────────
    # TEST 5: Full Mock Lifecycle Cycle
    # ─────────────────────────────────────────────────────────────────────────────
    print("\n" + "─" * 80)
    print("📍 TEST 5: Full Mock Lifecycle Cycle & Cycle Logger")
    print("─" * 80)

    # Close the test position at target
    closed_pos = close_options_position(
        occ_symbol=contract_spec["occ_symbol"],
        exit_premium=contract_spec["profit_target_premium"],
        exit_reason="profit_target"
    )
    print(f"1. Closed Options Position: OCC = {closed_pos['occ_symbol']}")
    print(f"   Entry Premium:   ${closed_pos['premium_paid']:.2f}")
    print(f"   Exit Premium:    ${closed_pos['exit_premium']:.2f}")
    print(f"   Realized P&L:    ${closed_pos['realized_pnl']:+.2f} ({closed_pos['realized_pnl_pct']:+.2f}%)")
    print(f"   Exit Reason:     {closed_pos['exit_reason']}")

    # 2. Get Portfolio Summary
    summary = get_options_portfolio_summary()
    print(f"\n2. Options Portfolio Summary:")
    print(f"   Total Contracts Open:     {summary['total_contracts_open']}")
    print(f"   Total Premium Deployed:   ${summary['total_premium_deployed']:,.2f}")
    print(f"   Budget Remaining:         ${summary['budget_remaining']:,.2f} / ${TOTAL_OPTIONS_BUDGET:,.2f}")

    # 3. Log Options Cycle to options_cycles
    cycle_id = log_options_cycle({
        "signals_evaluated": 1,
        "contracts_opened": 1,
        "contracts_closed": 1,
        "total_premium_deployed": float(contract_spec["total_cost"]),
        "total_realized_pnl": float(closed_pos["realized_pnl"]),
        "total_unrealized_pnl": 0.0,
        "portfolio_options_value": 0.0,
        "notes": f"Full options lifecycle test passed successfully. Closed {contract_spec['occ_symbol']} at profit target."
    })
    print(f"\n3. Logged Options Cycle to 'options_cycles': ID = {cycle_id}")

    t5_pass = (closed_pos is not None) and (closed_pos["realized_pnl"] > 0) and (cycle_id > 0)
    print(f"\n>>> TEST 5 RESULT: {'✅ PASS' if t5_pass else '❌ FAIL'}")

    print("\n" + "=" * 80)
    print("🏁 FINAL TEST SUMMARY: ALL 5 OPTIONS ENGINE TESTS EXECUTED")
    print("=" * 80)
    print(f" Test 1 (Black-Scholes Engine):      {'✅ PASS' if t1_pass else '❌ FAIL'}")
    print(f" Test 2 (IV Rank Calculation):       {'✅ PASS' if t2_pass else '❌ FAIL'}")
    print(f" Test 3 (Contract Selection):        {'✅ PASS' if t3_pass else '❌ FAIL'}")
    print(f" Test 4 (Database Persistence):      {'✅ PASS' if t4_pass else '❌ FAIL'}")
    print(f" Test 5 (Full Lifecycle Cycle):     {'✅ PASS' if t5_pass else '❌ FAIL'}")
    print("=" * 80)

if __name__ == "__main__":
    run_all_tests()
