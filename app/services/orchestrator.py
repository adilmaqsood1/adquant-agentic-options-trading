import os
import sys
import datetime
from typing import Dict, List, Any, Optional, TypedDict
import pandas as pd

from langgraph.graph import StateGraph, END

from app.services.market_state import fetch_all
from app.services.signal_detector import detect_all
from app.agents.reasoning_agent import reason_about_signal
from app.agents.risk_agent import evaluate_risk
from app.agents.data_agent import run_data_agent, get_all_snapshots
from app.agents.strategy_agents import run_all_strategy_agents
from app.agents.research_agent import run_research_agent, get_latest_insights
from app.core.database import (
    get_portfolio_summary, log_cycle, init_db, is_position_open,
    open_position, close_position
)
from app.reporting.email_reporter import send_cycle_report



class AgentState(TypedDict):
    cycle_time: datetime.datetime
    timeframe_scope: str                          # "2H", "4H", or "1D"
    strategy_ids: List[str]                       # which strategies run this cycle
    fresh_bars: Dict[str, Dict[str, pd.DataFrame]]# output of fetch_all()
    feature_snapshots: Dict[str, Any]            # Layer 1 Data Agent output
    all_signals: List[Dict[str, Any]]             # all signal dicts including non-fired
    fired_signals: List[Dict[str, Any]]           # only fired=True signals
    groq_decisions: List[Dict[str, Any]]          # one per fired signal
    risk_decisions: List[Dict[str, Any]]          # one per groq decision
    approved_orders: List[Dict[str, Any]]         # risk approved=True only
    research_insights: Dict[str, Any]             # Layer 3 Research Agent output
    cycle_summary: Dict[str, Any]                 # compiled at end
    errors: List[str]                             # any non-fatal errors during cycle


def fetch_node(state: AgentState) -> AgentState:
    strategy_ids = state.get("strategy_ids", [])
    print(f"\n[FETCH] Fetching fresh live bars for strategies: {strategy_ids}")

    # ── CIRCUIT BREAKER LEVEL 4 — Emergency Shutdown (>-15% portfolio drawdown) ──
    # Checked FIRST, before any market data fetch or position monitoring.
    try:
        from app.engine.performance_manager import get_current_circuit_breaker
        cb_state = get_current_circuit_breaker()
        cb_level = cb_state.get("circuit_breaker_level", 0)

        if cb_level >= 4:
            print(f"\n{'🚨' * 10}")
            print(f"[CIRCUIT BREAKER — LEVEL 4 BLACK] Portfolio drawdown: {cb_state.get('drawdown_pct', 0):.2f}%")
            print(f"[CIRCUIT BREAKER] Action: CLOSE ALL POSITIONS IMMEDIATELY — 24h pause activated.")
            print(f"{'🚨' * 10}\n")

            # Close every open position (options + spot)
            try:
                from app.core.database import get_open_positions
                from app.engine.options_position_manager import close_options_position
                open_pos = get_open_positions()
                closed_count = 0
                for pos in open_pos:
                    try:
                        if pos.get("asset_class") == "option" or bool(pos.get("option_symbol")):
                            # close_options_position(occ_symbol, exit_premium, exit_reason)
                            # Use entry_price as exit estimate — market is closed/shutdown
                            close_options_position(
                                occ_symbol=pos.get("option_symbol") or pos.get("symbol", ""),
                                exit_premium=float(pos.get("entry_price", 0)),
                                exit_reason="CB_LEVEL4_SHUTDOWN"
                            )
                        else:
                            # close_position(strategy_id, symbol, exit_price)
                            close_position(
                                strategy_id=pos.get("strategy_id", ""),
                                symbol=pos.get("symbol", ""),
                                exit_price=float(pos.get("entry_price", 0))
                            )
                        closed_count += 1
                    except Exception as close_err:
                        print(f"[CB4 CLOSE ERROR] pos {pos.get('id')} ({pos.get('symbol')}): {close_err}")

                print(f"[CIRCUIT BREAKER] Closed {closed_count}/{len(open_pos)} open positions.")
            except Exception as close_all_err:
                print(f"[CB4 CLOSE ALL ERROR] {close_all_err}")

            # Emergency email notification
            try:
                send_cycle_report({
                    "subject": "🚨 CIRCUIT BREAKER LEVEL 4 — PORTFOLIO SHUTDOWN",
                    "cb_level": 4,
                    "drawdown_pct": cb_state.get("drawdown_pct", 0),
                    "portfolio_value": cb_state.get("portfolio_value", 0),
                    "action": "All positions closed. Scheduler paused 24 hours.",
                })
            except Exception as email_err:
                print(f"[CB4 EMAIL ERROR] {email_err}")

            # Abort this entire cycle — set empty state and return immediately
            state["fresh_bars"] = {}
            state["fired_signals"] = []
            state["groq_decisions"] = []
            state["errors"].append("CB_LEVEL4_SHUTDOWN: Cycle aborted. All positions closed.")
            return state

        elif cb_level == 3:
            print(f"[CIRCUIT BREAKER — LEVEL 3 RED] Drawdown: {cb_state.get('drawdown_pct', 0):.2f}% — No new entries this cycle.")

        elif cb_level == 2:
            print(f"[CIRCUIT BREAKER — LEVEL 2 ORANGE] Drawdown: {cb_state.get('drawdown_pct', 0):.2f}% — All sizes -50%, REDUCE mode blocked.")

        elif cb_level == 1:
            print(f"[CIRCUIT BREAKER — LEVEL 1 YELLOW] Drawdown: {cb_state.get('drawdown_pct', 0):.2f}% — All sizes -20%.")

    except Exception as cb_err:
        print(f"[CB CHECK ERROR] {cb_err}")

    # ── 1. Options Monitor Agent — enforces 4-exit discipline on open positions ──
    try:
        from app.engine.options_monitor_agent import run_options_monitor_cycle
        mon_res = run_options_monitor_cycle()
        if mon_res.get("exits_triggered", 0) > 0:
            print(f"[MONITOR AGENT] 🎯 Monitored {mon_res['positions_monitored']} options positions | Triggered {mon_res['exits_triggered']} automated exits.")
    except Exception as mon_err:
        print(f"[MONITOR AGENT ERROR] {mon_err}")

    try:
        bars = fetch_all(strategy_ids)
        state["fresh_bars"] = bars
        print(f"[FETCH] Successfully fetched bars for {len(bars)} strategies")
    except Exception as e:
        err = f"fetch_node failed: {e}"
        print(f"[FETCH] ERROR: {err}")
        state["errors"].append(err)
        state["fresh_bars"] = {}
    return state



