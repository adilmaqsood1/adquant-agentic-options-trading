"""
Alpaca AI Options Trading Engine — Command Line Interface (CLI)
===============================================================
Official CLI tool for interacting with autonomous options agents,
Black-Scholes Greek calculators, circuit breakers, and paper accounts.

Commands:
  python alpaca_cli.py account
  python alpaca_cli.py positions
  python alpaca_cli.py inspect <symbol>
  python alpaca_cli.py circuit-breaker
  python alpaca_cli.py trade --symbol <symbol> --strategy <type> --confidence <0-100>
  python alpaca_cli.py close --symbol <symbol_or_occ>
  python alpaca_cli.py monitor
  python alpaca_cli.py scan [--timeframe 1D]
"""

import sys
import os
import argparse
import json
from tabulate import tabulate

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.mcp.alpaca_tools import (
    get_account_summary,
    get_active_positions,
    inspect_option_opportunity,
    get_system_circuit_breaker,
    execute_options_trade,
    close_active_position,
    run_monitor_cycle_tool
)

def print_header(title: str):
    print("\n" + "=" * 80)
    print(f"  ⚡ ALPACA AI OPTIONS ALPHA ENGINE — {title.upper()}")
    print("=" * 80)

def cmd_account(args):
    print_header("Live Account Status")
    acc = get_account_summary()
    table = [
        ["Status", acc.get("status", "ACTIVE")],
        ["Portfolio Value", f"${acc.get('portfolio_value', 0):,.2f}"],
        ["Cash Balance", f"${acc.get('cash', 0):,.2f}"],
        ["Buying Power", f"${acc.get('buying_power', 0):,.2f}"],
        ["Options Approved Level", acc.get("options_approved_level", 2)],
        ["PDT Status", "Yes" if acc.get("pattern_day_trader") else "No"],
        ["Trading Blocked", "Yes" if acc.get("trading_blocked") else "No"]
    ]
    print(tabulate(table, headers=["Metric", "Value"], tablefmt="fancy_grid"))

def cmd_positions(args):
    print_header("Active Positions")
    positions = get_active_positions()
    if not positions:
        print("\n  No open positions currently active.")
        return

    table = []
    for p in positions:
        pnl = float(p.get("realized_pnl") or 0.0)
        pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
        table.append([
            p.get("id"),
            p.get("strategy_id"),
            p.get("symbol"),
            p.get("asset_class", "stock").upper(),
            p.get("option_symbol") or "-",
            f"${float(p.get('entry_price', 0)):.2f}",
            p.get("quantity"),
            f"${float(p.get('allocated_capital', 0)):.2f}",
            pnl_str,
            p.get("status").upper()
        ])
    headers = ["ID", "Strategy", "Symbol", "Class", "OCC Symbol", "Entry Px", "Qty", "Capital", "PnL", "Status"]
    print(tabulate(table, headers=headers, tablefmt="fancy_grid"))

