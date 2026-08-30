import datetime
from typing import Dict, Any, Optional
from app.core.database import is_position_open, get_open_positions

TOTAL_PORTFOLIO_CAPITAL = 10_000_000.0  # Unlimited testing capacity
MAX_EXPOSURE_CAP = float('inf')          # No exposure cap during strategy evaluation
MAX_OPEN_POSITIONS = float('inf')        # Unlimited open positions across all strategies
CIRCUIT_BREAKER_DRAWDOWN_PCT = 50.0      # Relaxed for comprehensive backtest/forward-test
MIN_GROQ_CONFIDENCE = 40



def evaluate_risk(
    signal_dict: Dict[str, Any],
    groq_decision: Dict[str, Any],
    portfolio_summary: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Quantitative Risk Gate (Uncapped Strategy Testing Mode):
    Allows all valid strategy signals to be recorded and traded without artificial caps.
    """
    strategy_id = signal_dict.get("strategy_id", "unknown")
    symbol = signal_dict.get("symbol", "UNKNOWN")
    allocated_capital = float(signal_dict.get("allocated_capital", 25000.0))
    last_close = float(signal_dict.get("last_close", 0.0))

    total_allocated = float(portfolio_summary.get("total_allocated", 0.0))
    current_exposure_pct = round((total_allocated / 100000.0) * 100.0, 2)
    groq_confidence = int(groq_decision.get("confidence", 75))

    rules_checked = 0

    # Rule 1: Prevent duplicate open position on the exact same strategy + symbol
    rules_checked += 1
    if is_position_open(strategy_id, symbol):
        return _build_risk_response(
            strategy_id, symbol, approved=False,
            block_reason=f"Strategy already has active open position on {symbol}",
            rules_checked=rules_checked,
            groq_confidence=groq_confidence,
            exposure_pct=current_exposure_pct
        )

    # Calculate capital and quantity sizing
    suggested_size_pct = float(groq_decision.get("suggested_size_pct", 100)) / 100.0
    if suggested_size_pct <= 0:
        suggested_size_pct = 1.0
    final_capital = round(allocated_capital * suggested_size_pct, 2)
    final_quantity = round(final_capital / last_close, 8) if last_close > 0 else 0.0

    return {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "approved": True,
        "block_reason": None,
        "rules_checked": rules_checked,
        "final_capital": final_capital,
        "final_quantity": final_quantity,
        "groq_confidence": groq_confidence,
        "portfolio_exposure_pct": current_exposure_pct,
        "timestamp": datetime.datetime.utcnow()
    }




def _build_risk_response(
    strategy_id: str,
    symbol: str,
    approved: bool,
    block_reason: Optional[str],
    rules_checked: int,
    groq_confidence: int,
    exposure_pct: float
) -> Dict[str, Any]:
    return {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "approved": approved,
        "block_reason": block_reason,
        "rules_checked": rules_checked,
        "final_capital": None,
        "final_quantity": None,
        "groq_confidence": groq_confidence,
        "portfolio_exposure_pct": exposure_pct,
        "timestamp": datetime.datetime.utcnow()
    }
