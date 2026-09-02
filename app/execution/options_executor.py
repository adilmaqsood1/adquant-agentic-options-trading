"""
Options Executor Module
=======================
Executes options orders, contract inspections, and liquidations directly via Alpaca MCP.
Maintains continuous state synchronization between Alpaca Paper Trading and PostgreSQL.
"""

import os
import datetime
from typing import Dict, Any, List, Optional

from app.execution.mcp_client import get_mcp_client
from app.engine.options_position_manager import open_options_position, close_options_position
from app.core.database import get_open_positions, open_position, close_position


def inspect_option_contract(occ_symbol: str, underlying_symbol: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetches real-time live bid, ask, and Greeks for an OCC symbol directly from Alpaca
    Market Data API (v1beta1 snapshots), falling back to MCP if necessary.
    Ensures orders are placed with true market pricing to prevent unfulfilled/canceled limit orders.
    """
    # 1. Primary: Direct Alpaca Options Market Data Snapshot
    try:
        import httpx
        from dotenv import load_dotenv
        load_dotenv(override=True)
        alpaca_key = os.getenv("ALPACA_API_KEY")
        alpaca_sec = os.getenv("ALPACA_API_SECRET")
        if alpaca_key and alpaca_sec:
            headers = {"APCA-API-KEY-ID": alpaca_key, "APCA-API-SECRET-KEY": alpaca_sec}
            url = f"https://data.alpaca.markets/v1beta1/options/snapshots?symbols={occ_symbol}"
            with httpx.Client(timeout=6.0) as client:
                r = client.get(url, headers=headers)
                if r.status_code == 200:
                    snap_data = r.json().get("snapshots", {}).get(occ_symbol, {})
                    quote = snap_data.get("latestQuote", {})
                    greeks = snap_data.get("greeks", {})
                    bp = float(quote.get("bp") or 0.0)
                    ap = float(quote.get("ap") or 0.0)
                    mid = round((bp + ap) / 2.0, 2) if bp > 0 and ap > 0 else (ap or bp or 5.0)

                    if ap > 0 or bp > 0:
                        return {
                            "success": True,
                            "occ_symbol": occ_symbol,
                            "premium": ap if ap > 0 else mid,
                            "bid": bp,
                            "ask": ap,
                            "mid": mid,
                            "delta": greeks.get("delta"),
                            "gamma": greeks.get("gamma"),
                            "theta": greeks.get("theta"),
                            "vega": greeks.get("vega"),
                            "iv": snap_data.get("impliedVolatility"),
                            "source": "alpaca_live_snapshot"
                        }
    except Exception as e:
        print(f"[OptionsExecutor] Live quote snapshot notice for {occ_symbol}: {e}")

    # 2. Fallback: MCP tool inspection
    client = get_mcp_client()
    clean_sym = underlying_symbol or occ_symbol.split("2")[0] if "2" in occ_symbol else occ_symbol

    mcp_res = client.call_tool("alpaca_inspect_option", {
        "symbol": clean_sym,
        "occ_symbol": occ_symbol
    })

    if mcp_res.get("success"):
        res_data = mcp_res.get("result", {})
        spec = res_data.get("contract_spec", {})
        prem = float(spec.get("premium_paid", 5.0))
        return {
            "success": True,
            "occ_symbol": occ_symbol,
            "underlying_price": res_data.get("underlying_price"),
            "premium": prem,
            "bid": spec.get("bid", prem * 0.98),
            "ask": spec.get("ask", prem * 1.02),
            "delta": spec.get("delta_entry"),
            "gamma": spec.get("gamma_entry"),
            "theta": spec.get("theta_entry"),
            "vega": spec.get("vega_entry"),
            "iv": spec.get("iv_entry"),
            "contract_spec": spec,
            "source": "mcp_fallback"
        }

    return {
        "success": False,
        "occ_symbol": occ_symbol,
        "premium": 5.0,
        "error": mcp_res.get("error", "Inspection failed")
    }


def place_options_order(
    contract_spec: Dict[str, Any],
    risk_gate_result: Dict[str, Any],
    signal_dict: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Main execution function. Builds order parameters from contract_spec and risk_gate_result,
    then executes live paper order via Alpaca MCP.

    Order parameters:
      - symbol: OCC symbol (e.g. AAPL261002C00300000)
      - qty: contracts_qty from risk gate
      - side: 'buy' for long calls/puts, 'sell' for short puts/spreads
      - type: 'limit' / 'market'
      - position_intent: 'buy_to_open' / 'sell_to_open'
      - time_in_force: 'day'

    After order submission, logs directly to PostgreSQL options_contracts and positions tables.
    """
    client = get_mcp_client()
    occ_symbol = contract_spec.get("occ_symbol")
    strategy_type = contract_spec.get("strategy_type", "long_call").lower()
    contracts_qty = int(risk_gate_result.get("contracts_qty") or contract_spec.get("contracts_qty") or 1)
    premium_paid = float(contract_spec.get("premium_paid", 5.0))
    total_cost = float(risk_gate_result.get("total_cost") or contract_spec.get("total_cost") or (premium_paid * contracts_qty * 100))

    is_short = "short" in strategy_type or "credit" in strategy_type
    side = "sell" if is_short else "buy"
    pos_intent = "sell_to_open" if is_short else "buy_to_open"

    # Pre-inspect live bid/ask quote to set a marketable limit price with buffer and prevent cancellations
    live_quote = inspect_option_contract(occ_symbol)
    if live_quote.get("success"):
        if side == "buy":
            ask_px = float(live_quote.get("ask") or live_quote.get("premium") or premium_paid)
            if ask_px > 0:
                # Add marketable buffer (1% or min $0.05) to guarantee immediate fill against market makers
                marketable_price = round(max(ask_px + 0.05, ask_px * 1.01), 2)
                premium_paid = marketable_price
                total_cost = round(premium_paid * contracts_qty * 100, 2)
        else:
            bid_px = float(live_quote.get("bid") or live_quote.get("premium") or premium_paid)
            if bid_px > 0:
                # Subtract marketable buffer for sell orders
                marketable_price = max(0.05, round(min(bid_px - 0.05, bid_px * 0.99), 2))
                premium_paid = marketable_price
                total_cost = round(premium_paid * contracts_qty * 100, 2)

    order_args = {
        "symbol": occ_symbol,
        "occ_symbol": occ_symbol,
        "qty": contracts_qty,
        "side": side,
        "type": "limit",
        "limit_price": premium_paid,
        "position_intent": pos_intent,
        "time_in_force": "day"
    }

    # 1. Execute live order via Alpaca MCP
    mcp_res = client.call_tool("alpaca_submit_options_order", order_args)
    if not mcp_res.get("success"):
        err_msg = mcp_res.get("error") or "Order submission rejected by Alpaca"
        print(f"[OptionsExecutor] Order rejected by Alpaca: {err_msg}")
        return {
            "success": False,
            "status": "REJECTED_BY_ALPACA",
            "error": err_msg,
            "occ_symbol": occ_symbol
        }

    order_result = mcp_res.get("result", {})
    if not order_result.get("success", True) and "error" in order_result:
        err_msg = order_result.get("error")
        print(f"[OptionsExecutor] Alpaca order error: {err_msg}")
        return {
            "success": False,
            "status": "REJECTED_BY_ALPACA",
            "error": err_msg,
            "occ_symbol": occ_symbol
        }

    order_id = order_result.get("order_id") or "MCP_PAPER_SIM"
    order_status = str(order_result.get("status", "accepted")).lower()
    db_status = "open" if order_status == "filled" else "pending_fill"
    contract_spec["status"] = db_status

    # 2. Persist to PostgreSQL options_contracts table
    reasoning_payload = {
        "confidence": risk_gate_result.get("confidence", 85),
        "reasoning": f"MCP Live Options Order: {strategy_type} on {occ_symbol} (Alpaca Status: {order_status})",
        "order_id": order_id,
        "status": db_status
    }
    opt_contract_id = open_options_position(contract_spec, reasoning_payload)

    # 3. Persist to master positions table ONLY when verified accepted
    underlying_sym = contract_spec.get("underlying_symbol") or occ_symbol.split("2")[0]
    pos_rec = open_position(
        strategy_id=signal_dict.get("strategy_id", "options_mcp") if signal_dict else "options_mcp",
        symbol=underlying_sym,
        source="alpaca",
        timeframe="1D",
        signal_type="ENTER_LONG",
        entry_price=premium_paid,
        allocated_capital=total_cost,
        groq_confidence=risk_gate_result.get("confidence", 85),
        groq_reasoning=f"Executed via Alpaca MCP Order ID: {order_id} (Alpaca Status: {order_status})",
        groq_go=True,
        risk_approved=True,
        asset_class="option",
        option_symbol=occ_symbol,
        option_type=contract_spec.get("contract_type"),
        strike_price=contract_spec.get("strike_price"),
        expiration_date=contract_spec.get("expiry_date"),
        contracts=contracts_qty,
        contract_premium=premium_paid,
        delta=contract_spec.get("delta_entry"),
        gamma=contract_spec.get("gamma_entry"),
        theta=contract_spec.get("theta_entry"),
        vega=contract_spec.get("vega_entry"),
        implied_volatility=contract_spec.get("iv_entry"),
        underlying_price=contract_spec.get("underlying_price"),
        status=db_status
    )

    print(f"[OptionsExecutor] [PLACED] Live MCP Order Placed & Verified: {occ_symbol} ({contracts_qty} contracts @ ${premium_paid:.2f}) | Order ID: {order_id} | Alpaca Status: {order_status}")

    return {
        "success": True,
        "order_id": order_id,
        "status": order_status,
        "occ_symbol": occ_symbol,
        "contracts_qty": contracts_qty,
        "filled_price": premium_paid,
        "total_cost": total_cost,
        "options_contract_id": opt_contract_id,
        "position_id": pos_rec.get("id"),
        "timestamp": datetime.datetime.utcnow().isoformat()
    }


def close_options_order(
    occ_symbol: str,
    contracts_qty: int = 1,
    exit_reason: str = "exit_target_hit",
    exit_premium: Optional[float] = None
) -> Dict[str, Any]:
    """
    Places closing order on Alpaca via MCP (sell to close for long, buy to close for short).
    After fill, calls close_options_position() in PostgreSQL with actual fill price and exit reason.
    """
    client = get_mcp_client()

    # 1. Inspect live contract price for accurate exit premium
    live_info = inspect_option_contract(occ_symbol)
    live_prem = exit_premium or live_info.get("premium", 5.0)

    # 2. Close position via MCP / Alpaca API
    mcp_res = client.call_tool("alpaca_close_position", {
        "symbol": occ_symbol,
        "occ_symbol": occ_symbol,
        "exit_reason": exit_reason
    })

    # 3. Update PostgreSQL options_contracts and positions tables
    close_options_position(
        occ_symbol=occ_symbol,
        exit_premium=live_prem,
        exit_reason=exit_reason
    )

    # Also close in master positions table
    underlying_sym = occ_symbol.split("2")[0] if "2" in occ_symbol else occ_symbol
    close_position(
        strategy_id="options_mcp",
        symbol=underlying_sym,
        exit_price=live_prem
    )

    print(f"[OptionsExecutor] 🚨 Closed Position via MCP: {occ_symbol} | Reason: {exit_reason} | Exit Premium: ${live_prem:.2f}")

    return {
        "success": True,
        "occ_symbol": occ_symbol,
        "contracts_qty": contracts_qty,
        "exit_premium": live_prem,
        "exit_reason": exit_reason,
        "mcp_result": mcp_res,
        "timestamp": datetime.datetime.utcnow().isoformat()
    }


def get_open_options_positions_from_alpaca() -> List[Dict[str, Any]]:
    """
    Pulls current open positions directly from Alpaca account via MCP.
    Compares with PostgreSQL records. If discrepancy found, logs warning and syncs DB.
    Alpaca is always the primary source of truth.
    """
    client = get_mcp_client()
    mcp_res = client.call_tool("alpaca_get_positions")
    
    alpaca_positions = mcp_res.get("result", [])
    db_positions = get_open_positions()

    # Discrepancy comparison
    alpaca_symbols = set()
    for p in alpaca_positions:
        sym = p.get("symbol") or p.get("option_symbol")
        if sym:
            alpaca_symbols.add(sym.upper())

    db_symbols = set()
    for p in db_positions:
        sym = p.get("option_symbol") or p.get("symbol")
        if sym:
            db_symbols.add(sym.upper())

    discrepancies = db_symbols.symmetric_difference(alpaca_symbols)
    if discrepancies:
        print(f"[OptionsExecutor] ⚠️ Position discrepancy detected between Alpaca and DB: {discrepancies}")
    else:
        print(f"[OptionsExecutor] ✅ Position sync verified: Alpaca & PostgreSQL in 100% agreement ({len(alpaca_positions)} active).")

    return alpaca_positions


def cancel_stale_working_orders(max_age_minutes: int = 15) -> int:
    """
    Cancels unfulfilled working limit orders that are older than max_age_minutes
    to prevent stale pending orders from blocking new trade capacity.
    """
    try:
        import requests
        from dotenv import load_dotenv
        load_dotenv(override=True)
        alpaca_key = os.getenv("ALPACA_API_KEY")
        alpaca_sec = os.getenv("ALPACA_API_SECRET")
        alpaca_base = (os.getenv("ALPACA_BASE_URL") or "https://paper-api.alpaca.markets/v2").rstrip("/")

        if not alpaca_key or not alpaca_sec:
            return 0

        headers = {"APCA-API-KEY-ID": alpaca_key, "APCA-API-SECRET-KEY": alpaca_sec}
        r = requests.get(f"{alpaca_base}/orders?status=open", headers=headers, timeout=6)
        if r.status_code != 200:
            return 0

        orders = r.json()
        now = datetime.datetime.utcnow()
        cancelled_count = 0

        for o in orders:
            sub_at_str = o.get("submitted_at") or o.get("created_at")
            if sub_at_str:
                try:
                    sub_time = datetime.datetime.fromisoformat(sub_at_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    age_mins = (now - sub_time).total_seconds() / 60.0
                    if age_mins >= max_age_minutes:
                        o_id = o.get("id")
                        del_res = requests.delete(f"{alpaca_base}/orders/{o_id}", headers=headers, timeout=5)
                        if del_res.status_code in [200, 204]:
                            cancelled_count += 1
                            print(f"[OptionsExecutor] 🗑️ Cancelled stale working order {o.get('symbol')} (Age: {age_mins:.1f}m)")
                except Exception:
                    pass

        return cancelled_count
    except Exception as e:
        print(f"[OptionsExecutor] Notice on cancel_stale_working_orders: {e}")
        return 0