def detect_node(state: AgentState) -> AgentState:
    fresh_bars = state.get("fresh_bars", {})
    try:
        all_signals, fired_signals = detect_all(fresh_bars)
        state["all_signals"] = all_signals
        state["fired_signals"] = fired_signals
        print(f"[DETECT] {len(all_signals)} signals scanned, {len(fired_signals)} fired")
    except Exception as e:
        err = f"detect_node failed: {e}"
        print(f"[DETECT] ERROR: {err}")
        state["errors"].append(err)
        state["all_signals"] = []
        state["fired_signals"] = []
    return state


def reason_node(state: AgentState) -> AgentState:
    fired_signals = state.get("fired_signals", [])
    if not fired_signals:
        print("[REASON] No fired signals, skipping LLM reasoning.")
        return state

    print(f"[REASON] Groq evaluating {len(fired_signals)} fired signals...")
    groq_decisions: List[Dict[str, Any]] = []
    portfolio_summary = get_portfolio_summary()

    for sig in fired_signals:
        s_id = sig["strategy_id"]
        sym = sig["symbol"]
        df = state.get("fresh_bars", {}).get(s_id, {}).get(sym, pd.DataFrame())

        try:
            decision = reason_about_signal(sig, df, portfolio_summary)
            groq_decisions.append(decision)
            print(f"  [GROQ DECISION] [{s_id}] {sym} -> Go: {decision['go']}, Conf: {decision['confidence']}%, Size: {decision['suggested_size_pct']}%")
        except Exception as e:
            err = f"reason_node error on {s_id}/{sym}: {e}"
            print(f"[REASON] ERROR: {err}")
            state["errors"].append(err)

    state["groq_decisions"] = groq_decisions
    print(f"[REASON] Groq evaluation complete ({len(groq_decisions)} decisions)")
    return state


