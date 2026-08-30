import os
import datetime
from urllib.parse import urlparse
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

import psycopg2
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import RealDictCursor
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Load .env
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:ektrading123@localhost:5432/aplaca_trading")

# Standardize to sync postgresql driver URL for psycopg2 and SQLAlchemy sync operations
SYNC_DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

# Parse connection parameters for psycopg2 pool
_parsed = urlparse(SYNC_DATABASE_URL)
DB_NAME = _parsed.path.lstrip("/") or "aplaca_trading"
DB_USER = _parsed.username or "postgres"
DB_PASS = _parsed.password or "ektrading123"
DB_HOST = _parsed.hostname or "localhost"
DB_PORT = _parsed.port or 5432


_pool: Optional[SimpleConnectionPool] = None


def get_pool() -> SimpleConnectionPool:
    global _pool
    if _pool is None or _pool.closed:
        _pool = SimpleConnectionPool(
            minconn=1,
            maxconn=5,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            host=DB_HOST,
            port=DB_PORT
        )
    return _pool


# SQLAlchemy Engine & SessionMaker with connection pooling
engine = create_engine(
    SYNC_DATABASE_URL,
    pool_size=5,
    max_overflow=0,
    pool_pre_ping=True
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)



def init_db() -> None:
    """
    Creates both 'positions' and 'agent_cycles' tables if they don't exist.
    Called once on startup.
    """
    try:
        from app.db.models import Base
    except ImportError:
        from db.models import Base
    Base.metadata.create_all(bind=engine)
    print("[Database] init_db() executed successfully. Tables 'positions' and 'agent_cycles' verified.")



def open_position(
    strategy_id: str,
    symbol: str,
    source: str,
    timeframe: str,
    signal_type: str,
    entry_price: float,
    allocated_capital: float,
    groq_confidence: Optional[int] = None,
    groq_reasoning: Optional[str] = None,
    groq_go: Optional[bool] = None,
    risk_approved: Optional[bool] = None,
    risk_block_reason: Optional[str] = None,
    entry_time: Optional[datetime.datetime] = None,
    asset_class: str = "stock",
    option_symbol: Optional[str] = None,
    option_type: Optional[str] = None,
    strike_price: Optional[float] = None,
    expiration_date: Optional[str] = None,
    contracts: Optional[int] = None,
    contract_premium: Optional[float] = None,
    delta: Optional[float] = None,
    gamma: Optional[float] = None,
    theta: Optional[float] = None,
    vega: Optional[float] = None,
    implied_volatility: Optional[float] = None,
    underlying_price: Optional[float] = None
) -> Dict[str, Any]:
    """
    Inserts a new row into positions table.
    Calculates quantity automatically as (allocated_capital / entry_price).
    """
    if entry_time is None:
        entry_time = datetime.datetime.utcnow()

    entry_price_flt = float(entry_price)
    allocated_capital_flt = float(allocated_capital)
    
    # If option order, quantity is contracts * 100
    if asset_class == "option" and contracts and int(contracts) > 0:
        quantity = float(int(contracts) * 100)
    else:
        quantity = float(allocated_capital_flt / entry_price_flt) if entry_price_flt > 0 else 0.0

    # Ensure all option parameters are sanitized pure Python types
    strike_price_val = float(strike_price) if strike_price is not None else None
    contracts_val = int(contracts) if contracts is not None else None
    contract_premium_val = float(contract_premium) if contract_premium is not None else None
    delta_val = float(delta) if delta is not None else None
    gamma_val = float(gamma) if gamma is not None else None
    theta_val = float(theta) if theta is not None else None
    vega_val = float(vega) if vega is not None else None
    iv_val = float(implied_volatility) if implied_volatility is not None else None
    underlying_price_val = float(underlying_price) if underlying_price is not None else None
    groq_conf_val = int(groq_confidence) if groq_confidence is not None else None
    exp_date_val = str(expiration_date) if expiration_date is not None else None
    groq_go_val = bool(groq_go) if groq_go is not None else None
    risk_app_val = bool(risk_approved) if risk_approved is not None else None

    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = """
                INSERT INTO positions (
                    strategy_id, symbol, source, timeframe, signal_type,
                    entry_price, entry_time, allocated_capital, quantity,
                    status, groq_confidence, groq_reasoning, groq_go,
                    risk_approved, risk_block_reason,
                    asset_class, option_symbol, option_type, strike_price,
                    expiration_date, contracts, contract_premium,
                    delta, gamma, theta, vega, implied_volatility, underlying_price
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    'open', %s, %s, %s,
                    %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                ) RETURNING *;
            """
            cur.execute(query, (
                str(strategy_id), str(symbol).upper(), str(source).lower(), str(timeframe).upper(), str(signal_type).upper(),
                entry_price_flt, entry_time, allocated_capital_flt, quantity,
                groq_conf_val, groq_reasoning, groq_go_val,
                risk_app_val, risk_block_reason,
                str(asset_class), option_symbol, option_type, strike_price_val,
                exp_date_val, contracts_val, contract_premium_val,
                delta_val, gamma_val, theta_val, vega_val, iv_val, underlying_price_val
            ))
            row = cur.fetchone()
            conn.commit()
            return dict(row) if row else {}
    finally:
        pool.putconn(conn)




