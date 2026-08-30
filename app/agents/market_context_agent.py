"""
Market Context Agent (Layer 1.5 Context Engine)
Enriches Strategy Micro-Agents & Research Agent with:
1. Fear & Greed Index (Macro Sentiment Regime)
2. Fundamental Financial Ratios via yfinance (P/E, EPS, Margins, Debt/Equity)
3. Recent Financial News Headlines & VADER Sentiment Polarity Scoring
"""

import os
import time
import json
import urllib.request
import datetime
from typing import Dict, Any, List, Optional
import yfinance as yf
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_ANALYZER = SentimentIntensityAnalyzer()

# In-memory caches to ensure fast execution and zero rate limiting
_FNG_CACHE: Dict[str, Any] = {}
_FNG_CACHE_EXPIRY: float = 0.0

_FUNDAMENTALS_CACHE: Dict[str, Any] = {}
_SENTIMENT_CACHE: Dict[str, Any] = {}
CACHE_TTL_SECONDS = 14400  # 4 hours


def fetch_fear_and_greed_index() -> Dict[str, Any]:
    """
    Fetches the Fear & Greed Index (0-100 score + sentiment classification).
    Caches result for 30 minutes to prevent unnecessary network requests.
    """
    global _FNG_CACHE, _FNG_CACHE_EXPIRY
    now = time.time()
    if _FNG_CACHE and now < _FNG_CACHE_EXPIRY:
        return _FNG_CACHE

    try:
        req = urllib.request.Request(
            "https://api.alternative.me/fng/?limit=1",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as res:
            data = json.loads(res.read().decode())
            if "data" in data and len(data["data"]) > 0:
                item = data["data"][0]
                score = int(item.get("value", 50))
                classification = item.get("value_classification", "Neutral")
                result = {
                    "score": score,
                    "classification": classification,
                    "regime_bias": "RISK_ON" if score >= 55 else ("RISK_OFF" if score <= 40 else "NEUTRAL"),
                    "timestamp": datetime.datetime.utcnow().isoformat()
                }
                _FNG_CACHE = result
                _FNG_CACHE_EXPIRY = now + 1800  # 30 mins
                return result
    except Exception as e:
        print(f"[MarketContext] FNG fetch error: {e}, using fallback neutral")

    fallback = {
        "score": 50,
        "classification": "Neutral",
        "regime_bias": "NEUTRAL",
        "timestamp": datetime.datetime.utcnow().isoformat()
    }
    _FNG_CACHE = fallback
    _FNG_CACHE_EXPIRY = now + 300
    return fallback


def fetch_symbol_fundamentals(symbol: str) -> Dict[str, Any]:
    """
    Pulls fundamental summary stats from yfinance (P/E, Forward P/E, Margins, Debt/Equity).
    Caches per symbol for 4 hours.
    """
    clean_sym = symbol.upper().replace("/", "-").strip()
    # Skip crypto pairs for fundamental balance sheet queries
    if any(clean_sym.endswith(suffix) for suffix in ["-USD", "-USDT", "-USDC", "-BTC"]):
        return {
            "asset_type": "crypto",
            "valuation_summary": "Crypto asset (non-equity). Valuation driven by on-chain flow and liquidity."
        }

    now = time.time()
    cached = _FUNDAMENTALS_CACHE.get(clean_sym)
    if cached and (now - cached.get("_cached_at", 0)) < CACHE_TTL_SECONDS:
        return cached

    try:
        ticker = yf.Ticker(clean_sym)
        info = ticker.info or {}
        
        pe = info.get("trailingPE")
        fwd_pe = info.get("forwardPE")
        peg = info.get("pegRatio")
        pb = info.get("priceToBook")
        profit_margin = info.get("profitMargins")
        debt_to_equity = info.get("debtToEquity")
        roe = info.get("returnOnEquity")
        market_cap = info.get("marketCap")
        target_mean = info.get("targetMeanPrice")
        recommendation = info.get("recommendationKey", "none")

        val_status = "FAIR_VALUED"
        if pe:
            if pe > 45:
                val_status = "HIGH_GROWTH_PREMIUM"
            elif pe < 15:
                val_status = "VALUE_DEPRESSED"

        result = {
            "asset_type": "equity",
            "trailing_pe": round(float(pe), 2) if pe else None,
            "forward_pe": round(float(fwd_pe), 2) if fwd_pe else None,
            "peg_ratio": round(float(peg), 2) if peg else None,
            "price_to_book": round(float(pb), 2) if pb else None,
            "profit_margin_pct": round(float(profit_margin) * 100.0, 2) if profit_margin else None,
            "debt_to_equity": round(float(debt_to_equity), 2) if debt_to_equity else None,
            "return_on_equity_pct": round(float(roe) * 100.0, 2) if roe else None,
            "market_cap": market_cap,
            "analyst_target": target_mean,
            "analyst_rating": recommendation.upper(),
            "valuation_status": val_status,
            "_cached_at": now
        }
        _FUNDAMENTALS_CACHE[clean_sym] = result
        return result
    except Exception as e:
        print(f"[MarketContext] Fundamental fetch error for {clean_sym}: {e}")
        return {
            "asset_type": "equity",
            "valuation_status": "UNKNOWN",
            "error": str(e)
        }


def fetch_symbol_sentiment(symbol: str, max_headlines: int = 4) -> Dict[str, Any]:
    """
    Pulls recent financial news headlines and computes VADER sentiment compound polarity.
    Caches per symbol for 1 hour.
    """
    clean_sym = symbol.upper().replace("/", "-").strip()
    now = time.time()
    cached = _SENTIMENT_CACHE.get(clean_sym)
    if cached and (now - cached.get("_cached_at", 0)) < 3600:
        return cached

    headlines = []
    compound_scores = []

    try:
        ticker = yf.Ticker(clean_sym)
        raw_news = ticker.news or []
        for item in raw_news[:max_headlines]:
            title = item.get("title")
            if not title and isinstance(item.get("content"), dict):
                title = item.get("content", {}).get("title")
            if not title:
                continue

            scores = _ANALYZER.polarity_scores(title)
            c_score = scores.get("compound", 0.0)
            compound_scores.append(c_score)
            headlines.append({
                "title": title,
                "sentiment_compound": round(c_score, 3),
                "sentiment_label": "BULLISH" if c_score >= 0.15 else ("BEARISH" if c_score <= -0.15 else "NEUTRAL")
            })

    except Exception as e:
        print(f"[MarketContext] News sentiment fetch error for {clean_sym}: {e}")

    avg_compound = round(sum(compound_scores) / len(compound_scores), 3) if compound_scores else 0.0
    overall_sentiment = "BULLISH" if avg_compound >= 0.10 else ("BEARISH" if avg_compound <= -0.10 else "NEUTRAL")

    result = {
        "symbol": clean_sym,
        "overall_sentiment": overall_sentiment,
        "sentiment_score": avg_compound,
        "headlines_analyzed": len(headlines),
        "headlines": headlines,
        "_cached_at": now
    }
    _SENTIMENT_CACHE[clean_sym] = result
    return result


def get_market_context(symbol: Optional[str] = None) -> Dict[str, Any]:
    """
    Gathers comprehensive macro, fundamental, and sentiment context.
    """
    fng = fetch_fear_and_greed_index()
    context = {
        "macro_sentiment": fng,
        "timestamp": datetime.datetime.utcnow().isoformat()
    }

    if symbol:
        clean_sym = symbol.upper().strip()
        context["symbol"] = clean_sym
        context["fundamentals"] = fetch_symbol_fundamentals(clean_sym)
        context["news_sentiment"] = fetch_symbol_sentiment(clean_sym)

    return context


def format_market_context_for_prompt(symbol: str) -> str:
    """
    Produces a concise 4-6 line Markdown text block ready for injection into Groq LLM prompts.
    """
    ctx = get_market_context(symbol)
    fng = ctx.get("macro_sentiment", {})
    funds = ctx.get("fundamentals", {})
    sent = ctx.get("news_sentiment", {})

    lines = [
        f"--- MACRO & FUNDAMENTAL CONTEXT ({symbol}) ---",
        f"• Fear & Greed Index: {fng.get('score', 50)}/100 ({fng.get('classification', 'Neutral').upper()}) [Bias: {fng.get('regime_bias', 'NEUTRAL')}]"
    ]

    if funds.get("asset_type") == "equity":
        pe_str = f"P/E: {funds.get('trailing_pe', 'N/A')}" if funds.get("trailing_pe") else "P/E: N/A"
        fwd_pe = f"Fwd P/E: {funds.get('forward_pe', 'N/A')}" if funds.get("forward_pe") else ""
        margin = f"Margin: {funds.get('profit_margin_pct', 'N/A')}%" if funds.get("profit_margin_pct") else ""
        lines.append(f"• Valuation & Financials: {pe_str} | {fwd_pe} | {margin} | Rating: {funds.get('analyst_rating', 'N/A')}")
    else:
        lines.append("• Asset Class: Crypto / Digital Asset (Macro Momentum & Order Flow Regimes Active)")

    if sent.get("headlines"):
        lines.append(f"• News Sentiment: {sent.get('overall_sentiment')} (Score: {sent.get('sentiment_score', 0.0):+.2f})")
        for h in sent.get("headlines", [])[:2]:
            lines.append(f"  - [{h.get('sentiment_label')}] {h.get('title')[:75]}...")

    lines.append("--------------------------------------------------")
    return "\n".join(lines)