def risk_node(state: AgentState) -> AgentState:
    fired_signals = state.get("fired_signals", [])
    portfolio_summary = get_portfolio_summary()

    risk_decisions: List[Dict[str, Any]] = []
    approved_orders: List[Dict[str, Any]] = []

    # 1. Multi-Strategy Confluence Detection
    from app.engine.opportunity_ranker import detect_confluence_opportunities, rank_opportunities_tournament
    from app.engine.risk_gate_agent import compute_dynamic_options_capacity, evaluate_options_risk_gates
    from app.core.database import get_open_positions

    current_open_pos = get_open_positions()
    capacity_info = compute_dynamic_options_capacity(open_positions=current_open_pos)
    available_slots = max(0, capacity_info["max_simultaneous"] - len(current_open_pos))

    confluence_pool = detect_confluence_opportunities(fired_signals)
    print(f"[Confluence] Detected {len(confluence_pool)} unique symbol setups across {len(fired_signals)} strategy triggers.")

    # 2. DeepSeek-V3.2 Opportunity Tournament Ranking
    tournament = rank_opportunities_tournament(
        confluence_pool=confluence_pool,
        available_capacity=max(1, available_slots) if available_slots > 0 else 1,
        market_regime=state.get("research_insights", {}).get("market_regime", {}).get("regime", "STRONG_BULL")
    )

    selected_candidates = tournament.get("selected_for_execution", [])
    tournament_summary = tournament.get("tournament_summary", "")
    print(f"[Tournament] 🏆 DeepSeek Tournament: Selected Top {len(selected_candidates)} candidates for execution:\n  {tournament_summary}")

    # 3. Process Ranked Candidates through 5-Gate Defense & Alpaca MCP
    for item in selected_candidates:
        sig = item.get("signal_payload", {})
        s_id = sig.get("strategy_id", "options_core")
        sym = item.get("symbol", "").upper()
        exec_price = float(item.get("last_close") or sig.get("last_close", 0.0))
        sig_type = sig.get("signal_type", "ENTER_LONG")
        timeframe_val = sig.get("timeframe", state.get("timeframe_scope", "4H"))
        conf = int(item.get("tournament_score", 85))
        reasoning = item.get("rationale", "")

        g_dec = {
            "strategy_id": s_id,
            "symbol": sym,
            "go": True,
            "confidence": conf,
            "reasoning": reasoning,
            "suggested_size_pct": item.get("suggested_size_pct", 100)
        }

        try:
            r_dec = evaluate_risk(sig, g_dec, portfolio_summary)
            risk_decisions.append(r_dec)

            if r_dec["approved"]:
                final_cap = float(r_dec.get("final_capital", sig.get("allocated_capital", 20000.0)))
                final_qty = float(r_dec.get("final_quantity", 0.0))

                order_payload = {
                    "strategy_id": s_id,
                    "symbol": sym,
                    "signal_type": sig_type,
                    "timeframe": timeframe_val,
                    "execution_price": exec_price,
                    "allocated_capital": sig.get("allocated_capital", 20000.0),
                    "final_capital": final_cap,
                    "final_quantity": final_qty,
                    "groq_confidence": conf,
                    "groq_reasoning": reasoning,
                    "confluence_tier": item.get("confluence_tier", "SINGLE_STRATEGY"),
                    "tournament_rank": item.get("rank", 1),
                    "risk_approved": True,
                    "timestamp": r_dec.get("timestamp")
                }

                # Persist and route to Alpaca MCP
                try:
                    if sig_type == "ENTER_LONG":
                        is_equity = "/" not in sym
                        opt_data = None
                        if is_equity and exec_price > 0:
                            try:
                                from app.engine.contract_selector import select_contract
                                from app.engine.options_position_manager import open_options_position

                                contract_spec = select_contract(
                                    signal_dict={"symbol": sym, "strategy_id": s_id, "signal_type": sig_type},
                                    underlying_price=exec_price
                                )

                                # Evaluate all 5 Entry Gates with fresh positions
                                fresh_pos = get_open_positions()
                                gate_eval = evaluate_options_risk_gates(
                                    contract_spec=contract_spec,
                                    signal_dict={"symbol": sym, "groq_confidence": conf, "strategy_id": s_id, "suggested_size_pct": g_dec.get("suggested_size_pct", 100)},
                                    open_positions=fresh_pos,
                                    current_price=exec_price
                                )

                                # Route & Execute via Alpaca MCP
                                from app.execution.execution_router import route_and_execute
                                exec_res = route_and_execute(
                                    risk_gate_result=gate_eval,
                                    contract_spec=contract_spec,
                                    signal_dict={"symbol": sym, "strategy_id": s_id, "signal_type": sig_type, "confidence": conf}
                                )

                                if exec_res.get("success"):
                                    opt_data = contract_spec
                                    options_payload = {
                                        "strategy_id": s_id,
                                        "symbol": sym,
                                        "occ_symbol": contract_spec["occ_symbol"],
                                        "signal_type": sig_type,
                                        "timeframe": timeframe_val,
                                        "execution_price": float(contract_spec.get("premium_paid", 5.0)),
                                        "allocated_capital": float(contract_spec.get("total_cost", 500.0)),
                                        "final_capital": float(contract_spec.get("total_cost", 500.0)),
                                        "final_quantity": int(contract_spec.get("contracts_qty", 1)),
                                        "groq_confidence": conf,
                                        "groq_reasoning": reasoning,
                                        "confluence_tier": item.get("confluence_tier", "SINGLE_STRATEGY"),
                                        "tournament_rank": item.get("rank", 1),
                                        "risk_approved": True,
                                        "timestamp": r_dec.get("timestamp")
                                    }
                                    approved_orders.append(options_payload)
                                    print(f"  [MCP EXECUTION SUCCESS] ✅ Rank #{item.get('rank', 1)}: {contract_spec['occ_symbol']} ({item.get('confluence_tier')}) live options order routed through Alpaca MCP.")
                                else:
                                    print(f"  [MCP ROUTE NOTICE] {sym} -> {exec_res.get('status')}: {exec_res.get('reason') or exec_res.get('error')}")

                            except Exception as opt_err:
                                print(f"  [OPTIONS MCP PIPELINE ERROR] {opt_err}")

                    elif sig_type == "EXIT_LONG":
                        from app.execution.options_executor import close_options_order
                        close_res = close_options_order(
                            occ_symbol=sym,
                            exit_reason="signal_exit",
                            exit_premium=exec_price
                        )
                        print(f"  [MCP CLOSE POSITION] [{s_id}] {sym} @ ${exec_price}: {close_res.get('exit_reason')}")

                except Exception as db_err:
                    print(f"  [DB POSITIONS ERROR] Failed to write position {s_id}/{sym}: {db_err}")
                    state["errors"].append(f"DB position error {s_id}/{sym}: {db_err}")

                print(f"  [RISK APPROVED] [{s_id}] {sym} -> Capital: ${final_cap}, Qty: {final_qty}")

            else:
                print(f"  [RISK BLOCKED]  [{s_id}] {sym} -> Reason: {r_dec['block_reason']}")

        except Exception as e:
            err = f"risk_node error on {s_id}/{sym}: {e}"
            print(f"[RISK] ERROR: {err}")
            state["errors"].append(err)

    state["risk_decisions"] = risk_decisions
    state["approved_orders"] = approved_orders
    print(f"[RISK] {len(selected_candidates)} tournament candidates evaluated, {len(approved_orders)} approved")
    return state