def close_position(
    strategy_id: str,
    symbol: str,
    exit_price: float,
    exit_time: Optional[datetime.datetime] = None
) -> Optional[Dict[str, Any]]:
    """
    Finds the open position matching strategy_id + symbol.
    Updates exit_price, exit_time, and status to 'closed'.
    Calculates realized_pnl and realized_pnl_pct automatically.
    """
    if exit_time is None:
        exit_time = datetime.datetime.utcnow()

    exit_price_flt = float(exit_price)

    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1. Fetch current open position
            cur.execute("""
                SELECT id, entry_price, quantity, allocated_capital
                FROM positions
                WHERE strategy_id = %s AND symbol = %s AND status = 'open'
                ORDER BY id DESC LIMIT 1;
            """, (strategy_id, symbol.upper()))
            pos = cur.fetchone()

            if not pos:
                return None

            pos_id = pos["id"]
            entry_price_flt = float(pos["entry_price"])
            quantity_flt = float(pos["quantity"])

            # 2. Calculate Realized PnL
            gross_exit = quantity_flt * exit_price_flt
            cost_basis = quantity_flt * entry_price_flt
            realized_pnl = gross_exit - cost_basis
            realized_pnl_pct = ((exit_price_flt - entry_price_flt) / entry_price_flt) * 100.0 if entry_price_flt > 0 else 0.0

            # 3. Update to closed
            update_query = """
                UPDATE positions SET
                    exit_price = %s,
                    exit_time = %s,
                    status = 'closed',
                    realized_pnl = %s,
                    realized_pnl_pct = %s
                WHERE id = %s
                RETURNING *;
            """
            cur.execute(update_query, (
                exit_price_flt, exit_time,
                round(realized_pnl, 2), round(realized_pnl_pct, 4),
                pos_id
            ))
            closed_row = cur.fetchone()
            conn.commit()
            return dict(closed_row) if closed_row else None
    finally:
        pool.putconn(conn)


def get_open_positions() -> List[Dict[str, Any]]:
    """
    Returns all rows where status is 'open' as a list of dicts.
    """
    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM positions
                WHERE status = 'open'
                ORDER BY entry_time DESC;
            """)
            rows = cur.fetchall()
            return [dict(r) for r in rows]
    finally:
        pool.putconn(conn)

def is_position_open(strategy_id: str, symbol: str) -> bool:
    """
    Returns True if an open row exists for this strategy+symbol combo.
    Used by Signal Detector every cycle.
    """
    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 1 FROM positions
                WHERE strategy_id = %s AND symbol = %s AND status = 'open'
                LIMIT 1;
            """, (strategy_id, symbol.upper()))
            return cur.fetchone() is not None
    finally:
        pool.putconn(conn)


