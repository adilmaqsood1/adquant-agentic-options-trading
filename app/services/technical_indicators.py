import numpy as np
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average"""
    return series.rolling(window=period, min_periods=1).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average"""
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder's RSI)"""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    
    rs = avg_gain / (avg_loss + 1e-10)
    rsi_val = 100 - (100 / (1 + rs))
    return rsi_val.fillna(50.0)


def connors_rsi(series: pd.Series, rsi_period: int = 3, streak_period: int = 2, rank_period: int = 100) -> pd.Series:
    """Connors RSI (CRSI) = (RSI(Close, 3) + RSI(Streak, 2) + PercentRank(ROC(1), 100)) / 3"""
    r1 = rsi(series, period=rsi_period)
    
    # Calculate streak (consecutive up/down days)
    diff = series.diff()
    streak = pd.Series(0.0, index=series.index)
    current_streak = 0.0
    for i in range(1, len(diff)):
        if diff.iloc[i] > 0:
            current_streak = current_streak + 1.0 if current_streak > 0 else 1.0
        elif diff.iloc[i] < 0:
            current_streak = current_streak - 1.0 if current_streak < 0 else -1.0
        else:
            current_streak = 0.0
        streak.iloc[i] = current_streak
        
    r2 = rsi(streak, period=streak_period)
    
    # 1-day return percentile rank
    roc1 = series.pct_change()
    pct_rank = roc1.rolling(window=rank_period, min_periods=10).apply(
        lambda x: (np.sum(x[-1] >= x) / len(x)) * 100.0 if len(x) > 0 else 50.0,
        raw=True
    ).fillna(50.0)
    
    crsi = (r1 + r2 + pct_rank) / 3.0
    return crsi.fillna(50.0)


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Moving Average Convergence Divergence"""
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def bollinger_bands(series: pd.Series, period: int = 20, num_std: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Bollinger Bands (Upper, Middle, Lower)"""
    middle = sma(series, period)
    std = series.rolling(window=period, min_periods=1).std().fillna(0)
    upper = middle + (std * num_std)
    lower = middle - (std * num_std)
    return upper, middle, lower


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range"""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean().fillna(tr1)


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average Directional Index"""
    up_move = high.diff()
    down_move = -low.diff()
    
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    
    tr_series = atr(high, low, close, period=1)  # 1-period true range
    smooth_tr = pd.Series(tr_series).ewm(alpha=1.0 / period, adjust=False).mean()
    smooth_plus = pd.Series(plus_dm, index=high.index).ewm(alpha=1.0 / period, adjust=False).mean()
    smooth_minus = pd.Series(minus_dm, index=high.index).ewm(alpha=1.0 / period, adjust=False).mean()
    
    plus_di = 100.0 * (smooth_plus / (smooth_tr + 1e-10))
    minus_di = 100.0 * (smooth_minus / (smooth_tr + 1e-10))
    
    dx = 100.0 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10))
    adx_val = dx.ewm(alpha=1.0 / period, adjust=False).mean()
    return adx_val.fillna(20.0)


