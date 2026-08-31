from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any, Optional
import pandas as pd

try:
    from app.schemas.models import (
        BacktestRunRequest, CustomStrategyBacktestRequest, BacktestResponse,
        StrategyMetadata, UniverseMetadata
    )
    from app.services.registry import STRATEGY_DEFINITIONS, STRATEGY_MAP
    from app.services.custom_builder import evaluate_custom_rules
    from app.data.data_loader import UNIVERSES, get_available_symbols, get_market_data
    from app.services.backtester import run_portfolio_backtest
except ImportError:
    from schemas.models import (
        BacktestRunRequest, CustomStrategyBacktestRequest, BacktestResponse,
        StrategyMetadata, UniverseMetadata
    )
    from services.registry import STRATEGY_DEFINITIONS, STRATEGY_MAP
    from services.custom_builder import evaluate_custom_rules
    from data.data_loader import UNIVERSES, get_available_symbols, get_market_data
    from services.backtester import run_portfolio_backtest

router = APIRouter(prefix="/api", tags=["backtest"])


@router.get("/strategies", response_model=List[StrategyMetadata])
def get_strategies():
    """Return full registry of 20 production strategies with parameters and metadata"""
    clean_list = []
    for s in STRATEGY_DEFINITIONS:
        clean_list.append({
            "id": s["id"],
            "strategy": s["strategy"],
            "asset_class": s["asset_class"],
            "default_symbol": s["default_symbol"],
            "type": s["type"],
            "description": s["description"],
            "universe_symbols": s["universe_symbols"],
            "parameters": s["parameters"]
        })
    return clean_list


@router.get("/universes", response_model=List[UniverseMetadata])
def get_universes():
    """Return predefined market universes (S&P 500, Nasdaq 100, Crypto Top 15, etc.)"""
    return list(UNIVERSES.values())


@router.get("/market/symbols")
def get_symbols_list():
    """Return available market symbols (Equities & Crypto)"""
    return get_available_symbols()


@router.get("/market/history")
def get_symbol_history(
    symbol: str = Query("AAPL", description="Ticker symbol"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(300, ge=10, le=2000)
):
    """Return OHLCV candlestick historical data for charts"""
    df = get_market_data(symbol, start_date=start_date, end_date=end_date)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data available for symbol {symbol}")
        
    df_slice = df.tail(limit)
    records = []
    for dt, row in df_slice.iterrows():
        records.append({
            "time": dt.strftime("%Y-%m-%d") if hasattr(dt, 'strftime') else str(dt)[:10],
            "open": round(float(row["open"]), 2),
            "high": round(float(row["high"]), 2),
            "low": round(float(row["low"]), 2),
            "close": round(float(row["close"]), 2),
            "volume": int(row["volume"])
        })
    return {"symbol": symbol.upper(), "data": records}


@router.post("/backtest/run", response_model=BacktestResponse)
def run_strategy_backtest(req: BacktestRunRequest):
    """Execute end-to-end backtest on selected strategy with custom dynamic parameters"""
    strat = STRATEGY_MAP.get(req.strategy)
    if not strat:
        raise HTTPException(status_code=400, detail=f"Strategy '{req.strategy}' not found in registry")
        
    # Resolve symbols
    symbols_to_test = req.symbols
    if not symbols_to_test or len(symbols_to_test) == 0:
        symbols_to_test = strat["universe_symbols"]
    else:
        # Check if preset id passed like __preset:sp500
        expanded = []
        for s in symbols_to_test:
            if s.startswith("__preset:"):
                preset_id = s.split(":", 1)[1]
                if preset_id in UNIVERSES:
                    expanded.extend(UNIVERSES[preset_id]["symbols"])
                else:
                    expanded.append(strat["default_symbol"])
            elif s.lower() in UNIVERSES:
                expanded.extend(UNIVERSES[s.lower()]["symbols"])
            else:
                expanded.append(s)
        symbols_to_test = expanded if expanded else [strat["default_symbol"]]

    # Run backtest
    result = run_portfolio_backtest(
        symbols=symbols_to_test,
        signal_func=strat["handler"],
        strategy_params=req.strategyParams,
        start_date=req.startDate,
        end_date=req.endDate,
        initial_capital=req.initialCapital,
        portfolio_size=req.portfolioSize,
        benchmark_symbol=req.benchmark or "SPY",
        commission_pct=float(req.strategyParams.get("commission_pct", 0.1)) / 100.0
    )
    
    result["config"] = req.dict()
    return result


@router.post("/backtest/custom", response_model=BacktestResponse)
def run_custom_strategy_builder_backtest(req: CustomStrategyBacktestRequest):
    """Execute backtest on user-composed Strategy Builder rules"""
    if not req.rules:
        raise HTTPException(status_code=400, detail="No strategy rules provided")
        
    symbols_to_test = req.symbols
    if not symbols_to_test or len(symbols_to_test) == 0:
        symbols_to_test = ["SPY", "AAPL", "NVDA", "BTCUSDT"]

    def custom_signal_func(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
        rules_dict = [r.dict() if hasattr(r, 'dict') else r for r in req.rules]
        return evaluate_custom_rules(df, rules_dict)

    result = run_portfolio_backtest(
        symbols=symbols_to_test,
        signal_func=custom_signal_func,
        strategy_params={},
        start_date=req.startDate,
        end_date=req.endDate,
        initial_capital=req.initialCapital,
        portfolio_size=req.portfolioSize,
        benchmark_symbol=req.benchmark or "SPY",
        commission_pct=0.001
    )
    
    result["config"] = req.dict()
    return result
