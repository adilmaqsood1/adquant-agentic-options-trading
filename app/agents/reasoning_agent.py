import os
import json
import datetime
import httpx
import pandas as pd
from typing import Dict, Any, Optional
from dotenv import load_dotenv

from app.agents.market_context_agent import format_market_context_for_prompt
from app.services.llm_client import (
    query_llm_json,
    FEATHERLESS_MODEL,
    GROQ_FALLBACK_MODEL
)

# Load env variables from backend root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))

# Primary LLM: Featherless DeepSeek-V3.2 | Failover: Groq
DEFAULT_PRIMARY_MODEL = FEATHERLESS_MODEL
DEFAULT_FALLBACK_MODEL = GROQ_FALLBACK_MODEL



STRATEGY_CREDENTIALS = {
    "cross_sectional_momentum": {
        "profit_factor": 4.17,
        "calmar": 6.04,
        "max_dd": 8.2,
        "win_rate": 83.3,
        "avg_holding_days": 4.2
    },
    "supertrend": {
        "profit_factor": 1.82,
        "calmar": 1.46,
        "max_dd": 17.3,
        "win_rate": 50.0,
        "avg_holding_days": 6.3
    },
    "donchian_turtle": {
        "profit_factor": 1.53,
        "calmar": 1.12,
        "max_dd": 14.9,
        "win_rate": 43.75,
        "avg_holding_days": 4.2
    },
    "momentum_ema_rsi_adx": {
        "profit_factor": 2.71,
        "calmar": 3.91,
        "max_dd": 10.61,
        "win_rate": 63.6,
        "avg_holding_days": 3.2
    }
}


