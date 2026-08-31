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

# Check for Supabase / PostgreSQL database URLs
DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or os.getenv("POSTGRES_URL")
    or os.getenv("SUPABASE_DB_URL")
    or ""
)

SYNC_DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://") if DATABASE_URL else ""

if SYNC_DATABASE_URL:
    _parsed = urlparse(SYNC_DATABASE_URL)
    DB_NAME = _parsed.path.lstrip("/") or "postgres"
    DB_USER = _parsed.username or "postgres"
    DB_PASS = _parsed.password or ""
    DB_HOST = _parsed.hostname or "localhost"
    DB_PORT = _parsed.port or 5432
else:
    DB_NAME = "postgres"
    DB_USER = "postgres"
    DB_PASS = ""
    DB_HOST = "localhost"
    DB_PORT = 5432

_pool: Optional[SimpleConnectionPool] = None
_pool_init_attempted: bool = False
_db_online: bool = False

# Resilient In-Memory Fallback State (Active whenever Postgres is offline/unreachable)
_in_memory_positions: Dict[int, Dict[str, Any]] = {}
_in_memory_cycles: List[Dict[str, Any]] = []
_in_memory_strategy_perf: Dict[str, Dict[str, Any]] = {}
_in_memory_portfolio_state: List[Dict[str, Any]] = []
_pos_id_counter: int = 1000


def get_pool() -> Optional[SimpleConnectionPool]:
    """
    Returns the active psycopg2 connection pool.
    Gracefully returns None if PostgreSQL is unreachable or connection fails.
    """
    global _pool, _pool_init_attempted, _db_online
    if not SYNC_DATABASE_URL:
        return None

    if _pool is not None and not _pool.closed:
        return _pool

    try:
        sslmode = "require" if ("supabase" in DB_HOST or "amazonaws" in DB_HOST) else "prefer"
        _pool = SimpleConnectionPool(
            minconn=1,
            maxconn=5,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            host=DB_HOST,
            port=DB_PORT,
            connect_timeout=3,
            sslmode=sslmode
        )
        _db_online = True
        return _pool
    except Exception as exc:
        if not _pool_init_attempted:
            print(f"[Database] ⚠️ PostgreSQL connection notice ({DB_HOST}:{DB_PORT}): {exc}")
            print("[Database] 💡 Operating in resilient in-memory mode. To persist data to PostgreSQL/Supabase, set DATABASE_URL.")
            _pool_init_attempted = True
        _pool = None
        _db_online = False
        return None


# SQLAlchemy Engine & SessionMaker
if SYNC_DATABASE_URL:
    try:
        engine = create_engine(
            SYNC_DATABASE_URL,
            pool_size=5,
            max_overflow=0,
            pool_pre_ping=True
        )
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    except Exception:
        engine = None
        SessionLocal = None
else:
    engine = None
    SessionLocal = None