def donchian_channel(high: pd.Series, low: pd.Series, period: int = 20) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Donchian Channels (Upper, Middle, Lower)"""
    upper = high.rolling(window=period, min_periods=1).max()
    lower = low.rolling(window=period, min_periods=1).min()
    middle = (upper + lower) / 2.0
    return upper, middle, lower


def supertrend(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 10, multiplier: float = 3.0) -> tuple[pd.Series, pd.Series]:
    """Supertrend Indicator -> (supertrend_line, direction [1 for bull, -1 for bear])"""
    atr_val = atr(high, low, close, period)
    hl2 = (high + low) / 2.0
    
    basic_upper = hl2 + (multiplier * atr_val)
    basic_lower = hl2 - (multiplier * atr_val)
    
    upper_band = basic_upper.copy()
    lower_band = basic_lower.copy()
    trend = pd.Series(1, index=close.index)
    
    for i in range(1, len(close)):
        # Final Upper Band
        if basic_upper.iloc[i] < upper_band.iloc[i-1] or close.iloc[i-1] > upper_band.iloc[i-1]:
            upper_band.iloc[i] = basic_upper.iloc[i]
        else:
            upper_band.iloc[i] = upper_band.iloc[i-1]
            
        # Final Lower Band
        if basic_lower.iloc[i] > lower_band.iloc[i-1] or close.iloc[i-1] < lower_band.iloc[i-1]:
            lower_band.iloc[i] = basic_lower.iloc[i]
        else:
            lower_band.iloc[i] = lower_band.iloc[i-1]
            
        # Trend Direction
        if close.iloc[i] > upper_band.iloc[i-1]:
            trend.iloc[i] = 1
        elif close.iloc[i] < lower_band.iloc[i-1]:
            trend.iloc[i] = -1
        else:
            trend.iloc[i] = trend.iloc[i-1]
            
    st_line = np.where(trend == 1, lower_band, upper_band)
    return pd.Series(st_line, index=close.index), trend


def kalman_filter_trend(series: pd.Series, process_variance: float = 1e-4, measurement_variance: float = 1e-2) -> pd.Series:
    """1D Kalman Filter for smooth adaptive price state estimation"""
    n = len(series)
    estimates = np.zeros(n)
    if n == 0:
        return series
    
    x_hat = series.iloc[0]
    p = 1.0
    
    for i in range(n):
        z = series.iloc[i]
        # Predict
        p = p + process_variance
        # Update
        k = p / (p + measurement_variance)
        x_hat = x_hat + k * (z - x_hat)
        p = (1 - k) * p
        estimates[i] = x_hat
        
    return pd.Series(estimates, index=series.index)


def z_score_spread(s1: pd.Series, s2: pd.Series, window: int = 60) -> pd.Series:
    """Spread Z-score for Cointegration / Pairs Trading"""
    # Align indices
    aligned = pd.concat([s1, s2], axis=1).dropna()
    if len(aligned) < window:
        return pd.Series(0.0, index=s1.index)
    
    ratio = aligned.iloc[:, 0] / (aligned.iloc[:, 1] + 1e-10)
    mean = ratio.rolling(window=window, min_periods=5).mean()
    std = ratio.rolling(window=window, min_periods=5).std()
    zscore = (ratio - mean) / (std + 1e-10)
    return zscore.reindex(s1.index).fillna(0.0)


def volume_delta_imbalance(close: pd.Series, high: pd.Series, low: pd.Series, volume: pd.Series, period: int = 14) -> pd.Series:
    """Approximate buyer/seller volume delta ratio using candle position"""
    range_hl = (high - low).replace(0, 1e-10)
    # Buying pressure ratio from candle close position within range
    buy_ratio = (close - low) / range_hl
    buy_vol = volume * buy_ratio
    sell_vol = volume * (1.0 - buy_ratio)
    
    net_delta = (buy_vol - sell_vol).rolling(window=period, min_periods=1).sum()
    total_vol = volume.rolling(window=period, min_periods=1).sum()
    
    imbalance_ratio = net_delta / (total_vol + 1e-10)
    return imbalance_ratio.fillna(0.0)


def keltner_channel(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20, multiplier: float = 1.5) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Keltner Channels: Middle (EMA 20), Upper (EMA + mult*ATR), Lower (EMA - mult*ATR)"""
    middle = ema(close, period)
    atr_val = atr(high, low, close, period)
    upper = middle + (atr_val * multiplier)
    lower = middle - (atr_val * multiplier)
    return upper, middle, lower


def hurst_exponent(series: pd.Series, max_lag: int = 20) -> float:
    """
    Computes rolling Hurst exponent (H):
    H > 0.55 = Trending / Persistent
    H < 0.45 = Mean-Reverting / Anti-persistent
    0.45 <= H <= 0.55 = Random Walk / Noise
    """
    if len(series) < max_lag * 2:
        return 0.50
    try:
        ts = np.log(series.values)
        lags = range(2, max_lag)
        tau = [np.std(ts[lag:] - ts[:-lag]) for lag in lags]
        reg = np.polyfit(np.log(lags), np.log(tau), 1)
        h = reg[0] * 2.0
        return float(np.clip(h, 0.0, 1.0))
    except Exception:
        return 0.50


def vwap_deviation_bands(df: pd.DataFrame, window: int = 30) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """
    Computes rolling VWAP and Standard Deviation Bands (+2sigma, -2sigma, and z-score distance).
    """
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    vol = df["volume"].replace(0, 1.0)
    pv = tp * vol
    
    rolling_pv = pv.rolling(window=window, min_periods=5).sum()
    rolling_v = vol.rolling(window=window, min_periods=5).sum()
    vwap_line = rolling_pv / (rolling_v + 1e-10)
    
    # Deviation std
    dev = (df["close"] - vwap_line)
    dev_std = dev.rolling(window=window, min_periods=5).std().fillna(1.0)
    
    upper_2sigma = vwap_line + (dev_std * 2.0)
    lower_2sigma = vwap_line - (dev_std * 2.0)
    z_score = dev / (dev_std + 1e-10)
    
    return vwap_line, upper_2sigma, lower_2sigma, z_score