def cmd_inspect(args):
    symbol = args.symbol.upper()
    print_header(f"Option Contract & Greeks Analysis — {symbol}")
    res = inspect_option_opportunity(symbol, args.signal_type)
    spec = res.get("contract_spec", {})
    risk = res.get("risk_gate_evaluation", {})

    print(f"\n📍 Spot Price: ${res.get('underlying_price', 0):,.2f}")
    print(f"📍 Selected Strategy: {spec.get('strategy_type', '').upper()} ({spec.get('contract_type', '').upper()})")
    print(f"📍 OCC Symbol: {spec.get('occ_symbol')}")
    print(f"📍 Strike: ${spec.get('strike_price', 0):.2f} | DTE: {spec.get('dte_at_entry')} days | Expiry: {spec.get('expiry_date')}")
    print(f"📍 Option Premium: ${spec.get('premium_paid', 0):.2f}/sh (${spec.get('premium_paid', 0)*100:.2f} per contract)")
    
    print("\n--- Black-Scholes Greeks Profile ---")
    greeks = [
        ["Delta (Δ)", f"{spec.get('delta_entry', 0):.4f}", "Directional sensitivity / share equivalence"],
        ["Gamma (Γ)", f"{spec.get('gamma_entry', 0):.6f}", "Delta acceleration per $1 move in underlying"],
        ["Theta (Θ)", f"${spec.get('theta_entry', 0):.4f}/day", "Daily time decay cost"],
        ["Vega (V)", f"${spec.get('vega_entry', 0):.4f}", "PnL change per 1% change in Implied Volatility"],
        ["Implied Volatility (IV)", f"{spec.get('iv_entry', 0)*100:.1f}%", "Market expected annualized volatility"],
        ["IV Rank", f"{spec.get('iv_rank_entry', 0):.1f} / 100", f"Regime: {spec.get('iv_regime', '').upper()}"]
    ]
    print(tabulate(greeks, headers=["Greek", "Value", "Interpretation"], tablefmt="fancy_grid"))

    print("\n--- 5-Gate Entry Filter & Risk Sizing ---")
    print(f"  Approved: {'✅ YES' if risk.get('approved') else '❌ BLOCKED'}")
    if risk.get("approved"):
        print(f"  Allocated Contracts: {risk.get('contracts_qty')} (${risk.get('total_cost', 0):,.2f} total premium)")
        print(f"  Gates Passed: {', '.join(risk.get('gates_passed', []))}")
    else:
        print(f"  Block Reason: {risk.get('reason')}")

def cmd_circuit_breaker(args):
    print_header("5-Level Circuit Breaker & Performance Modes")
    data = get_system_circuit_breaker()
    cb = data.get("circuit_breaker", {})
    strategies = data.get("strategies_tracked", [])

    print(f"\n🛡️ Portfolio Value: ${cb.get('portfolio_value', 0):,.2f} | Peak: ${cb.get('peak_value', 0):,.2f}")
    print(f"🛡️ Current Drawdown: {cb.get('drawdown_pct', 0):.2f}%")
    print(f"🛡️ Circuit Breaker Level: Level {cb.get('circuit_breaker_level', 0)} — {cb.get('circuit_breaker_label', 'Green')}")
    print(f"🛡️ CB Sizing Multiplier: {cb.get('cb_multiplier', 1.0)}x")
    print(f"🛡️ Action Enforcement: {cb.get('action', 'Full normal operation')}")

    if strategies:
        print("\n--- Tracked Strategy Performance Modes ---")
        table = []
        for s in strategies:
            table.append([
                s.get("strategy_id"),
                s.get("mode"),
                f"{float(s.get('size_multiplier', 1.0)):.2f}x",
                f"{float(s.get('win_rate', 0.5))*100:.1f}%",
                f"{float(s.get('win_loss_ratio', 2.0)):.2f}x",
                f"{float(s.get('quarter_kelly_pct', 0.025))*100:.2f}%",
                s.get("consecutive_losses", 0)
            ])
        headers = ["Strategy ID", "Mode", "Size Mult", "Win Rate", "W:L Ratio", "1/4 Kelly %", "Losing Streak"]
        print(tabulate(table, headers=headers, tablefmt="fancy_grid"))

def cmd_trade(args):
    print_header(f"Execute Options Trade — {args.symbol.upper()}")
    res = execute_options_trade(
        symbol=args.symbol,
        strategy_type=args.strategy,
        groq_confidence=args.confidence
    )
    if res.get("success"):
        print(f"✅ Trade Executed Successfully!")
        print(f"  Position ID: #{res.get('position_id')}")
        print(f"  OCC Symbol:  {res.get('occ_symbol')}")
        print(f"  Strategy:    {res.get('strategy_type').upper()}")
        print(f"  Contracts:   {res.get('contracts_qty')} @ ${res.get('premium_paid'):.2f}/sh (${res.get('total_cost'):,.2f} total)")
        print(f"  Delta:       {res.get('delta')}")
        print(f"  Target (+60%): ${res.get('profit_target_premium'):.2f}")
        print(f"  Stop (-35%):   ${res.get('stop_loss_premium'):.2f}")
        print(f"  Time Stop:     {res.get('time_stop_dte')} DTE")
    else:
        print(f"❌ Trade Rejected: {res.get('reason')}")