def report_node(state: AgentState) -> AgentState:
    cycle_time = state.get("cycle_time", datetime.datetime.utcnow())
    now = datetime.datetime.utcnow()
    duration_sec = round((now - cycle_time).total_seconds(), 2)

    all_signals = state.get("all_signals", [])
    fired_signals = state.get("fired_signals", [])
    groq_decisions = state.get("groq_decisions", [])
    risk_decisions = state.get("risk_decisions", [])
    approved_orders = state.get("approved_orders", [])
    timeframe_scope = state.get("timeframe_scope", "4H")

    groq_approved_count = sum(1 for g in groq_decisions if g.get("go"))
    risk_approved_count = len(approved_orders)

    portfolio_summary = get_portfolio_summary()

    # Blocked reasons summary
    blocked_list = []
    for r in risk_decisions:
        if not r.get("approved"):
            blocked_list.append({
                "strategy_id": r["strategy_id"],
                "symbol": r["symbol"],
                "reason": r.get("block_reason")
            })

    summary = {
        "cycle_time": cycle_time.isoformat(),
        "timeframe_scope": timeframe_scope,
        "duration_seconds": duration_sec,
        "symbols_scanned": len(all_signals),
        "signals_detected": len(fired_signals),
        "groq_approved": groq_approved_count,
        "risk_approved": risk_approved_count,
        "orders_placed": risk_approved_count,
        "approved_orders": approved_orders,
        "blocked_signals": blocked_list,
        "portfolio_summary": portfolio_summary,
        "research_insights": state.get("research_insights", {}),
        "errors": state.get("errors", [])
    }
    state["cycle_summary"] = summary


    # Log cycle to PostgreSQL database
    try:
        log_cycle(
            timeframe_scope=timeframe_scope,
            symbols_scanned=len(all_signals),
            signals_detected=len(fired_signals),
            groq_approved=groq_approved_count,
            risk_approved=risk_approved_count,
            notes=f"Cycle completed in {duration_sec}s. {risk_approved_count} approved orders.",
            portfolio_value=portfolio_summary.get("total_allocated", 0.0),
            orders_placed=risk_approved_count,
            cycle_time=cycle_time
        )
    except Exception as e:
        print(f"[REPORT] DB log_cycle error: {e}")
        state["errors"].append(f"DB log_cycle error: {e}")

    # Dispatch email report ONLY if an actual live trade was executed in this cycle
    if risk_approved_count > 0:
        try:
            send_cycle_report(summary)
        except Exception as e:
            print(f"[REPORT] Email dispatch error: {e}")
            state["errors"].append(f"Email dispatch error: {e}")

    print("\n" + "=" * 75)
    print(f"[REPORT] Cycle Complete ({timeframe_scope}) | Duration: {duration_sec}s | Scanned: {len(all_signals)} | Fired: {len(fired_signals)} | Approved: {risk_approved_count}")
    print("=" * 75)
    return state


