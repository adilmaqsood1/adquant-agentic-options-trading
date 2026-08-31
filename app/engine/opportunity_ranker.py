"""
Opportunity Ranker & Multi-Strategy Confluence Engine
=====================================================
Processes the global pool of fired signals from all quantitative strategies:
  1. Detects Multi-Strategy Confluence (multiple strategies firing on the same symbol)
  2. Calculates Confluence Scores (+25 bonus for Triple Confluence, +15 for Double Confluence)
  3. Executes a DeepSeek-V3.2 Opportunity Tournament:
     - Cross-sectional comparative analysis
     - Sector diversification enforcement (max 2 per sector)
     - IV regime & Delta efficiency ranking
     - Generates detailed institutional rationale for why top picks were chosen
"""

import json
import datetime
from typing import Dict, Any, List, Optional
from app.services.llm_client import query_llm_json


def _clean_text(s: str) -> str:
    if not s:
        return ""
    return str(s).replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "--").replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')


def detect_confluence_opportunities(fired_signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Groups all fired signals by underlying symbol to detect multi-strategy confluence.
    Calculates composite confluence metrics and priority tags.
    """
    if not fired_signals:
        return []

    # 1. Group signals by symbol
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for sig in fired_signals:
        sym = sig.get("symbol", "").upper().replace("/", "")
        if not sym:
            continue
        if sym not in grouped:
            grouped[sym] = []
        grouped[sym].append(sig)

    confluence_pool = []

    for sym, sig_list in grouped.items():
        unique_strategies = list(set([s.get("strategy_id", "options_core") for s in sig_list]))
        confluence_count = len(unique_strategies)

        # Primary signal reference (highest conviction)
        primary_sig = max(sig_list, key=lambda s: int(s.get("groq_confidence", s.get("confidence", 80))))

        signal_type = primary_sig.get("signal_type", "ENTER_LONG")
        last_close = float(primary_sig.get("last_close", 0.0))
        timeframe = primary_sig.get("timeframe", "4H")
        base_confidence = int(primary_sig.get("groq_confidence", primary_sig.get("confidence", 80)))

        # 2. Confluence Classification & Scoring Bonus
        if confluence_count >= 3:
            confluence_tier = "TRIPLE_CONFLUENCE"
            confluence_bonus = 25
            tier_label = f"Triple Strategy Confluence ({', '.join(unique_strategies)})"
        elif confluence_count == 2:
            confluence_tier = "DOUBLE_CONFLUENCE"
            confluence_bonus = 15
            tier_label = f"Double Strategy Confluence ({', '.join(unique_strategies)})"
        else:
            confluence_tier = "SINGLE_STRATEGY"
            confluence_bonus = 0
            tier_label = f"Single Strategy ({unique_strategies[0]})"

        composite_conviction = min(99, base_confidence + confluence_bonus)

        confluence_pool.append({
            "symbol": sym,
            "primary_strategy_id": primary_sig.get("strategy_id", "options_core"),
            "strategies_fired": unique_strategies,
            "confluence_count": confluence_count,
            "confluence_tier": confluence_tier,
            "confluence_label": tier_label,
            "confluence_bonus": confluence_bonus,
            "signal_type": signal_type,
            "last_close": last_close,
            "timeframe": timeframe,
            "base_confidence": base_confidence,
            "composite_conviction": composite_conviction,
            "raw_signals": sig_list,
            "primary_signal": primary_sig
        })

    # Sort descending by composite conviction and confluence count
    confluence_pool.sort(key=lambda x: (x["confluence_count"], x["composite_conviction"]), reverse=True)
    return confluence_pool


def rank_opportunities_tournament(
    confluence_pool: List[Dict[str, Any]],
    available_capacity: int = 5,
    market_regime: str = "STRONG_BULL",
    market_vix: float = 16.5
) -> Dict[str, Any]:
    """
    Executes a DeepSeek-V3.2 Cross-Sectional Tournament on the candidate pool.
    Ranks setups from best to worst, selecting the top N opportunities for execution.
    """
    if not confluence_pool:
        return {
            "ranked_candidates": [],
            "selected_for_execution": [],
            "tournament_summary": "No strategy signals fired in this cycle."
        }

    # Prepare candidate summaries for the AI Tournament
    candidates_payload = []
    for idx, c in enumerate(confluence_pool[:15], 1):
        candidates_payload.append({
            "candidate_id": f"CAND-{idx}",
            "symbol": c["symbol"],
            "strategies": c["strategies_fired"],
            "confluence_count": c["confluence_count"],
            "confluence_tier": c["confluence_tier"],
            "current_price": c["last_close"],
            "composite_score": c["composite_conviction"],
            "signal_type": c["signal_type"],
            "timeframe": c["timeframe"]
        })

    system_prompt = (
        "You are the Lead Quantitative Portfolio Manager & Opportunity Tournament Agent for an institutional Options Desk.\n"
        "Your task is to analyze a batch of candidate option trade signals, compare them cross-sectionally, and rank them.\n\n"
        "EVALUATION CRITERIA:\n"
        "1. MULTI-STRATEGY CONFLUENCE: Symbols with 2+ strategies firing simultaneously have the highest statistical win rates and MUST be prioritized.\n"
        "2. ASYMMETRIC REWARD/RISK: Prioritize clear directional breakouts and high-liquidity leaders with optimal delta leverage.\n"
        "3. SECTOR DIVERSIFICATION: Avoid selecting more than 2 stocks in the exact same sector (e.g. limit Mega-Cap Tech to 2 max).\n"
        "4. REGIME COMPATIBILITY: Align long calls/spreads with current market regime.\n\n"
        "OUTPUT FORMAT (STRICT JSON ONLY):\n"
        "{\n"
        '  "tournament_summary": "Executive summary explaining the macro context, confluence findings, and ranking logic.",\n'
        '  "top_ranked": [\n'
        "    {\n"
        '      "rank": 1,\n'
        '      "symbol": "TICKER",\n'
        '      "confluence_tier": "TRIPLE_CONFLUENCE|DOUBLE_CONFLUENCE|SINGLE_STRATEGY",\n'
        '      "tournament_score": 95,\n'
        '      "rationale": "Clear, concise 2-sentence institutional justification for why this is the #1 pick.",\n'
        '      "recommended_action": "BUY CALL (ITM) | BUY PUT (ITM) | SPREAD",\n'
        '      "suggested_size_pct": 100\n'
        "    }\n"
        "  ]\n"
        "}"
    )

    user_prompt = (
        f"MARKET REGIME: {market_regime} (VIX: {market_vix})\n"
        f"AVAILABLE POSITION CAPACITY: {available_capacity} open slots\n"
        f"CANDIDATE OPPORTUNITIES ({len(candidates_payload)} total):\n"
        f"{json.dumps(candidates_payload, indent=2)}\n\n"
        f"Perform the cross-sectional ranking tournament and select the top {available_capacity} candidates for live order execution."
    )

    ranked_candidates = []
    tournament_summary = ""

    try:
        llm_resp, model_name, _ = query_llm_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,
            max_tokens=1200,
            timeout=18.0
        )

        if isinstance(llm_resp, dict) and "top_ranked" in llm_resp:
            tournament_summary = _clean_text(llm_resp.get("tournament_summary", "DeepSeek-V3.2 tournament evaluation completed."))
            raw_ranked = llm_resp.get("top_ranked", [])
            
            # Map back to confluence_pool items
            pool_map = {c["symbol"].upper(): c for c in confluence_pool}
            for item in raw_ranked:
                sym = item.get("symbol", "").upper()
                c_obj = pool_map.get(sym)
                if c_obj:
                    ranked_candidates.append({
                        "rank": item.get("rank", len(ranked_candidates) + 1),
                        "symbol": sym,
                        "confluence_tier": c_obj["confluence_tier"],
                        "confluence_count": c_obj["confluence_count"],
                        "strategies_fired": c_obj["strategies_fired"],
                        "tournament_score": item.get("tournament_score", c_obj["composite_conviction"]),
                        "rationale": _clean_text(item.get("rationale", f"Selected with {c_obj['confluence_tier']} conviction.")),
                        "recommended_action": item.get("recommended_action", "BUY CALL (ITM)"),
                        "suggested_size_pct": item.get("suggested_size_pct", 100),
                        "signal_payload": c_obj["primary_signal"],
                        "last_close": c_obj["last_close"]
                    })
    except Exception as e:
        print(f"[OpportunityRanker] DeepSeek tournament notice: {e}. Applying mathematical confluence ranker.")

    # Fallback to Mathematical Confluence Ranking if LLM response is empty/failed
    if not ranked_candidates:
        tournament_summary = f"Mathematical Confluence Ranker: Sorted {len(confluence_pool)} opportunities by confluence tier and conviction."
        for rank_idx, c in enumerate(confluence_pool, 1):
            ranked_candidates.append({
                "rank": rank_idx,
                "symbol": c["symbol"],
                "confluence_tier": c["confluence_tier"],
                "confluence_count": c["confluence_count"],
                "strategies_fired": c["strategies_fired"],
                "tournament_score": c["composite_conviction"],
                "rationale": f"High probability {c['confluence_label']}. Composite score {c['composite_conviction']}%.",
                "recommended_action": "BUY CALL (ITM)" if "LONG" in c["signal_type"] else "BUY PUT (ITM)",
                "suggested_size_pct": 100 if c["confluence_count"] >= 2 else 80,
                "signal_payload": c["primary_signal"],
                "last_close": c["last_close"]
            })

    # Select top N up to available capacity
    selected_for_execution = ranked_candidates[:available_capacity]

    return {
        "ranked_candidates": ranked_candidates,
        "selected_for_execution": selected_for_execution,
        "tournament_summary": tournament_summary,
        "total_evaluated": len(confluence_pool),
        "selected_count": len(selected_for_execution)
    }