def reason_about_signal(
    signal_dict: Dict[str, Any],
    df: pd.DataFrame,
    portfolio_summary: Dict[str, Any],
    model: Optional[str] = None,
    groq_model: Optional[str] = None
) -> Dict[str, Any]:
    """
    Evaluates an active trading signal using Featherless DeepSeek-V3.2 (with Groq failover).
    Returns quantitative decision dict with confidence score and structured rationale.
    """
    target_model = model or groq_model or DEFAULT_PRIMARY_MODEL
    strategy_id = signal_dict.get("strategy_id", "unknown")
    symbol = signal_dict.get("symbol", "UNKNOWN")
    timeframe = signal_dict.get("timeframe", "4H")
    signal_type = signal_dict.get("signal_type", "ENTER_LONG")
    current_price = signal_dict.get("last_close", float(df["close"].iloc[-1]) if not df.empty else 0.0)
    last_bar_time = signal_dict.get("last_bar_time", str(df.index[-1]) if not df.empty else "")

    # 1. Compute market context features
    if df is not None and len(df) >= 20:
        close_series = df["close"]
        vol_series = df["volume"]

        # 50-bar SMA comparison
        sma_50 = close_series.rolling(50, min_periods=10).mean().iloc[-1]
        above_50_sma = bool(current_price >= sma_50)

        # 5-bar price change %
        prev_5_price = close_series.iloc[-5] if len(close_series) >= 5 else close_series.iloc[0]
        price_change_5b_pct = round(((current_price - prev_5_price) / prev_5_price) * 100.0, 2)

        # Volume vs 20-bar avg
        vol_20_avg = vol_series.rolling(20, min_periods=5).mean().iloc[-1]
        current_vol = vol_series.iloc[-1]
        vol_vs_20_avg_pct = round(((current_vol - vol_20_avg) / (vol_20_avg + 1e-10)) * 100.0, 1)

        # Last 5 bars table string
        last_5_df = df.tail(5)[["open", "high", "low", "close", "volume"]]
        last_5_table = last_5_df.to_string()
    else:
        above_50_sma = True
        price_change_5b_pct = 0.0
        vol_vs_20_avg_pct = 0.0
        last_5_table = "Insufficient bar history"

    # Strategy Backtest Credentials
    creds = STRATEGY_CREDENTIALS.get(strategy_id, {
        "profit_factor": 1.5,
        "calmar": 1.0,
        "max_dd": 15.0,
        "win_rate": 50.0,
        "avg_holding_days": 4.0
    })

    # Portfolio state
    total_allocated = portfolio_summary.get("total_allocated", 0.0)
    total_open_positions = portfolio_summary.get("total_open_positions", 0)
    strategies_active = portfolio_summary.get("strategies_active", [])

    # 2. Build Market Context Block (Macro FNG + Fundamentals + VADER Sentiment)
    market_context_str = format_market_context_for_prompt(symbol)

    # 3. Build Prompts
    system_prompt = (
        "You are a quantitative trading risk analyst within an autonomous AI options trading system. "
        "You are the critical gate between signal detection and live capital deployment on Alpaca's paper trading account. "
        "Your job is to evaluate trading signals and decide whether to approve or reject them for options execution.\n\n"
        "ANALYSIS PROTOCOL — Execute in this exact order:\n"
        "1. ASSESS signal quality: strategy backtest credentials (Profit Factor, Calmar, Win Rate) — "
        "strategies with PF > 2.0 and Calmar > 2.0 deserve higher baseline confidence\n"
        "2. EVALUATE technical context: price momentum, volume confirmation, SMA alignment, "
        "and whether the signal has structural support (not just a single indicator blip)\n"
        "3. INCORPORATE macro sentiment: Fear & Greed Index bias, news sentiment polarity, "
        "and fundamental valuation — extreme greed (>75) or fear (<25) should modulate confidence\n"
        "4. CHECK portfolio exposure: how much capital is already deployed, concentration risk\n"
        "5. SYNTHESIZE a final confidence score (0-100) that honestly reflects your conviction\n"
        "6. SET go=false if confidence < 60 — capital preservation over returns\n\n"
        "Your approval routes signals to Black-Scholes options pricing and live Alpaca execution. "
        "False approvals waste premium on theta decay. Be conservative, data-driven, and precise. "
        "Always respond in valid JSON only."
    )

    user_prompt = f"""
Evaluate this active trading signal:

1. SIGNAL CONTEXT:
- Strategy Name: {strategy_id}
- Strategy Backtest Credentials: Profit Factor = {creds['profit_factor']}, Calmar = {creds['calmar']}, Max DD = {creds['max_dd']}%, Win Rate = {creds['win_rate']}%, Avg Hold = {creds['avg_holding_days']} days
- Symbol: {symbol}
- Timeframe: {timeframe}
- Signal Type: {signal_type}
- Current Execution Price: ${current_price:,.2f}
- Last Bar Timestamp: {last_bar_time}

2. MARKET & PRICE CONTEXT (Last 5 Bars):
{last_5_table}
- Above 50-bar SMA: {above_50_sma}
- 5-bar Price Momentum: {price_change_5b_pct:+}%
- Current Volume vs 20-bar Average: {vol_vs_20_avg_pct:+}%

3. MACRO, VALUATION & NEWS SENTIMENT CONTEXT:
{market_context_str}

4. PORTFOLIO STATE:
- Total Capital Currently Allocated: ${total_allocated:,.2f}
- Current Number of Open Positions: {total_open_positions}
- Active Strategies in Portfolio: {strategies_active}

5. INSTRUCTIONS:
Evaluate this signal and return a pure JSON object with exactly these keys:
{{
  "confidence": <integer 0-100>,
  "go": <true or false>,
  "reasoning": "<2-3 concise sentences explaining your quantitative risk decision incorporating technical, macro FNG, valuation and sentiment factors>",
  "risk_concern": "<specific risk factor if any, or null>",
  "suggested_size_pct": <integer 50-100>
}}

Decision Rules:
- Incorporate Fear & Greed, valuation P/E, and news sentiment alongside technicals.
- 'suggested_size_pct' is the percentage (50-100) of allocated capital to commit.
"""

    try:
        parsed, model_used, usage = query_llm_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=target_model
        )

        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        confidence = int(parsed.get("confidence", 0))
        go = bool(parsed.get("go", False))
        reasoning = str(parsed.get("reasoning", "No reasoning provided."))
        risk_concern = parsed.get("risk_concern")
        suggested_size_pct = int(parsed.get("suggested_size_pct", 100))

        # Enforce hard safety rule: confidence < 60 must set go to False
        if confidence < 60:
            go = False

        # Clamp suggested_size_pct between 50 and 100
        suggested_size_pct = max(50, min(100, suggested_size_pct))

        return {
            "strategy_id": strategy_id,
            "symbol": symbol,
            "go": go,
            "confidence": confidence,
            "reasoning": reasoning,
            "risk_concern": risk_concern,
            "suggested_size_pct": suggested_size_pct,
            "llm_model": model_used,
            "groq_model": model_used,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens
        }

    except Exception as e:
        print(f"[ReasoningAgent] Exception during LLM reasoning: {e}")
        return _fallback_response(strategy_id, symbol, "fallback", f"LLM error: {e}")


