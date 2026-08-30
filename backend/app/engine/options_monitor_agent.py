
import datetime
from typing import Dict, Any, List, Optional, Tuple
from app.core.database import get_open_positions, close_position
from app.engine.options_position_manager import close_options_position, snapshot_greeks
from app.engine.options_pricing import BlackScholesEngine
from app.data.alpaca_source import fetch_alpaca_latest_prices

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

        # --- EVALUATE EXITS IN STRICT PRIORITY ORDER ---
        exit_reason = None
        exit_details = ""

        # EXIT 3 (CHECKED FIRST): Time Stop at 14 DTE
        if dte <= 14:
            exit_reason = "time_stop_14_dte"
            exit_details = f"DTE reached {dte} (<=14 DTE threshold). Force closed to eliminate exponential theta decay."

        # EXIT 1: Profit Target (+60% long options, +40% spreads, +50% short puts)
        elif strategy_type in ["long_call", "long_put"] and prem_pnl_pct >= 60.0:
            exit_reason = "profit_target_60pct"
            exit_details = f"Profit target reached (+{prem_pnl_pct:.1f}% >= +60.0% target). Took money off the table."
        elif "spread" in strategy_type and prem_pnl_pct >= 40.0:
            exit_reason = "profit_target_spread_40pct"
            exit_details = f"Spread profit target reached (+{prem_pnl_pct:.1f}% >= +40.0%)."
        elif strategy_type == "short_put" and prem_pnl_pct >= 50.0:
            exit_reason = "profit_target_short_put_50pct"
            exit_details = f"Short put captured 50% decay credit (+{prem_pnl_pct:.1f}%)."

        # EXIT 2: Stop Loss (-35% long options, -50% spreads, 4% underlying drop on short puts)
        elif strategy_type in ["long_call", "long_put"] and prem_pnl_pct <= -35.0:
            exit_reason = "stop_loss_35pct"
            exit_details = f"Stop loss triggered ({prem_pnl_pct:.1f}% <= -35.0% stop). Cut loser fast."
        elif "spread" in strategy_type and prem_pnl_pct <= -50.0:
            exit_reason = "stop_loss_spread_50pct"
            exit_details = f"Spread max loss stop triggered ({prem_pnl_pct:.1f}% <= -50.0%)."
        elif strategy_type == "short_put" and strike > 0 and (underlying_px < strike * 0.96):
            exit_reason = "stop_loss_short_put_underlying_drop"
            exit_details = f"Underlying dropped 4% below short strike (${underlying_px:.2f} < ${strike * 0.96:.2f})."

        # EXIT 4: Signal Reversal
        elif current_signals:
            for sig in current_signals:
                if sig.get("symbol", "").upper() == sym:
                    sig_type = sig.get("signal_type", "").upper()
                    if ("SELL" in sig_type or "BEAR" in sig_type or "EXIT" in sig_type) and opt_type == "call":
                        exit_reason = "signal_reversal"
                        exit_details = f"Quantitative model {strategy_id} generated opposite signal ({sig_type}). Closed immediately."
                        break

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
