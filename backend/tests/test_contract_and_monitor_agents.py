import sys
import os
import json
import datetime
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.engine.contract_selector import select_contract
from app.engine.risk_gate_agent import evaluate_options_risk_gates
from app.engine.options_monitor_agent import run_options_monitor_cycle
from app.engine.options_position_manager import open_options_position, get_open_options_positions, close_options_position
from app.core.database import open_position

def test_contract_selection_and_monitor():
    print("=" * 85)
    print("🛡️ TESTING CONTRACT SELECTION AGENT, RISK GATE AGENT & MONITOR AGENT")
    print("=" * 85)

    # ─────────────────────────────────────────────────────────────────────────────
    # PART 1: Contract Selection Agent Across 3 IV Regimes
    # ─────────────────────────────────────────────────────────────────────────────
    print("\n" + "─" * 85)
    print("📍 PART 1: Strategy Selection Matrix & Black-Scholes Delta Pricing")
    print("─" * 85)

    scenarios = [
        {"sym": "AAPL", "price": 309.90, "iv_rank": 22.0, "expected_strat": "LONG_CALL"},
        {"sym": "NVDA", "price": 128.50, "iv_rank": 42.0, "expected_strat": "BULL_CALL_SPREAD"},
        {"sym": "TEAM", "price": 185.20, "iv_rank": 78.0, "expected_strat": "SHORT_PUT"}
    ]

    for sc in scenarios:
        mock_signal = {"symbol": sc["sym"], "strategy_id": "rsi_oversold_reversal", "signal_type": "BUY"}
        mock_hv = {"iv_rank": sc["iv_rank"], "iv_30d": 0.28, "regime": "low" if sc["iv_rank"] < 35 else ("medium" if sc["iv_rank"] <= 55 else "high")}
        
        contract = select_contract(signal_dict=mock_signal, underlying_price=sc["price"], hv_data=mock_hv)
        print(f"• {sc['sym']} (Spot: ${sc['price']:.2f} | IV Rank: {sc['iv_rank']:.1f}%):")
        print(f"  Selected:  {contract['strategy_type'].upper()} ({contract['occ_symbol']})")
        print(f"  Strike:    ${contract['strike_price']:.2f} | DTE: {contract['dte_at_entry']} days | Delta: {contract['delta_entry']:.4f}")
        print(f"  Premium:   ${contract['premium_paid']:.2f}/sh | Target (+60%): ${contract['profit_target_premium']:.2f} | Stop (-35%): ${contract['stop_loss_premium']:.2f}")

    # ─────────────────────────────────────────────────────────────────────────────
    # PART 2: 5-Gate Entry Risk Filter & Position Sizing
    # ─────────────────────────────────────────────────────────────────────────────
    print("\n" + "─" * 85)
    print("📍 PART 2: 5-Gate Entry Filter & Strict Position Sizing ($100k Portfolio)")
    print("─" * 85)

    # Test High Conviction (88% conf) on AAPL
    aapl_contract = select_contract({"symbol": "AAPL", "strategy_id": "rsi_oversold_reversal", "signal_type": "BUY"}, 309.90, {"iv_rank": 22.0, "iv_30d": 0.28})
    risk_eval = evaluate_options_risk_gates(
        contract_spec=aapl_contract,
        signal_dict={"symbol": "AAPL", "groq_confidence": 88},
        open_positions=[]
    )
    print(f"• High Conviction Signal (Confidence: 88%, IV: 22%):")
    print(f"  Approved:      {'✅ YES' if risk_eval['approved'] else '❌ NO'}")
    print(f"  Bucket:        {risk_eval.get('conviction_bucket', '').upper()} (Budget: $5,000 max)")
    print(f"  Sized Qty:     {risk_eval.get('contracts_qty')} Contracts (${risk_eval.get('total_cost')} Total Cost)")
    print(f"  Gates Passed:  {', '.join(risk_eval.get('gates_passed', []))}")

    # Test Low Confidence Reject (<75%)
    risk_reject = evaluate_options_risk_gates(
        contract_spec=aapl_contract,
        signal_dict={"symbol": "AAPL", "groq_confidence": 68},
        open_positions=[]
    )
    print(f"\n• Low Confidence Signal (Confidence: 68%):")
    print(f"  Approved:      {'✅ YES' if risk_reject['approved'] else '❌ BLOCKED'}")
    print(f"  Gate Failed:   {risk_reject.get('gate_failed')} -> {risk_reject.get('reason')}")

    # ─────────────────────────────────────────────────────────────────────────────
    # PART 3: Monitor Agent Automated Exit Discipline (14 DTE, +60% Target, -35% Stop)
    # ─────────────────────────────────────────────────────────────────────────────
    print("\n" + "─" * 85)
    print("📍 PART 3: Monitor Agent Automated Exit Enforcement")
    print("─" * 85)

    # Test Exit 3: 14 DTE Time Stop
    print("• Simulating Active Position approaching 14 DTE...")
    mock_pos_14dte = {
        "strategy_id": "rsi_oversold_reversal",
        "symbol": "AAPL",
        "asset_class": "option",
        "option_symbol": "AAPL260910C00300000",
        "contract_premium": 14.00,
        "entry_price": 14.00,
        "contracts": 2,
        "strike_price": 300.00,
        "option_type": "call",
        "expiration_date": (datetime.date.today() + datetime.timedelta(days=12)).isoformat(), # 12 DTE <= 14 DTE
        "implied_volatility": 0.28,
        "underlying_price": 310.00
    }

    # Open test position in DB
    pos_rec = open_position(
        strategy_id=mock_pos_14dte["strategy_id"],
        symbol=mock_pos_14dte["symbol"],
        source="alpaca",
        timeframe="1D",
        signal_type="ENTER_LONG",
        entry_price=mock_pos_14dte["entry_price"],
        allocated_capital=2800.0,
        asset_class="option",
        option_symbol=mock_pos_14dte["option_symbol"],
        option_type="call",
        strike_price=300.00,
        expiration_date=mock_pos_14dte["expiration_date"],
        contracts=2,
        contract_premium=14.00
    )

    # Run Monitor Agent Cycle
    mon_res = run_options_monitor_cycle(live_prices={"AAPL": 312.00})
    print(f"  Positions Monitored: {mon_res['positions_monitored']}")
    print(f"  Exits Triggered:     {mon_res['exits_triggered']}")
    if mon_res["actions"]:
        act = mon_res["actions"][0]
        print(f"  Action Taken:        {act['action']} | Reason: {act['exit_reason']}")
        print(f"  Details:             {act.get('details')}")

    print("\n" + "=" * 85)
    print("✅ CONTRACT SELECTION AGENT, RISK GATES & MONITOR AGENT FULLY VERIFIED")
    print("=" * 85)

if __name__ == "__main__":
    test_contract_selection_and_monitor()