#Layer 1: Data Agent Node
def data_agent_node(state: AgentState) -> AgentState:
    """Layer 1 — Builds FeatureSnapshot for every symbol. Pure Python, no LLM."""
    fresh_bars = state.get("fresh_bars", {})
    try:
        snapshots = run_data_agent(fresh_bars)
        state["feature_snapshots"] = snapshots
        print(f"[DataAgent] FeatureSnapshot built for {len(snapshots)} symbols")
    except Exception as e:
        err = f"data_agent_node failed: {e}"
        print(f"[DataAgent] ERROR: {err}")
        state["errors"].append(err)
        state["feature_snapshots"] = {}
    return state


#Layer 2: Strategy Agents Node
def strategy_agents_node(state: AgentState) -> AgentState:
    """Layer 2 — Runs strategy evaluation (micro-agents & mathematical signal detection)."""
    snapshots    = state.get("feature_snapshots", {})
    strategy_ids = state.get("strategy_ids", [])
    fresh_bars   = state.get("fresh_bars", {})
    
    try:
        # 1. Run direct signal detection across all requested strategies
        all_signals, fired_signals = detect_all(fresh_bars)
        
        # 2. Build Groq decisions for risk evaluation
        groq_decisions = []
        for s in fired_signals:
            groq_decisions.append({
                "strategy_id": s["strategy_id"],
                "symbol": s["symbol"],
                "go": True,
                "confidence": 80,
                "reasoning": f"Mathematical quantitative entry signal fired: {s.get('signal_type')} at ${s.get('last_close')}",
                "suggested_size_pct": 100
            })
            
        state["all_signals"]   = all_signals
        state["fired_signals"] = fired_signals
        state["groq_decisions"] = groq_decisions
        print(f"[StrategyAgents] Scan Complete: {len(all_signals)} evaluated | {len(fired_signals)} fired")
    except Exception as e:
        err = f"strategy_agents_node failed: {e}"
        print(f"[StrategyAgents] ERROR: {err}")
        state["errors"].append(err)
        state["all_signals"]   = []
        state["fired_signals"] = []
        state["groq_decisions"] = []
    return state



#Layer 3: Research Agent Node
def research_agent_node(state: AgentState) -> AgentState:
    """Layer 3 — Research Agent: market regime analysis + novel strategy generation."""
    all_signals   = state.get("all_signals", [])
    snapshots     = state.get("feature_snapshots", {})
    timeframe     = state.get("timeframe_scope", "4H")
    try:
        insights = run_research_agent(all_signals, snapshots, cycle_timeframe=timeframe)
        state["research_insights"] = insights
        regime_data = insights.get("market_regime", {})
        regime = regime_data.get("regime", regime_data.get("equity_regime", "unknown")) if isinstance(regime_data, dict) else str(regime_data)
        print(f"[ResearchAgent] Done | Regime: {regime} | Novel strategies: {len(insights.get('novel_strategies', []))}")
    except Exception as e:
        err = f"research_agent_node failed: {e}"
        print(f"[ResearchAgent] ERROR: {err}")
        state["errors"].append(err)
        state["research_insights"] = {}
    return state


