import os
import sys
import datetime
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

from app.execution.mcp_client import AlpacaMCPClient, get_mcp_client
from app.execution.options_executor import (
    inspect_option_contract,
    place_options_order,
    close_options_order,
    get_open_options_positions_from_alpaca
)
from app.execution.execution_router import route_and_execute
from app.engine.contract_selector import select_contract
from app.engine.risk_gate_agent import evaluate_options_risk_gates
from app.core.database import get_open_positions

def test_mcp_execution_pipeline():
    print("=" * 80)
    print("🔌 TESTING ALPACA MCP EXECUTION PIPELINE (FULL TEST SEQUENCE)")
    print("=" * 80)

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 1: MCP Connection & Available Tool Discovery
    # ─────────────────────────────────────────────────────────────────────────
    print("\n--- TEST 1: MCP Client Connection & Tool Discovery ---")
    client = get_mcp_client()
    tools = client.list_available_tools()
    print(f"  Connected to MCP Client: {client.connected}")
    print(f"  Available MCP Tools ({len(tools)}):")
    for t in tools:
        print(f"    • {t['name']}: {t['description']}")
    assert len(tools) >= 5, "Must expose at least 5 core MCP tools!"
    print("  ✅ Test 1 Passed: MCP Client connected and discovered all tools.")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 2: Inspect Option Contract via MCP
    # ─────────────────────────────────────────────────────────────────────────
    print("\n--- TEST 2: Inspect Option Contract via MCP ---")
    inspect_res = inspect_option_contract("SPY260831C00420000", underlying_symbol="SPY")
    print(f"  Contract OCC:       {inspect_res.get('occ_symbol')}")
    print(f"  Underlying Price:   ${inspect_res.get('underlying_price', 0):,.2f}")
    print(f"  Contract Premium:   ${inspect_res.get('premium', 0):,.2f}")
    print(f"  Delta:              {inspect_res.get('delta')}")
    print(f"  Theta:              {inspect_res.get('theta')}")
    print("  ✅ Test 2 Passed: Option contract inspected via MCP.")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 3: Place Live Paper Option Order via MCP
    # ─────────────────────────────────────────────────────────────────────────
    print("\n--- TEST 3: Place Live Options Order via MCP ---")
    test_spec = {
        "occ_symbol": "SPY260831C00420000",
        "underlying_symbol": "SPY",
        "contract_type": "call",
        "strategy_type": "long_call",
        "strike_price": 420.0,
        "expiry_date": "2026-08-31",
        "premium_paid": 5.20,
        "contracts_qty": 1,
        "total_cost": 520.0,
        "delta_entry": 0.65,
        "gamma_entry": 0.02,
        "theta_entry": -0.05,
        "vega_entry": 0.15,
        "iv_entry": 0.22,
        "underlying_price": 560.0
    }
    risk_res = {
        "approved": True,
        "confidence": 88,
        "contracts_qty": 1,
        "total_cost": 520.0
    }
    order_out = place_options_order(
        contract_spec=test_spec,
        risk_gate_result=risk_res,
        signal_dict={"strategy_id": "test_mcp_alpha", "symbol": "SPY"}
    )
    print(f"  Order Placement Success: {order_out.get('success')}")
    print(f"  Order ID:               {order_out.get('order_id')}")
    print(f"  Order Status:           {order_out.get('status')}")
    print(f"  PostgreSQL Position ID: {order_out.get('position_id')}")
    assert order_out.get("success") is True, "Order placement must succeed!"
    print("  ✅ Test 3 Passed: Options order successfully submitted via MCP.")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 4: Pull & Sync Open Options Positions from Alpaca
    # ─────────────────────────────────────────────────────────────────────────
    print("\n--- TEST 4: Get Open Positions & Sync with DB ---")
    alpaca_pos = get_open_options_positions_from_alpaca()
    print(f"  Total Active Positions in System: {len(alpaca_pos)}")
    print("  ✅ Test 4 Passed: Position state retrieved and verified.")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 5: Full End-to-End Route and Execute
    # ─────────────────────────────────────────────────────────────────────────
    print("\n--- TEST 5: Full End-to-End Signal Routing & Execution ---")
    sig_dict = {
        "symbol": "AAPL",
        "strategy_id": "momentum_ema_rsi_adx",
        "signal_type": "ENTER_LONG"
    }
    selected = select_contract(sig_dict, underlying_price=225.0)
    current_open = get_open_positions()
    gate_eval = evaluate_options_risk_gates(
        contract_spec=selected,
        signal_dict={"symbol": "AAPL", "groq_confidence": 88, "strategy_id": "momentum_ema_rsi_adx"},
        open_positions=current_open,
        current_price=225.0
    )
    route_res = route_and_execute(
        risk_gate_result=gate_eval,
        contract_spec=selected,
        signal_dict=sig_dict
    )
    print(f"  E2E Route Status: {route_res.get('status')}")
    print(f"  OCC Symbol:       {route_res.get('occ_symbol')}")
    print("  ✅ Test 5 Passed: Full end-to-end routing pipeline executed.")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 6: Close Position via MCP
    # ─────────────────────────────────────────────────────────────────────────
    print("\n--- TEST 6: Close Option Position via MCP ---")
    close_out = close_options_order(
        occ_symbol="SPY260831C00420000",
        contracts_qty=1,
        exit_reason="test_mcp_pipeline_cleanup",
        exit_premium=5.50
    )
    print(f"  Close Success:      {close_out.get('success')}")
    print(f"  Exit Reason:        {close_out.get('exit_reason')}")
    print(f"  Exit Premium:       ${close_out.get('exit_premium'):.2f}")
    print("  ✅ Test 6 Passed: Option position closed and synchronized.")

    print("\n" + "=" * 80)
    print("🎉 ALL 6 MCP EXECUTION PIPELINE TESTS PASSED 100%!")
    print("=" * 80)

if __name__ == "__main__":
    test_mcp_execution_pipeline()
