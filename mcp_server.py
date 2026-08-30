"""
Alpaca Model Context Protocol (MCP) Server
===========================================
Official MCP Server exposing Alpaca Trading, Options Alpha Engine,
Greeks pricing, and Risk Circuit Breakers over stdio / JSON-RPC.

Compatible with:
  - Claude Desktop
  - Gemini / Antigravity Agents
  - Cursor / Windsurf
  - Standalone MCP Clients

Usage:
  python mcp_server.py
"""

import sys
import os
import json
import asyncio
from typing import Dict, Any, List

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

# ─────────────────────────────────────────────────────────────────────────────
# FASTMCP SERVER IMPLEMENTATION
# ─────────────────────────────────────────────────────────────────────────────
try:
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("alpaca-options-trading-agent")

    @mcp.tool()
    def alpaca_get_account() -> str:
        """Get live Alpaca paper trading account status, portfolio value, buying power, and cash balance."""
        return json.dumps(get_account_summary(), indent=2)

    @mcp.tool()
    def alpaca_get_positions() -> str:
        """Get all open stock, crypto, and options positions with live unrealized PnL and Greek exposures."""
        return json.dumps(get_active_positions(), indent=2, default=str)

    @mcp.tool()
    def alpaca_inspect_option(symbol: str, signal_type: str = "ENTER_LONG") -> str:
        """
        Inspect options opportunity for a given stock symbol (e.g. AAPL, NVDA, TSLA).
        Calculates Black-Scholes Greeks (Delta, Gamma, Theta, Vega), IV Rank, contract strike, and 5-Gate risk verification.
        """
        return json.dumps(inspect_option_opportunity(symbol, signal_type), indent=2, default=str)

    @mcp.tool()
    def alpaca_get_circuit_breaker_status() -> str:
        """Get the 5-Level Circuit Breaker status (Green/Yellow/Orange/Red/Black) and Kelly performance modes (GROWTH/NORMAL/REDUCE/PAUSE)."""
        return json.dumps(get_system_circuit_breaker(), indent=2, default=str)

    @mcp.tool()
    def alpaca_submit_options_order(symbol: str, strategy_type: str = "long_call", groq_confidence: int = 85) -> str:
        """
        Submit a quantitative options order through the 5-Gate Risk pipeline.
        Sized dynamically using Quarter Kelly Criterion and IV regime scalar.
        """
        return json.dumps(execute_options_trade(symbol, strategy_type, groq_confidence), indent=2, default=str)

    @mcp.tool()
    def alpaca_close_position(symbol_or_occ: str, exit_reason: str = "mcp_close_order") -> str:
        """Close an active position by stock ticker or options OCC symbol."""
        return json.dumps(close_active_position(symbol_or_occ, exit_reason), indent=2, default=str)

    @mcp.tool()
    def alpaca_run_options_monitor() -> str:
        """Run the Options Monitor Agent cycle to enforce the 4-Exit System (14 DTE Time Stop, +60% Target, -35% Stop Loss)."""
        return json.dumps(run_monitor_cycle_tool(), indent=2, default=str)

    def run_fastmcp():
        print("[Alpaca MCP Server] Starting FastMCP stdio server...", file=sys.stderr)
        mcp.run(transport="stdio")

except ImportError:
    mcp = None

    def run_fastmcp():
        pass


# ─────────────────────────────────────────────────────────────────────────────
# JSON-RPC 2.0 PROTOCOL RUNNER (Fallback / Direct stdio)
# ─────────────────────────────────────────────────────────────────────────────
TOOL_REGISTRY = {
    "alpaca_get_account": lambda args: get_account_summary(),
    "alpaca_get_positions": lambda args: get_active_positions(),
    "alpaca_inspect_option": lambda args: inspect_option_opportunity(args.get("symbol", "AAPL"), args.get("signal_type", "ENTER_LONG")),
    "alpaca_get_circuit_breaker_status": lambda args: get_system_circuit_breaker(),
    "alpaca_submit_options_order": lambda args: execute_options_trade(args.get("symbol", "AAPL"), args.get("strategy_type", "long_call"), int(args.get("groq_confidence", 85))),
    "alpaca_close_position": lambda args: close_active_position(args.get("symbol_or_occ", ""), args.get("exit_reason", "mcp_close")),
    "alpaca_run_options_monitor": lambda args: run_monitor_cycle_tool()
}

def run_stdio_jsonrpc():
    """Lightweight stdio JSON-RPC 2.0 protocol handler."""
    sys.stderr.write("[Alpaca MCP Server] Ready on stdio (JSON-RPC 2.0)\n")
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            req_id = req.get("id")
            method = req.get("method")
            params = req.get("params", {})

            if method == "tools/list":
                tools = [
                    {"name": k, "description": f"Alpaca trading tool: {k}"}
                    for k in TOOL_REGISTRY.keys()
                ]
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}}
            elif method == "tools/call":
                tool_name = params.get("name")
                tool_args = params.get("arguments", {})
                if tool_name in TOOL_REGISTRY:
                    res_val = TOOL_REGISTRY[tool_name](tool_args)
                    resp = {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(res_val, default=str)}]}}
                else:
                    resp = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Tool '{tool_name}' not found"}}
            else:
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {"status": "ok", "service": "alpaca-mcp-server"}}

            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        except Exception as e:
            err_resp = {"jsonrpc": "2.0", "error": {"code": -32603, "message": str(e)}}
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    if mcp is not None:
        run_fastmcp()
    else:
        run_stdio_jsonrpc()
