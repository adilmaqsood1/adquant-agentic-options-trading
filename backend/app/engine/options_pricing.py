import math
from typing import Dict, Any, List, Optional, Tuple, Union
from scipy.stats import norm
import numpy as np
import pandas as pd

class BlackScholesEngine:
    """
    Core Analytical Black-Scholes-Merton Pricing and Greeks Engine.
    """
    
    @staticmethod
    def calculate_option_price(
        S: float,
        K: float,
        T: float,
        r: float = 0.045,
        sigma: float = 0.28,
        option_type: str = "call"
    ) -> float:
        """
        Calculates theoretical option price using the Black-Scholes formula.
        S = Underlying price
        K = Strike price
        T = Time to expiration in years (DTE / 365.0)
        r = Risk-free rate (0.045)
        sigma = Implied volatility
        option_type = 'call' or 'put'
        """
        if S <= 0 or K <= 0 or T <= 0:
            return max(0.0, S - K) if option_type.lower() == "call" else max(0.0, K - S)

        T = max(1e-5, T)
        sigma = max(0.01, sigma)

        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        if option_type.lower() == "call":
            price = S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
        else:
            price = K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

        return float(max(0.01, price))

    @staticmethod
    def calculate_greeks(
        S: float,
        K: float,
        T: float,
        r: float = 0.045,
        sigma: float = 0.28,
        option_type: str = "call"
    ) -> Dict[str, float]:
        """
        Computes analytical Greeks & Breakeven:
        - delta: Rate of price change vs underlying (dC/dS)
        - gamma: Rate of delta change (d²C/dS²)
        - theta: Daily time decay in dollars per calendar day (dC/dt / 365)
        - vega: Sensitivity to 1% IV change (dC/dsigma / 100)
        - iv: Input volatility (sigma)
        - breakeven: Strike + premium (call) or Strike - premium (put)
        """
        if S <= 0 or K <= 0 or T <= 0:
            price = max(0.0, S - K) if option_type.lower() == "call" else max(0.0, K - S)
            return {
                "price": round(price, 4),
                "delta": 1.0 if (option_type.lower() == "call" and S > K) else 0.0,
                "gamma": 0.0,
                "theta": 0.0,
                "vega": 0.0,
                "iv": float(sigma),
                "breakeven": round(K + price if option_type.lower() == "call" else K - price, 2)
            }

        T = max(1e-5, T)
        sigma = max(0.01, sigma)

        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        nd1_pdf = norm.pdf(d1)

        if option_type.lower() == "call":
            price = S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
            delta = norm.cdf(d1)
            theta = (- (S * nd1_pdf * sigma) / (2.0 * math.sqrt(T)) - r * K * math.exp(-r * T) * norm.cdf(d2)) / 365.0
            breakeven = K + price
        else:
            price = K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
            delta = norm.cdf(d1) - 1.0
            theta = (- (S * nd1_pdf * sigma) / (2.0 * math.sqrt(T)) + r * K * math.exp(-r * T) * norm.cdf(-d2)) / 365.0
            breakeven = K - price

        gamma = nd1_pdf / (S * sigma * math.sqrt(T))
        vega = (S * math.sqrt(T) * nd1_pdf) / 100.0  # per 1% change in vol

        return {
            "price": round(float(max(0.01, price)), 4),
            "premium": round(float(max(0.01, price)), 4),
            "delta": round(float(delta), 4),
            "gamma": round(float(gamma), 6),
            "theta": round(float(theta), 4),
            "vega": round(float(vega), 4),
            "iv": round(float(sigma), 4),
            "breakeven": round(float(breakeven), 2)
        }

    @staticmethod
    def find_strike_by_delta(
        S: float,
        K_range: List[float],
        T: float,
        r: float = 0.045,
        sigma: float = 0.28,
        target_delta: float = 0.70,
        option_type: str = "call"
    ) -> float:
        """
        Iterates through a candidate range of strikes and returns the strike whose Delta is closest to target_delta.
        """
        best_strike = K_range[0] if K_range else S
        best_diff = 999.0

        for k in K_range:
            g = BlackScholesEngine.calculate_greeks(S=S, K=k, T=T, r=r, sigma=sigma, option_type=option_type)
            actual_delta = abs(g["delta"])
            diff = abs(actual_delta - abs(target_delta))
            if diff < best_diff:
                best_diff = diff
                best_strike = k

        return best_strike

    @staticmethod
    def calculate_iv_rank(
        symbol: str,
        current_hv: float,
        historical_hv_series: Union[List[float], np.ndarray, pd.Series]
    ) -> Tuple[float, str]:
        """
        Takes current HV and 252-day series of daily HV values.
        Returns: (iv_rank: 0-100, regime: "low" | "medium" | "high")
        """
        if historical_hv_series is None or len(historical_hv_series) == 0:
            return 50.0, "medium"

        clean_series = pd.Series(historical_hv_series).dropna()
        if clean_series.empty:
            return 50.0, "medium"

        min_hv = float(clean_series.min())
        max_hv = float(clean_series.max())

        if max_hv - min_hv < 1e-6:
            iv_rank = 50.0
        else:
            iv_rank = ((current_hv - min_hv) / (max_hv - min_hv)) * 100.0
            iv_rank = max(0.0, min(100.0, iv_rank))

        if iv_rank < 40.0:
            regime = "low"
        elif iv_rank <= 60.0:
            regime = "medium"
        else:
            regime = "high"

        return round(iv_rank, 2), regime