def route_after_detect(state: AgentState) -> str:
    fired = state.get("fired_signals", [])
    if len(fired) > 0:
        return "reason_node"
    return "report_node"


def route_after_strategy_agents(state: AgentState) -> str:
    fired = state.get("fired_signals", [])
    if len(fired) > 0:
        return "risk_node"
    return "research_agent_node"


def build_graph():
    """
    Constructs and compiles the LangGraph Multi-Agent StateGraph.
    Pipeline:
    fetch_node → data_agent_node → strategy_agents_node
                                          ↓ (if signals fired)
                                     risk_node → research_agent_node → report_node
                                          ↓ (no signals)
                                   research_agent_node → report_node
    """
    workflow = StateGraph(AgentState)

    # ── Nodes ──
    workflow.add_node("fetch_node",            fetch_node)
    workflow.add_node("detect_node",           detect_node)            # legacy fallback
    workflow.add_node("data_agent_node",       data_agent_node)        # Layer 1
    workflow.add_node("strategy_agents_node",  strategy_agents_node)   # Layer 2
    workflow.add_node("research_agent_node",   research_agent_node)    # Layer 3
    workflow.add_node("reason_node",           reason_node)
    workflow.add_node("risk_node",             risk_node)
    workflow.add_node("report_node",           report_node)

    # ── Edges ──
    workflow.set_entry_point("fetch_node")
    workflow.add_edge("fetch_node",           "data_agent_node")
    workflow.add_edge("data_agent_node",      "strategy_agents_node")

    # After strategy agents: if signals fired → risk_node, else → research_agent_node
    workflow.add_conditional_edges(
        "strategy_agents_node",
        route_after_strategy_agents,
        {
            "risk_node":            "risk_node",
            "research_agent_node": "research_agent_node"
        }
    )

    workflow.add_edge("risk_node",            "research_agent_node")
    workflow.add_edge("research_agent_node",  "report_node")
    workflow.add_edge("report_node",          END)

    return workflow.compile()


# Singleton compiled graph instance
_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def run_cycle(
    timeframe_scope: str = "4H",
    strategy_ids: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Executes one complete end-to-end multi-agent cycle.
    Wraps entire execution in fault-tolerant try/except.
    """
    if strategy_ids is None:
        if timeframe_scope == "2H":
            strategy_ids = ["momentum_ema_rsi_adx"]
        elif timeframe_scope == "4H":
            strategy_ids = [
                "liquidity_sweep_absorption",
                "rsi_oversold_reversal",
                "cvd_divergence_squeeze",
                "lead_lag_propagation",
                "trend_pullback_continuation"
            ]
        elif timeframe_scope == "1D":
            strategy_ids = [
                "rsi_oversold_reversal",
                "trend_pullback_continuation",
                "lead_lag_propagation",
                "liquidity_sweep_absorption"
            ]
        else:
            strategy_ids = [
                "liquidity_sweep_absorption",
                "rsi_oversold_reversal",
                "cvd_divergence_squeeze",
                "lead_lag_propagation",
                "trend_pullback_continuation"
            ]






    init_db()

    initial_state: AgentState = {
        "cycle_time": datetime.datetime.utcnow(),
        "timeframe_scope": timeframe_scope,
        "strategy_ids": strategy_ids,
        "fresh_bars": {},
        "feature_snapshots": {},
        "all_signals": [],
        "fired_signals": [],
        "groq_decisions": [],
        "risk_decisions": [],
        "approved_orders": [],
        "research_insights": {},
        "cycle_summary": {},
        "errors": []
    }

    try:
        graph = get_graph()
        final_state = graph.invoke(initial_state)
        return final_state.get("cycle_summary", {})
    except Exception as e:
        err = f"Fatal cycle exception: {e}"
        print(f"[Orchestrator] FATAL ERROR: {err}")
        return {
            "cycle_time": initial_state["cycle_time"].isoformat(),
            "timeframe_scope": timeframe_scope,
            "error": err,
            "status": "failed"
        }