def cmd_close(args):
    print_header(f"Close Position — {args.symbol.upper()}")
    res = close_active_position(args.symbol, args.reason)
    if res.get("success"):
        print(f"✅ Closed {res.get('closed_type').upper()} position on {args.symbol.upper()}.")
    else:
        print(f"❌ Error: {res.get('error')}")

def cmd_monitor(args):
    print_header("Run Options Monitor Agent (4-Exit System)")
    res = run_monitor_cycle_tool()
    print(f"🎯 Positions Monitored: {res.get('positions_monitored', 0)}")
    print(f"🎯 Exits Triggered:     {res.get('exits_triggered', 0)}")
    for exit_item in res.get("exits", []):
        print(f"   -> Closed {exit_item.get('occ_symbol')} on {exit_item.get('symbol')} | Reason: {exit_item.get('exit_reason')} | PnL: ${exit_item.get('realized_pnl'):.2f}")

def cmd_scan(args):
    print_header(f"Run Autonomous Multi-Agent Scan ({args.timeframe})")
    from app.services.orchestrator import run_orchestrator_cycle
    summary = run_orchestrator_cycle(args.timeframe)
    print(f"📊 Cycle Complete in {summary.get('cycle_duration_sec', 0)}s")
    print(f"📊 Assets Scanned:    {summary.get('symbols_scanned', 0)}")
    print(f"📊 Signals Detected:  {summary.get('signals_detected', 0)}")
    print(f"📊 Groq Approved:     {summary.get('groq_approved', 0)}")
    print(f"📊 Risk Approved:     {summary.get('risk_approved', 0)}")
    print(f"📊 Orders Placed:     {summary.get('orders_placed', 0)}")

def main():
    parser = argparse.ArgumentParser(description="Alpaca AI Options Trading Engine CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("account", help="Show live Alpaca paper account status")
    subparsers.add_parser("positions", help="List all open positions and PnL")
    
    p_inspect = subparsers.add_parser("inspect", help="Inspect options pricing and Greeks for a symbol")
    p_inspect.add_argument("symbol", type=str, help="Stock ticker (e.g. AAPL, NVDA)")
    p_inspect.add_argument("--signal-type", type=str, default="ENTER_LONG", help="Signal direction")

    subparsers.add_parser("circuit-breaker", help="View Circuit Breaker & Kelly Modes")

    p_trade = subparsers.add_parser("trade", help="Submit options trade through 5-gate pipeline")
    p_trade.add_argument("--symbol", type=str, required=True, help="Underlying ticker")
    p_trade.add_argument("--strategy", type=str, default="long_call", help="Options strategy")
    p_trade.add_argument("--confidence", type=int, default=85, help="Conviction (0-100)")

    p_close = subparsers.add_parser("close", help="Close an open position")
    p_close.add_argument("--symbol", type=str, required=True, help="Ticker or OCC symbol")
    p_close.add_argument("--reason", type=str, default="manual_cli_exit", help="Exit reason")

    subparsers.add_parser("monitor", help="Run 4-Exit Monitor Agent (14 DTE, targets, stops)")

    p_scan = subparsers.add_parser("scan", help="Run full autonomous multi-agent cycle")
    p_scan.add_argument("--timeframe", type=str, default="1D", help="Timeframe (2H, 4H, 1D)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    commands = {
        "account": cmd_account,
        "positions": cmd_positions,
        "inspect": cmd_inspect,
        "circuit-breaker": cmd_circuit_breaker,
        "trade": cmd_trade,
        "close": cmd_close,
        "monitor": cmd_monitor,
        "scan": cmd_scan
    }
    commands[args.command](args)

if __name__ == "__main__":
    main()
