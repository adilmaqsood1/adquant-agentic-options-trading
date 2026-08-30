"""
Layer 3: Research Agent
────────────────────────
This is the creative agent. It reads all strategy reports from Layer 2,
identifies patterns in what's working and what isn't, assesses the current
market regime, and uses LLM reasoning to:

1. Generate novel strategy variations based on what the market is showing
2. Identify opportunities that existing strategies missed
3. Produce a market regime assessment for the dashboard

One LLM call per cycle (Featherless DeepSeek-V3.2 primary, Groq failover) with a broader 2000-token context window.
"""
import os
import json
import datetime
import httpx
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

from app.services.llm_client import query_llm_json, FEATHERLESS_MODEL, FEATHERLESS_API_KEY

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
load_dotenv()



# In-memory cache for latest research insights
_LATEST_INSIGHTS: Dict[str, Any] = {}


def run_research_agent(
    all_strategy_reports: List[Dict[str, Any]],
    snapshots: Dict[str, Any],
    cycle_timeframe: str = "4H"
) -> Dict[str, Any]:
    """
    Layer 3 Research Agent.
    Analyzes all 20 strategy reports and the full market snapshot,
    then uses Groq to produce:
    - Market regime assessment
    - Patterns in firing vs non-firing signals
    - Novel strategy variations
    - Specific opportunities identified
    """
    global _LATEST_INSIGHTS

    if not FEATHERLESS_API_KEY:
        return _empty_insights("llm_unavailable")

    # Summarize Strategy Reports 
    fired   = [r for r in all_strategy_reports if r.get("fired")]
    no_fire = [r for r in all_strategy_reports if not r.get("fired")]

    # High-confidence non-firing (interesting — nearly triggered)
    near_misses = sorted(
        [r for r in no_fire if r.get("confidence", 0) >= 50],
        key=lambda r: r.get("confidence", 0),
        reverse=True
    )[:8]

    # Top fired signals summary
    top_fired_summary = []
    for r in fired[:6]:
        top_fired_summary.append({
            "strategy": r.get("strategy_id"),
            "symbol": r.get("symbol"),
            "signal": r.get("signal_type"),
            "confidence": r.get("confidence"),
            "key_factor": r.get("key_factor"),
            "reasoning": r.get("reasoning", "")[:120]
        })

    near_miss_summary = []
    for r in near_misses:
        near_miss_summary.append({
            "strategy": r.get("strategy_id"),
            "symbol": r.get("symbol"),
            "confidence": r.get("confidence"),
            "key_factor": r.get("key_factor"),
            "reasoning": r.get("reasoning", "")[:100]
        })

    # Aggregate Market Snapshot Stats
    crypto_snaps  = {k: v for k, v in snapshots.items() if "/" in k}
    equity_snaps  = {k: v for k, v in snapshots.items() if "/" not in k}

    def avg_indicator(snaps, key):
        vals = [v.get(key) for v in snaps.values() if isinstance(v.get(key), (int, float))]
        return round(sum(vals) / len(vals), 2) if vals else None

    # Unified Market Summary (100% US Equities Options Universe)
    market_summary = {
        "avg_rsi": avg_indicator(snapshots, "rsi_14"),
        "avg_adx": avg_indicator(snapshots, "adx_14"),
        "avg_ret_30d": avg_indicator(snapshots, "ret_30d_pct"),
        "avg_vol_30d_annual": avg_indicator(snapshots, "vol_30d_annual_pct"),
        "pct_above_ema200": round(sum(1 for v in snapshots.values() if v.get("price_above_ema200")) / max(len(snapshots), 1) * 100, 1),
        "pct_supertrend_bullish": round(sum(1 for v in snapshots.values() if v.get("supertrend_bullish")) / max(len(snapshots), 1) * 100, 1),
        "pct_in_squeeze": round(sum(1 for v in snapshots.values() if v.get("bb_squeeze_active")) / max(len(snapshots), 1) * 100, 1),
        "num_volume_surges": sum(1 for v in snapshots.values() if v.get("volume_surge")),
        "symbols_scanned": len(snapshots)
    }

    # Build Prompt
    system_prompt = (
        "You are a senior quantitative research analyst and creative strategy designer "
        "for an autonomous AI options trading system executing on Alpaca's Trading API. "
        "You serve as the system's 'creative brain' — analyzing aggregate results from 20+ strategy micro-agents "
        "to identify market regime patterns, discover missed opportunities, and propose novel alpha strategies.\n\n"
        "RESEARCH REASONING PROTOCOL:\n"
        "1. SYNTHESIZE all strategy agent results — identify WHY signals fired or didn't fire\n"
        "2. DETECT regime patterns across the options universe using aggregate RSI, ADX, volatility, and momentum\n"
        "3. IDENTIFY near-miss patterns — strategies that almost triggered reveal forming setups\n"
        "4. PROPOSE novel strategies that exploit the current regime better than existing strategies\n"
        "5. PRIORITIZE actionable watchlist items with specific entry triggers and timeframes\n"
        "6. ASSESS macro risk — Fear & Greed sentiment bias, volatility regime shifts, and market breadth\n\n"
        "CRITICAL OPTIONS CONSTRAINT: Every novel strategy you propose MUST be executable as an options trade on Alpaca:\n"
        "- Specify the recommended option structure (long_call, long_put, bull_call_spread, bear_call_spread, or short_put)\n"
        "- Ensure expected move duration fits a 21-45 day DTE window (optimal for theta management)\n"
        "- Align with the current volatility regime (buy premium in low vol, sell or spread in elevated vol)\n\n"
        "Your research output drives the next cycle's focus and informs portfolio-level decisions. "
        "Think like a hedge fund portfolio manager who must justify every recommendation with data. "
        "Always return valid JSON only."
    )

    user_prompt = f"""
CYCLE RESEARCH ANALYSIS — {cycle_timeframe} Cycle — {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}

═══ US EQUITIES OPTIONS UNIVERSE ({market_summary['symbols_scanned']} assets) ═══
- Average RSI-14: {market_summary['avg_rsi']}
- Average ADX (trend strength): {market_summary['avg_adx']}
- Average 30-day Return: {market_summary['avg_ret_30d']}%
- Annualized Volatility: {market_summary['avg_vol_30d_annual']}%
- % Assets Above EMA200 (Long-Term Trend): {market_summary['pct_above_ema200']}%
- % Assets Supertrend Bullish: {market_summary['pct_supertrend_bullish']}%
- % Assets in Bollinger Squeeze: {market_summary['pct_in_squeeze']}%
- Volume Surges Detected: {market_summary['num_volume_surges']}

═══ STRATEGY AGENT RESULTS SUMMARY ═══

FIRED SIGNALS ({len(fired)} total):
{json.dumps(top_fired_summary, indent=2)}

HIGH-CONFIDENCE NEAR-MISSES ({len(near_misses)} — confidence 50-59, didn't fire):
{json.dumps(near_miss_summary, indent=2)}

TOTAL STRATEGY EVALUATIONS: {len(all_strategy_reports)}
TOTAL FIRED: {len(fired)}
TOTAL NO-FIRE: {len(no_fire)}

═══ YOUR RESEARCH TASK ═══

Based on all the above data, produce a comprehensive options research report in JSON:

{{
  "market_regime": {{
    "regime": "<one of: STRONG_BULL | BULL | SIDEWAYS_CONSOLIDATION | BEAR | STRONG_BEAR>",
    "overall_assessment": "<2-3 sentences: what the options market is doing right now and why>",
    "key_risk": "<primary risk to watch right now>",
    "opportunity_window": "<1 sentence: what options setup is forming that traders should watch>"
  }},
  "pattern_analysis": {{
    "why_signals_firing": "<explain what conditions are causing signals to fire (or not)>",
    "near_miss_insight": "<what do the near-miss signals tell us about market conditions?>",
    "strategies_to_watch": ["<strategy_id1>", "<strategy_id2>"]
  }},
  "novel_strategies": [
    {{
      "name": "<creative strategy name>",
      "logic": "<entry/exit logic in 1-2 sentences>",
      "why_now": "<why this strategy fits current market regime>",
      "option_structure": "<long_call | long_put | bull_call_spread | bear_call_spread | short_put>",
      "optimal_dte": "<e.g. 30-35>",
      "indicators_needed": ["<indicator1>", "<indicator2>"],
      "estimated_confidence": <integer 0-100>
    }}
  ],
  "top_watchlist": [
    {{
      "symbol": "<symbol>",
      "reason": "<why this symbol is interesting for options right now>",
      "setup": "<what option setup to watch for>",
      "timeframe": "<2H|4H|1D>"
    }}
  ],
  "actionable_insight": "<single most important actionable insight for the options trader right now>",
  "next_cycle_focus": "<what to prioritize in the next cycle>"
}}

Generate 2-3 novel options strategies and 3-5 watchlist items. Be specific, quantitative, and actionable.
"""

    try:
        from app.services.llm_client import query_llm_json as _query_llm
        insights, model_used, usage = _query_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=2000,
            timeout=35.0
        )

        # Add metadata
        insights["cycle_timeframe"] = cycle_timeframe
        insights["timestamp_utc"] = datetime.datetime.utcnow().isoformat()
        insights["signals_fired"] = len(fired)
        insights["signals_evaluated"] = len(all_strategy_reports)
        insights["market_summary"] = market_summary
        insights["llm_model"] = model_used

        _LATEST_INSIGHTS = insights
        regime_val = insights.get("market_regime", {})
        regime_str = regime_val.get("regime", "unknown") if isinstance(regime_val, dict) else str(regime_val)
        novel_count = len(insights.get("novel_strategies", [])) if isinstance(insights.get("novel_strategies"), list) else 0
        print(f"\n[ResearchAgent] ✅ Research complete [{model_used}] | Regime: {regime_str} | Novel strategies: {novel_count}")
        return insights

    except Exception as e:
        print(f"[ResearchAgent] LLM Error: {e}")
        return _empty_insights(f"llm_error: {e}")


def get_latest_insights() -> Dict[str, Any]:
    """Returns the cached latest research insights."""
    return _LATEST_INSIGHTS.copy()


def _empty_insights(reason: str) -> Dict[str, Any]:
    return {
        "market_regime": {"regime": "UNKNOWN", "overall_assessment": reason, "key_risk": "N/A", "opportunity_window": "N/A"},
        "pattern_analysis": {},
        "novel_strategies": [],
        "top_watchlist": [],
        "actionable_insight": "Research agent unavailable.",
        "next_cycle_focus": "Retry next cycle.",
        "signals_fired": 0,
        "signals_evaluated": 0,
        "timestamp_utc": datetime.datetime.utcnow().isoformat()
    }