def init_db() -> None:
    """
    Creates both 'positions' and 'agent_cycles' tables if they don't exist.
    Called once on startup. Gracefully handles unreachable database in cloud/local environments.
    """
    if engine is None:
        return
    try:
        try:
            from app.db.models import Base
        except ImportError:
            from db.models import Base
        Base.metadata.create_all(bind=engine)
        print("[Database] init_db() executed successfully. Tables verified.")
    except Exception as exc:
        print(f"[Database] ⚠️ Database connection notice (PostgreSQL unreachable on {DB_HOST}:{DB_PORT}): {exc}")



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
    Inserts a new row into positions table (or memory fallback).
    Calculates quantity automatically as (allocated_capital / entry_price).
    """
    global _pos_id_counter
    if entry_time is None:
        entry_time = datetime.datetime.utcnow()

    entry_price_flt = float(entry_price)
    allocated_capital_flt = float(allocated_capital)
    
    if asset_class == "option" and contracts and int(contracts) > 0:
        quantity = float(int(contracts) * 100)
    else:
        quantity = float(allocated_capital_flt / entry_price_flt) if entry_price_flt > 0 else 0.0

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

    # Try PostgreSQL first
    pool = get_pool()
    if pool is not None:
        try:
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
                    if row:
                        return dict(row)
            finally:
                pool.putconn(conn)
        except Exception as e:
            print(f"[Database] Notice on open_position: {e}. Falling back to memory.")

    # In-memory fallback
    _pos_id_counter += 1
    new_pos = {
        "id": _pos_id_counter,
        "strategy_id": str(strategy_id),
        "symbol": str(symbol).upper(),
        "source": str(source).lower(),
        "timeframe": str(timeframe).upper(),
        "signal_type": str(signal_type).upper(),
        "entry_price": entry_price_flt,
        "entry_time": entry_time,
        "allocated_capital": allocated_capital_flt,
        "quantity": quantity,
        "status": "open",
        "groq_confidence": groq_conf_val,
        "groq_reasoning": groq_reasoning,
        "groq_go": groq_go_val,
        "risk_approved": risk_app_val,
        "risk_block_reason": risk_block_reason,
        "asset_class": str(asset_class),
        "option_symbol": option_symbol,
        "option_type": option_type,
        "strike_price": strike_price_val,
        "expiration_date": exp_date_val,
        "contracts": contracts_val,
        "contract_premium": contract_premium_val,
        "delta": delta_val,
        "gamma": gamma_val,
        "theta": theta_val,
        "vega": vega_val,
        "implied_volatility": iv_val,
        "underlying_price": underlying_price_val,
        "exit_price": None,
        "exit_time": None,
        "realized_pnl": None,
        "realized_pnl_pct": None
    }
    _in_memory_positions[_pos_id_counter] = new_pos
    return new_pos


def close_position(
    strategy_id: str,
    symbol: str,
    exit_price: float,
    exit_time: Optional[datetime.datetime] = None
) -> Optional[Dict[str, Any]]:
    """
    Finds the open position matching strategy_id + symbol and marks as closed.
    """
    if exit_time is None:
        exit_time = datetime.datetime.utcnow()

    exit_price_flt = float(exit_price)

    pool = get_pool()
    if pool is not None:
        try:
            conn = pool.getconn()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT id, entry_price, quantity, allocated_capital
                        FROM positions
                        WHERE strategy_id = %s AND symbol = %s AND status = 'open'
                        ORDER BY id DESC LIMIT 1;
                    """, (strategy_id, symbol.upper()))
                    pos = cur.fetchone()

                    if pos:
                        pos_id = pos["id"]
                        entry_price_flt = float(pos["entry_price"])
                        quantity_flt = float(pos["quantity"])

                        gross_exit = quantity_flt * exit_price_flt
                        cost_basis = quantity_flt * entry_price_flt
                        realized_pnl = gross_exit - cost_basis
                        realized_pnl_pct = ((exit_price_flt - entry_price_flt) / entry_price_flt) * 100.0 if entry_price_flt > 0 else 0.0

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
                        if closed_row:
                            return dict(closed_row)
            finally:
                pool.putconn(conn)
        except Exception as e:
            print(f"[Database] Notice on close_position: {e}. Falling back to memory.")

    # In-memory fallback
    for pos_id, pos in reversed(list(_in_memory_positions.items())):
        if pos.get("strategy_id") == strategy_id and pos.get("symbol") == symbol.upper() and pos.get("status") == "open":
            entry_p = float(pos.get("entry_price") or exit_price_flt)
            qty = float(pos.get("quantity") or 1.0)
            realized_pnl = (exit_price_flt - entry_p) * qty
            realized_pnl_pct = ((exit_price_flt - entry_p) / entry_p) * 100.0 if entry_p > 0 else 0.0

            pos["status"] = "closed"
            pos["exit_price"] = exit_price_flt
            pos["exit_time"] = exit_time
            pos["realized_pnl"] = round(realized_pnl, 2)
            pos["realized_pnl_pct"] = round(realized_pnl_pct, 4)
            return pos

    return None


def extract_underlying_ticker(sym: str) -> str:
    """Extracts root ticker from OCC string (e.g. ABT from ABT261002C00108000) or returns clean sym."""
    import re
    if not sym:
        return ""
    m = re.match(r"^([A-Z]+)\d{6}[CP]\d{8}$", sym)
    if m:
        return m.group(1)
    return sym.upper()


