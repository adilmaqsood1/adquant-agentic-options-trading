import math
import datetime
from typing import Dict, Any, List, Optional, Tuple
from scipy.stats import norm
import numpy as np

# Risk-free interest rate benchmark (e.g. 10-year / Fed funds rate ~4.5%)
RISK_FREE_RATE = 0.045

def black_scholes_pricing(
    spot: float,
    strike: float,
    dte_days: float,
    volatility: float = 0.30,
    r: float = RISK_FREE_RATE,
    option_type: str = "call"
) -> Dict[str, float]:
    """
    Computes theoretical option price and analytical Greeks using the Black-Scholes-Merton model.
    """
    if spot <= 0 or strike <= 0 or dte_days <= 0:
        return {
            "price": max(0.0, spot - strike) if option_type.lower() == "call" else max(0.0, strike - spot),
            "delta": 1.0 if (option_type.lower() == "call" and spot > strike) else 0.0,
            "gamma": 0.0,
            "theta": 0.0,
            "vega": 0.0,
            "iv": volatility
        }

    T = max(1e-4, dte_days / 365.0)
    sigma = max(0.05, min(3.0, volatility))

    d1 = (math.log(spot / strike) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    nd1_pdf = norm.pdf(d1)

    if option_type.lower() == "call":
        price = spot * norm.cdf(d1) - strike * math.exp(-r * T) * norm.cdf(d2)
        delta = norm.cdf(d1)
        theta = (- (spot * nd1_pdf * sigma) / (2 * math.sqrt(T)) - r * strike * math.exp(-r * T) * norm.cdf(d2)) / 365.0
    else:
        price = strike * math.exp(-r * T) * norm.cdf(-d2) - spot * norm.cdf(-d1)
        delta = norm.cdf(d1) - 1.0
        theta = (- (spot * nd1_pdf * sigma) / (2 * math.sqrt(T)) + r * strike * math.exp(-r * T) * norm.cdf(-d2)) / 365.0

    gamma = nd1_pdf / (spot * sigma * math.sqrt(T))
    vega = (spot * math.sqrt(T) * nd1_pdf) / 100.0 # per 1% vol change

    return {
        "price": round(max(0.01, price), 2),
        "delta": round(delta, 3),
        "gamma": round(gamma, 4),
        "theta": round(theta, 3),
        "vega": round(vega, 3),
        "iv": round(sigma * 100.0, 1)
    }


def generate_occ_symbol(symbol: str, expiry_date: datetime.date, strike: float, option_type: str = "C") -> str:
    """
    Generates standard OCC (Options Clearing Corporation) symbol:
    Root (up to 6 chars) + YYMMDD + C/P + 8-digit strike price (strike * 1000).
    Example: AAPL, 2026-09-18, Strike 230 Call -> AAPL260918C00230000
    """
    root = symbol.upper().replace("/", "")
    expiry_str = expiry_date.strftime("%y%m%d")
    type_char = "C" if option_type.upper().startswith("C") else "P"
    strike_int = int(round(strike * 1000))
    strike_str = f"{strike_int:08d}"
    return f"{root}{expiry_str}{type_char}{strike_str}"


def select_optimal_option_contract(
    symbol: str,
    spot_price: float,
    signal_type: str = "BUY",
    target_delta: float = 0.70,
    target_dte: int = 35,
    allocated_capital: float = 25000.0,
    historical_vol: float = 0.32
) -> Dict[str, Any]:
    """
    Selects the optimal In-The-Money / Near-The-Money options contract for a strategy trade signal.
    """
    clean_sym = symbol.upper().replace("/", "")
    today = datetime.date.today()
    
    # 1. Target Expiration Date (Next Friday closest to 30-45 DTE)
    raw_expiry = today + datetime.timedelta(days=target_dte)
    days_to_friday = (4 - raw_expiry.weekday()) % 7
    expiry_date = raw_expiry + datetime.timedelta(days=days_to_friday)
    actual_dte = (expiry_date - today).days

    # 2. Select Strike Price for Target Delta (~0.70 ITM Call for Bullish signals)
    is_call = "BUY" in signal_type.upper() or "LONG" in signal_type.upper()
    opt_type = "call" if is_call else "put"
    
    spot_price = float(spot_price)
    allocated_capital = float(allocated_capital)
    historical_vol = float(historical_vol)

    # Strike interval rounding ($0.50, $1.00, $2.50, or $5.00 depending on price)
    if spot_price < 25:
        strike_step = 0.50
    elif spot_price < 100:
        strike_step = 1.00
    elif spot_price < 250:
        strike_step = 2.50
    else:
        strike_step = 5.00

    if is_call:
        # ITM call at ~0.70 Delta is typically 3-5% below spot
        ideal_strike = spot_price * 0.96
        strike_price = float(round(round(ideal_strike / strike_step) * strike_step, 2))
    else:
        # ITM put at ~0.70 Delta is typically 3-5% above spot
        ideal_strike = spot_price * 1.04
        strike_price = float(round(round(ideal_strike / strike_step) * strike_step, 2))

    # 3. Calculate Greeks & Premium
    greeks = black_scholes_pricing(
        spot=spot_price,
        strike=strike_price,
        dte_days=actual_dte,
        volatility=historical_vol,
        option_type=opt_type
    )

    contract_premium = float(greeks["price"])
    cost_per_contract = float(contract_premium * 100.0) # 1 contract = 100 shares

    # 4. Sizing: Calculate number of whole contracts
    num_contracts = int(max(1, int(allocated_capital / cost_per_contract))) if cost_per_contract > 0 else 1
    total_committed = float(round(num_contracts * cost_per_contract, 2))

    occ_sym = generate_occ_symbol(
        symbol=clean_sym,
        expiry_date=expiry_date,
        strike=strike_price,
        option_type="C" if is_call else "P"
    )

    breakeven = float(round(strike_price + contract_premium if is_call else strike_price - contract_premium, 2))
    leverage_mult = float(round((greeks["delta"] * spot_price) / max(0.1, contract_premium), 2))

    return {
        "asset_class": "option",
        "underlying_symbol": clean_sym,
        "option_symbol": occ_sym,
        "option_type": opt_type,
        "strike_price": float(strike_price),
        "expiration_date": expiry_date.isoformat(),
        "dte": int(actual_dte),
        "contracts": int(num_contracts),
        "contract_premium": float(contract_premium),
        "cost_per_contract": float(cost_per_contract),
        "total_allocated": float(total_committed),
        "underlying_price": float(spot_price),
        "breakeven_price": float(breakeven),
        "leverage_multiplier": float(leverage_mult),
        "greeks": {
            "price": float(greeks["price"]),
            "delta": float(greeks["delta"]),
            "gamma": float(greeks["gamma"]),
            "theta": float(greeks["theta"]),
            "vega": float(greeks["vega"]),
            "iv": float(greeks["iv"])
        }
    }

