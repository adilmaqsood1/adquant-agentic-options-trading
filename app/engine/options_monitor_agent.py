
import datetime
from typing import Dict, Any, List, Optional, Tuple
from app.core.database import get_open_positions, close_position
from app.engine.options_position_manager import close_options_position, snapshot_greeks
from app.engine.options_pricing import BlackScholesEngine
from data.alpaca_source import fetch_alpaca_latest_prices

def run_options_monitor_cycle(
    live_prices: Optional[Dict[str, float]] = None,
    current_signals: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Monitor Agent (Runs every single cycle for all open positions):
    Enforces the Non-Negotiable 4-Exit System:

    EXIT 3 (Checked FIRST): Time Stop at 14 DTE
      -> Close ALL long options when DTE reaches 14. Prevents exponential theta decay.

    EXIT 1: Profit Target
      -> Long Calls/Puts: Close at +60% gain on premium.
      -> Spreads: Close at +40% max profit.
      -> Short Puts: Close at +50% premium collected.

    EXIT 2: Stop Loss
      -> Long Calls/Puts: Close at -35% loss on premium.
      -> Spreads: Close at -50% max loss.
      -> Short Puts: Close if underlying drops 4% below short strike.

    EXIT 4: Signal Reversal
      -> Close immediately if opposite strategy signal fires.
    """
    open_pos = get_open_positions()
    options_pos = [p for p in open_pos if p.get("asset_class") == "option" or bool(p.get("option_symbol"))]

    if not options_pos:
        return {
            "positions_monitored": 0,
            "exits_triggered": 0,
            "actions": [],
            "status": "No active options positions to monitor."
        }

    # Fetch live prices if not provided
    if live_prices is None:
        syms = list(set([p.get("symbol") for p in options_pos if p.get("symbol")]))
        live_prices = fetch_alpaca_latest_prices(syms)

    actions = []
    exits_triggered = 0

    for p in options_pos:
        sym = p.get("symbol", "").upper()
        occ_symbol = p.get("option_symbol") or f"{sym}_OPT"
        strategy_id = p.get("strategy_id", "options_core")
        entry_prem = float(p.get("contract_premium") or p.get("entry_price") or 0.0)
        contracts = int(p.get("contracts") or 1)
        strike = float(p.get("strike_price") or 0.0)
        opt_type = p.get("option_type") or "call"
        exp_date_str = p.get("expiration_date")
        strategy_type = p.get("strategy_type", "long_call")

        # 1. Compute DTE remaining
        today = datetime.date.today()
        dte = 30
        if exp_date_str:
            try:
                if isinstance(exp_date_str, str):
                    exp_date = datetime.date.fromisoformat(exp_date_str.split("T")[0])
                else:
                    exp_date = exp_date_str
                dte = (exp_date - today).days
            except Exception:
                dte = 30

        # 2. Get live underlying price & calculate live option mark
        underlying_px = live_prices.get(sym, float(p.get("underlying_price") or 0.0))
        if underlying_px <= 0:
            underlying_px = float(p.get("underlying_price") or 100.0)

        T = max(1e-4, dte / 365.0)
        iv = float(p.get("implied_volatility") or 0.28)
        if iv > 1.0:
            iv = iv / 100.0

        try:
            greeks = BlackScholesEngine.calculate_greeks(
                S=underlying_px,
                K=strike,
                T=T,
                r=0.045,
                sigma=iv,
                option_type=opt_type
            )
            live_opt_prem = greeks["price"]
        except Exception:
            live_opt_prem = entry_prem
            greeks = {"delta": 0.70, "theta": -0.10}

        # Snapshot real-time Greeks to options_greeks_history
        try:
            if occ_symbol:
                snapshot_greeks(occ_symbol, underlying_px)
        except Exception:
            pass

        # Calculate PnL & return %
        prem_pnl = live_opt_prem - entry_prem
        prem_pnl_pct = (prem_pnl / entry_prem * 100.0) if entry_prem > 0 else 0.0

        # Extract opposing strategy signal if present
        opposing_sig = None
        if current_signals:
            for sig in current_signals:
                if sig.get("symbol", "").upper() == sym:
                    opposing_sig = sig.get("signal_type", "")
                    break

        # --- EVALUATE WITH HYBRID DEEPSEEK-V3.2 EXIT GUARDIAN ---
        from app.engine.options_exit_guardian import evaluate_position_exit_with_ai
        guardian_eval = evaluate_position_exit_with_ai(
            position=p,
            live_premium=live_opt_prem,
            underlying_price=underlying_px,
            current_dte=dte,
            greeks=greeks,
            market_regime="SIDEWAYS_CONSOLIDATION",
            opposing_signal=opposing_sig
        )

        should_close = guardian_eval.get("should_close", False)
        exit_reason = guardian_eval.get("exit_reason") if should_close else None
        exit_details = guardian_eval.get("reasoning", "")

        # Execute Exit if Triggered
        if exit_reason:
            exits_triggered += 1
            realized_pnl = round(prem_pnl * contracts * 100.0, 2)
            
            # Execute closing order via Alpaca MCP & synchronize PostgreSQL
            try:
                from app.execution.options_executor import close_options_order
                close_options_order(
                    occ_symbol=occ_symbol,
                    contracts_qty=contracts,
                    exit_reason=exit_reason,
                    exit_premium=live_opt_prem
                )
            except Exception as mcp_err:
                print(f"[MonitorAgent] Options executor close error: {mcp_err}")
                # Fallback to direct DB close
                try:
                    close_position(strategy_id=strategy_id, symbol=sym, exit_price=live_opt_prem)
                    close_options_position(occ_symbol=occ_symbol, exit_premium=live_opt_prem, exit_reason=exit_reason)
                except Exception as db_err:
                    print(f"[MonitorAgent] DB fallback close error: {db_err}")

            action_record = {
                "symbol": sym,
                "occ_symbol": occ_symbol,
                "strategy_id": strategy_id,
                "action": "CLOSE_OPTION",
                "exit_reason": exit_reason,
                "entry_premium": entry_prem,
                "exit_premium": round(live_opt_prem, 2),
                "realized_pnl": realized_pnl,
                "realized_pnl_pct": round(prem_pnl_pct, 2),
                "dte_at_exit": dte,
                "details": exit_details
            }
            actions.append(action_record)
            print(f"[MONITOR AGENT EXIT] 🚨 Closed {occ_symbol} on {sym} | Reason: {exit_reason} | PnL: ${realized_pnl:+.2f} ({prem_pnl_pct:+.1f}%)")
        else:
            actions.append({
                "symbol": sym,
                "occ_symbol": occ_symbol,
                "action": "HOLD",
                "dte": dte,
                "live_premium": round(live_opt_prem, 2),
                "unrealized_pnl": round(prem_pnl * contracts * 100.0, 2),
                "unrealized_pct": round(prem_pnl_pct, 2),
                "delta": greeks.get("delta"),
                "theta": greeks.get("theta")
            })

    return {
        "positions_monitored": len(options_pos),
        "exits_triggered": exits_triggered,
        "actions": actions,
        "timestamp": datetime.datetime.utcnow().isoformat()
    }
