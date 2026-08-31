import os
import datetime
import pandas as pd
from typing import Optional
from dotenv import load_dotenv

# Load env from backend root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
load_dotenv()

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets/v2")

TIMEFRAME_MAP = {
    "1d": "Day",
    "1h": "Hour",
    "15m": "Minute",
    "5m": "Minute",
    "1m": "Minute"
}


def fetch_alpaca_crypto_bars(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    interval: str = "1d"
) -> pd.DataFrame:
    """
    Fetches historical crypto bars using Alpaca CryptoHistoricalDataClient.
    Accepts symbols formatted like BTC/USD, ETH/USD, SOL/USD, BTC/USDT, etc.
    """
    clean_sym = symbol.upper().strip()
    if "/" not in clean_sym:
        if clean_sym.endswith("USD"):
            clean_sym = f"{clean_sym[:-3]}/USD"
        elif clean_sym.endswith("USDT"):
            clean_sym = f"{clean_sym[:-4]}/USDT"
        elif clean_sym.endswith("USDC"):
            clean_sym = f"{clean_sym[:-4]}/USDC"

    start_dt = pd.to_datetime(start) if start else (datetime.datetime.utcnow() - datetime.timedelta(days=730))
    end_dt = pd.to_datetime(end) if end else datetime.datetime.utcnow()

    if ALPACA_API_KEY and ALPACA_API_SECRET:
        try:
            from alpaca.data.historical import CryptoHistoricalDataClient
            from alpaca.data.requests import CryptoBarsRequest
            from alpaca.data.timeframe import TimeFrame

            client = CryptoHistoricalDataClient(ALPACA_API_KEY, ALPACA_API_SECRET)

            tf = TimeFrame.Day
            if interval.lower() in ["1h", "2h", "4h"]:
                tf = TimeFrame.Hour
            elif interval.lower() in ["1m", "5m", "15m"]:
                tf = TimeFrame.Minute

            req = CryptoBarsRequest(
                symbol_or_symbols=[clean_sym],
                timeframe=tf,
                start=start_dt,
                end=end_dt
            )
            bars = client.get_crypto_bars(req)
            if hasattr(bars, "df") and not bars.df.empty:
                df = bars.df.copy()
                if isinstance(df.index, pd.MultiIndex):
                    try:
                        df = df.xs(clean_sym, level=0)
                    except Exception:
                        df = df.droplevel(0)
                
                # Standardize columns
                df.columns = [c.lower() for c in df.columns]
                df = df[["open", "high", "low", "close", "volume"]]
                df.index.name = "date"
                if df.index.tz is not None:
                    df.index = df.index.tz_localize(None)
                return df
        except Exception as e:
            print(f"[AlpacaSource] Crypto API error for {clean_sym}: {e}")

    return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])


def fetch_alpaca_stock_bars(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    interval: str = "1d"
) -> pd.DataFrame:
    """
    Fetches historical stock bars using Alpaca StockHistoricalDataClient.
    Falls back gracefully to yfinance if Alpaca API returns an error or no bars.
    """
    clean_sym = symbol.upper().strip()

    # Route crypto formatted symbols to fetch_alpaca_crypto_bars
    if "/" in clean_sym or clean_sym.endswith("/USD") or clean_sym.endswith("/USDT"):
        return fetch_alpaca_crypto_bars(clean_sym, start=start, end=end, interval=interval)

    start_dt = pd.to_datetime(start) if start else (datetime.datetime.utcnow() - datetime.timedelta(days=730))
    end_dt = pd.to_datetime(end) if end else datetime.datetime.utcnow()

    # Attempt Alpaca API fetch
    if ALPACA_API_KEY and ALPACA_API_SECRET:
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame
            from alpaca.data.enums import DataFeed

            client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_API_SECRET)
            
            tf = TimeFrame.Day
            if interval.lower() == "1h":
                tf = TimeFrame.Hour
            elif interval.lower() == "1m":
                tf = TimeFrame.Minute

            req = StockBarsRequest(
                symbol_or_symbols=clean_sym,
                timeframe=tf,
                start=start_dt,
                end=end_dt,
                feed=DataFeed.IEX
            )
            bars = client.get_stock_bars(req)
            if hasattr(bars, "df") and not bars.df.empty:
                df = bars.df.copy()
                if isinstance(df.index, pd.MultiIndex):
                    df = df.xs(clean_sym, level="symbol")
                
                # Standardize columns
                df.columns = [c.lower() for c in df.columns]
                df = df[["open", "high", "low", "close", "volume"]]
                df.index.name = "date"
                return df
        except Exception as e:
            print(f"[AlpacaSource] Stock API error for {clean_sym}: {e}, falling back to yfinance")

    # Fallback to yfinance
    try:
        import yfinance as yf
        ticker = yf.Ticker(clean_sym)
        yf_interval = "1d" if interval.lower() == "1d" else ("1h" if interval.lower() == "1h" else "1d")
        df = ticker.history(start=start_dt, end=end_dt, interval=yf_interval)
        if not df.empty:
            df.columns = [c.lower() for c in df.columns]
            df = df[["open", "high", "low", "close", "volume"]]
            df.index.name = "date"
            return df
    except Exception as e:
        print(f"[AlpacaSource] yfinance fallback failed for {clean_sym}: {e}")

    return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])