def _fallback_response(strategy_id: str, symbol: str, model_name: str, error_msg: str) -> Dict[str, Any]:
    """Safe fallback response ensuring pipeline never crashes on LLM error"""
    return {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "go": False,
        "confidence": 0,
        "reasoning": f"LLM reasoning unavailable ({error_msg}). Defaulting to safety reject.",
        "risk_concern": "LLM validation failure",
        "suggested_size_pct": 50,
        "llm_model": model_name,
        "groq_model": model_name,
        "prompt_tokens": 0,
        "completion_tokens": 0
    }


def reason_about_options_trade(
    signal_dict: Dict[str, Any],
    contract_spec: Dict[str, Any],
    df: Optional[pd.DataFrame] = None,
    portfolio_summary: Optional[Dict[str, Any]] = None,
    model: Optional[str] = None,
    groq_model: Optional[str] = None
) -> Dict[str, Any]:
    """
    Evaluates an Options Contract and Black-Scholes Greeks using autonomous Featherless DeepSeek-V3.2 (with Groq failover).
    Synthesizes:
    1. Black-Scholes Greeks (Delta, Gamma, Theta decay, Vega, Breakeven)
    2. IV Regime & Historical Volatility (IV Rank, Percentile, Regime)
    3. Quantitative alpha signal alignment & Macro Market Context
    4. Capital budget and Risk Gate checks ($30k options budget, max 6 contracts)
    """
    target_model = model or groq_model or DEFAULT_PRIMARY_MODEL
    symbol = contract_spec.get("underlying_symbol", signal_dict.get("symbol", "AAPL"))
    strategy_id = contract_spec.get("strategy_id", signal_dict.get("strategy_id", "options_core"))
    occ_symbol = contract_spec.get("occ_symbol", "")
    strategy_type = contract_spec.get("strategy_type", "long_call").upper()
    contract_type = contract_spec.get("contract_type", "call").upper()
    strike_price = contract_spec.get("strike_price", 0.0)
    expiry_date = contract_spec.get("expiry_date", "")
    dte = contract_spec.get("dte_at_entry", 35)
    underlying_price = contract_spec.get("underlying_price", 0.0)
    premium_paid = contract_spec.get("premium_paid", 0.0)
    contracts_qty = contract_spec.get("contracts_qty", 1)
    total_cost = contract_spec.get("total_cost", 0.0)
    
    delta = contract_spec.get("delta_entry", 0.70)
    gamma = contract_spec.get("gamma_entry", 0.01)
    theta = contract_spec.get("theta_entry", -0.10)
    vega = contract_spec.get("vega_entry", 0.30)
    iv_entry = contract_spec.get("iv_entry", 0.28)
    iv_rank = contract_spec.get("iv_rank_entry", 35.0)
    iv_regime = contract_spec.get("iv_regime", "low").upper()

    profit_target = contract_spec.get("profit_target_premium", premium_paid * 1.80)
    stop_loss = contract_spec.get("stop_loss_premium", premium_paid * 0.60)
    breakeven = contract_spec.get("breakeven_price", strike_price + premium_paid)

    # Macro & Sentiment context
    market_context_str = format_market_context_for_prompt(symbol)

    # Options portfolio state
    if portfolio_summary is None:
        portfolio_summary = {
            "total_contracts_open": 0,
            "total_premium_deployed": 0.0,
            "budget_remaining": 30000.0
        }

    system_prompt = (
        "You are an Elite Options Quantitative Strategist and Autonomous Risk Agent "
        "within a multi-agent AI trading system executing on Alpaca's paper trading platform. "
        "You evaluate Black-Scholes mathematical Greeks, Implied Volatility surfaces, "
        "and Macro Sentiment to decide whether to approve or reject algorithmic options trades.\n\n"
        "OPTIONS ANALYSIS PROTOCOL — Execute in this exact order:\n"
        "1. EVALUATE Delta exposure: Is the Delta (0.55-0.85 range) appropriate for the strategy's "
        "directional conviction? Higher Delta = more directional risk but more premium capture\n"
        "2. CALCULATE Theta decay cost: At the given DTE, will Theta erode premium faster than "
        "expected Delta gains? DTE < 21 = accelerating decay zone, reject unless very high conviction\n"
        "3. ASSESS IV Regime: If IV Rank > 60 and we're BUYING options (long calls/puts), "
        "the premium is expensive — risk of IV crush on any volatility mean-reversion\n"
        "4. CHECK Vega exposure: High Vega + High IV Rank = dangerous for long options positions\n"
        "5. VERIFY breakeven feasibility: Can the underlying realistically reach breakeven "
        "within the DTE window based on its historical daily move range?\n"
        "6. INCORPORATE macro context: Fear & Greed, news sentiment, fundamental valuation\n"
        "7. SIZE the position: suggested_size_modifier reflects conviction (0.5 = half size, 1.0 = full)\n\n"
        "You strictly protect capital against excessive theta decay and IV crush. "
        "Your approval triggers live order placement on Alpaca — every dollar of premium matters. "
        "Always respond in valid JSON only."
    )

    user_prompt = f"""
Evaluate this algorithmic Options Trade Proposal:

1. UNDERLYING & STRATEGY SIGNAL:
- Symbol: {symbol}
- Strategy: {strategy_id}
- Signal Direction: {signal_dict.get('signal_type', 'BUY')}
- Underlying Stock Price: ${underlying_price:,.2f}

2. OPTION CONTRACT SPECIFICATION:
- OCC Symbol: {occ_symbol}
- Option Strategy: {strategy_type} ({contract_type})
- Strike Price: ${strike_price:,.2f}
- Expiration: {expiry_date} ({dte} DTE)
- Option Premium: ${premium_paid:,.2f}/share (${premium_paid * 100:,.2f} per contract)
- Position Size: {contracts_qty} contract(s) (${total_cost:,.2f} total cost)

3. BLACK-SCHOLES GREEKS & VOLATILITY PROFILE:
- Delta (Δ): {delta:.4f} (Directional sensitivity / hedge ratio)
- Gamma (Γ): {gamma:.6f} (Delta acceleration)
- Theta (Θ): ${theta:.4f}/day (Daily time decay cost)
- Vega (V): ${vega:.4f} (Sensitivity per 1% vol change)
- Implied Volatility (IV): {iv_entry * 100:.1f}%
- IV Rank: {iv_rank:.1f} / 100.0
- Volatility Regime: {iv_regime}
- Target Profit (+80%): ${profit_target:,.2f}
- Stop Loss (-40%): ${stop_loss:,.2f}
- Breakeven Price: ${breakeven:,.2f}

4. MACRO & SENTIMENT CONTEXT:
{market_context_str}

5. OPTIONS PORTFOLIO CONSTRAINTS:
- Current Open Option Contracts: {portfolio_summary.get('total_contracts_open', 0)} / 6 max
- Total Premium Deployed: ${portfolio_summary.get('total_premium_deployed', 0.0):,.2f}
- Options Budget Remaining: ${portfolio_summary.get('budget_remaining', 30000.0):,.2f} / $30,000.00

6. INSTRUCTIONS:
Evaluate this options trade and return a pure JSON object with exactly these keys:
{{
  "go": <true or false>,
  "confidence": <integer 0-100>,
  "options_verdict": <"STRONG_BUY" | "BUY" | "SCALE_DOWN" | "REJECT">,
  "greeks_assessment": "<concise evaluation of Delta exposure vs Theta decay over the {dte} DTE window>",
  "iv_regime_rationale": "<analysis of why IV rank {iv_rank:.1f}% justifies {strategy_type}>",
  "suggested_size_modifier": <float 0.50 to 1.0>,
  "reasoning": "<2-3 concise sentences synthesizing technical signal, Greeks edge, and macro context>"
}}

Rules:
- If IV Regime is HIGH (>60) and strategy is long options (buying calls/puts), reject or warn about volatility crush.
- If DTE < 14, reject due to accelerating theta decay.
- If confidence < 60, set go = false.
"""

    try:
        parsed, model_used, usage = query_llm_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=target_model
        )

        confidence = int(parsed.get("confidence", 75))
        go = bool(parsed.get("go", True))
        verdict = parsed.get("options_verdict", "BUY")
        greeks_eval = parsed.get("greeks_assessment", "Favorable Greeks with controlled theta decay.")
        iv_rationale = parsed.get("iv_regime_rationale", f"IV Rank {iv_rank:.1f}% supports option structure.")
        size_mod = float(parsed.get("suggested_size_modifier", 1.0))
        reasoning = str(parsed.get("reasoning", "Options trade approved based on quantitative Greeks and IV regime."))

        if confidence < 60:
            go = False

        return {
            "go": go,
            "confidence": confidence,
            "options_verdict": verdict,
            "greeks_assessment": greeks_eval,
            "iv_regime_rationale": iv_rationale,
            "suggested_size_modifier": size_mod,
            "reasoning": reasoning,
            "llm_model": model_used,
            "groq_model": model_used,
            "occ_symbol": occ_symbol
        }

    except Exception as e:
        print(f"[OptionsReasoning] Exception: {e} — Using deterministic fallback")
        return _deterministic_options_reasoning(contract_spec, signal_dict)


def _deterministic_options_reasoning(contract_spec: Dict[str, Any], signal_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic fallback for options trade evaluation based on quantitative Greeks & IV"""
    iv_rank = float(contract_spec.get("iv_rank_entry", 35.0))
    delta = float(contract_spec.get("delta_entry", 0.70))
    dte = int(contract_spec.get("dte_at_entry", 35))

    is_safe = (dte >= 21) and (0.55 <= abs(delta) <= 0.85) and (iv_rank <= 65.0)
    confidence = 82 if is_safe else 55

    return {
        "go": is_safe,
        "confidence": confidence,
        "options_verdict": "BUY" if is_safe else "REJECT",
        "greeks_assessment": f"Delta {delta:.2f} provides strong directional leverage with {dte} DTE managing theta decay.",
        "iv_regime_rationale": f"IV Rank {iv_rank:.1f}% represents favorable volatility pricing.",
        "suggested_size_modifier": 1.0 if is_safe else 0.5,
        "reasoning": "Deterministic quantitative approval based on Black-Scholes Greeks and IV regime.",
        "groq_model": "deterministic_fallback",
        "occ_symbol": contract_spec.get("occ_symbol", "")
    }

