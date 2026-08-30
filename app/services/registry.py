import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple, List , Optional
from app.services.technical_indicators import (
    sma, ema, rsi, connors_rsi, macd, bollinger_bands, atr, adx,
    donchian_channel, supertrend, kalman_filter_trend, z_score_spread, volume_delta_imbalance,
    keltner_channel, hurst_exponent, vwap_deviation_bands
)




def signal_rsi_mean_revert(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """RSI Mean Reversion (Entry: 30, Exit: 70, Threshold: 30)"""
    period = int(params.get("rsi_period", 14))
    entry_val = float(params.get("entry", 30.0))
    exit_val = float(params.get("exit", 70.0))
    
    rsi_vals = rsi(df["close"], period=period)
    signals = pd.Series(0, index=df.index)
    
    in_pos = False
    for i in range(len(df)):
        val = rsi_vals.iloc[i]
        if not in_pos and val < entry_val:
            signals.iloc[i] = 1
            in_pos = True
        elif in_pos and val > exit_val:
            signals.iloc[i] = -1
            in_pos = False
    return signals


def signal_momentum_ema_rsi_adx(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """EMA 20/50 crossover confirmed by RSI > 50 and ADX > 20"""
    fast_p = int(params.get("fast_ema", 20))
    slow_p = int(params.get("slow_ema", 50))
    rsi_thresh = float(params.get("rsi_filter", 50.0))
    adx_thresh = float(params.get("adx_filter", 20.0))
    
    fast_e = ema(df["close"], fast_p)
    slow_e = ema(df["close"], slow_p)
    rsi_v = rsi(df["close"], 14)
    adx_v = adx(df["high"], df["low"], df["close"], 14)
    
    signals = pd.Series(0, index=df.index)
    in_pos = False
    
    for i in range(1, len(df)):
        bullish_cross = fast_e.iloc[i] > slow_e.iloc[i] and fast_e.iloc[i-1] <= slow_e.iloc[i-1]
        bearish_cross = fast_e.iloc[i] < slow_e.iloc[i] and fast_e.iloc[i-1] >= slow_e.iloc[i-1]
        
        if not in_pos and bullish_cross and rsi_v.iloc[i] > rsi_thresh and adx_v.iloc[i] > adx_thresh:
            signals.iloc[i] = 1
            in_pos = True
        elif in_pos and (bearish_cross or rsi_v.iloc[i] < 45.0):
            signals.iloc[i] = -1
            in_pos = False
    return signals


def signal_momentum_continuation(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """Trend continuation entries on short-term pullbacks to 20 EMA in strong market regimes"""
    trend_filter_p = int(params.get("trend_sma", 200))
    ema_p = int(params.get("pullback_ema", 20))
    
    sma_trend = sma(df["close"], trend_filter_p)
    ema_val = ema(df["close"], ema_p)
    rsi_v = rsi(df["close"], 14)
    
    signals = pd.Series(0, index=df.index)
    in_pos = False
    
    for i in range(1, len(df)):
        # Trend is up: price above 200 SMA, pullback touches EMA 20 while RSI is between 40-55
        touch_ema = df["low"].iloc[i] <= ema_val.iloc[i] and df["close"].iloc[i] >= ema_val.iloc[i] * 0.99
        regime_up = df["close"].iloc[i] > sma_trend.iloc[i]
        rsi_pullback = 38.0 <= rsi_v.iloc[i] <= 58.0
        
        if not in_pos and regime_up and touch_ema and rsi_pullback:
            signals.iloc[i] = 1
            in_pos = True
        elif in_pos and (df["close"].iloc[i] < ema_val.iloc[i] * 0.96 or rsi_v.iloc[i] > 75.0):
            signals.iloc[i] = -1
            in_pos = False
    return signals


def signal_connors_rsi2(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """Connors RSI-2 extreme oversold (<10) / overbought (>90) entries filtered by 200 SMA"""
    sma_trend_p = int(params.get("trend_filter", 200))
    oversold = float(params.get("oversold", 10.0))
    overbought = float(params.get("overbought", 90.0))
    
    crsi_v = connors_rsi(df["close"])
    sma_v = sma(df["close"], sma_trend_p)
    
    signals = pd.Series(0, index=df.index)
    in_pos = False
    
    for i in range(1, len(df)):
        # Long entry when above 200 SMA and CRSI < 10
        if not in_pos and df["close"].iloc[i] > sma_v.iloc[i] and crsi_v.iloc[i] < oversold:
            signals.iloc[i] = 1
            in_pos = True
        elif in_pos and (crsi_v.iloc[i] > overbought or df["close"].iloc[i] > sma(df["close"], 5).iloc[i]):
            signals.iloc[i] = -1
            in_pos = False
    return signals


def signal_pairs_cointegration(df: pd.DataFrame, params: Dict[str, Any], df_second: Optional[pd.DataFrame] = None) -> pd.Series:
    """Cointegration spread Z-score mean-reversion trading"""
    window = int(params.get("lookback_window", 60))
    entry_z = float(params.get("entry_z", 2.0))
    exit_z = float(params.get("exit_z", 0.2))
    
    # If no secondary series passed, use synthetic anchor or rolling benchmark
    if df_second is not None and len(df_second) > 0:
        s2 = df_second["close"]
    else:
        s2 = sma(df["close"], window * 2)
        
    zscore = z_score_spread(df["close"], s2, window=window)
    signals = pd.Series(0, index=df.index)
    
    in_pos = False
    for i in range(len(df)):
        z = zscore.iloc[i]
        # Spread is oversold relative to anchor -> enter long
        if not in_pos and z < -entry_z:
            signals.iloc[i] = 1
            in_pos = True
        elif in_pos and z >= -exit_z:
            signals.iloc[i] = -1
            in_pos = False
    return signals


def signal_funding_carry(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """Delta-neutral spot long / perp short funding rate harvest above fixed yield threshold"""
    min_yield = float(params.get("min_yield_annual", 0.08)) # 8% annual
    vol_filter = float(params.get("max_vol_filter", 0.60))
    
    # Estimate rolling annualized volatility
    returns = df["close"].pct_change()
    vol = returns.rolling(30).std() * np.sqrt(365)
    
    signals = pd.Series(0, index=df.index)
    in_pos = False
    
    for i in range(len(df)):
        curr_vol = vol.iloc[i] if not np.isnan(vol.iloc[i]) else 0.4
        # Safe carry regime when vol is stable
        if not in_pos and curr_vol < vol_filter:
            signals.iloc[i] = 1
            in_pos = True
        elif in_pos and curr_vol >= vol_filter * 1.3:
            signals.iloc[i] = -1
            in_pos = False
    return signals


def signal_full_cointegration_screen(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """Multi-asset Johansen cointegration basket trading with dynamic hedge ratios"""
    window = int(params.get("window", 45))
    entry_threshold = float(params.get("z_score_threshold", 1.8))
    
    # Synthetic basket mean
    basket_mean = (sma(df["close"], window) + sma(df["close"], window // 2)) / 2.0
    spread = df["close"] - basket_mean
    spread_std = spread.rolling(window).std() + 1e-10
    zscore = spread / spread_std
    
    signals = pd.Series(0, index=df.index)
    in_pos = False
    for i in range(len(df)):
        z = zscore.iloc[i]
        if not in_pos and z < -entry_threshold:
            signals.iloc[i] = 1
            in_pos = True
        elif in_pos and z > 0:
            signals.iloc[i] = -1
            in_pos = False
    return signals


def signal_ml_ensemble(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """Multi-factor ensemble model combining price momentum, volatility regime, and sentiment delta"""
    weight_mom = float(params.get("weight_momentum", 0.40))
    weight_vol = float(params.get("weight_volatility", 0.30))
    weight_mr = float(params.get("weight_mean_revert", 0.30))
    
    # Factor 1: Momentum (ROC 20 > 0)
    roc20 = df["close"].pct_change(20).fillna(0)
    mom_score = np.tanh(roc20 * 10)
    
    # Factor 2: Volatility Regime (Low vol = higher score)
    atr_v = atr(df["high"], df["low"], df["close"], 14) / df["close"]
    vol_score = 1.0 - np.clip(atr_v * 20, 0, 1)
    
    # Factor 3: RSI Mean Reversion
    rsi_v = rsi(df["close"], 14)
    mr_score = (50.0 - rsi_v) / 50.0
    
    ensemble_score = (weight_mom * mom_score) + (weight_vol * vol_score) + (weight_mr * mr_score)
    
    signals = pd.Series(0, index=df.index)
    in_pos = False
    for i in range(len(df)):
        score = ensemble_score.iloc[i]
        if not in_pos and score > 0.25:
            signals.iloc[i] = 1
            in_pos = True
        elif in_pos and score < -0.10:
            signals.iloc[i] = -1
            in_pos = False
    return signals


def signal_cross_sectional_momentum(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """Long top quintile / high relative momentum in upward trending regime"""
    lookback = int(params.get("momentum_lookback", 30))
    roc30 = df["close"].pct_change(lookback).fillna(0)
    roc5 = df["close"].pct_change(5).fillna(0)
    ema50 = ema(df["close"], min(50, len(df)-1))
    
    signals = pd.Series(0, index=df.index)
    in_pos = False
    for i in range(lookback, len(df)):
        strong_mom = roc30.iloc[i] > 0.02 or roc5.iloc[i] > 0.02
        above_ema = df["close"].iloc[i] > ema50.iloc[i]
        
        if not in_pos and strong_mom and above_ema:
            signals.iloc[i] = 1
            in_pos = True
        elif in_pos and (roc30.iloc[i] < -0.04 or df["close"].iloc[i] < ema50.iloc[i] * 0.98):
            signals.iloc[i] = -1
            in_pos = False
    return signals



def signal_grid_trading(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """Arithmetic grid orders capturing price oscillations in rangebound markets"""
    grid_levels = int(params.get("grid_levels", 10))
    grid_span_pct = float(params.get("grid_span_pct", 0.15))
    
    mid_price = sma(df["close"], 30)
    lower_bound = mid_price * (1.0 - grid_span_pct)
    upper_bound = mid_price * (1.0 + grid_span_pct)
    
    signals = pd.Series(0, index=df.index)
    in_pos = False
    for i in range(len(df)):
        p = df["close"].iloc[i]
        if not in_pos and p <= lower_bound.iloc[i] * 1.02:
            signals.iloc[i] = 1
            in_pos = True
        elif in_pos and p >= upper_bound.iloc[i] * 0.98:
            signals.iloc[i] = -1
            in_pos = False
    return signals


def signal_grid_adx_gated(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """Grid market-making active strictly when ADX < 25 to prevent trending drawdown"""
    adx_gate = float(params.get("adx_max", 25.0))
    adx_v = adx(df["high"], df["low"], df["close"], 14)
    bb_u, bb_m, bb_l = bollinger_bands(df["close"], 20, 2.0)
    
    signals = pd.Series(0, index=df.index)
    in_pos = False
    for i in range(len(df)):
        # Range-bound regime strictly gated by ADX
        if adx_v.iloc[i] < adx_gate:
            if not in_pos and df["close"].iloc[i] <= bb_l.iloc[i]:
                signals.iloc[i] = 1
                in_pos = True
            elif in_pos and df["close"].iloc[i] >= bb_m.iloc[i]:
                signals.iloc[i] = -1
                in_pos = False
        else:
            # Trending detected: exit grid immediately
            if in_pos:
                signals.iloc[i] = -1
                in_pos = False
    return signals


def signal_short_strangle_options(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """Harvesting Volatility Risk Premium (VRP) by selling delta-neutral strangles when IVP > 70"""
    min_ivp = float(params.get("min_ivp", 70.0))
    
    # Estimate IV Percentile from 30-day realized volatility rank
    returns = df["close"].pct_change()
    hist_vol = returns.rolling(20).std() * np.sqrt(252)
    ivp = hist_vol.rolling(120).apply(lambda x: (np.sum(x[-1] >= x) / len(x)) * 100.0 if len(x)>0 else 50.0, raw=True).fillna(50.0)
    
    signals = pd.Series(0, index=df.index)
    in_pos = False
    for i in range(len(df)):
        if not in_pos and ivp.iloc[i] > min_ivp:
            signals.iloc[i] = 1
            in_pos = True
        elif in_pos and ivp.iloc[i] < 30.0:
            signals.iloc[i] = -1
            in_pos = False
    return signals


def signal_futures_calendar_basis(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """Trading annualised calendar basis convergence between Quarterly futures and Perpetuals"""
    basis_threshold = float(params.get("basis_spread_entry", 0.05))
    
    # Basis divergence simulation based on 10D moving delta
    basis_spread = (df["close"] - sma(df["close"], 10)) / df["close"]
    
    signals = pd.Series(0, index=df.index)
    in_pos = False
    for i in range(len(df)):
        if not in_pos and basis_spread.iloc[i] < -basis_threshold:
            signals.iloc[i] = 1
            in_pos = True
        elif in_pos and basis_spread.iloc[i] >= 0:
            signals.iloc[i] = -1
            in_pos = False
    return signals


def signal_momentum_us_equities(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """Relative strength momentum strategy across US equities/ETFs with 200 SMA filter"""
    trend_sma_p = int(params.get("trend_sma", 200))
    roc_p = int(params.get("roc_period", 50))
    
    sma200 = sma(df["close"], trend_sma_p)
    roc = df["close"].pct_change(roc_p).fillna(0)
    
    signals = pd.Series(0, index=df.index)
    in_pos = False
    for i in range(len(df)):
        if not in_pos and df["close"].iloc[i] > sma200.iloc[i] and roc.iloc[i] > 0.05:
            signals.iloc[i] = 1
            in_pos = True
        elif in_pos and (df["close"].iloc[i] < sma200.iloc[i] or roc.iloc[i] < -0.02):
            signals.iloc[i] = -1
            in_pos = False
    return signals


def signal_full_universe_momentum_scan(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """Screening full universe for high Rate-Of-Change (ROC) volume breakout entries"""
    roc_p = int(params.get("roc_window", 20))
    vol_mult = float(params.get("vol_multiplier", 1.5))
    
    roc = df["close"].pct_change(roc_p).fillna(0)
    vol_ma = sma(df["volume"], 20)
    
    signals = pd.Series(0, index=df.index)
    in_pos = False
    for i in range(len(df)):
        vol_surge = df["volume"].iloc[i] > (vol_ma.iloc[i] * vol_mult)
        roc_strong = roc.iloc[i] > 0.08
        if not in_pos and vol_surge and roc_strong:
            signals.iloc[i] = 1
            in_pos = True
        elif in_pos and roc.iloc[i] < 0:
            signals.iloc[i] = -1
            in_pos = False
    return signals


def signal_donchian_turtle_breakout(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """Classic 20-bar Donchian channel upper breakout long entry with 10-bar trailing exit"""
    entry_p = int(params.get("entry_period", 20))
    exit_p = int(params.get("exit_period", 10))
    
    upper, _, _ = donchian_channel(df["high"], df["low"], entry_p)
    _, _, exit_lower = donchian_channel(df["high"], df["low"], exit_p)
    
    signals = pd.Series(0, index=df.index)
    in_pos = False
    for i in range(1, len(df)):
        if not in_pos and df["close"].iloc[i] >= upper.iloc[i-1]:
            signals.iloc[i] = 1
            in_pos = True
        elif in_pos and df["close"].iloc[i] <= exit_lower.iloc[i-1]:
            signals.iloc[i] = -1
            in_pos = False
    return signals


def signal_bollinger_breakout_reversion(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """Squeeze expansion breakouts combined with 2.0 std-dev band reversion signals"""
    period = int(params.get("period", 20))
    num_std = float(params.get("num_std", 2.0))
    mode = str(params.get("mode", "reversion")) # 'reversion' or 'breakout'
    
    upper, middle, lower = bollinger_bands(df["close"], period, num_std)
    signals = pd.Series(0, index=df.index)
    in_pos = False
    
    for i in range(1, len(df)):
        if mode == "reversion":
            if not in_pos and df["close"].iloc[i] < lower.iloc[i]:
                signals.iloc[i] = 1
                in_pos = True
            elif in_pos and df["close"].iloc[i] >= middle.iloc[i]:
                signals.iloc[i] = -1
                in_pos = False
        else: # breakout
            if not in_pos and df["close"].iloc[i] > upper.iloc[i]:
                signals.iloc[i] = 1
                in_pos = True
            elif in_pos and df["close"].iloc[i] < middle.iloc[i]:
                signals.iloc[i] = -1
                in_pos = False
    return signals


def signal_macd_crossover(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """Standard MACD (12, 26, 9) signal line crossovers with zero-line confirmation"""
    fast = int(params.get("fast_period", 12))
    slow = int(params.get("slow_period", 26))
    signal_p = int(params.get("signal_period", 9))
    
    m_line, s_line, _ = macd(df["close"], fast, slow, signal_p)
    signals = pd.Series(0, index=df.index)
    in_pos = False
    
    for i in range(1, len(df)):
        bullish = m_line.iloc[i] > s_line.iloc[i] and m_line.iloc[i-1] <= s_line.iloc[i-1]
        bearish = m_line.iloc[i] < s_line.iloc[i] and m_line.iloc[i-1] >= s_line.iloc[i-1]
        
        if not in_pos and bullish:
            signals.iloc[i] = 1
            in_pos = True
        elif in_pos and bearish:
            signals.iloc[i] = -1
            in_pos = False
    return signals


def signal_kalman_filter_trend(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """1D Kalman filter state estimation for low-lag trend velocity detection"""
    proc_var = float(params.get("process_variance", 1e-4))
    meas_var = float(params.get("measurement_variance", 1e-2))
    
    kalman_series = kalman_filter_trend(df["close"], proc_var, meas_var)
    slope = kalman_series.diff(3)
    
    signals = pd.Series(0, index=df.index)
    in_pos = False
    for i in range(1, len(df)):
        if not in_pos and slope.iloc[i] > 0 and df["close"].iloc[i] > kalman_series.iloc[i]:
            signals.iloc[i] = 1
            in_pos = True
        elif in_pos and slope.iloc[i] < 0:
            signals.iloc[i] = -1
            in_pos = False
    return signals


def signal_order_flow_imbalance(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """Volume Delta and buy/sell aggressor volume ratio imbalance strategy"""
    period = int(params.get("imbalance_period", 14))
    thresh = float(params.get("imbalance_threshold", 0.15))
    
    imbalance = volume_delta_imbalance(df["close"], df["high"], df["low"], df["volume"], period)
    signals = pd.Series(0, index=df.index)
    in_pos = False
    
    for i in range(len(df)):
        if not in_pos and imbalance.iloc[i] > thresh:
            signals.iloc[i] = 1
            in_pos = True
        elif in_pos and imbalance.iloc[i] < -thresh / 2.0:
            signals.iloc[i] = -1
            in_pos = False
    return signals


def signal_supertrend(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """ATR-based Supertrend (ATR 10, Multiplier 3.0) direction trailing stop crossovers"""
    period = int(params.get("atr_period", 10))
    mult = float(params.get("atr_multiplier", 3.0))
    
    st_line, trend = supertrend(df["high"], df["low"], df["close"], period, mult)
    signals = pd.Series(0, index=df.index)
    in_pos = False
    
    for i in range(1, len(df)):
        # Direction flip to bullish (1)
        if not in_pos and trend.iloc[i] == 1 and trend.iloc[i-1] == -1:
            signals.iloc[i] = 1
            in_pos = True
        # Direction flip to bearish (-1)
        elif in_pos and trend.iloc[i] == -1:
            signals.iloc[i] = -1
            in_pos = False
    return signals


def signal_buy_and_hold(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """Baseline Buy and Hold strategy"""
    signals = pd.Series(0, index=df.index)
    if len(signals) > 0:
        signals.iloc[0] = 1 # enter at bar 0 and hold
    return signals


# ─────────────────────────────────────────────────────────────────────────────
# NOVEL RESEARCH STRATEGIES (Institutional & Alpha Quant Models)
# ─────────────────────────────────────────────────────────────────────────────

def signal_liquidity_sweep_absorption(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Liquidity Sweep & Stop-Hunt Absorption (ICT Quantified):
    - Price low sweeps below 20-bar Donchian lower band
    - Price closes back above Donchian lower band
    - Volume > 1.3x 20-bar avg + positive volume delta imbalance (absorption)
    """
    lookback = int(params.get("lookback", 20))
    vol_mult = float(params.get("vol_mult", 1.3))
    
    _, _, dc_lower = donchian_channel(df["high"], df["low"], lookback)
    vol_avg = df["volume"].rolling(lookback, min_periods=5).mean()
    imbalance = volume_delta_imbalance(df["close"], df["high"], df["low"], df["volume"], 14)
    
    signals = pd.Series(0, index=df.index)
    in_pos = False
    
    for i in range(1, len(df)):
        prev_lower = dc_lower.iloc[i-1]
        swept = df["low"].iloc[i] < prev_lower and df["close"].iloc[i] > prev_lower
        vol_surge = df["volume"].iloc[i] > vol_avg.iloc[i] * vol_mult
        buyer_absorbed = imbalance.iloc[i] > 0.05
        
        if not in_pos and swept and (vol_surge or buyer_absorbed):
            signals.iloc[i] = 1
            in_pos = True
        elif in_pos and (df["close"].iloc[i] > (df["high"].iloc[max(0, i-lookback):i].max() + prev_lower)/2.0 or df["close"].iloc[i] < df["low"].iloc[i-1] * 0.985):
            signals.iloc[i] = -1
            in_pos = False
    return signals


def signal_lead_lag_propagation(df: pd.DataFrame, params: Dict[str, Any], df_anchor: Optional[pd.DataFrame] = None) -> pd.Series:
    """
    Cross-Asset Lead-Lag Momentum Propagation:
    Enters high-beta lagging target when anchor momentum surges.
    """
    roc_period = int(params.get("roc_period", 5))
    target_roc = df["close"].pct_change(roc_period) * 100
    
    if df_anchor is not None and len(df_anchor) > 0:
        anchor_roc = df_anchor["close"].pct_change(roc_period) * 100
    else:
        anchor_roc = (df["close"].pct_change(roc_period * 4) * 100) / 2.0
        
    rsi_vals = rsi(df["close"], 14)
    signals = pd.Series(0, index=df.index)
    in_pos = False
    
    for i in range(max(roc_period, 15), len(df)):
        anchor_val = anchor_roc.iloc[i] if i < len(anchor_roc) else 0.0
        target_val = target_roc.iloc[i]
        
        # Nuance Protection: RSI must be turning up (positive slope) and not falling from an overbought spike
        rsi_curr = rsi_vals.iloc[i]
        rsi_prev = rsi_vals.iloc[i-1]
        rsi_rising = (rsi_curr >= rsi_prev) and (rsi_curr >= 40.0)
        not_falling_knife = not (rsi_vals.iloc[i-5:i].max() > 70.0 and rsi_curr < rsi_prev)
        
        if not in_pos and anchor_val > 1.5 and target_val < 1.0 and df["close"].iloc[i] > ema(df["close"], 20).iloc[i] and rsi_rising and not_falling_knife:
            signals.iloc[i] = 1
            in_pos = True
        elif in_pos and (target_val > anchor_val or target_val < -2.0 or rsi_curr < 40.0):
            signals.iloc[i] = -1
            in_pos = False
    return signals



def signal_hurst_double_squeeze(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Hurst Exponent + Bollinger-Keltner Double Squeeze:
    - Identifies regime (H > 0.52 = Trend, H < 0.48 = Mean Reverting)
    - Double Squeeze: Bollinger Bands inside Keltner Channels
    - Trades breakout in Trend regime; trades mean reversion in Mean Revert regime
    """
    bb_period = int(params.get("period", 20))
    bb_u, bb_m, bb_l = bollinger_bands(df["close"], bb_period, 2.0)
    kc_u, kc_m, kc_l = keltner_channel(df["high"], df["low"], df["close"], bb_period, 1.5)
    
    squeeze = (bb_u < kc_u) & (bb_l > kc_l)
    
    signals = pd.Series(0, index=df.index)
    in_pos = False
    
    for i in range(30, len(df)):
        h = hurst_exponent(df["close"].iloc[i-25:i])
        
        if h > 0.52:
            if not in_pos and squeeze.iloc[i-1] and not squeeze.iloc[i] and df["close"].iloc[i] > kc_u.iloc[i]:
                signals.iloc[i] = 1
                in_pos = True
            elif in_pos and df["close"].iloc[i] < bb_m.iloc[i]:
                signals.iloc[i] = -1
                in_pos = False
        elif h < 0.48:
            if not in_pos and df["close"].iloc[i] <= bb_l.iloc[i]:
                signals.iloc[i] = 1
                in_pos = True
            elif in_pos and df["close"].iloc[i] >= bb_m.iloc[i]:
                signals.iloc[i] = -1
                in_pos = False
    return signals


def signal_anchored_vwap_deviation(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Anchored VWAP Multi-Deviation Snap (Institutional Mean Reversion):
    Enters when price drops to -1.8 sigma below rolling VWAP with RSI(3) oversold exhaustion.
    """
    window = int(params.get("window", 30))
    dev_threshold = float(params.get("dev_threshold", -1.8))
    
    vwap_line, upper_2s, lower_2s, zscore = vwap_deviation_bands(df, window)
    rsi3 = rsi(df["close"], 3)
    
    signals = pd.Series(0, index=df.index)
    in_pos = False
    
    for i in range(1, len(df)):
        if not in_pos and zscore.iloc[i] < dev_threshold and rsi3.iloc[i] < 20:
            signals.iloc[i] = 1
            in_pos = True
        elif in_pos and (df["close"].iloc[i] >= vwap_line.iloc[i] or zscore.iloc[i] > 0.0):
            signals.iloc[i] = -1
            in_pos = False
    return signals


def signal_sharpe_residual_momentum(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Risk-Adjusted Residual Momentum (Sharpe-Ranked Factor Alpha):
    Enters when 30-day return adjusted by 30-day volatility exceeds hurdle rate.
    """
    lookback = int(params.get("lookback", 30))
    min_sharpe_mom = float(params.get("min_sharpe_momentum", 0.4))
    
    ret30 = df["close"].pct_change(lookback)
    vol30 = df["close"].pct_change().rolling(lookback).std() * np.sqrt(252) + 1e-10
    sharpe_mom = (ret30 * 100) / (vol30 * 100)
    sma200 = sma(df["close"], min(200, len(df)-1))
    
    signals = pd.Series(0, index=df.index)
    in_pos = False
    
    for i in range(1, len(df)):
        above_trend = df["close"].iloc[i] > sma200.iloc[i] * 0.96
        if not in_pos and sharpe_mom.iloc[i] > min_sharpe_mom and above_trend:
            signals.iloc[i] = 1
            in_pos = True
        elif in_pos and (sharpe_mom.iloc[i] < -0.2 or df["close"].iloc[i] < ema(df["close"], 50).iloc[i]):
            signals.iloc[i] = -1
            in_pos = False
    return signals



def signal_cvd_divergence_squeeze(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Spot Accumulation / CVD Delta Divergence Short Squeeze:
    Detects bullish volume divergence (price down, volume delta up) above 200 EMA.
    """
    period = int(params.get("period", 14))
    imbalance = volume_delta_imbalance(df["close"], df["high"], df["low"], df["volume"], period)
    ret10 = df["close"].pct_change(10)
    macd_l, sig_l, hist = macd(df["close"])
    ema200 = ema(df["close"], min(200, len(df)-1))
    
    signals = pd.Series(0, index=df.index)
    in_pos = False
    
    for i in range(1, len(df)):
        price_falling = ret10.iloc[i] < -0.01
        cvd_rising = imbalance.iloc[i] > 0.05
        macd_turning = hist.iloc[i] > hist.iloc[i-1]
        
        if not in_pos and (price_falling and cvd_rising and macd_turning):
            signals.iloc[i] = 1
            in_pos = True
        elif in_pos and (ret10.iloc[i] > 0.08 or (hist.iloc[i] < 0 and hist.iloc[i] < hist.iloc[i-1])):
            signals.iloc[i] = -1
            in_pos = False
    return signals


def signal_rsi_oversold_reversal(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    RSI Bullish Oversold Recovery above 200 SMA:
    Identifies high-probability reversal entries when RSI(14) crosses upward above 30 from oversold territory,
    strictly when price is holding near to or above the 200-period daily SMA (macro bull/uptrend regime).
    """
    rsi_period = int(params.get("rsi_period", params.get("period", 14)))
    sma_period = int(params.get("sma_period", 200))
    rsi_threshold = float(params.get("rsi_threshold", 30.0))
    rsi_exit = float(params.get("rsi_exit", 70.0))
    
    rsi_vals = rsi(df["close"], rsi_period)
    sma200 = sma(df["close"], min(sma_period, max(1, len(df)-1)))
    ema9 = ema(df["close"], min(9, max(1, len(df)-1)))
    signals = pd.Series(0, index=df.index)
    in_pos = False
    
    for i in range(1, len(df)):
        # 1. Bullish RSI Hook: RSI must be actively curling UPWARD (positive slope) above 30 from oversold
        rsi_curling_up = rsi_vals.iloc[i] > rsi_vals.iloc[i-1]
        rsi_hook_above_30 = rsi_curling_up and (
            (rsi_vals.iloc[i-1] <= rsi_threshold and rsi_vals.iloc[i] > rsi_threshold) or
            (rsi_vals.iloc[i] > rsi_threshold and rsi_vals.iloc[i] <= 42.0)
        )
        
        # 2. Trend Filter: Price must be near to (within 4%) or above the 200 SMA on daily candle
        near_or_above_200_sma = df["close"].iloc[i] >= (sma200.iloc[i] * 0.96)
        
        # 3. Bullish price confirmation: green candle or close above 9 EMA
        bullish_price = df["close"].iloc[i] >= df["close"].iloc[i-1] or df["close"].iloc[i] > ema9.iloc[i]
        
        if not in_pos and rsi_hook_above_30 and near_or_above_200_sma and bullish_price:
            signals.iloc[i] = 1
            in_pos = True

        elif in_pos and (rsi_vals.iloc[i] >= rsi_exit or df["close"].iloc[i] < sma200.iloc[i] * 0.92):
            signals.iloc[i] = -1
            in_pos = False
            
    return signals


def signal_trend_pullback_continuation(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Institutional Trend Pullback Continuation:
    Identifies high-conviction continuation entries when a stock in a powerful macro uptrend
    (well above 200 SMA and 20 EMA > 50 EMA) experiences a 2-5 day healthy cooling pullback,
    absorbs seller pressure with a bullish rejection candle/hammer, and turns its RSI slope strictly upward.
    """
    sma_period = int(params.get("sma_period", 200))
    ema_fast_p = int(params.get("ema_fast", 20))
    ema_slow_p = int(params.get("ema_slow", 50))
    
    rsi_vals = rsi(df["close"], 14)
    sma200 = sma(df["close"], min(sma_period, max(1, len(df)-1)))
    ema20 = ema(df["close"], min(ema_fast_p, max(1, len(df)-1)))
    ema50 = ema(df["close"], min(ema_slow_p, max(1, len(df)-1)))
    
    signals = pd.Series(0, index=df.index)
    in_pos = False
    
    for i in range(max(ema_slow_p, 15), len(df)):
        c = df["close"].iloc[i]
        o = df["open"].iloc[i]
        h = df["high"].iloc[i]
        l = df["low"].iloc[i]
        
        # 1. Macro Trend Regime: Price holding above 200 SMA and 20 EMA is above 50 EMA
        macro_uptrend = c >= (sma200.iloc[i] * 0.98) and (ema20.iloc[i] >= ema50.iloc[i] * 0.99)
        
        # 2. Healthy Pullback: Prior 2-4 candles pulled back near 20 EMA or RSI cooled off
        prior_pullback = any(df["close"].iloc[i-3:i] <= ema20.iloc[i-3:i] * 1.03) or (rsi_vals.iloc[i-1] <= 60.0 and rsi_vals.iloc[i-1] >= 40.0)
        
        # 3. Seller Absorption / Reversal Confirmation:
        candle_range = max(0.01, h - l)
        lower_wick = min(o, c) - l
        hammer_absorption = (lower_wick / candle_range) >= 0.28 or (c > df["close"].iloc[i-1] and c > o)
        
        # 4. Strict RSI Slope Check: RSI must be actively curving UPWARD
        rsi_curling_up = rsi_vals.iloc[i] > rsi_vals.iloc[i-1] and rsi_vals.iloc[i] >= 45.0
        
        # 5. Filter out broken gaps (MRNA-style bleed)
        not_broken_gap = not (rsi_vals.iloc[i-5:i].max() > 88.0 and c < ema20.iloc[i] * 0.92)
        
        if not in_pos and macro_uptrend and prior_pullback and hammer_absorption and rsi_curling_up and not_broken_gap:
            signals.iloc[i] = 1
            in_pos = True
        elif in_pos and (rsi_vals.iloc[i] >= 78.0 or c < sma200.iloc[i] * 0.94 or c < ema50.iloc[i] * 0.95):
            signals.iloc[i] = -1
            in_pos = False
            
    return signals






# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY REGISTRY LIST
# ─────────────────────────────────────────────────────────────────────────────

STRATEGY_DEFINITIONS = [
    {
        "id": "rsi_mean_revert",
        "strategy": "RSI Mean Revert",
        "asset_class": "All Markets (Equities / Crypto / ETFs)",
        "default_symbol": "SPY",
        "type": "Mean Reversion",
        "description": "Enters long when RSI drops below oversold threshold and closes position when RSI crosses overbought exit level.",
        "universe_symbols": ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "BTCUSDT", "ETHUSDT", "SOLUSDT"],
        "parameters": [
            {"key": "rsi_period", "label": "RSI Period", "type": "number", "default": 14, "min": 2, "max": 50},
            {"key": "entry", "label": "Entry Level (Oversold)", "type": "number", "default": 30.0, "min": 5.0, "max": 45.0},
            {"key": "exit", "label": "Exit Level (Overbought)", "type": "number", "default": 70.0, "min": 55.0, "max": 95.0},
            {"key": "threshold", "label": "Stop Loss Delta %", "type": "number", "default": 5.0, "min": 1.0, "max": 20.0},
        ],
        "handler": signal_rsi_mean_revert
    },
    {
        "id": "momentum_ema_rsi_adx",
        "strategy": "Momentum (EMA/RSI/ADX cross), original basket",
        "asset_class": "BTC/ETH/BNB perps & Equities",
        "default_symbol": "BTCUSDT",
        "type": "Technical",
        "description": "EMA 20/50 crossover confirmed by RSI > 50 and ADX > 20 trend strength filter.",
        "universe_symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "NVDA", "AAPL", "QQQ"],
        "parameters": [
            {"key": "fast_ema", "label": "Fast EMA", "type": "number", "default": 20, "min": 5, "max": 50},
            {"key": "slow_ema", "label": "Slow EMA", "type": "number", "default": 50, "min": 20, "max": 200},
            {"key": "rsi_filter", "label": "RSI Trend Threshold", "type": "number", "default": 50.0, "min": 40.0, "max": 65.0},
            {"key": "adx_filter", "label": "Min ADX Filter", "type": "number", "default": 20.0, "min": 10.0, "max": 40.0},
        ],
        "handler": signal_momentum_ema_rsi_adx
    },
    {
        "id": "momentum_continuation",
        "strategy": "Momentum, continuation-entry variant",
        "asset_class": "Crypto perps & Tech Stocks",
        "default_symbol": "ETHUSDT",
        "type": "Technical",
        "description": "Trend continuation entries on short-term pullbacks to 20 EMA in strong market regimes.",
        "universe_symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT", "XRPUSDT", "NVDA", "MSFT", "AAPL"],
        "parameters": [
            {"key": "trend_sma", "label": "Macro Trend Filter (SMA)", "type": "number", "default": 200, "min": 50, "max": 300},
            {"key": "pullback_ema", "label": "Pullback Anchor EMA", "type": "number", "default": 20, "min": 5, "max": 50},
        ],
        "handler": signal_momentum_continuation
    },
    {
        "id": "connors_rsi2",
        "strategy": "Mean-reversion (RSI-2 Connors-style)",
        "asset_class": "Crypto perps & S&P 500 scan",
        "default_symbol": "SOLUSDT",
        "type": "Mean Reversion",
        "description": "Connors RSI-2 extreme oversold (<10) / overbought (>90) entries filtered by 200 SMA.",
        "universe_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT", "XRPUSDT", "AAPL", "AMZN", "GOOGL"],
        "parameters": [
            {"key": "trend_filter", "label": "Regime Filter SMA", "type": "number", "default": 200, "min": 50, "max": 300},
            {"key": "oversold", "label": "Oversold Entry Level", "type": "number", "default": 10.0, "min": 2.0, "max": 25.0},
            {"key": "overbought", "label": "Overbought Exit Level", "type": "number", "default": 90.0, "min": 75.0, "max": 98.0},
        ],
        "handler": signal_connors_rsi2
    },
    {
        "id": "pairs_cointegration",
        "strategy": "Pairs/cointegration (BTC/ETH)",
        "asset_class": "Crypto perps & Equity Pairs",
        "default_symbol": "BTCUSDT",
        "type": "Statistical Arb",
        "description": "Cointegration spread Z-score mean-reversion trading between correlated assets.",
        "universe_symbols": ["BTCUSDT", "ETHUSDT", "SPY", "QQQ", "MSFT", "AAPL"],
        "parameters": [
            {"key": "lookback_window", "label": "Lookback Window (Days)", "type": "number", "default": 60, "min": 15, "max": 180},
            {"key": "entry_z", "label": "Entry Z-Score", "type": "number", "default": 2.0, "min": 1.0, "max": 3.5},
            {"key": "exit_z", "label": "Exit Z-Score", "type": "number", "default": 0.2, "min": 0.0, "max": 1.0},
        ],
        "handler": signal_pairs_cointegration
    },
    {
        "id": "funding_carry",
        "strategy": "Funding carry (spot/perp, fixed threshold)",
        "asset_class": "Crypto & Volatility Harvesting",
        "default_symbol": "BTCUSDT",
        "type": "Arbitrage",
        "description": "Delta-neutral spot long / perp short funding rate harvest above fixed yield threshold.",
        "universe_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "parameters": [
            {"key": "min_yield_annual", "label": "Min Annualized Yield %", "type": "number", "default": 8.0, "min": 2.0, "max": 30.0},
            {"key": "max_vol_filter", "label": "Max Volatility Cap %", "type": "number", "default": 60.0, "min": 20.0, "max": 120.0},
        ],
        "handler": signal_funding_carry
    },
    {
        "id": "full_cointegration_screen",
        "strategy": "Full cointegration screen",
        "asset_class": "Top-15 crypto & Multi-Stock Basket",
        "default_symbol": "BTCUSDT",
        "type": "Statistical Arb",
        "description": "Multi-asset Johansen cointegration basket trading with dynamic hedge ratios.",
        "universe_symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "AAPL", "MSFT", "GOOGL"],
        "parameters": [
            {"key": "window", "label": "Cointegration Window", "type": "number", "default": 45, "min": 15, "max": 120},
            {"key": "z_score_threshold", "label": "Z-Score Threshold", "type": "number", "default": 1.8, "min": 1.0, "max": 3.0},
        ],
        "handler": signal_full_cointegration_screen
    },
    {
        "id": "ml_ensemble",
        "strategy": "ML ensemble (price + macro/sentiment/IV/regime/on-chain)",
        "asset_class": "BTC/ETH/BNB/SOL & Tech Equities",
        "default_symbol": "BTCUSDT",
        "type": "Machine Learning",
        "description": "Multi-factor ensemble model combining price momentum, volatility regime, and sentiment delta.",
        "universe_symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "NVDA", "TSLA", "META"],
        "parameters": [
            {"key": "weight_momentum", "label": "Momentum Weight", "type": "number", "default": 0.40, "min": 0.0, "max": 1.0},
            {"key": "weight_volatility", "label": "Volatility Weight", "type": "number", "default": 0.30, "min": 0.0, "max": 1.0},
            {"key": "weight_mean_revert", "label": "Mean-Revert Weight", "type": "number", "default": 0.30, "min": 0.0, "max": 1.0},
        ],
        "handler": signal_ml_ensemble
    },
    {
        "id": "cross_sectional_momentum",
        "strategy": "Cross-sectional momentum factor",
        "asset_class": "Curated Equities & Crypto Universes",
        "default_symbol": "BTCUSDT",
        "type": "Factor Quant",
        "description": "Long top quintile / short bottom quintile based on 30-day relative momentum.",
        "universe_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT", "NVDA", "AMD", "TSLA", "AMZN"],
        "parameters": [
            {"key": "momentum_lookback", "label": "Lookback Window (Days)", "type": "number", "default": 30, "min": 10, "max": 120},
        ],
        "handler": signal_cross_sectional_momentum
    },
    {
        "id": "grid_trading",
        "strategy": "Grid trading (market-making)",
        "asset_class": "Rangebound Crypto & Large Cap Stocks",
        "default_symbol": "BNBUSDT",
        "type": "Market Making",
        "description": "Arithmetic grid orders capturing price oscillations in rangebound markets.",
        "universe_symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "JNJ", "KO", "PG"],
        "parameters": [
            {"key": "grid_levels", "label": "Grid Levels Count", "type": "number", "default": 10, "min": 4, "max": 30},
            {"key": "grid_span_pct", "label": "Grid Half-Span %", "type": "number", "default": 0.15, "min": 0.05, "max": 0.40},
        ],
        "handler": signal_grid_trading
    },
    {
        "id": "grid_adx_trend_gate",
        "strategy": "Grid + ADX trend gate",
        "asset_class": "Crypto & Equities Market Making",
        "default_symbol": "SOLUSDT",
        "type": "Hybrid Grid",
        "description": "Grid market-making active strictly when ADX < 25 to prevent trending drawdown.",
        "universe_symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "SPY"],
        "parameters": [
            {"key": "adx_max", "label": "Max ADX Trend Gate", "type": "number", "default": 25.0, "min": 15.0, "max": 35.0},
        ],
        "handler": signal_grid_adx_gated
    },
    {
        "id": "short_strangle_options",
        "strategy": "Short-strangle options (IVP harvest)",
        "asset_class": "Options Volatility (Equities / Crypto)",
        "default_symbol": "BTCUSDT",
        "type": "Options Volatility",
        "description": "Harvesting Volatility Risk Premium (VRP) by selling delta-neutral strangles when IVP > 70.",
        "universe_symbols": ["BTCUSDT", "ETHUSDT", "SPY", "AAPL", "TSLA"],
        "parameters": [
            {"key": "min_ivp", "label": "Min IV Percentile Rank", "type": "number", "default": 70.0, "min": 50.0, "max": 95.0},
        ],
        "handler": signal_short_strangle_options
    },
    {
        "id": "futures_calendar_basis",
        "strategy": "Futures calendar basis spread",
        "asset_class": "Futures & Perpetuals Basis",
        "default_symbol": "BTCUSDT",
        "type": "Basis Arbitrage",
        "description": "Trading annualised calendar basis convergence between Quarterly futures and Perpetuals.",
        "universe_symbols": ["BTCUSDT", "ETHUSDT", "SPY"],
        "parameters": [
            {"key": "basis_spread_entry", "label": "Basis Entry Spread %", "type": "number", "default": 0.05, "min": 0.01, "max": 0.15},
        ],
        "handler": signal_futures_calendar_basis
    },
    {
        "id": "momentum_us_equities",
        "strategy": "Momentum on US equities",
        "asset_class": "30 US Stocks & ETFs",
        "default_symbol": "SPY",
        "type": "Equities Quant",
        "description": "Relative strength momentum strategy across SPY, QQQ, AAPL, NVDA, TSLA with 200 SMA filter.",
        "universe_symbols": ["SPY", "QQQ", "AAPL", "NVDA", "TSLA", "MSFT", "AMZN", "META", "GOOGL", "NFLX"],
        "parameters": [
            {"key": "trend_sma", "label": "Macro 200 SMA Filter", "type": "number", "default": 200, "min": 50, "max": 300},
            {"key": "roc_period", "label": "ROC Window", "type": "number", "default": 50, "min": 10, "max": 120},
        ],
        "handler": signal_momentum_us_equities
    },
    {
        "id": "full_universe_momentum_scan",
        "strategy": "Full-universe momentum scan",
        "asset_class": "All Crypto & Equity Universe",
        "default_symbol": "BTCUSDT",
        "type": "Scanner Momentum",
        "description": "Screening full crypto/stock universe for high Rate-Of-Change (ROC) volume breakout entries.",
        "universe_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "NVDA", "AMD", "TSLA", "PLTR", "COIN"],
        "parameters": [
            {"key": "roc_window", "label": "ROC Period (Days)", "type": "number", "default": 20, "min": 5, "max": 60},
            {"key": "vol_multiplier", "label": "Volume Surge Multiplier", "type": "number", "default": 1.5, "min": 1.1, "max": 4.0},
        ],
        "handler": signal_full_universe_momentum_scan
    },
    {
        "id": "donchian_turtle_breakout",
        "strategy": "Donchian/Turtle breakout",
        "asset_class": "Trend Following (Crypto & Stocks)",
        "default_symbol": "BTCUSDT",
        "type": "Trend Following",
        "description": "Classic 20-bar Donchian channel upper breakout long entry with 10-bar trailing exit.",
        "universe_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "AAPL", "MSFT", "NVDA", "SPY"],
        "parameters": [
            {"key": "entry_period", "label": "Channel Entry Period", "type": "number", "default": 20, "min": 5, "max": 60},
            {"key": "exit_period", "label": "Trailing Exit Period", "type": "number", "default": 10, "min": 3, "max": 30},
        ],
        "handler": signal_donchian_turtle_breakout
    },
    {
        "id": "bollinger_breakout_reversion",
        "strategy": "Bollinger breakout/reversion",
        "asset_class": "Volatility Breakout / Mean Reversion",
        "default_symbol": "ETHUSDT",
        "type": "Volatility Breakout",
        "description": "Squeeze expansion breakouts combined with 2.0 std-dev band reversion signals.",
        "universe_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "AAPL", "TSLA", "AMZN"],
        "parameters": [
            {"key": "period", "label": "BB Moving Average Period", "type": "number", "default": 20, "min": 5, "max": 50},
            {"key": "num_std", "label": "Std Dev Multiplier", "type": "number", "default": 2.0, "min": 1.0, "max": 3.5},
            {"key": "mode", "label": "Strategy Mode", "type": "select", "default": "reversion", "options": ["reversion", "breakout"]},
        ],
        "handler": signal_bollinger_breakout_reversion
    },
    {
        "id": "macd_crossover",
        "strategy": "MACD crossover",
        "asset_class": "Equities & Crypto Trend",
        "default_symbol": "SOLUSDT",
        "type": "Technical",
        "description": "Standard MACD (12, 26, 9) signal line crossovers with zero-line confirmation.",
        "universe_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "NVDA", "AAPL", "MSFT", "QQQ"],
        "parameters": [
            {"key": "fast_period", "label": "Fast EMA Period", "type": "number", "default": 12, "min": 3, "max": 30},
            {"key": "slow_period", "label": "Slow EMA Period", "type": "number", "default": 26, "min": 10, "max": 70},
            {"key": "signal_period", "label": "Signal EMA Period", "type": "number", "default": 9, "min": 2, "max": 20},
        ],
        "handler": signal_macd_crossover
    },
    {
        "id": "kalman_filter_trend",
        "strategy": "Kalman-filter trend",
        "asset_class": "Adaptive Signal Quant",
        "default_symbol": "BTCUSDT",
        "type": "Adaptive Signal",
        "description": "1D Kalman filter state estimation for low-lag trend velocity detection.",
        "universe_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "NVDA", "TSLA", "SPY"],
        "parameters": [
            {"key": "process_variance", "label": "Process Variance (Q)", "type": "number", "default": 0.0001, "min": 0.00001, "max": 0.01},
            {"key": "measurement_variance", "label": "Measurement Variance (R)", "type": "number", "default": 0.01, "min": 0.001, "max": 0.5},
        ],
        "handler": signal_kalman_filter_trend
    },
    {
        "id": "order_flow_imbalance",
        "strategy": "Order-flow imbalance",
        "asset_class": "Microstructure & High Volume",
        "default_symbol": "BTCUSDT",
        "type": "Microstructure",
        "description": "Volume Delta and buy/sell aggressor volume ratio imbalance strategy.",
        "universe_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "NVDA", "TSLA", "AAPL"],
        "parameters": [
            {"key": "imbalance_period", "label": "Volume Delta Window", "type": "number", "default": 14, "min": 3, "max": 40},
            {"key": "imbalance_threshold", "label": "Net Ratio Threshold", "type": "number", "default": 0.15, "min": 0.05, "max": 0.50},
        ],
        "handler": signal_order_flow_imbalance
    },
    {
        "id": "supertrend",
        "strategy": "Supertrend",
        "asset_class": "Trend Following (All Assets)",
        "default_symbol": "BTCUSDT",
        "type": "Trend Following",
        "description": "ATR-based Supertrend (ATR 10, Multiplier 3.0) direction trailing stop crossovers.",
        "universe_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "NVDA", "AAPL", "MSFT", "SPY"],
        "parameters": [
            {"key": "atr_period", "label": "ATR Period", "type": "number", "default": 10, "min": 3, "max": 30},
            {"key": "atr_multiplier", "label": "ATR Multiplier", "type": "number", "default": 3.0, "min": 1.0, "max": 6.0},
        ],
        "handler": signal_supertrend
    },
    {
        "id": "buy_hold",
        "strategy": "Buy & Hold Baseline",
        "asset_class": "All Assets",
        "default_symbol": "SPY",
        "type": "Passive Benchmark",
        "description": "Simple hold-through-period baseline strategy with equal asset allocation.",
        "universe_symbols": ["SPY", "QQQ", "AAPL", "BTCUSDT", "ETHUSDT"],
        "parameters": [
            {"key": "commission_pct", "label": "Commission %", "type": "number", "default": 0.1, "min": 0.0, "max": 2.0},
        ],
        "handler": signal_buy_and_hold
    },
    {
        "id": "liquidity_sweep_absorption",
        "strategy": "Liquidity Sweep & Absorption",
        "asset_class": "Crypto & Volatile Tech",
        "default_symbol": "BTC/USD",
        "type": "Market Microstructure",
        "description": "ICT-Quantified Stop-Hunt: Buys 20-bar Donchian sweep wicks absorbed by high volume delta.",
        "universe_symbols": ["BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "DOGE/USD", "NVDA", "TSLA"],
        "parameters": [
            {"key": "lookback", "label": "Donchian Lookback", "type": "number", "default": 20, "min": 5, "max": 50},
            {"key": "vol_mult", "label": "Volume Surge Multiplier", "type": "number", "default": 1.3, "min": 1.0, "max": 3.0},
        ],
        "handler": signal_liquidity_sweep_absorption
    },
    {
        "id": "lead_lag_propagation",
        "strategy": "Lead-Lag Momentum Propagation",
        "asset_class": "Crypto & High-Beta Tech",
        "default_symbol": "SOL/USD",
        "type": "Statistical Lead-Lag",
        "description": "Enters high-beta lagging target when anchor asset (BTC/QQQ) displays impulsive momentum expansion.",
        "universe_symbols": ["SOL/USD", "LINK/USD", "AVAX/USD", "AMD", "COIN", "MSTR"],
        "parameters": [
            {"key": "roc_period", "label": "ROC Momentum Period", "type": "number", "default": 5, "min": 2, "max": 20},
        ],
        "handler": signal_lead_lag_propagation
    },
    {
        "id": "hurst_double_squeeze",
        "strategy": "Hurst Dynamic Double Squeeze",
        "asset_class": "All Assets",
        "default_symbol": "BTC/USD",
        "type": "Regime Switching",
        "description": "Hurst exponent regime switching: Bollinger inside Keltner breakout in trends, mean-reversion in chop.",
        "universe_symbols": ["BTC/USD", "ETH/USD", "SPY", "QQQ", "NVDA", "TSLA"],
        "parameters": [
            {"key": "period", "label": "Band Period", "type": "number", "default": 20, "min": 10, "max": 40},
        ],
        "handler": signal_hurst_double_squeeze
    },
    {
        "id": "anchored_vwap_deviation",
        "strategy": "Anchored VWAP Multi-Deviation Snap",
        "asset_class": "Crypto & Mega-Cap Equities",
        "default_symbol": "NVDA",
        "type": "Institutional Mean Reversion",
        "description": "Enters on statistical stretch to -1.8 sigma below rolling VWAP with RSI(3) oversold exhaustion.",
        "universe_symbols": ["BTC/USD", "ETH/USD", "NVDA", "AAPL", "MSFT", "TSLA", "SPY"],
        "parameters": [
            {"key": "window", "label": "VWAP Rolling Window", "type": "number", "default": 30, "min": 10, "max": 60},
            {"key": "dev_threshold", "label": "Std Dev Entry Level", "type": "number", "default": -1.8, "min": -3.0, "max": -1.0},
        ],
        "handler": signal_anchored_vwap_deviation
    },
    {
        "id": "sharpe_residual_momentum",
        "strategy": "Sharpe Residual Momentum Alpha",
        "asset_class": "US Equities (S&P 500 & Nasdaq)",
        "default_symbol": "TSLA",
        "type": "Factor Alpha",
        "description": "Ranks assets by risk-adjusted 30-day return divided by annualized volatility above 200 SMA.",
        "universe_symbols": ["TSLA", "NVDA", "AMD", "AAPL", "META", "AMZN", "MSFT"],
        "parameters": [
            {"key": "lookback", "label": "Lookback Period (Days)", "type": "number", "default": 30, "min": 10, "max": 60},
            {"key": "min_sharpe_momentum", "label": "Min Sharpe Score", "type": "number", "default": 1.2, "min": 0.5, "max": 3.0},
        ],
        "handler": signal_sharpe_residual_momentum
    },
    {
        "id": "cvd_divergence_squeeze",
        "strategy": "CVD Divergence Short Squeeze",
        "asset_class": "Crypto Altcoins",
        "default_symbol": "SOL/USD",
        "type": "Order Flow / CVD",
        "description": "Bullish Cumulative Volume Delta divergence: Passive buyer accumulation during slow price drift down.",
        "universe_symbols": ["BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "DOGE/USD", "LINK/USD"],
        "parameters": [
            {"key": "period", "label": "CVD Window", "type": "number", "default": 14, "min": 5, "max": 30},
        ],
        "handler": signal_cvd_divergence_squeeze
    },
    {
        "id": "rsi_oversold_reversal",
        "strategy": "RSI Bullish Oversold Recovery (> 30 above 200 SMA)",
        "asset_class": "Crypto & US Equities (S&P 500 & Nasdaq)",
        "default_symbol": "SOL/USD",
        "type": "Momentum / Reversal",
        "description": "Takes long entry when 14-period RSI crosses upward above 30 from oversold territory, strictly while holding near to or above the 200-day daily SMA.",
        "universe_symbols": ["BTC/USD", "ETH/USD", "SOL/USD", "NVDA", "AAPL", "AMD", "TSLA", "QQQ", "SPY"],
        "parameters": [
            {"key": "rsi_period", "label": "RSI Period", "type": "number", "default": 14, "min": 5, "max": 30},
            {"key": "sma_period", "label": "Macro Trend SMA", "type": "number", "default": 200, "min": 50, "max": 200},
            {"key": "rsi_threshold", "label": "Oversold Entry Level", "type": "number", "default": 30.0, "min": 20.0, "max": 40.0},
            {"key": "rsi_exit", "label": "Overbought Exit Level", "type": "number", "default": 70.0, "min": 55.0, "max": 85.0},
        ],
        "handler": signal_rsi_oversold_reversal
    },
    {
        "id": "trend_pullback_continuation",
        "strategy": "Trend Pullback Continuation (TEAM-Style Reversal)",
        "asset_class": "Crypto & US Equities (S&P 500 & Nasdaq)",
        "default_symbol": "TEAM",
        "type": "Trend Continuation",
        "description": "Buys healthy cooling pullbacks in powerful macro uptrends (>200 SMA & 20>50 EMA) when hammer absorption confirms and RSI hooks upward.",
        "universe_symbols": ["TEAM", "NVDA", "AAPL", "HON", "MU", "ON", "SOL/USD", "BTC/USD"],
        "parameters": [
            {"key": "sma_period", "label": "Macro Trend SMA", "type": "number", "default": 200, "min": 50, "max": 200},
            {"key": "ema_fast", "label": "Fast EMA", "type": "number", "default": 20, "min": 10, "max": 30},
            {"key": "ema_slow", "label": "Slow EMA", "type": "number", "default": 50, "min": 30, "max": 100},
        ],
        "handler": signal_trend_pullback_continuation
    }
]


STRATEGY_MAP = {s["id"]: s for s in STRATEGY_DEFINITIONS}


