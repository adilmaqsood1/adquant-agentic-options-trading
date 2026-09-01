import os
import pandas as pd
from typing import Dict, List, Optional
try:
    from data.adapter import get_data
except ImportError:
    from app.data.adapter import get_data

RAW_PATH = os.path.join(os.path.dirname(__file__), "SP500_Data_10Y")

UNIVERSES = {
    "sp500": {
        "id": "sp500",
        "label": "S&P 500 Top Holdings",
        "market": "Equities",
        "symbols": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "BRK-B", "JPM", "V", "XOM", "UNH", "PG", "HD", "MA", "CVX", "MRK", "ABBV", "LLY", "COST", "SPY"]
    },
    "nasdaq100": {
        "id": "nasdaq100",
        "label": "Nasdaq 100 Tech Leaders",
        "market": "Equities",
        "symbols": ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AVGO", "COST", "NFLX", "AMD", "ADBE", "CSCO", "INTC", "INTU", "QCOM", "TXN", "AMAT", "QQQ"]
    },
    "crypto_alpaca": {
        "id": "crypto_alpaca",
        "label": "Alpaca Tradable Crypto (Top USD Pairs)",
        "market": "Crypto",
        "symbols": ["BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "DOGE/USD", "ADA/USD", "AVAX/USD", "LINK/USD", "LTC/USD", "DOT/USD", "AAVE/USD", "UNI/USD", "PEPE/USD", "SHIB/USD", "BONK/USD", "WIF/USD", "RENDER/USD", "ARB/USD"]
    },
    "crypto_core": {
        "id": "crypto_core",
        "label": "Alpaca Crypto Core Basket (BTC/ETH/SOL/DOGE)",
        "market": "Crypto",
        "symbols": ["BTC/USD", "ETH/USD", "SOL/USD", "DOGE/USD"]
    },
    "us_equities_momentum": {
        "id": "us_equities_momentum",
        "label": "US Equities Momentum Basket",
        "market": "Equities",
        "symbols": ["SPY", "QQQ", "AAPL", "NVDA", "TSLA", "MSFT", "AMZN", "META", "GOOGL", "NFLX"]
    }
}


def get_market_data(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    source: Optional[str] = None,
    interval: str = "1d"
) -> pd.DataFrame:
    """Unified access to normalized market data via Master Adapter"""
    return get_data(symbol=symbol, source=source, start=start_date, end=end_date, interval=interval)


def get_available_symbols() -> List[Dict[str, str]]:
    """Return all available US Equities and Optionable ETF symbols"""
    symbols = []
    if os.path.exists(RAW_PATH):
        for f in os.listdir(RAW_PATH):
            if f.endswith(".csv"):
                s = f.replace(".csv", "")
                symbols.append({"symbol": s, "asset_class": "US Equities", "source": "S&P 500 Options Universe"})
    
    # Core high-liquidity ETF symbols
    etfs = ["SPY", "QQQ", "IWM", "DIA", "XLF", "XLK", "XLE", "SMH", "TLT", "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA"]
    seen = {item["symbol"] for item in symbols}
    for e in etfs:
        if e not in seen:
            symbols.append({"symbol": e, "asset_class": "US Equities & ETFs", "source": "Alpaca Options"})
        
    return symbols
