"""
Layer 2: Strategy Micro-Agents (20+ agents, one per strategy)
─────────────────────────────────────────────────────────────
Each agent reads the FeatureSnapshot from the Data Agent and makes
exactly ONE LLM call per cycle via Featherless DeepSeek-V3.2 (with Groq failover).

The LLM call sees the full indicator picture and reasons holistically:
"RSI=49.8 but EMA cross + ADX strong = fire with confidence 78"

This overcomes the hard Python threshold problem where RSI=49.8 vs filter=50.0
would block a signal entirely.
"""
import os
import json
import time
import datetime
import httpx
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

from app.services.llm_client import query_llm_json, FEATHERLESS_MODEL, GROQ_FALLBACK_MODEL

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
load_dotenv()


# NOTE: allocated_capital in each strategy definition is INDICATIVE only.
# Actual per-trade allocation is computed dynamically by
# performance_manager.get_dynamic_allocation() using Quarter Kelly,
# circuit breaker level, volatility ratio, and LLM confidence scalar.
# These values serve as reference anchors for prompt context only.

# Strategy Agent Definitions 
STRATEGY_AGENTS: List[Dict[str, Any]] = [
    {
        "id": "momentum_ema_rsi_adx",
        "name": "EMA Momentum + RSI + ADX",
        "timeframe": "2H",
        "allocated_capital": 25000.0,
        "description": "EMA 20/50 crossover confirmed by RSI>50 and ADX>20. Strong trend-following in momentum regimes.",
        "entry_logic": "Bullish EMA cross (20>50) with RSI above midpoint and strong ADX trend.",
        "exit_logic": "Bearish EMA cross or RSI drops below 45.",
        "key_indicators": ["ema_bullish_cross", "ema_bearish_cross", "rsi_14", "adx_14", "ema20_ema50_gap_pct"],
    },
    {
        "id": "supertrend",
        "name": "Supertrend ATR Trend Filter",
        "timeframe": "4H",
        "allocated_capital": 15000.0,
        "description": "ATR-based Supertrend indicator. Flips to bullish on band breakout.",
        "entry_logic": "Supertrend flips bullish (direction changes from -1 to +1).",
        "exit_logic": "Supertrend flips bearish.",
        "key_indicators": ["supertrend_bullish", "supertrend_bullish_flip", "supertrend_bearish_flip", "atr_pct", "price_above_ema200"],
    },
    {
        "id": "donchian_turtle",
        "name": "Donchian Turtle Breakout",
        "timeframe": "4H",
        "allocated_capital": 20000.0,
        "description": "Classic Turtle Trading. Enter on 20-bar high breakout, exit on 10-bar low break.",
        "entry_logic": "Price breaks above 20-bar Donchian upper band.",
        "exit_logic": "Price breaks below 10-bar Donchian lower band.",
        "key_indicators": ["donchian_breakout_up", "donchian_exit_down", "dc20_upper", "volume_surge", "adx_14"],
    },
    {
        "id": "cross_sectional_momentum",
        "name": "Cross-Sectional 30D Momentum",
        "timeframe": "1D",
        "allocated_capital": 40000.0,
        "description": "Ranks assets by 30-day returns and enters top performers.",
        "entry_logic": "Asset shows positive 30-day return with recent price momentum acceleration.",
        "exit_logic": "30-day return turns negative or asset drops from top tier.",
        "key_indicators": ["ret_30d_pct", "ret_20d_pct", "ret_5d_pct", "price_above_ema200", "rsi_14"],
    },
    {
        "id": "rsi_mean_reversion",
        "name": "RSI-2 Mean Reversion",
        "timeframe": "4H",
        "allocated_capital": 12000.0,
        "description": "RSI-2 oversold entry below 10 with 200 SMA uptrend filter.",
        "entry_logic": "RSI-3 below 15, price above 200 EMA — extreme oversold in uptrend.",
        "exit_logic": "RSI-3 rises above 80 — overbought reversion complete.",
        "key_indicators": ["rsi_3", "rsi_14", "price_above_ema200", "bb_pct_b"],
    },
    {
        "id": "bollinger_squeeze",
        "name": "Bollinger Band Squeeze Expansion",
        "timeframe": "4H",
        "allocated_capital": 15000.0,
        "description": "Enters after volatility squeeze (tight bands) as bands expand — catches the explosion move.",
        "entry_logic": "BB squeeze active + bands beginning to expand + price breaks above BB upper.",
        "exit_logic": "BB width expands beyond 2x squeeze level or price drops below BB middle.",
        "key_indicators": ["bb_squeeze_active", "bb_width_pct", "bb_pct_b", "volume_surge", "macd_hist_turning_up"],
    },
    {
        "id": "macd_histogram_flip",
        "name": "MACD Histogram Reversal",
        "timeframe": "4H",
        "allocated_capital": 10000.0,
        "description": "Enters when MACD histogram turns positive from negative (bullish momentum shift).",
        "entry_logic": "MACD histogram flips from negative to positive — buyer momentum re-entering.",
        "exit_logic": "MACD histogram turns negative again.",
        "key_indicators": ["macd_histogram", "macd_hist_turning_up", "macd_bullish_cross", "macd", "macd_signal"],
    },
    {
        "id": "volume_breakout",
        "name": "Volume-Confirmed Price Breakout",
        "timeframe": "4H",
        "allocated_capital": 12000.0,
        "description": "Classic price-volume breakout. Price hits new high confirmed by volume surge > 1.5x average.",
        "entry_logic": "Price near 20-bar Donchian high with 1.5x+ volume surge.",
        "exit_logic": "Volume fades without follow-through or price reverses below EMA 20.",
        "key_indicators": ["volume_surge", "volume_ratio_vs_20avg", "donchian_breakout_up", "ret_5d_pct", "adx_14"],
    },
    {
        "id": "kalman_trend_follow",
        "name": "Kalman Filter Adaptive Trend",
        "timeframe": "4H",
        "allocated_capital": 10000.0,
        "description": "Adaptive Kalman-filtered price state estimates trend direction. Smoother than EMA.",
        "entry_logic": "Kalman trend turns up and price is above Kalman estimate.",
        "exit_logic": "Kalman trend turns down.",
        "key_indicators": ["kalman_trending_up", "price_above_ema50", "rsi_14", "adx_14"],
    },
    {
        "id": "atr_volatility_expansion",
        "name": "ATR Volatility Expansion Entry",
        "timeframe": "4H",
        "allocated_capital": 10000.0,
        "description": "Enters after a period of low ATR (compression) when ATR begins expanding — catches early trend.",
        "entry_logic": "ATR% below 1.5% (compressed) and price starts moving with volume confirmation.",
        "exit_logic": "ATR% exceeds 4% (overextended volatility) or price reverses.",
        "key_indicators": ["atr_pct", "bb_squeeze_active", "volume_surge", "ret_5d_pct"],
    },
    {
        "id": "momentum_continuation_pullback",
        "name": "Momentum Pullback to EMA-20",
        "timeframe": "4H",
        "allocated_capital": 12000.0,
        "description": "Trend-following pullback entry. In strong uptrend, buy the dip to 20 EMA.",
        "entry_logic": "Price above 200 EMA (uptrend confirmed), pulls back to touch 20 EMA, RSI 38-55.",
        "exit_logic": "Price drops below 200 EMA or RSI exceeds 75.",
        "key_indicators": ["price_above_ema200", "ema20", "rsi_14", "ret_20d_pct", "adx_14"],
    },
    {
        "id": "connors_rsi2_extremes",
        "name": "Connors RSI-2 Extremes",
        "timeframe": "1D",
        "allocated_capital": 10000.0,
        "description": "Short-term mean reversion. Enter when RSI-3 hits extreme oversold < 10, exit at RSI-3 > 70.",
        "entry_logic": "RSI-3 below 10 + price above 200 EMA — extreme short-term oversold in uptrend.",
        "exit_logic": "RSI-3 above 70 — mean reversion complete.",
        "key_indicators": ["rsi_3", "rsi_14", "price_above_ema200", "ret_5d_pct"],
    },
    {
        "id": "vwap_deviation_snap",
        "name": "VWAP Deviation Snap-Back",
        "timeframe": "2H",
        "allocated_capital": 12000.0,
        "description": "Price deviation from VWAP (approximated by 20-bar SMA). Enter when price snaps back after deviation.",
        "entry_logic": "BB %B below 0.2 (price at lower band = below VWAP proxy) + volume imbalance positive (buyers).",
        "exit_logic": "BB %B exceeds 0.8 (price at upper band = mean reverted).",
        "key_indicators": ["bb_pct_b", "volume_imbalance", "rsi_14", "price_above_ema200"],
    },
    {
        "id": "range_breakout",
        "name": "4H Range Breakout",
        "timeframe": "4H",
        "allocated_capital": 15000.0,
        "description": "Detects when price breaks out of a tight range with strong momentum.",
        "entry_logic": "Price near upper Donchian + ADX rising + volume surge = genuine breakout.",
        "exit_logic": "ADX falls below 20 (trend weakening) or price reverses below 20 EMA.",
        "key_indicators": ["donchian_breakout_up", "adx_14", "volume_surge", "atr_pct", "ret_5d_pct"],
    },
    {
        "id": "trend_strength_adx",
        "name": "Trend Strength ADX Breakout",
        "timeframe": "4H",
        "allocated_capital": 12000.0,
        "description": "Enters when ADX exceeds 25 with fresh directional momentum — confirms genuine trend.",
        "entry_logic": "ADX > 25 (strong trend) + EMA20 above EMA50 + RSI > 50.",
        "exit_logic": "ADX drops below 20 or EMA bearish cross.",
        "key_indicators": ["adx_14", "strong_trend", "ema_bullish_cross", "rsi_14", "supertrend_bullish"],
    },
    {
        "id": "multi_timeframe_confluence",
        "name": "Multi-Timeframe Confluence",
        "timeframe": "4H",
        "allocated_capital": 20000.0,
        "description": "Only enters when multiple indicators across different lookback periods agree.",
        "entry_logic": "Supertrend bullish + MACD positive + RSI > 50 + price above EMA200 = full confluence.",
        "exit_logic": "Any two confluence factors reverse.",
        "key_indicators": ["supertrend_bullish", "macd_histogram", "rsi_14", "price_above_ema200", "adx_14"],
    },
    {
        "id": "price_volume_divergence",
        "name": "Price-Volume Divergence",
        "timeframe": "4H",
        "allocated_capital": 10000.0,
        "description": "Detects divergence: price making higher highs but volume declining = distribution. Fade the move.",
        "entry_logic": "Price at 20-bar high but volume imbalance is negative (sellers winning) — short opportunity or warning.",
        "exit_logic": "Volume surges to confirm breakout or price reverses.",
        "key_indicators": ["donchian_breakout_up", "volume_imbalance", "volume_ratio_vs_20avg", "ret_5d_pct"],
    },
    {
        "id": "funding_carry_proxy",
        "name": "Low-Volatility Carry Proxy",
        "timeframe": "1D",
        "allocated_capital": 15000.0,
        "description": "Enters when 30-day annualized vol is below 40% — safe low-vol regime for carry-like exposure.",
        "entry_logic": "Annualized vol < 40% + price stable above EMA50 = safe hold regime.",
        "exit_logic": "Annualized vol exceeds 60% — regime break.",
        "key_indicators": ["vol_30d_annual_pct", "low_vol_regime", "price_above_ema50", "bb_width_pct"],
    },
    {
        "id": "ml_ensemble_factor",
        "name": "Multi-Factor ML Ensemble",
        "timeframe": "4H",
        "allocated_capital": 20000.0,
        "description": "Weighted ensemble of momentum, volatility, and mean-reversion factors.",
        "entry_logic": "Momentum score positive + low volatility regime + RSI not overbought = composite buy.",
        "exit_logic": "Momentum score turns negative or volatility spikes.",
        "key_indicators": ["ret_20d_pct", "vol_30d_annual_pct", "rsi_14", "macd_histogram", "adx_14"],
    },
    {
        "id": "pairs_cointegration",
        "name": "Cointegration Z-Score Mean Reversion",
        "timeframe": "1D",
        "allocated_capital": 15000.0,
        "description": "Z-score spread mean reversion. Enter when price deviates significantly below rolling mean.",
        "entry_logic": "30-day return is deeply negative (oversold vs mean) while volume imbalance shows buyers.",
        "exit_logic": "30-day return returns to near 0 or positive.",
        "key_indicators": ["ret_30d_pct", "ret_5d_pct", "volume_imbalance", "rsi_14", "bb_pct_b"],
    },
    {
        "id": "liquidity_sweep_absorption",
        "name": "Liquidity Sweep & Stop-Hunt Absorption",
        "timeframe": "4H",
        "allocated_capital": 20000.0,
        "description": "ICT-Quantified Stop-Hunt: Buys 20-bar Donchian sweep wicks absorbed by high volume delta.",
        "entry_logic": "Price low sweeps below 20-bar Donchian lower band and closes back inside with positive buyer absorption.",
        "exit_logic": "Price reaches Donchian midpoint target or breaks below the sweep wick.",
        "key_indicators": ["donchian_breakout_down", "volume_surge", "volume_imbalance", "rsi_14"],
    },
    {
        "id": "lead_lag_propagation",
        "name": "Lead-Lag Momentum Propagation",
        "timeframe": "4H",
        "allocated_capital": 15000.0,
        "description": "Enters high-beta lagging target when anchor asset displays impulsive momentum expansion.",
        "entry_logic": "Macro anchor momentum surges while high-beta target is lagging with positive RSI divergence.",
        "exit_logic": "Target catches up to anchor return or momentum fades.",
        "key_indicators": ["ret_5d_pct", "ret_20d_pct", "rsi_14", "adx_14", "ema20_ema50_gap_pct"],
    },
    {
        "id": "hurst_double_squeeze",
        "name": "Hurst Dynamic Double Squeeze",
        "timeframe": "4H",
        "allocated_capital": 20000.0,
        "description": "Hurst exponent regime switching: Bollinger inside Keltner breakout in trends, mean-reversion in chop.",
        "entry_logic": "In persistent trend regime (H > 0.52), buys expansion out of double squeeze. In chop (H < 0.48), buys lower band touch.",
        "exit_logic": "Price reaches opposite band or Bollinger baseline.",
        "key_indicators": ["bb_squeeze_active", "bb_pct_b", "adx_14", "atr_pct"],
    },
    {
        "id": "anchored_vwap_deviation",
        "name": "Anchored VWAP Multi-Deviation Snap",
        "timeframe": "4H",
        "allocated_capital": 20000.0,
        "description": "Institutional Mean Reversion: Buys extreme -1.8 sigma stretches below rolling VWAP with RSI(3) oversold exhaustion.",
        "entry_logic": "Price reaches -1.8 sigma below VWAP while short-term RSI is deeply oversold.",
        "exit_logic": "Price mean-reverts back to VWAP baseline (0 sigma).",
        "key_indicators": ["bb_pct_b", "rsi_3", "rsi_14", "volume_imbalance", "price_above_ema200"],
    },
    {
        "id": "sharpe_residual_momentum",
        "name": "Sharpe Residual Momentum Alpha",
        "timeframe": "1D",
        "allocated_capital": 30000.0,
        "description": "Factor Alpha: Ranks assets by risk-adjusted 30-day return divided by annualized volatility above 200 SMA.",
        "entry_logic": "Asset demonstrates top-tier Sharpe momentum score while holding above 200-day SMA.",
        "exit_logic": "Sharpe momentum drops below zero or price falls below 50-day EMA.",
        "key_indicators": ["ret_30d_pct", "vol_30d_annual_pct", "price_above_ema200", "rsi_14"],
    },
    {
        "id": "cvd_divergence_squeeze",
        "name": "CVD Divergence Short Squeeze",
        "timeframe": "4H",
        "allocated_capital": 15000.0,
        "description": "Order Flow: Detects bullish Cumulative Volume Delta divergence during slow price drifts.",
        "entry_logic": "Price makes lower 10-bar lows but buyer volume delta is rising while holding above 200 EMA.",
        "exit_logic": "Short squeeze target reached (50 EMA or +5% profit).",
        "key_indicators": ["volume_imbalance", "ret_5d_pct", "macd_hist_turning_up", "price_above_ema200"],
    },
    {
        "id": "rsi_oversold_reversal",
        "name": "RSI Bullish Oversold Recovery (> 30 above 200 SMA)",
        "timeframe": "4H",
        "allocated_capital": 25000.0,
        "description": "Momentum Reversal: Takes long entry when 14-period RSI was oversold (<=30) and crosses back above 30, strictly while price holds near to or above the 200-day daily SMA.",
        "entry_logic": "RSI(14) crosses upward above 30 from oversold and daily price holds near to/above 200 SMA.",
        "exit_logic": "RSI reaches overbought target (>=70) or price breaks 200 SMA support.",
        "key_indicators": ["rsi_14", "rsi_oversold_hook", "price_above_ema200", "ema20_ema50_gap_pct"],
    }
]



