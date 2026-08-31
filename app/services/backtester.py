import time
import math
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Callable
try:
    from app.data.adapter import get_data
except ImportError:
    from data.adapter import get_data


def clean_num(val: Any, default: float = 0.0) -> float:
    """Ensure float is finite and JSON compliant (no NaN, Infinity)"""
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def compute_metrics(portfolio_series: pd.Series, bench_series: pd.Series, trades: List[Dict[str, Any]], initial_capital: float) -> Dict[str, Any]:
    """Calculate quantitative performance metrics with JSON compliance"""
    if len(portfolio_series) < 2:
        return {
            "totalReturn": 0.0,
            "annualizedReturn": 0.0,
            "benchmarkReturn": 0.0,
            "benchmarkAnnualizedReturn": 0.0,
            "sharpeRatio": 0.0,
            "sortinoRatio": 0.0,
            "maxDrawdown": 0.0,
            "winRate": 0.0,
            "profitFactor": 0.0,
            "volatility": 0.0,
            "calmarRatio": 0.0,
            "totalTrades": len(trades)
        }

    final_val = float(portfolio_series.iloc[-1])
    total_return = (final_val - initial_capital) / initial_capital

    bench_initial = float(bench_series.iloc[0]) if len(bench_series) > 0 else 1.0
    bench_final = float(bench_series.iloc[-1]) if len(bench_series) > 0 else 1.0
    bench_return = (bench_final - bench_initial) / (bench_initial + 1e-10)

    # Days
    days = max(1, (portfolio_series.index[-1] - portfolio_series.index[0]).days)
    years = max(days / 365.25, 0.05)

    ann_return = ((1.0 + total_return) ** (1.0 / years)) - 1.0 if (1.0 + total_return) > 0 else -0.99
    bench_ann_return = ((1.0 + bench_return) ** (1.0 / years)) - 1.0 if (1.0 + bench_return) > 0 else -0.99

    # Daily returns
    daily_rets = portfolio_series.pct_change().dropna()
    
    # Sharpe
    std = float(daily_rets.std())
    mean_ret = float(daily_rets.mean())
    sharpe = float((mean_ret / (std + 1e-10)) * np.sqrt(252)) if std > 0 else 0.0

    # Sortino (downside deviation)
    downside = daily_rets[daily_rets < 0]
    downside_std = float(downside.std()) if len(downside) > 0 else 0.0
    sortino = float((mean_ret / (downside_std + 1e-10)) * np.sqrt(252)) if downside_std > 0 else 0.0

    # Max Drawdown
    cummax = portfolio_series.cummax()
    drawdown = (cummax - portfolio_series) / cummax
    max_dd = float(drawdown.max())

    # Volatility
    volatility = float(std * np.sqrt(252)) if std > 0 else 0.0

    # Calmar Ratio
    calmar = float(ann_return / (max_dd + 1e-10)) if max_dd > 0 else 0.0

    # Trade stats
    completed_trades = [t for t in trades if t.get("status") in ["win", "loss"]]
    wins = [t for t in completed_trades if t.get("status") == "win"]
    win_rate = float(len(wins) / len(completed_trades)) if len(completed_trades) > 0 else 0.0

    gross_profit = sum(t["pnl"] for t in wins if t["pnl"] is not None)
    losses = [t for t in completed_trades if t.get("status") == "loss"]
    gross_loss = abs(sum(t["pnl"] for t in losses if t["pnl"] is not None))
    profit_factor = float(gross_profit / (gross_loss + 1e-10)) if gross_loss > 0 else (10.0 if gross_profit > 0 else 1.0)

    return {
        "totalReturn": clean_num(round(total_return, 4)),
        "annualizedReturn": clean_num(round(ann_return, 4)),
        "benchmarkReturn": clean_num(round(bench_return, 4)),
        "benchmarkAnnualizedReturn": clean_num(round(bench_ann_return, 4)),
        "sharpeRatio": clean_num(round(sharpe, 2)),
        "sortinoRatio": clean_num(round(sortino, 2)),
        "maxDrawdown": clean_num(round(max_dd, 4)),
        "winRate": clean_num(round(win_rate, 4)),
        "profitFactor": clean_num(round(profit_factor, 2)),
        "volatility": clean_num(round(volatility, 4)),
        "calmarRatio": clean_num(round(calmar, 2)),
        "totalTrades": len(trades)
    }