def get_portfolio_summary(current_prices: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """
    Returns portfolio summary dict calculated across spot and options contracts:
    {
      "total_allocated": float,
      "total_open_positions": int,
      "unrealized_pnl": float,
      "options_count": int,
      "crypto_count": int,
      "strategies_active": list
    }
    """
    if current_prices is None:
        current_prices = {}

    open_positions = get_open_positions()
    
    total_allocated = 0.0
    unrealized_pnl = 0.0
    options_count = 0
    crypto_count = 0
    strategies_active = set()

    for p in open_positions:
        alloc = float(p.get("allocated_capital") or 0.0)
        total_allocated += alloc
        strat = p.get("strategy_id")
        if strat:
            strategies_active.add(strat)

        sym = p.get("symbol", "")
        entry_p = float(p.get("entry_price") or 0.0)
        curr_p = current_prices.get(sym, entry_p)

        is_option = (p.get("asset_class") == "option") or bool(p.get("option_symbol"))

        if is_option:
            options_count += 1
            contracts = int(p.get("contracts") or 1)
            strike = float(p.get("strike_price") or entry_p)
            exp_date = p.get("expiration_date")
            opt_type = p.get("option_type") or "call"
            iv = float(p.get("implied_volatility") or 0.28)
            if iv > 1.0: # normalize percentage vs decimal
                iv = iv / 100.0

            # Calculate DTE
            dte = 35
            if exp_date:
                try:
                    if isinstance(exp_date, str):
                        exp_d = datetime.date.fromisoformat(exp_date.split("T")[0])
                    else:
                        exp_d = exp_date
                    dte = max(1, (exp_d - datetime.date.today()).days)
                except Exception:
                    dte = 35
            
            T = max(1e-4, dte / 365.0)

            # Compute Black-Scholes live theoretical mark
            try:
                from app.engine.options_pricing import BlackScholesEngine
                live_opt_prem = BlackScholesEngine.calculate_option_price(
                    S=curr_p,
                    K=strike,
                    T=T,
                    r=0.045,
                    sigma=iv,
                    option_type=opt_type
                )
            except Exception:
                live_opt_prem = entry_p

            pos_unreal = (live_opt_prem - entry_p) * contracts * 100.0
            unrealized_pnl += pos_unreal
        else:
            crypto_count += 1
            qty = float(p.get("quantity") or 0.0)
            if qty > 0 and curr_p > 0:
                unrealized_pnl += (qty * curr_p) - (qty * entry_p)

    return {
        "total_allocated": round(total_allocated, 2),
        "total_open_positions": len(open_positions),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "options_count": options_count,
        "crypto_count": crypto_count,
        "strategies_active": sorted(list(strategies_active))
    }



def log_cycle(
    timeframe_scope: str,
    symbols_scanned: int,
    signals_detected: int,
    groq_approved: int,
    risk_approved: int,
    notes: Optional[str] = None,
    portfolio_value: float = 0.0,
    orders_placed: int = 0,
    cycle_time: Optional[datetime.datetime] = None
) -> Dict[str, Any]:
    """
    Inserts one row into agent_cycles. Called at end of every orchestrator run.
    """
    if cycle_time is None:
        cycle_time = datetime.datetime.utcnow()

    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = """
                INSERT INTO agent_cycles (
                    cycle_time, timeframe_scope, symbols_scanned,
                    signals_detected, groq_approved, risk_approved,
                    orders_placed, portfolio_value, notes
                ) VALUES (
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s
                ) RETURNING *;
            """
            cur.execute(query, (
                cycle_time, timeframe_scope.upper(), int(symbols_scanned),
                int(signals_detected), int(groq_approved), int(risk_approved),
                int(orders_placed), float(portfolio_value), notes
            ))
            row = cur.fetchone()
            conn.commit()
            return dict(row) if row else {}
    finally:
        pool.putconn(conn)