# Map strategy id → agent config for quick lookup
STRATEGY_AGENT_MAP: Dict[str, Dict[str, Any]] = {a["id"]: a for a in STRATEGY_AGENTS}


def _call_groq(system_prompt: str, user_prompt: str, model: str = None, max_tokens: int = 600) -> Optional[Dict[str, Any]]:
    """Makes structured LLM call via primary Featherless DeepSeek-V3.2 with Groq failover."""
    try:
        parsed, model_used, usage = query_llm_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model or FEATHERLESS_MODEL,
            temperature=0.15,
            max_tokens=max_tokens,
            timeout=20.0
        )
        return parsed
    except Exception as e:
        print(f"[StrategyAgent] LLM call failed: {e}")
        return None


def run_strategy_agent(
    agent_config: Dict[str, Any],
    symbol: str,
    snapshot: Dict[str, Any],
    in_position: bool = False
) -> Dict[str, Any]:
    """
    Runs a single strategy micro-agent for one symbol.
    Makes exactly one Groq call and returns a structured signal report.
    """
    agent_id    = agent_config["id"]
    agent_name  = agent_config["name"]
    timeframe   = agent_config["timeframe"]
    alloc       = agent_config["allocated_capital"]
    description = agent_config["description"]
    entry_logic = agent_config["entry_logic"]
    exit_logic  = agent_config["exit_logic"]
    key_ind     = agent_config["key_indicators"]

    if snapshot.get("error") or snapshot.get("bars", 0) < 20:
        return _agent_no_signal(agent_id, symbol, timeframe, alloc, "insufficient_data")

    # Build indicator summary for this strategy
    ind_summary = {k: snapshot.get(k) for k in key_ind if k in snapshot}

    system_prompt = (
        "You are an autonomous quantitative options trading signal agent within a multi-agent AI system. "
        "You are one of 20+ specialized strategy micro-agents, each running independently every market cycle. "
        "Your role is to analyze the full technical indicator snapshot for a specific quantitative strategy "
        "and determine if the mathematical conditions justify firing a trade signal.\n\n"
        "CRITICAL: Every signal you fire will be routed to the OPTIONS execution pipeline — "
        "your signal buys CALL or PUT option contracts on Alpaca, NOT spot equity shares. "
        "This means your analysis must consider whether the setup is suitable for OPTIONS specifically.\n\n"
        "REASONING PROTOCOL (execute every step):\n"
        "1. ASSESS each key indicator against the strategy's entry/exit logic thresholds\n"
        "2. EVALUATE indicator confluence — how many indicators agree vs disagree\n"
        "3. CONSIDER borderline cases: if an indicator is within 5% of threshold (e.g. RSI=49.8 vs filter=50), "
        "weigh the strength of supporting indicators before rejecting\n"
        "4. ASSESS trend regime via ADX and Supertrend before approving momentum signals\n"
        "5. FACTOR volume confirmation — signals without volume support deserve lower confidence\n"
        "6. OPTIONS SUITABILITY ANALYSIS (MANDATORY):\n"
        "   a) VOLATILITY REGIME: Is current annualized vol favorable for buying options? "
        "Low vol (<30%) = cheaper premiums, good for long calls/puts. High vol (>60%) = expensive premiums, risk of IV crush\n"
        "   b) TREND CLARITY: Options need directional conviction. Sideways/choppy markets "
        "(ADX<20) are terrible for directional options — Theta eats premium with no Delta gains\n"
        "   c) MOMENTUM SUSTAINABILITY: Can this move sustain for 21-45 days (typical DTE window)? "
        "One-bar spikes with no follow-through waste option premium on mean-reversion\n"
        "   d) PREMIUM EFFICIENCY: Strong signals with multiple confluent indicators justify full-size option contracts. "
        "Weak/borderline signals should suggest reduced size (50-70%) to limit premium risk\n"
        "7. OUTPUT a confidence score that honestly reflects conviction for an OPTIONS trade, not just a spot trade\n\n"
        "False signals cost REAL premium that decays daily via Theta. Be precise and conservative. "
        "Always respond in valid JSON only."
    )

    position_context = (
        f"CURRENT POSITION STATUS: {'ALREADY IN POSITION — evaluate EXIT_LONG only' if in_position else 'NO OPEN POSITION — evaluate ENTER_LONG only'}"
    )

    user_prompt = f"""
Analyze this trading opportunity for OPTIONS execution:

STRATEGY: {agent_name}
Description: {description}
Entry Logic: {entry_logic}
Exit Logic:  {exit_logic}
Timeframe:   {timeframe}
Symbol:      {symbol}
Allocated Capital: ${alloc:,.0f}

{position_context}

CURRENT MARKET INDICATORS:
{json.dumps(ind_summary, indent=2)}

FULL PRICE CONTEXT:
- Current Price: ${snapshot.get('price', 0):,.4f}
- 5-bar return:  {snapshot.get('ret_5d_pct', 0):+.2f}%
- 20-bar return: {snapshot.get('ret_20d_pct', 0):+.2f}%
- 30-bar return: {snapshot.get('ret_30d_pct', 0):+.2f}%
- ADX (trend strength): {snapshot.get('adx_14', 0):.1f} ({'Strong Trend' if snapshot.get('strong_trend') else 'Weak/No Trend'})
- RSI-14: {snapshot.get('rsi_14', 50):.1f}
- Supertrend: {'Bullish' if snapshot.get('supertrend_bullish') else 'Bearish'}
- Volume vs 20-bar avg: {snapshot.get('volume_ratio_vs_20avg', 1.0):.2f}x ({'SURGE' if snapshot.get('volume_surge') else 'Normal'})
- BB Squeeze Active: {snapshot.get('bb_squeeze_active', False)}

VOLATILITY & OPTIONS CONTEXT:
- 30-Day Annualized Volatility: {snapshot.get('vol_30d_annual_pct', 0):.1f}%
- Volatility Regime: {'LOW (cheap premiums, favorable for buying options)' if snapshot.get('low_vol_regime') else 'ELEVATED (expensive premiums, IV crush risk)'}
- BB Width %: {snapshot.get('bb_width_pct', 0):.2f}% (narrower = compressed vol, wider = expanded vol)
- ATR as % of Price: {snapshot.get('atr_pct', 0):.2f}% (daily expected move range)

Last Bar Time: {snapshot.get('last_bar_time', 'unknown')}

INSTRUCTIONS:
Based on ALL the indicators above, reason about whether this strategy should fire a signal RIGHT NOW.
CRITICAL: This signal will be used to BUY OPTION CONTRACTS (calls/puts), not spot shares.
You must evaluate whether the setup has enough directional conviction and trend sustainability 
to justify paying option premium that decays daily.

Be adaptive — if indicators are borderline (e.g. RSI=49.8 with strong trend), lean toward firing if confidence >= 60.
{'Focus only on EXIT_LONG: should we exit the current open position?' if in_position else 'Focus only on ENTER_LONG: should we enter a new position?'}

Return EXACTLY this JSON:
{{
  "signal_type": "ENTER_LONG" | "EXIT_LONG" | "NONE",
  "fired": true | false,
  "confidence": <integer 0-100>,
  "reasoning": "<2-3 concise sentences explaining your decision including technical AND options suitability factors>",
  "key_factor": "<the single most important indicator that drove your decision>",
  "risk_note": "<one sentence about primary risk to the OPTIONS trade, or null>",
  "options_suitability": "<STRONG | MODERATE | WEAK | UNFAVORABLE> — how suitable is this signal for buying options specifically",
  "options_reasoning": "<1-2 sentences explaining why this signal is good/bad for options: consider vol regime, trend clarity, momentum sustainability, and premium efficiency>",
  "suggested_size_pct": <integer 50-100>
}}

Rules:
- fired must be true only when signal_type is ENTER_LONG or EXIT_LONG
- If confidence < 60, set fired=false and signal_type=NONE
- If options_suitability is UNFAVORABLE, reduce confidence by 15 points and set suggested_size_pct to 50
- {'Set signal_type=ENTER_LONG if entry conditions are met' if not in_position else 'Set signal_type=EXIT_LONG if exit conditions are met'}
"""

    result = _call_groq(system_prompt, user_prompt)

    if result is None:
        return _agent_no_signal(agent_id, symbol, timeframe, alloc, "llm_unavailable")

    # Validate and clamp
    signal_type = result.get("signal_type", "NONE")
    confidence  = max(0, min(100, int(result.get("confidence", 0))))
    fired       = bool(result.get("fired", False)) and confidence >= 60

    if fired and signal_type not in ("ENTER_LONG", "EXIT_LONG"):
        fired = False
        signal_type = "NONE"

    # Enforce position logic
    if not in_position and signal_type == "EXIT_LONG":
        fired = False
        signal_type = "NONE"
    if in_position and signal_type == "ENTER_LONG":
        fired = False
        signal_type = "ALREADY_IN"

    # Extract options analysis fields
    options_suitability = result.get("options_suitability", "MODERATE")
    options_reasoning = result.get("options_reasoning", "")

    # If LLM flagged UNFAVORABLE, enforce confidence reduction
    if options_suitability == "UNFAVORABLE" and fired:
        confidence = max(0, confidence - 15)
        if confidence < 60:
            fired = False
            signal_type = "NONE"

    return {
        "strategy_id": agent_id,
        "strategy_name": agent_name,
        "symbol": symbol,
        "timeframe": timeframe,
        "allocated_capital": alloc,
        "signal_type": signal_type,
        "fired": fired,
        "confidence": confidence,
        "reasoning": result.get("reasoning", ""),
        "key_factor": result.get("key_factor", ""),
        "risk_note": result.get("risk_note"),
        "options_suitability": options_suitability,
        "options_reasoning": options_reasoning,
        "suggested_size_pct": max(50, min(100, int(result.get("suggested_size_pct", 100)))),
        "last_close": snapshot.get("price", 0.0),
        "last_bar_time": snapshot.get("last_bar_time", ""),
        "llm_model": FEATHERLESS_MODEL,
        "groq_model": FEATHERLESS_MODEL,
        "groq_call_made": True,
        "timestamp": datetime.datetime.utcnow().isoformat()
    }