def fetch_alpaca_latest_prices(symbols: list) -> dict:
    """
    Fetches real-time latest trade price for a list of symbols (crypto and stocks).
    Returns dict: {'AAPL': 225.50, 'BTC/USD': 64000.0, ...}
    """
    if not symbols or not ALPACA_API_KEY or not ALPACA_API_SECRET:
        return {}

    crypto_syms = [s for s in symbols if "/" in s]
    stock_syms = [s for s in symbols if "/" not in s]
    results = {}

    # 1. Fetch Crypto Latest Trades (Normalize all USD stablecoins to primary /USD liquid books)
    if crypto_syms:
        try:
            from alpaca.data.historical import CryptoHistoricalDataClient
            from alpaca.data.requests import CryptoLatestTradeRequest
            client = CryptoHistoricalDataClient(ALPACA_API_KEY, ALPACA_API_SECRET)
            
            # Form primary USD counterpart for all crypto symbols to ensure live liquid quotes
            expanded_crypto = set(crypto_syms)
            for s in crypto_syms:
                if "/" in s:
                    base = s.split("/")[0]
                    expanded_crypto.add(f"{base}/USD")
                    
            req = CryptoLatestTradeRequest(symbol_or_symbols=list(expanded_crypto))
            trades = client.get_crypto_latest_trade(req)
            for sym, t in trades.items():
                if hasattr(t, "price") and t.price > 0:
                    results[sym] = float(t.price)
                    
            # Normalize stablecoin pairs (/USDC, /USDT) to primary /USD price to prevent illiquid/stale ghost trade prices
            for s in crypto_syms:
                if "/" in s and (s.endswith("/USDC") or s.endswith("/USDT")):
                    base = s.split("/")[0]
                    usd_pair = f"{base}/USD"
                    if usd_pair in results and results[usd_pair] > 0:
                        results[s] = results[usd_pair]
        except Exception as e:
            print(f"[AlpacaSource] Error fetching crypto latest trades: {e}")

    # 2. Fetch Stock Latest Trades
    if stock_syms:
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockLatestTradeRequest
            from alpaca.data.enums import DataFeed
            client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_API_SECRET)
            req = StockLatestTradeRequest(symbol_or_symbols=stock_syms, feed=DataFeed.IEX)
            trades = client.get_stock_latest_trade(req)
            for sym, t in trades.items():
                if hasattr(t, "price") and t.price > 0:
                    results[sym] = float(t.price)
        except Exception as e:
            print(f"[AlpacaSource] Error fetching stock latest trades: {e}")

    return results


# ═════════════════════════════════════════════════════════════════════════════════
# ALPACA LIVE ORDER EXECUTION BRIDGE (Options, Stocks, Crypto)
# ═════════════════════════════════════════════════════════════════════════════════

