import re
import numpy as np
import pandas as pd
from typing import Dict, Any, List
from app.services.technical_indicators import (
    sma, ema, rsi, macd, bollinger_bands, atr, adx, donchian_channel, supertrend
)


def compute_indicator_series(df: pd.DataFrame, indicator_str: str) -> pd.Series:
    """Compute indicator series from indicator name or expression like SMA(20), RSI(14)"""
    ind = indicator_str.strip()
    
    # Check if number constant
    try:
        val = float(ind)
        return pd.Series(val, index=df.index)
    except ValueError:
        pass
        
    # Match patterns like SMA(20), EMA(50), RSI(14)
    match = re.match(r"([A-Za-z\s]+)\((\d+)\)", ind)
    if match:
        name = match.group(1).strip().upper()
        period = int(match.group(2))
        if name in ["SMA", "MA"]:
            return sma(df["close"], period)
        elif name == "EMA":
            return ema(df["close"], period)
        elif name == "RSI":
            return rsi(df["close"], period)
        elif name == "ATR":
            return atr(df["high"], df["low"], df["close"], period)
        elif name == "ADX":
            return adx(df["high"], df["low"], df["close"], period)
            
    # Default indicator mappings
    name_clean = ind.upper().replace(" ", "")
    if "RSI" in name_clean:
        return rsi(df["close"], 14)
    elif "MACD" in name_clean:
        m_line, _, _ = macd(df["close"], 12, 26, 9)
        return m_line
    elif "SMA" in name_clean:
        return sma(df["close"], 20)
    elif "EMA" in name_clean:
        return ema(df["close"], 20)
    elif "VOLUME" in name_clean:
        return df["volume"].astype(float)
    elif "PRICE" in name_clean or "CLOSE" in name_clean:
        return df["close"]
    elif "HIGH" in name_clean:
        return df["high"]
    elif "LOW" in name_clean:
        return df["low"]
    elif "ATR" in name_clean:
        return atr(df["high"], df["low"], df["close"], 14)
    elif "ADX" in name_clean:
        return adx(df["high"], df["low"], df["close"], 14)
        
    return df["close"]


def evaluate_condition(df: pd.DataFrame, cond: Dict[str, Any]) -> pd.Series:
    """Evaluate a single condition over the time series -> boolean Series"""
    ind_series = compute_indicator_series(df, cond.get("indicator", "RSI"))
    val_series = compute_indicator_series(df, str(cond.get("value", "30")))
    op = cond.get("operator", "<")
    
    if op == "<":
        return ind_series < val_series
    elif op == ">":
        return ind_series > val_series
    elif op == "<=":
        return ind_series <= val_series
    elif op == ">=":
        return ind_series >= val_series
    elif op == "==":
        return (ind_series - val_series).abs() < 1e-4
    elif op in ["crosses_above", "crosses_up"]:
        prev_ind = ind_series.shift(1)
        prev_val = val_series.shift(1)
        return (prev_ind <= prev_val) & (ind_series > val_series)
    elif op in ["crosses_below", "crosses_down"]:
        prev_ind = ind_series.shift(1)
        prev_val = val_series.shift(1)
        return (prev_ind >= prev_val) & (ind_series < val_series)
    else:
        return ind_series < val_series


def evaluate_custom_rules(df: pd.DataFrame, rules: List[Dict[str, Any]]) -> pd.Series:
    """Evaluate all custom strategy builder rules into signals (1: Buy, -1: Sell/Exit, 0: Hold)"""
    signals = pd.Series(0, index=df.index)
    if len(df) == 0:
        return signals
        
    entry_rules = [r for r in rules if r.get("type") == "entry"]
    exit_rules = [r for r in rules if r.get("type") == "exit"]
    
    # Compute combined entry condition
    entry_mask = pd.Series(False, index=df.index)
    for rule in entry_rules:
        conds = rule.get("conditions", [])
        if not conds:
            continue
        rule_mask = evaluate_condition(df, conds[0])
        for c in conds[1:]:
            c_mask = evaluate_condition(df, c)
            logic = c.get("logic", "AND").upper()
            if logic == "OR":
                rule_mask = rule_mask | c_mask
            else:
                rule_mask = rule_mask & c_mask
        entry_mask = entry_mask | rule_mask

    # Compute combined exit condition
    exit_mask = pd.Series(False, index=df.index)
    for rule in exit_rules:
        conds = rule.get("conditions", [])
        if not conds:
            continue
        rule_mask = evaluate_condition(df, conds[0])
        for c in conds[1:]:
            c_mask = evaluate_condition(df, c)
            logic = c.get("logic", "AND").upper()
            if logic == "OR":
                rule_mask = rule_mask | c_mask
            else:
                rule_mask = rule_mask & c_mask
        exit_mask = exit_mask | rule_mask

    # Generate sequential signals
    in_pos = False
    for i in range(len(df)):
        if not in_pos and entry_mask.iloc[i]:
            signals.iloc[i] = 1
            in_pos = True
        elif in_pos and exit_mask.iloc[i]:
            signals.iloc[i] = -1
            in_pos = False
            
    return signals