def run_portfolio_backtest(
    symbols: List[str],
    signal_func: Callable[[pd.DataFrame, Dict[str, Any]], pd.Series],
    strategy_params: Dict[str, Any],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    initial_capital: float = 100000.0,
    portfolio_size: int = 10,
    benchmark_symbol: str = "SPY",
    commission_pct: float = 0.001
) -> Dict[str, Any]:
    """Multi-asset simulation with capital allocation, trade logging, and equity curve calculation"""
    t_start = time.time()
    
    if not symbols:
        symbols = ["SPY"]
        
    selected_symbols = symbols[:portfolio_size] if portfolio_size < len(symbols) else symbols
    num_assets = max(1, len(selected_symbols))
    capital_per_asset = initial_capital / num_assets
    
    all_trades: List[Dict[str, Any]] = []
    trade_id = 1
    asset_series_list: List[pd.Series] = []
    
    # Run backtest per asset in portfolio
    for sym in selected_symbols:
        df = get_data(sym, start=start_date, end=end_date)
        if df.empty or len(df) < 5:
            continue
            
        signals = signal_func(df, strategy_params)
        
        # Simulate trades for this asset
        cash = capital_per_asset
        shares = 0.0
        entry_price = 0.0
        entry_date = ""
        
        equity_curve = pd.Series(index=df.index, dtype=float)
        
        for i in range(len(df)):
            dt = df.index[i]
            close_p = float(df["close"].iloc[i])
            sig = int(signals.iloc[i]) if not pd.isna(signals.iloc[i]) else 0
            
            # Entry Signal
            if sig == 1 and shares == 0.0:
                cost = close_p * (1.0 + commission_pct)
                shares = cash / cost if cost > 0 else 0.0
                entry_price = close_p
                entry_date = dt.strftime("%Y-%m-%d") if hasattr(dt, 'strftime') else str(dt)[:10]
                cash = 0.0
            # Exit Signal
            elif sig == -1 and shares > 0.0:
                exit_price = close_p
                exit_date = dt.strftime("%Y-%m-%d") if hasattr(dt, 'strftime') else str(dt)[:10]
                gross_proceeds = shares * exit_price * (1.0 - commission_pct)
                pnl = gross_proceeds - (shares * entry_price)
                ret_pct = (exit_price - entry_price) / (entry_price + 1e-10)
                
                all_trades.append({
                    "id": trade_id,
                    "symbol": sym,
                    "entryDate": entry_date,
                    "exitDate": exit_date,
                    "entryPrice": clean_num(round(entry_price, 2)),
                    "exitPrice": clean_num(round(exit_price, 2)),
                    "returnPct": clean_num(round(ret_pct, 4)),
                    "pnl": clean_num(round(pnl, 2)),
                    "status": "win" if ret_pct >= 0 else "loss"
                })
                trade_id += 1
                cash = gross_proceeds
                shares = 0.0
                
            curr_val = cash + (shares * close_p)
            equity_curve.iloc[i] = clean_num(curr_val, default=capital_per_asset)
            
        # If position still open at end
        if shares > 0.0:
            last_p = float(df["close"].iloc[-1])
            ret_pct = (last_p - entry_price) / (entry_price + 1e-10)
            pnl = (shares * last_p) - (shares * entry_price)
            all_trades.append({
                "id": trade_id,
                "symbol": sym,
                "entryDate": entry_date,
                "exitDate": None,
                "entryPrice": clean_num(round(entry_price, 2)),
                "exitPrice": clean_num(round(last_p, 2)),
                "returnPct": clean_num(round(ret_pct, 4)),
                "pnl": clean_num(round(pnl, 2)),
                "status": "open"
            })
            trade_id += 1
            
        asset_series_list.append(equity_curve)

    # If no data could be loaded, fallback gracefully
    if not asset_series_list:
        dates = pd.date_range(end=pd.Timestamp.now(), periods=100, freq="D")
        combined_portfolio = pd.Series(initial_capital, index=dates)
    else:
        combined_df = pd.concat(asset_series_list, axis=1).ffill().bfill()
        combined_portfolio = combined_df.sum(axis=1)

    # Benchmark series (e.g. SPY or first symbol)
    bench_df = get_data(benchmark_symbol, start=start_date, end=end_date)
    if bench_df.empty or len(bench_df) < 2:
        bench_df = get_data("SPY", start=start_date, end=end_date)
        
    if not bench_df.empty:
        aligned_bench = bench_df["close"].reindex(combined_portfolio.index).ffill().bfill()
        bench_scaled = (aligned_bench / (aligned_bench.iloc[0] + 1e-10)) * initial_capital
    else:
        bench_scaled = pd.Series(initial_capital, index=combined_portfolio.index)

    # Resample chart data points to ~100 points
    n_points = len(combined_portfolio)
    step = max(1, n_points // 80)
    chart_data = []
    
    for idx in range(0, n_points, step):
        dt = combined_portfolio.index[idx]
        chart_data.append({
            "date": dt.strftime("%b %d '%y") if hasattr(dt, 'strftime') else str(dt)[:10],
            "strategy": clean_num(round(float(combined_portfolio.iloc[idx]), 2), default=initial_capital),
            "benchmark": clean_num(round(float(bench_scaled.iloc[idx]), 2), default=initial_capital)
        })
        
    last_dt = combined_portfolio.index[-1]
    chart_data.append({
        "date": last_dt.strftime("%b %d '%y") if hasattr(last_dt, 'strftime') else str(last_dt)[:10],
        "strategy": clean_num(round(float(combined_portfolio.iloc[-1]), 2), default=initial_capital),
        "benchmark": clean_num(round(float(bench_scaled.iloc[-1]), 2), default=initial_capital)
    })

    metrics = compute_metrics(combined_portfolio, bench_scaled, all_trades, initial_capital)
    run_duration_ms = int((time.time() - t_start) * 1000)

    return {
        "runId": f"RUN-{int(time.time()*1000)%1000000:06d}",
        "runDurationMs": run_duration_ms,
        "metrics": metrics,
        "chartData": chart_data,
        "trades": all_trades
    }