def submit_alpaca_option_order(
    occ_symbol: str,
    contracts_qty: int,
    side: str = "buy",
    order_type: str = "limit",
    limit_price: Optional[float] = None,
    position_intent: str = "buy_to_open",
    time_in_force: str = "day"
) -> dict:
    """
    Submits a live paper options order directly to Alpaca Trading API.
    Defaults to limit order using premium limit price to support 24/7 order submission & queuing.
    """
    if not ALPACA_API_KEY or not ALPACA_API_SECRET:
        return {"success": False, "error": "Alpaca API credentials missing"}

    url = f"{ALPACA_BASE_URL}/orders"
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET,
        "Content-Type": "application/json"
    }

    # Ensure limit_price is set if order_type is limit
    req_type = order_type.lower()
    if req_type == "limit" and (limit_price is None or float(limit_price) <= 0):
        # Default safety limit price if not provided
        limit_price = 5.00

    payload = {
        "symbol": occ_symbol.upper().strip(),
        "qty": str(int(contracts_qty)),
        "side": side.lower(),
        "type": req_type,
        "time_in_force": time_in_force.lower(),
        "position_intent": position_intent.lower()
    }
    if req_type == "limit" and limit_price is not None:
        payload["limit_price"] = str(round(float(limit_price), 2))

    try:
        import httpx
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code in [200, 201]:
                order_data = resp.json()
                print(f"[AlpacaExecution] ✅ LIVE OPTION ORDER SUBMITTED: {occ_symbol} ({contracts_qty} contracts {side.upper()} @ ${limit_price if req_type == 'limit' else 'MKT'}) | Order ID: {order_data.get('id')}")
                return {
                    "success": True,
                    "order_id": order_data.get("id"),
                    "client_order_id": order_data.get("client_order_id"),
                    "status": order_data.get("status"),
                    "symbol": order_data.get("symbol"),
                    "qty": order_data.get("qty"),
                    "side": order_data.get("side"),
                    "type": order_data.get("type"),
                    "limit_price": float(order_data.get("limit_price")) if order_data.get("limit_price") else limit_price,
                    "filled_avg_price": float(order_data.get("filled_avg_price") or 0.0) if order_data.get("filled_avg_price") else None,
                    "created_at": order_data.get("created_at")
                }
            else:
                # If market order was rejected due to market hours, retry automatically as limit order
                if "market hours" in resp.text and req_type == "market":
                    fallback_px = round(float(limit_price or 5.0), 2)
                    payload["type"] = "limit"
                    payload["limit_price"] = str(fallback_px)
                    retry_resp = client.post(url, headers=headers, json=payload)
                    if retry_resp.status_code in [200, 201]:
                        order_data = retry_resp.json()
                        print(f"[AlpacaExecution] ✅ LIVE OPTION LIMIT ORDER QUEUED: {occ_symbol} | Order ID: {order_data.get('id')}")
                        return {
                            "success": True,
                            "order_id": order_data.get("id"),
                            "status": order_data.get("status"),
                            "symbol": order_data.get("symbol"),
                            "limit_price": fallback_px
                        }

                err_msg = f"HTTP {resp.status_code}: {resp.text}"
                print(f"[AlpacaExecution] ❌ Option Order Failed: {err_msg}")
                return {"success": False, "error": err_msg, "payload": payload}
    except Exception as e:
        print(f"[AlpacaExecution] Exception submitting option order: {e}")
        return {"success": False, "error": str(e)}

    try:
        import httpx
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code in [200, 201]:
                order_data = resp.json()
                print(f"[AlpacaExecution] ✅ LIVE OPTION ORDER SUBMITTED: {occ_symbol} ({contracts_qty} contracts {side.upper()}) | Order ID: {order_data.get('id')}")
                return {
                    "success": True,
                    "order_id": order_data.get("id"),
                    "client_order_id": order_data.get("client_order_id"),
                    "status": order_data.get("status"),
                    "symbol": order_data.get("symbol"),
                    "qty": order_data.get("qty"),
                    "side": order_data.get("side"),
                    "type": order_data.get("type"),
                    "filled_avg_price": float(order_data.get("filled_avg_price") or 0.0) if order_data.get("filled_avg_price") else None,
                    "created_at": order_data.get("created_at")
                }
            else:
                err_msg = f"HTTP {resp.status_code}: {resp.text}"
                print(f"[AlpacaExecution] ❌ Option Order Failed: {err_msg}")
                return {"success": False, "error": err_msg, "payload": payload}
    except Exception as e:
        print(f"[AlpacaExecution] Exception submitting option order: {e}")
        return {"success": False, "error": str(e)}


