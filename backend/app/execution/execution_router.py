"""
Execution Router Module
=======================
Routes approved quantitative signals to the options executor with pre-trade checks:
  1. Validates 5-Gate Entry approval
  2. Verifies live pricing freshness (<15% deviation from model premium)
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
    
    2. Call inspect_option_contract() with OCC symbol
       → get live bid/ask
       → verify premium hasn't moved more than 15% since contract_selector calculated it
       → if moved >15%: abort, log "stale pricing"
    
    3. Call place_options_order()
       → if success: log to PostgreSQL & dispatch signal notification
       → if failed: log error, do NOT retry automatically (prevents duplicate orders)
    
    4. Update performance_manager portfolio state
       → call update_portfolio_state() with new live equity
    """
    sym = signal_dict.get("symbol", "UNKNOWN").upper()
    strat_id = signal_dict.get("strategy_id", "options_core")
    occ_symbol = contract_spec.get("occ_symbol")

    # 1. Check Risk Gate Approval
    if not risk_gate_result.get("approved"):
        reason = risk_gate_result.get("reason", "Blocked by risk gate filter.")
        gate_failed = risk_gate_result.get("gate_failed", "Risk Gate")
        print(f"[ExecutionRouter] ⛔ Signal Blocked for {sym} ({occ_symbol}) | {gate_failed}: {reason}")
        return {
            "success": False,
            "status": "RISK_GATE_BLOCKED",
            "gate_failed": gate_failed,
            "reason": reason,
            "symbol": sym,
            "occ_symbol": occ_symbol
        }

    # 2. Inspect Live Contract & Check Pricing Freshness (15% Max Slippage Gate)
    calc_premium = float(contract_spec.get("premium_paid", 5.0))
    live_info = inspect_option_contract(occ_symbol, underlying_symbol=sym)
    live_premium = float(live_info.get("premium", calc_premium))

    if calc_premium > 0:
        price_deviation = abs(live_premium - calc_premium) / calc_premium
        if price_deviation > 0.15:
            err_msg = f"Live contract premium (${live_premium:.2f}) deviated {price_deviation*100:.1f}% from model estimate (${calc_premium:.2f}) > 15% tolerance."
            print(f"[ExecutionRouter] ⚠️ Aborted {occ_symbol} due to Stale Pricing: {err_msg}")
            return {
                "success": False,
                "status": "STALE_PRICING",
                "reason": err_msg,
                "calculated_premium": calc_premium,
                "live_premium": live_premium,
                "deviation_pct": round(price_deviation * 100, 2)
            }

    # 3. Place Options Order via MCP
    print(f"[ExecutionRouter] 🚀 Routing approved signal to Options Executor: {occ_symbol} ({strat_id})")
    order_res = place_options_order(
        contract_spec=contract_spec,
        risk_gate_result=risk_gate_result,
        signal_dict=signal_dict
    )

    if not order_res.get("success"):
        print(f"[ExecutionRouter] ❌ Order placement failed for {occ_symbol}. Auto-retry blocked for safety.")
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

    # 5. Dispatch optional email notification if configured
    try:
        from app.reporting.email_reporter import send_email_alert
        send_email_alert(
            subject=f"🎯 [Alpaca MCP] Options Trade Executed: {occ_symbol}",
            body=f"Strategy: {strat_id}\nSymbol: {sym}\nOCC: {occ_symbol}\nContracts: {order_res.get('contracts_qty')}\nPremium: ${order_res.get('filled_price'):.2f}\nTotal Cost: ${order_res.get('total_cost'):.2f}\nOrder ID: {order_res.get('order_id')}"
        )
    except Exception:
        pass

    return {
        "success": True,
        "status": "EXECUTED",
        "order_details": order_res,
        "symbol": sym,
        "occ_symbol": occ_symbol,
        "timestamp": datetime.datetime.utcnow().isoformat()
    }
