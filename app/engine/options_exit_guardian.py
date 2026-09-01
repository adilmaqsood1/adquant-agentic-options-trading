import os
import json
import re
from typing import Dict, Any, Optional
from datetime import datetime, date


def evaluate_position_exit_with_ai(
    position: Dict[str, Any],
    live_premium: float,
    underlying_price: float,
    current_dte: int,
    greeks: Optional[Dict[str, float]] = None,
    market_regime: str = "SIDEWAYS_CONSOLIDATION",
    opposing_signal: Optional[str] = None
) -> Dict[str, Any]:
    """
    Hybrid Position Exit Guardian (3-Level Architecture):
    1. Level 1: Hard Safety Rails (Non-negotiable -35% Stop Loss, <= 7 DTE Time Stop, Persisted Trailing Stop Floor Hit).
    2. Level 2: DeepSeek-V3.2 Dynamic AI Positioning Agent (Triggered ONLY at active decision points).
    3. Level 3: Zero-Latency Quantitative Algorithmic Fallback.
    """
    from app.engine.options_position_manager import update_options_trail_stop

    greeks = greeks or {"delta": 0.50, "gamma": 0.05, "theta": -0.08, "vega": 0.12}
    
    sym = position.get("symbol", position.get("underlying_symbol", "")).upper()
    occ_symbol = position.get("option_symbol", position.get("occ_symbol", sym))
    strategy_id = position.get("strategy_id", "options_core")
    strategy_type = position.get("strategy_type", "long_call").lower()
    entry_prem = float(position.get("entry_price") or position.get("premium_paid") or live_premium or 1.0)
    current_prem = float(live_premium if live_premium > 0 else entry_prem)
    contracts = int(position.get("quantity") or position.get("contracts_qty") or 1)
    strike = float(position.get("strike_price") or 0.0)
    opt_type = position.get("option_type", "call").lower()

    # Calculate current PnL %
    prem_pnl = current_prem - entry_prem
    pnl_pct = (prem_pnl / entry_prem * 100.0) if entry_prem > 0 else 0.0

    # ─────────────────────────────────────────────────────────────────────────
    # 1. LEVEL 1: HARD SAFETY GUARDRAILS (Non-negotiable, zero LLM cost, instant)
    # ─────────────────────────────────────────────────────────────────────────
    # A. Active Persisted Trailing Stop Floor Enforcement
    trail_floor = float(position.get("trail_stop_floor_pct") or 0.0)
    trail_prem = float(position.get("trail_stop_premium") or 0.0)
    if trail_floor > 0.0 and pnl_pct <= trail_floor:
        return {
            "should_close": True,
            "action": "TRAILING_STOP_HIT",
            "exit_reason": f"trailing_stop_floor_{trail_floor:.1f}pct_hit",
            "exit_premium": current_prem,
            "pnl_pct": round(pnl_pct, 2),
            "confidence": 100,
            "reasoning": f"Persisted trailing profit floor triggered ({pnl_pct:.1f}% <= +{trail_floor:.1f}% floor). Closed to lock in accrued runner gains."
        }
    if trail_prem > 0.0 and current_prem <= trail_prem:
        return {
            "should_close": True,
            "action": "TRAILING_STOP_HIT",
            "exit_reason": "trailing_stop_premium_hit",
            "exit_premium": current_prem,
            "pnl_pct": round(pnl_pct, 2),
            "confidence": 100,
            "reasoning": f"Persisted trailing stop price hit (${current_prem:.2f} <= ${trail_prem:.2f}). Closed to preserve profits."
        }

    # B. Hard Stop-Loss (-35% single leg, -50% spreads)
    hard_stop_thresh = -50.0 if "spread" in strategy_type else -35.0
    if pnl_pct <= hard_stop_thresh:
        return {
            "should_close": True,
            "action": "HARD_STOP_LOSS",
            "exit_reason": f"hard_stop_loss_{abs(int(hard_stop_thresh))}pct",
            "exit_premium": current_prem,
            "pnl_pct": round(pnl_pct, 2),
            "confidence": 100,
            "reasoning": f"Non-negotiable hard stop loss triggered ({pnl_pct:.1f}% <= {hard_stop_thresh}%). Position closed immediately to protect capital."
        }

    # C. Hard Time-Stop (<= 7 DTE for single leg, <= 14 DTE for spreads)
    min_dte_allowed = 14 if "spread" in strategy_type else 7
    if current_dte <= min_dte_allowed:
        return {
            "should_close": True,
            "action": "HARD_TIME_STOP",
            "exit_reason": f"time_stop_{min_dte_allowed}_dte",
            "exit_premium": current_prem,
            "pnl_pct": round(pnl_pct, 2),
            "confidence": 100,
            "reasoning": f"Non-negotiable time stop triggered ({current_dte} DTE <= {min_dte_allowed} DTE). Closed before exponential theta decay cliff."
        }

    # D. Strategy Signal Reversal
    if opposing_signal and ("SELL" in opposing_signal.upper() or "BEAR" in opposing_signal.upper() or "EXIT" in opposing_signal.upper()):
        if opt_type == "call":
            return {
                "should_close": True,
                "action": "SIGNAL_REVERSAL",
                "exit_reason": "strategy_signal_reversal",
                "exit_premium": current_prem,
                "pnl_pct": round(pnl_pct, 2),
                "confidence": 95,
                "reasoning": f"Strategy {strategy_id} generated opposing technical reversal signal ({opposing_signal}). Closed to preserve capital."
            }

    # ─────────────────────────────────────────────────────────────────────────
    # 2. LEVEL 2: DEEPSEEK-V3.2 DYNAMIC AI EXIT GUARDIAN (Decision-Point Filtered)
    # ─────────────────────────────────────────────────────────────────────────
    # Decision Point Gate: Only invoke LLM if position is at a real inflection point
    # (Allow trades room to breathe between -20% and +40% without premature micro-exits)
    is_decision_point = (pnl_pct >= 45.0 or pnl_pct <= -25.0 or current_dte <= 16)

    if is_decision_point:
        try:
            from app.services.llm_client import query_llm_json

            prompt = f"""You are an institutional quantitative options manager. Analyze this active options position:

POSITION DATA:
- Symbol: {sym} (OCC: {occ_symbol})
- Strategy: {strategy_id} ({strategy_type})
- Option Type: {opt_type.upper()} @ Strike ${strike:.2f}
- Underlying Price: ${underlying_price:.2f}
- Entry Premium: ${entry_prem:.2f}
- Live Premium: ${current_prem:.2f}
- Current PnL: {pnl_pct:+.2f}%
- Days to Expiry (DTE): {current_dte} days
- Greeks: Delta {greeks.get('delta', 0):.2f}, Gamma {greeks.get('gamma', 0):.3f}, Theta ${greeks.get('theta', 0):.2f}/day
- Market Regime: {market_regime}

INSTITUTIONAL RULES:
1. Default to HOLD: If DTE > 14 and PnL has not reached target (+50%+), HOLD to let the option strategy develop. Do NOT exit on minor noise.
2. TRAIL_STOP: If profit is +40% to +80%+ and momentum is strong, set TRAIL_STOP (should_close: false) to lock in a floor while letting gains run.
3. EARLY_TAKE_PROFIT: ONLY if profit exceeds +50% to +80% AND momentum has clearly saturated or theta decay is overtaking delta.
4. EARLY_DEFENSIVE_EXIT: ONLY if severe technical breakdown occurs with PnL < -25% before the hard -35% stop.

Output ONLY valid JSON matching this exact schema:
{{
  "action": "HOLD" | "TRAIL_STOP" | "EARLY_TAKE_PROFIT" | "EARLY_DEFENSIVE_EXIT",
  "should_close": true | false,
  "exit_reason": "string description",
  "confidence": 85,
  "reasoning": "2-3 sentences of quantitative rationale"
}}"""

            parsed, model_name, _ = query_llm_json(
                system_prompt="You are an expert institutional quantitative options portfolio risk manager. Output pure valid JSON.",
                user_prompt=prompt,
                timeout=8.0
            )
            if parsed and isinstance(parsed, dict):
                action = parsed.get("action", "HOLD").upper()
                should_close = bool(parsed.get("should_close", False))
                
                if action in ["EARLY_TAKE_PROFIT", "EARLY_DEFENSIVE_EXIT", "PROFIT_TARGET_CLOSE"]:
                    should_close = True
                elif action in ["HOLD", "TRAIL_STOP"]:
                    should_close = False

                # If TRAIL_STOP, persist updated floor to PostgreSQL options_contracts
                if action == "TRAIL_STOP":
                    new_floor_pct = max(trail_floor, round(pnl_pct - 25.0, 1), 20.0)
                    new_trail_prem = round(entry_prem * (1.0 + new_floor_pct / 100.0), 4)
                    update_options_trail_stop(occ_symbol, new_floor_pct, new_trail_prem)

                return {
                    "should_close": should_close,
                    "action": action,
                    "exit_reason": parsed.get("exit_reason", f"ai_{action.lower()}"),
                    "exit_premium": current_prem,
                    "pnl_pct": round(pnl_pct, 2),
                    "confidence": int(parsed.get("confidence", 85)),
                    "reasoning": parsed.get("reasoning", f"{model_name} Dynamic Exit Guardian evaluation.")
                }
        except Exception as llm_err:
            print(f"[ExitGuardian] LLM notice ({llm_err}). Engaging quantitative algorithmic rule matrix.")

    # ─────────────────────────────────────────────────────────────────────────
    # 3. LEVEL 3: QUANTITATIVE ALGORITHMIC FALLBACK MATRIX
    # ─────────────────────────────────────────────────────────────────────────
    if pnl_pct >= 60.0:
        if current_dte > 21:
            new_floor_pct = max(trail_floor, round(pnl_pct - 25.0, 1), 35.0)
            new_trail_prem = round(entry_prem * (1.0 + new_floor_pct / 100.0), 4)
            update_options_trail_stop(occ_symbol, new_floor_pct, new_trail_prem)
            return {
                "should_close": False,
                "action": "TRAIL_STOP",
                "exit_reason": "profit_trailing_active",
                "exit_premium": current_prem,
                "pnl_pct": round(pnl_pct, 2),
                "confidence": 90,
                "reasoning": f"Position at +{pnl_pct:.1f}% profit with {current_dte} DTE. Dynamic trailing stop floor persisted at +{new_floor_pct:.1f}% (${new_trail_prem:.2f}) to capture potential super-runner expansion."
            }
        else:
            return {
                "should_close": True,
                "action": "EARLY_TAKE_PROFIT",
                "exit_reason": "profit_target_60pct",
                "exit_premium": current_prem,
                "pnl_pct": round(pnl_pct, 2),
                "confidence": 95,
                "reasoning": f"Profit target achieved (+{pnl_pct:.1f}% >= +60%). Locked in gains before time decay accelerates."
            }
    elif pnl_pct >= 35.0:
        new_floor_pct = max(trail_floor, round(pnl_pct - 20.0, 1), 15.0)
        new_trail_prem = round(entry_prem * (1.0 + new_floor_pct / 100.0), 4)
        update_options_trail_stop(occ_symbol, new_floor_pct, new_trail_prem)
        return {
            "should_close": False,
            "action": "TRAIL_STOP",
            "exit_reason": "profit_trailing_active",
            "exit_premium": current_prem,
            "pnl_pct": round(pnl_pct, 2),
            "confidence": 85,
            "reasoning": f"Gain of +{pnl_pct:.1f}% secured. Trailing stop floor persisted to +{new_floor_pct:.1f}% (${new_trail_prem:.2f}) to eliminate downside risk."
        }
    elif pnl_pct <= -20.0 and market_regime in ["BEAR_EXPANSION", "VOLATILE_CHOP"]:
        return {
            "should_close": True,
            "action": "EARLY_DEFENSIVE_EXIT",
            "exit_reason": "defensive_regime_exit",
            "exit_premium": current_prem,
            "pnl_pct": round(pnl_pct, 2),
            "confidence": 88,
            "reasoning": f"Early defensive exit at {pnl_pct:.1f}% loss due to hostile {market_regime} market conditions. Preserved capital vs full stop."
        }

    return {
        "should_close": False,
        "action": "HOLD",
        "exit_reason": "hold_trend_intact",
        "exit_premium": current_prem,
        "pnl_pct": round(pnl_pct, 2),
        "confidence": 80,
        "reasoning": f"Position within normal variance ({pnl_pct:+.1f}% PnL, {current_dte} DTE). Trend structure remains intact."
    }