def submit_alpaca_equity_order(
    symbol: str,
    qty: Optional[float] = None,
    notional: Optional[float] = None,
    side: str = "buy",
    order_type: str = "market",
    limit_price: Optional[float] = None,
    time_in_force: str = "day"
) -> dict:
    """
    Submits a live spot stock or crypto order directly to Alpaca Trading API.
    """
    if not ALPACA_API_KEY or not ALPACA_API_SECRET:
        return {"success": False, "error": "Alpaca API credentials missing"}

    clean_sym = symbol.upper().strip()
    is_crypto = "/" in clean_sym or clean_sym.endswith("USD") or clean_sym.endswith("USDT")
    if is_crypto and "/" not in clean_sym and clean_sym.endswith("USD"):
        clean_sym = f"{clean_sym[:-3]}/USD"

    url = f"{ALPACA_BASE_URL}/orders"
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET,
        "Content-Type": "application/json"
    }

    tif = "gtc" if is_crypto else time_in_force.lower()
    payload = {
        "symbol": clean_sym,
        "side": side.lower(),
        "type": order_type.lower(),
        "time_in_force": tif
    }
    if qty is not None and float(qty) > 0:
        payload["qty"] = str(round(float(qty), 6 if is_crypto else 2))
    elif notional is not None and float(notional) > 0:
        payload["notional"] = str(round(float(notional), 2))

    if order_type.lower() == "limit" and limit_price is not None:
        payload["limit_price"] = str(round(float(limit_price), 2))

    try:
        import httpx
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code in [200, 201]:
                order_data = resp.json()
                print(f"[AlpacaExecution] ✅ LIVE SPOT ORDER SUBMITTED: {clean_sym} ({side.upper()}) | Order ID: {order_data.get('id')}")
                return {
                    "success": True,
                    "order_id": order_data.get("id"),
                    "status": order_data.get("status"),
                    "symbol": order_data.get("symbol"),
                    "qty": order_data.get("qty"),
                    "side": order_data.get("side"),
                    "filled_avg_price": float(order_data.get("filled_avg_price") or 0.0) if order_data.get("filled_avg_price") else None
                }
            else:
                err_msg = f"HTTP {resp.status_code}: {resp.text}"
                print(f"[AlpacaExecution] ❌ Spot Order Failed: {err_msg}")
                return {"success": False, "error": err_msg}
    except Exception as e:
        print(f"[AlpacaExecution] Exception submitting spot order: {e}")
        return {"success": False, "error": str(e)}


def submit_alpaca_close_position(symbol_or_occ: str, qty: Optional[float] = None) -> dict:
    """
    Liquidates an open position directly in Alpaca via DELETE /v2/positions/{symbol}.
    """
    if not ALPACA_API_KEY or not ALPACA_API_SECRET:
        return {"success": False, "error": "Alpaca API credentials missing"}

    clean_sym = symbol_or_occ.upper().strip()
    url = f"{ALPACA_BASE_URL}/positions/{clean_sym}"
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET
    }
    params = {}
    if qty is not None and float(qty) > 0:
        params["qty"] = str(qty)

    try:
        import httpx
        with httpx.Client(timeout=15.0) as client:
            resp = client.delete(url, headers=headers, params=params)
            if resp.status_code in [200, 204]:
                print(f"[AlpacaExecution] ✅ LIVE POSITION CLOSED ON ALPACA: {clean_sym}")
                return {"success": True, "symbol": clean_sym, "status": "closed"}
            else:
                err_msg = f"HTTP {resp.status_code}: {resp.text}"
                print(f"[AlpacaExecution] ⚠️ Close position warning: {err_msg}")
                return {"success": False, "error": err_msg}
    except Exception as e:
        print(f"[AlpacaExecution] Exception closing position: {e}")
        return {"success": False, "error": str(e)}
