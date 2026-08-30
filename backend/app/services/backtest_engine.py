import math
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Callable


def clean_val(v: Any, default: float = 0.0) -> float:
    """Ensure finite, JSON-compliant numbers"""
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def run_backtest(
    df: pd.DataFrame,
    strategy_handler: Callable[[pd.DataFrame, Dict[str, Any]], pd.Series],
    params: Optional[Dict[str, Any]] = None,
    initial_capital: float = 100_000.0,
    commission_rate: float = 0.001,  # 0.1% per side (0.2% round trip)
    slippage_rate: float = 0.0005,   # 0.05% per side
    risk_free_rate: float = 0.045,   # 4.5% annual (T-Bill)
    strategy_id: str = "custom",
    symbol: str = "ASSET",
    source: str = "adapter"
) -> Dict[str, Any]:
    """
    Core Backtesting Engine:
    - Simulates bar-by-bar execution at next bar's OPEN (no lookahead bias)
    - Full transaction friction: commissions + slippages
    - Computes returns, risk metrics (Sharpe @ 4.5% Rf, Sortino, Calmar, Max DD), and trade statistics
    """
    if params is None:
        params = {}

    n_bars = len(df)
    if n_bars < 2:
        return _empty_result(strategy_id, symbol, source, initial_capital)

    # 1. Generate signals using the strategy handler (evaluated at close of bar i)
    try:
        signals = strategy_handler(df, params)
    except Exception as e:
        print(f"[BacktestEngine] Error executing strategy handler: {e}")
        return _empty_result(strategy_id, symbol, source, initial_capital)

    dates = df.index
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    sig_vals = signals.values

    # Tracking simulation state
    equity_curve = np.zeros(n_bars, dtype=np.float64)
    drawdown_series = np.zeros(n_bars, dtype=np.float64)
    
    cash = initial_capital
    position_shares = 0.0
    entry_price = 0.0
    entry_idx = 0
    entry_date_str = ""

    trades: List[Dict[str, Any]] = []

    # Bar-by-bar walk forward
    for i in range(n_bars):
        current_close = closes[i]

        # 1. Check if we received a signal from previous bar (i-1) to execute at current bar's open (i)
        if i > 0:
            prev_sig = int(sig_vals[i - 1]) if not pd.isna(sig_vals[i - 1]) else 0

            # Long Entry execution (at next bar open + slippage)
            if prev_sig == 1 and position_shares == 0.0 and cash > 0:
                exec_price = opens[i] * (1.0 + slippage_rate)
                # Deduct commission from entry capital
                invest_capital = cash * (1.0 - commission_rate)
                position_shares = invest_capital / exec_price if exec_price > 0 else 0.0
                entry_price = exec_price
                entry_idx = i
                entry_date_str = dates[i].strftime("%Y-%m-%d") if hasattr(dates[i], "strftime") else str(dates[i])[:10]
                cash = 0.0

            # Exit execution (at next bar open - slippage)
            elif prev_sig == -1 and position_shares > 0.0:
                exec_price = opens[i] * (1.0 - slippage_rate)
                gross_proceeds = position_shares * exec_price
                net_proceeds = gross_proceeds * (1.0 - commission_rate)
                
                trade_pnl_usd = net_proceeds - (position_shares * entry_price)
                trade_pnl_pct = (exec_price - entry_price) / entry_price - (2 * commission_rate + 2 * slippage_rate)
                
                exit_date_str = dates[i].strftime("%Y-%m-%d") if hasattr(dates[i], "strftime") else str(dates[i])[:10]
                holding_days = max(1, (dates[i] - dates[entry_idx]).days if hasattr(dates[i] - dates[entry_idx], "days") else (i - entry_idx))

                trades.append({
                    "trade_id": len(trades) + 1,
                    "entry_date": entry_date_str,
                    "exit_date": exit_date_str,
                    "entry_price": clean_val(round(entry_price, 4)),
                    "exit_price": clean_val(round(exec_price, 4)),
                    "pnl_pct": clean_val(round(trade_pnl_pct * 100.0, 3)),
                    "pnl_usd": clean_val(round(trade_pnl_usd, 2)),
                    "holding_days": holding_days,
                    "status": "win" if trade_pnl_pct > 0 else "loss"
                })

                cash = net_proceeds
                position_shares = 0.0

        # 2. Mark to market equity at close of bar i
        current_equity = cash + (position_shares * current_close)
        if current_equity <= 0:
            current_equity = 0.0
            equity_curve[i:] = 0.0
            break
            
        equity_curve[i] = current_equity

    # Force close open position at the very last bar
    if position_shares > 0.0:
        last_i = n_bars - 1
        exec_price = closes[last_i] * (1.0 - slippage_rate)
        gross_proceeds = position_shares * exec_price
        net_proceeds = gross_proceeds * (1.0 - commission_rate)
        
        trade_pnl_usd = net_proceeds - (position_shares * entry_price)
        trade_pnl_pct = (exec_price - entry_price) / entry_price - (2 * commission_rate + 2 * slippage_rate)
        
        exit_date_str = dates[last_i].strftime("%Y-%m-%d") if hasattr(dates[last_i], "strftime") else str(dates[last_i])[:10]
        holding_days = max(1, (dates[last_i] - dates[entry_idx]).days if hasattr(dates[last_i] - dates[entry_idx], "days") else (last_i - entry_idx))

        trades.append({
            "trade_id": len(trades) + 1,
            "entry_date": entry_date_str,
            "exit_date": exit_date_str,
            "entry_price": clean_val(round(entry_price, 4)),
            "exit_price": clean_val(round(exec_price, 4)),
            "pnl_pct": clean_val(round(trade_pnl_pct * 100.0, 3)),
            "pnl_usd": clean_val(round(trade_pnl_usd, 2)),
            "holding_days": holding_days,
            "status": "win" if trade_pnl_pct > 0 else "loss"
        })

        cash = net_proceeds
        position_shares = 0.0
        equity_curve[-1] = net_proceeds

    # 3. Calculate Drawdown Series
    running_max = np.maximum.accumulate(equity_curve)
    drawdowns = np.where(running_max > 0, (equity_curve - running_max) / running_max, 0.0)
    drawdown_series = np.round(drawdowns * 100.0, 3)
    max_drawdown_pct = float(np.min(drawdown_series)) # Negative percentage

    # 4. Performance & Return Metrics
    final_equity = equity_curve[-1]
    total_return_pct = ((final_equity - initial_capital) / initial_capital) * 100.0

    start_date_dt = dates[0]
    end_date_dt = dates[-1]
    total_days = max(1, (end_date_dt - start_date_dt).days if hasattr(end_date_dt - start_date_dt, "days") else n_bars)
    years = max(total_days / 365.25, 0.05)

    if final_equity > 0 and (final_equity / initial_capital) > 0:
        annualized_return_pct = (((final_equity / initial_capital) ** (1.0 / years)) - 1.0) * 100.0
    else:
        annualized_return_pct = -100.0

    # 5. Risk Metrics (Sharpe with 4.5% Rf, Sortino, Calmar)
    eq_series = pd.Series(equity_curve, index=dates)
    daily_returns = eq_series.pct_change().dropna()

    daily_rf = (1.0 + risk_free_rate) ** (1.0 / 252.0) - 1.0
    excess_returns = daily_returns - daily_rf

    std_daily = float(daily_returns.std())
    mean_excess = float(excess_returns.mean())

    if std_daily > 1e-8:
        sharpe_ratio = (mean_excess / std_daily) * np.sqrt(252)
    else:
        sharpe_ratio = 0.0

    # Sortino (penalizing only downside volatility relative to 0)
    downside_returns = daily_returns[daily_returns < 0]
    downside_std = float(downside_returns.std()) if len(downside_returns) > 1 else 0.0
    
    if downside_std > 1e-8:
        sortino_ratio = (mean_excess / downside_std) * np.sqrt(252)
    else:
        sortino_ratio = 0.0 if sharpe_ratio <= 0 else sharpe_ratio * 1.5

    # Calmar Ratio (Ann Return / abs(Max DD))
    if abs(max_drawdown_pct) > 0.01:
        calmar_ratio = annualized_return_pct / abs(max_drawdown_pct)
    else:
        calmar_ratio = 0.0

    # 6. Trade Statistics
    total_trades = len(trades)
    if total_trades > 0:
        pnl_list = [t["pnl_pct"] for t in trades]
        winning_trades = [p for p in pnl_list if p > 0]
        losing_trades = [p for p in pnl_list if p <= 0]
        
        win_rate_pct = (len(winning_trades) / total_trades) * 100.0
        avg_win_pct = float(np.mean(winning_trades)) if winning_trades else 0.0
        avg_loss_pct = float(np.mean(losing_trades)) if losing_trades else 0.0
        
        gross_wins = sum(t["pnl_usd"] for t in trades if t["pnl_usd"] > 0)
        gross_losses = abs(sum(t["pnl_usd"] for t in trades if t["pnl_usd"] < 0))
        profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else (10.0 if gross_wins > 0 else 1.0)
        
        avg_holding_days = float(np.mean([t["holding_days"] for t in trades]))
        best_trade_pct = float(np.max(pnl_list))
        worst_trade_pct = float(np.min(pnl_list))

        # Consecutive streaks
        max_consec_wins = 0
        max_consec_losses = 0
        curr_w = 0
        curr_l = 0
        for p in pnl_list:
            if p > 0:
                curr_w += 1
                curr_l = 0
                max_consec_wins = max(max_consec_wins, curr_w)
            else:
                curr_l += 1
                curr_w = 0
                max_consec_losses = max(max_consec_losses, curr_l)
    else:
        win_rate_pct = 0.0
        avg_win_pct = 0.0
        avg_loss_pct = 0.0
        profit_factor = 0.0
        avg_holding_days = 0.0
        best_trade_pct = 0.0
        worst_trade_pct = 0.0
        max_consec_wins = 0
        max_consec_losses = 0

    # 7. Benchmark Comparison (Buy & Hold from start open to end close)
    bench_initial_price = opens[0]
    bench_final_price = closes[-1]
    benchmark_return_pct = ((bench_final_price - bench_initial_price) / bench_initial_price) * 100.0
    outperformance_pct = total_return_pct - benchmark_return_pct

    # Correlation
    bench_series = pd.Series(closes, index=dates).pct_change().dropna()
    aligned_returns = pd.concat([daily_returns, bench_series], axis=1).dropna()
    if len(aligned_returns) > 5 and aligned_returns.iloc[:, 0].std() > 0 and aligned_returns.iloc[:, 1].std() > 0:
        correlation = float(aligned_returns.iloc[:, 0].corr(aligned_returns.iloc[:, 1]))
    else:
        correlation = 0.0

    start_str = dates[0].strftime("%Y-%m-%d") if hasattr(dates[0], "strftime") else str(dates[0])[:10]
    end_str = dates[-1].strftime("%Y-%m-%d") if hasattr(dates[-1], "strftime") else str(dates[-1])[:10]

    return {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "source": source,
        "start_date": start_str,
        "end_date": end_str,
        "total_return_pct": clean_val(round(total_return_pct, 2)),
        "annualized_return_pct": clean_val(round(annualized_return_pct, 2)),
        "max_drawdown_pct": clean_val(round(max_drawdown_pct, 2)),
        "sharpe_ratio": clean_val(round(sharpe_ratio, 2)),
        "sortino_ratio": clean_val(round(sortino_ratio, 2)),
        "calmar_ratio": clean_val(round(calmar_ratio, 2)),
        "total_trades": total_trades,
        "win_rate_pct": clean_val(round(win_rate_pct, 2)),
        "avg_win_pct": clean_val(round(avg_win_pct, 2)),
        "avg_loss_pct": clean_val(round(avg_loss_pct, 2)),
        "profit_factor": clean_val(round(profit_factor, 2)),
        "avg_holding_days": clean_val(round(avg_holding_days, 1)),
        "best_trade_pct": clean_val(round(best_trade_pct, 2)),
        "worst_trade_pct": clean_val(round(worst_trade_pct, 2)),
        "max_consecutive_wins": max_consec_wins,
        "max_consecutive_losses": max_consec_losses,
        "benchmark_return_pct": clean_val(round(benchmark_return_pct, 2)),
        "outperformance_pct": clean_val(round(outperformance_pct, 2)),
        "correlation_to_benchmark": clean_val(round(correlation, 3)),
        "equity_curve": [clean_val(round(v, 2), default=initial_capital) for v in equity_curve],
        "drawdown_series": [clean_val(round(v, 2), default=0.0) for v in drawdown_series],
        "trades": trades
    }


def _empty_result(strategy_id: str, symbol: str, source: str, initial_capital: float) -> Dict[str, Any]:
    """Safe fallback dictionary for zero-data or failed runs"""
    return {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "source": source,
        "start_date": "",
        "end_date": "",
        "total_return_pct": 0.0,
        "annualized_return_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "sharpe_ratio": 0.0,
        "sortino_ratio": 0.0,
        "calmar_ratio": 0.0,
        "total_trades": 0,
        "win_rate_pct": 0.0,
        "avg_win_pct": 0.0,
        "avg_loss_pct": 0.0,
        "profit_factor": 0.0,
        "avg_holding_days": 0.0,
        "best_trade_pct": 0.0,
        "worst_trade_pct": 0.0,
        "max_consecutive_wins": 0,
        "max_consecutive_losses": 0,
        "benchmark_return_pct": 0.0,
        "outperformance_pct": 0.0,
        "correlation_to_benchmark": 0.0,
        "equity_curve": [initial_capital],
        "drawdown_series": [0.0],
        "trades": []
    }