def get_open_positions() -> List[Dict[str, Any]]:
    """
    Returns live open positions AND working open orders directly from Alpaca Broker API when connected,
    falling back to database / in-memory ledger.
    """
    try:
        from dotenv import load_dotenv
        import os, requests
        load_dotenv(override=True)
        alpaca_key = os.getenv("ALPACA_API_KEY")
        alpaca_sec = os.getenv("ALPACA_API_SECRET")
        alpaca_base = (os.getenv("ALPACA_BASE_URL") or "https://paper-api.alpaca.markets/v2").rstrip("/")

        if alpaca_key and alpaca_sec:
            headers = {"APCA-API-KEY-ID": alpaca_key, "APCA-API-SECRET-KEY": alpaca_sec}
            alpaca_list = []
            seen_occ = set()

            # 1. Filled Active Positions
            r_pos = requests.get(f"{alpaca_base}/positions", headers=headers, timeout=8)
            if r_pos.status_code == 200:
                for p in r_pos.json():
                    sym = p.get("symbol", "")
                    und = extract_underlying_ticker(sym)
                    seen_occ.add(sym)
                    alpaca_list.append({
                        "id": p.get("asset_id"),
                        "symbol": und,
                        "underlying_symbol": und,
                        "option_symbol": sym,
                        "asset_class": "option" if len(sym) > 6 else "equity",
                        "quantity": abs(float(p.get("qty", 1))),
                        "entry_price": float(p.get("avg_entry_price", 0.0)),
                        "current_price": float(p.get("current_price", 0.0)),
                        "unrealized_pl": float(p.get("unrealized_pl", 0.0)),
                        "status": "open",
                        "is_working_order": False
                    })

            # 2. Working / Pending Open Orders
            r_ord = requests.get(f"{alpaca_base}/orders?status=open", headers=headers, timeout=8)
            if r_ord.status_code == 200:
                for o in r_ord.json():
                    sym = o.get("symbol", "")
                    if sym not in seen_occ:
                        und = extract_underlying_ticker(sym)
                        alpaca_list.append({
                            "id": o.get("id"),
                            "symbol": und,
                            "underlying_symbol": und,
                            "option_symbol": sym,
                            "asset_class": "option" if len(sym) > 6 else "equity",
                            "quantity": abs(float(o.get("qty", 1))),
                            "entry_price": float(o.get("limit_price") or 0.0),
                            "current_price": float(o.get("limit_price") or 0.0),
                            "unrealized_pl": 0.0,
                            "status": "pending_order",
                            "is_working_order": True
                        })
            return alpaca_list
    except Exception as e:
        print(f"[Database] Live Alpaca positions sync notice: {e}")

    pool = get_pool()
    if pool is not None:
        try:
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
        except Exception as e:
            print(f"[Database] Notice on get_open_positions: {e}. Using memory state.")

    return [pos for pos in _in_memory_positions.values() if pos.get("status") == "open"]


def is_position_open(strategy_id: str, symbol: str) -> bool:
    """
    Returns True if an open position exists for this strategy+symbol combo.
    """
    pool = get_pool()
    if pool is not None:
        try:
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
        except Exception as e:
            print(f"[Database] Notice on is_position_open: {e}. Using memory state.")

    for pos in _in_memory_positions.values():
        if pos.get("strategy_id") == strategy_id and pos.get("symbol") == symbol.upper() and pos.get("status") == "open":
            return True
    return False


def get_portfolio_summary(current_prices: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """
    Returns portfolio summary dict calculated across spot and options contracts.
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
            if iv > 1.0:
                iv = iv / 100.0

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
    if pool is not None:
        try:
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
                    if row:
                        return dict(row)
            finally:
                pool.putconn(conn)
        except Exception as e:
            print(f"[Database] Notice on log_cycle: {e}. Storing in memory.")

    cycle_rec = {
        "id": len(_in_memory_cycles) + 1,
        "cycle_time": cycle_time,
        "timeframe_scope": timeframe_scope.upper(),
        "symbols_scanned": int(symbols_scanned),
        "signals_detected": int(signals_detected),
        "groq_approved": int(groq_approved),
        "risk_approved": int(risk_approved),
        "orders_placed": int(orders_placed),
        "portfolio_value": float(portfolio_value),
        "notes": notes
    }
    _in_memory_cycles.append(cycle_rec)
    return cycle_rec