"""
Execution Router Module
=======================
Routes approved quantitative signals to the options executor with pre-trade checks:
  1. Validates 5-Gate Entry approval
  2. Syncs true live Alpaca contract quote & dynamically sizes contracts
  3. Executes order via Alpaca MCP
  4. Refreshes performance manager portfolio state and circuit breaker
"""

import os
import datetime
from typing import Dict, Any, Optional

from app.execution.options_executor import inspect_option_contract, place_options_order
from app.engine.performance_manager import update_portfolio_state, fetch_live_alpaca_equity


def route_and_execute(
    risk_gate_result: Dict[str, Any],
    contract_spec: Dict[str, Any],
    signal_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Main signal-to-execution router for 100% Options Alpha Trading:
    
    1. Check risk_gate_result["approved"] == True
       → if False: log blocked reason, return
    
    2. Inspect Live Contract on Alpaca:
       → fetch real-time bid/ask quote
       → dynamically calibrate contracts_qty and total_cost to true market premium
       → abort only if market quote is invalid or zero
    
    3. Call place_options_order() via Alpaca MCP
    
    4. Update performance_manager portfolio state
    """
    sym = signal_dict.get("symbol", "UNKNOWN").upper()
    strat_id = signal_dict.get("strategy_id", "options_core")
    occ_symbol = contract_spec.get("occ_symbol")

    # 1. Check Risk Gate Approval
    if not risk_gate_result.get("approved"):
        reason = risk_gate_result.get("reason", "Blocked by risk gate filter.")
        gate_failed = risk_gate_result.get("gate_failed", "Risk Gate")
        print(f"[ExecutionRouter] [BLOCKED] {sym} ({occ_symbol}) | {gate_failed}: {reason}")
        return {
            "success": False,
            "status": "RISK_GATE_BLOCKED",
            "gate_failed": gate_failed,
            "reason": reason,
            "symbol": sym,
            "occ_symbol": occ_symbol
        }

    # 2. Inspect Live Contract & Dynamically Calibrate to True Live Market Quote
    calc_premium = float(contract_spec.get("premium_paid", 5.0))
    live_info = inspect_option_contract(occ_symbol, underlying_symbol=sym)
    live_premium = float(live_info.get("premium") or calc_premium)

    if live_premium <= 0.05:
        err_msg = f"Invalid or non-tradable option premium quote (${live_premium:.2f}) for {occ_symbol}."
        print(f"[ExecutionRouter] [ABORTED] {occ_symbol}: {err_msg}")
        return {
            "success": False,
            "status": "INVALID_PREMIUM_QUOTE",
            "reason": err_msg,
            "live_premium": live_premium
        }

    # Update contract_spec with true live market premium and calibrate quantity
    contract_spec["premium_paid"] = round(live_premium, 4)
    allocated_cap = float(risk_gate_result.get("allocated_capital") or contract_spec.get("total_cost") or 1000.0)
    calibrated_qty = max(1, int(allocated_cap / (live_premium * 100.0)))
    contract_spec["contracts_qty"] = calibrated_qty
    contract_spec["total_cost"] = round(calibrated_qty * live_premium * 100.0, 2)

    # 3. Place Options Order via MCP
    print(f"[ExecutionRouter] Routing approved signal to Options Executor: {occ_symbol} ({strat_id}) | {calibrated_qty} contracts @ ${live_premium:.2f}")
    order_res = place_options_order(
        contract_spec=contract_spec,
        risk_gate_result=risk_gate_result,
        signal_dict=signal_dict
    )

    if not order_res.get("success"):
        print(f"[ExecutionRouter] Order placement failed for {occ_symbol}. Auto-retry blocked for safety.")
        return {
            "success": False,
            "status": "ORDER_SUBMISSION_FAILED",
            "error": order_res.get("error"),
            "occ_symbol": occ_symbol
        }

    # 4. Update Performance Manager Portfolio State
    try:
        live_equity = fetch_live_alpaca_equity()
        update_portfolio_state(live_equity)
    except Exception as e:
        print(f"[ExecutionRouter] Warning updating portfolio state: {e}")

    return {
        "success": True,
        "status": "EXECUTED",
        "order_details": order_res,
        "symbol": sym,
        "occ_symbol": occ_symbol,
        "contracts_qty": calibrated_qty,
        "execution_price": live_premium,
        "total_cost": contract_spec["total_cost"],
        "timestamp": datetime.datetime.utcnow().isoformat()
    }
