import datetime
import math
from typing import Dict, Any, List, Optional, Tuple
from app.engine.options_pricing import BlackScholesEngine
from app.engine.iv_calculator import compute_iv_rank

def generate_occ_symbol(symbol: str, expiry_date: datetime.date, strike: float, contract_type: str = "call") -> str:
    """
    Generates standard OCC (Options Clearing Corporation) symbol:
    Root + YYMMDD + C/P + 8-digit strike price (strike * 1000).
    Example: AAPL, 2026-10-02, Strike 295.00 Call -> AAPL261002C00295000
    """
    clean_sym = symbol.upper().replace("/", "").replace("-", "")
    expiry_str = expiry_date.strftime("%y%m%d")
    type_char = "C" if contract_type.lower().startswith("c") else "P"
    strike_int = int(round(strike * 1000.0))
    return f"{clean_sym}{expiry_str}{type_char}{strike_int:08d}"


def select_contract(
    signal_dict: Dict[str, Any],
    underlying_price: float,
    hv_data: Optional[Dict[str, Any]] = None,
    groq_confidence: int = 80
) -> Dict[str, Any]:
    """
    Contract Selection Agent (Pure Math & Black-Scholes):
    1. Determines Strategy Type from Matrix (Signal Direction + IV Rank)
       - Bullish + IV < 35   -> Long Call (Δ 0.65 - 0.70)
       - Bullish + IV 35-55  -> Bull Call Spread (Buy Δ0.65 Call + Sell Δ0.40 Call)
       - Bullish + IV > 55   -> Short Cash-Secured Put (OTM Δ -0.25 to -0.30, 5-7% below spot)
       - Bearish + IV < 35   -> Long Put (Δ -0.65 to -0.70)
       - Bearish + IV > 55   -> Bear Call Spread (Sell Δ0.30 Call + Buy Δ0.50 Call)
    2. Expiry Selection: Target 30-35 DTE sweet spot (Nearest Friday, min 21 DTE, max 45 DTE)
    3. Mathematical Greeks via Black-Scholes
    4. Exact Exit Thresholds: +60% Profit Target, -35% Stop Loss, 14 DTE Time Stop
    """
    symbol = signal_dict.get("symbol", "AAPL").upper().replace("/", "")
    signal_type = signal_dict.get("signal_type", "BUY").upper()
    strategy_id = signal_dict.get("strategy_id", "options_core")
    signal_id = signal_dict.get("signal_id", f"{strategy_id}_{symbol}_{datetime.datetime.utcnow().strftime('%Y%m%d%H%M')}")

    # 1. Fetch IV Rank
    if hv_data is None:
        hv_data = compute_iv_rank(symbol)

    iv_rank = float(hv_data.get("iv_rank", 30.0))
    iv_regime = hv_data.get("regime", "low")
    sigma = float(hv_data.get("iv_30d", 0.28))

    is_bullish = any(w in signal_type for w in ["BUY", "LONG", "BULL"])
    is_bearish = any(w in signal_type for w in ["SELL", "SHORT", "BEAR"])

    # 2. Strategy Selection Matrix
    if is_bullish:
        if iv_rank < 35.0:
            strategy_type = "long_call"
            contract_type = "call"
            target_delta = 0.68
        elif iv_rank <= 55.0:
            strategy_type = "bull_call_spread"
            contract_type = "call"
            target_delta = 0.65
        else:
            strategy_type = "short_put"
            contract_type = "put"
            target_delta = -0.28
    elif is_bearish:
        if iv_rank < 35.0:
            strategy_type = "long_put"
            contract_type = "put"
            target_delta = -0.68
        elif iv_rank <= 55.0:
            strategy_type = "bear_put_spread"
            contract_type = "put"
            target_delta = -0.65
        else:
            strategy_type = "bear_call_spread"
            contract_type = "call"
            target_delta = 0.30
    else:
        strategy_type = "long_call"
        contract_type = "call"
        target_delta = 0.68

    # 3. Expiration Selection: 30-35 DTE Sweet Spot (Nearest Friday)
    today = datetime.date.today()
    target_dte_days = 32
    raw_expiry = today + datetime.timedelta(days=target_dte_days)
    days_to_friday = (4 - raw_expiry.weekday()) % 7
    expiry_date = raw_expiry + datetime.timedelta(days=days_to_friday)
    actual_dte = max(21, min(45, (expiry_date - today).days))
    T = actual_dte / 365.0

    # 4. Strike Selection Grid
    if underlying_price < 25:
        step = 0.50
    elif underlying_price < 100:
        step = 1.00
    elif underlying_price < 250:
        step = 2.50
    elif underlying_price < 500:
        step = 5.00
    else:
        step = 10.00

    min_k = round(underlying_price * 0.80 / step) * step
    max_k = round(underlying_price * 1.20 / step) * step
    k_range = [round(min_k + i * step, 2) for i in range(int(round((max_k - min_k) / step)) + 1)]

    # Select Primary Strike
    if strategy_type == "short_put":
        # 5-7% OTM below spot price
        ideal_strike = underlying_price * 0.94
        strike_price = round(round(ideal_strike / step) * step, 2)
    else:
        strike_price = BlackScholesEngine.find_strike_by_delta(
            S=underlying_price,
            K_range=k_range,
            T=T,
            r=0.045,
            sigma=sigma,
            target_delta=target_delta,
            option_type=contract_type
        )

    # 5. Greeks & Pricing
    greeks = BlackScholesEngine.calculate_greeks(
        S=underlying_price,
        K=strike_price,
        T=T,
        r=0.045,
        sigma=sigma,
        option_type=contract_type
    )

    premium_paid = greeks["price"]

    # If spread strategy, compute secondary leg
    short_strike_price = None
    spread_net_premium = premium_paid
    if "spread" in strategy_type:
        if strategy_type == "bull_call_spread":
            short_strike_price = round(strike_price * 1.05 / step) * step # ~Δ0.40 call
            short_greeks = BlackScholesEngine.calculate_greeks(S=underlying_price, K=short_strike_price, T=T, r=0.045, sigma=sigma, option_type="call")
            spread_net_premium = max(0.50, premium_paid - short_greeks["price"])
        elif strategy_type == "bear_call_spread":
            short_strike_price = round(strike_price * 1.05 / step) * step # hedge leg
            short_greeks = BlackScholesEngine.calculate_greeks(S=underlying_price, K=short_strike_price, T=T, r=0.045, sigma=sigma, option_type="call")
            spread_net_premium = max(0.50, premium_paid - short_greeks["price"])

    effective_premium = spread_net_premium if "spread" in strategy_type else premium_paid

    # 6. Exit Thresholds according to the Winning Edge Specification:
    # EXIT 1: Profit Target (+60% long options, +40% spreads, +50% short puts)
    # EXIT 2: Stop Loss (-35% long options, -50% spreads, 4% underlying drop on short puts)
    # EXIT 3: Time Stop (14 DTE non-negotiable)
    if "spread" in strategy_type:
        profit_target_premium = round(effective_premium * 1.40, 4) # +40%
        stop_loss_premium = round(effective_premium * 0.50, 4)     # -50%
    elif strategy_type == "short_put":
        profit_target_premium = round(effective_premium * 0.50, 4) # 50% decay captured
        stop_loss_premium = round(effective_premium * 1.80, 4)
    else:
        profit_target_premium = round(effective_premium * 1.60, 4) # +60% target
        stop_loss_premium = round(effective_premium * 0.65, 4)     # -35% stop loss

    time_stop_dte = 14 # 14 DTE hard cut-off
    occ_symbol = generate_occ_symbol(symbol=symbol, expiry_date=expiry_date, strike=strike_price, contract_type=contract_type)

    return {
        "signal_id": str(signal_id),
        "strategy_id": str(strategy_id),
        "underlying_symbol": symbol,
        "occ_symbol": occ_symbol,
        "contract_type": contract_type,
        "strategy_type": strategy_type,
        "strike_price": float(strike_price),
        "short_strike_price": float(short_strike_price) if short_strike_price else None,
        "expiry_date": expiry_date.isoformat(),
        "dte_at_entry": actual_dte,
        "underlying_price": float(underlying_price),
        "premium_paid": float(effective_premium),
        "raw_premium": float(premium_paid),
        "multiplier": 100,
        "delta_entry": float(greeks["delta"]),
        "gamma_entry": float(greeks["gamma"]),
        "theta_entry": float(greeks["theta"]),
        "vega_entry": float(greeks["vega"]),
        "iv_entry": float(sigma),
        "iv_rank_entry": float(iv_rank),
        "iv_regime": iv_regime,
        "profit_target_premium": float(profit_target_premium),
        "stop_loss_premium": float(stop_loss_premium),
        "time_stop_dte": time_stop_dte,
        "breakeven_price": float(greeks["breakeven"]),
        "greeks": greeks
    }