def run_all_strategy_agents(
    snapshots: Dict[str, Any],
    strategy_ids: List[str],
    is_position_open_fn=None
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Runs all strategy micro-agents across all symbols in the snapshot.
    strategy_ids: list of strategy IDs to run this cycle
    is_position_open_fn: callable(strategy_id, symbol) -> bool

    Returns: (all_reports, fired_reports)
    """
    all_reports: List[Dict[str, Any]]   = []
    fired_reports: List[Dict[str, Any]] = []

    agents_to_run = [a for a in STRATEGY_AGENTS if a["id"] in strategy_ids or not strategy_ids]

    print(f"\n[StrategyAgents] Running {len(agents_to_run)} strategy agents across {len(snapshots)} symbols...")
    print("=" * 75)

    for i, agent in enumerate(agents_to_run):
        agent_id  = agent["id"]
        timeframe = agent["timeframe"]

        # Find symbols that match this strategy's timeframe
        relevant_symbols = [
            sym for sym, snap in snapshots.items()
            if snap.get("bars", 0) >= 20
            and snap.get("timeframe", timeframe) == timeframe
        ]

        # 1D strategies scan top 15 (daily — broader scan across options universe)
        # 4H/2H strategies scan top 15 by volume activity (faster cycles, focus on most active equities)
        if timeframe == "1D":
            # Sort equities by absolute 30-day return momentum
            relevant_symbols = sorted(
                relevant_symbols,
                key=lambda s: abs(snapshots[s].get("ret_30d_pct", 0)),
                reverse=True
            )[:15]
        else:
            # Sort equities by volume activity (most active first)
            # 4H and 2H strategies scan top 15 most active symbols
            relevant_symbols = sorted(
                relevant_symbols,
                key=lambda s: snapshots[s].get("volume_ratio_vs_20avg", 0),
                reverse=True
            )[:15]

        print(f"\n  [{i+1:02d}/{len(agents_to_run)}] Strategy: {agent['name']} ({timeframe}) | Scanning {len(relevant_symbols)} top symbols...")

        for symbol in relevant_symbols:
            snap = snapshots.get(symbol, {})

            in_pos = False
            if is_position_open_fn:
                try:
                    in_pos = is_position_open_fn(agent_id, symbol)
                except Exception:
                    in_pos = False

            report = run_strategy_agent(agent, symbol, snap, in_position=in_pos)
            all_reports.append(report)

            if report["fired"]:
                fired_reports.append(report)
                print(f"    [🔥 FIRED] {symbol} → {report['signal_type']} | Conf: {report['confidence']}% | {report['reasoning'][:80]}...")
            else:
                print(f"    [  HOLD ] {symbol} → {report['signal_type']} | Conf: {report['confidence']}%")

            # Rate limit: 0.4s between Groq calls to stay within free tier
            time.sleep(0.4)

    print("\n" + "=" * 75)
    print(f"[StrategyAgents] Complete: {len(all_reports)} evaluations | {len(fired_reports)} signals fired")
    print("=" * 75)

    return all_reports, fired_reports


def _agent_no_signal(agent_id, symbol, timeframe, alloc, reason) -> Dict[str, Any]:
    return {
        "strategy_id": agent_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "allocated_capital": alloc,
        "signal_type": "NONE",
        "fired": False,
        "confidence": 0,
        "reasoning": f"No signal: {reason}",
        "key_factor": reason,
        "risk_note": None,
        "suggested_size_pct": 100,
        "last_close": 0.0,
        "last_bar_time": "",
        "llm_model": FEATHERLESS_MODEL,
        "groq_model": FEATHERLESS_MODEL,
        "groq_call_made": False,
        "timestamp": datetime.datetime.utcnow().isoformat()
    }
