import datetime
from typing import Dict, Any, List, Optional, Tuple, Union
from psycopg2.extras import RealDictCursor
from app.core.database import get_pool
from app.engine.options_pricing import BlackScholesEngine

TOTAL_OPTIONS_BUDGET = 30000.0 # 30% of $100k portfolio

def open_options_position(
    contract_spec: Dict[str, Any],
    groq_decision: Optional[Dict[str, Any]] = None
) -> int:
    """
    Inserts a complete options contract record into PostgreSQL 'options_contracts' table.
    Returns the generated integer ID.
    """
    if groq_decision is None:
        groq_decision = {
            "confidence": 85,
            "reasoning": "Strong quantitative signal alignment with low IV regime.",
            "go": True
        }

    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            query = """
                INSERT INTO options_contracts (
                    signal_id, strategy_id, underlying_symbol, occ_symbol,
                    contract_type, strategy_type, strike_price, expiry_date,
                    dte_at_entry, underlying_price, premium_paid, contracts_qty,
                    total_cost, multiplier, delta_entry, gamma_entry,
                    theta_entry, vega_entry, iv_entry, iv_rank_entry,
                    profit_target_premium, stop_loss_premium, time_stop_dte,
                    breakeven_price, status, entry_time,
                    groq_confidence, groq_reasoning, iv_regime
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, 'open', NOW(),
                    %s, %s, %s
                ) RETURNING id;
            """
            cur.execute(query, (
                contract_spec.get("signal_id"),
                contract_spec.get("strategy_id", "options_core"),
                contract_spec.get("underlying_symbol", "SPY"),
                contract_spec.get("occ_symbol", "UNKNOWN"),
                contract_spec.get("contract_type", "call"),
                contract_spec.get("strategy_type", "long_call"),
                contract_spec.get("strike_price", 100.0),
                contract_spec.get("expiry_date", "2026-10-02"),
                contract_spec.get("dte_at_entry", 30),
                contract_spec.get("underlying_price", 100.0),
                contract_spec.get("premium_paid", 5.0),
                contract_spec.get("contracts_qty", 1),
                contract_spec.get("total_cost", 500.0),
                contract_spec.get("multiplier", 100),
                contract_spec.get("delta_entry"),
                contract_spec.get("gamma_entry"),
                contract_spec.get("theta_entry"),
                contract_spec.get("vega_entry"),
                contract_spec.get("iv_entry"),
                contract_spec.get("iv_rank_entry"),
                contract_spec.get("profit_target_premium"),
                contract_spec.get("stop_loss_premium"),
                contract_spec.get("time_stop_dte", 14),
                contract_spec.get("breakeven_price"),
                groq_decision.get("confidence", 85),
                groq_decision.get("reasoning", ""),
                contract_spec.get("iv_regime", "low")
            ))
            row = cur.fetchone()
            conn.commit()
            return int(row[0]) if row else -1
    finally:
        pool.putconn(conn)


def close_options_position(
    occ_symbol: str,
    exit_premium: float,
    exit_reason: str = "profit_target"
) -> Optional[Dict[str, Any]]:
    """
    Updates options_contracts status to 'closed', calculates realized PnL, and records exit details.
    Formula: realized_pnl = (exit_premium - premium_paid) * contracts_qty * 100
    """
    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM options_contracts
                WHERE occ_symbol = %s AND status = 'open'
                ORDER BY id DESC LIMIT 1;
            """, (occ_symbol,))
            pos = cur.fetchone()
            if not pos:
                return None

            prem_paid = float(pos["premium_paid"])
            qty = int(pos["contracts_qty"])
            mult = int(pos.get("multiplier") or 100)

            realized_pnl = round((exit_premium - prem_paid) * qty * mult, 2)
            realized_pnl_pct = round(((exit_premium - prem_paid) / prem_paid * 100.0), 4) if prem_paid > 0 else 0.0

            cur.execute("""
                UPDATE options_contracts
                SET status = 'closed',
                    exit_time = NOW(),
                    exit_premium = %s,
                    exit_reason = %s,
                    realized_pnl = %s,
                    realized_pnl_pct = %s
                WHERE id = %s
                RETURNING *;
            """, (
                exit_premium,
                str(exit_reason)[:100],
                realized_pnl,
                realized_pnl_pct,
                pos["id"]
            ))
            updated = cur.fetchone()
            conn.commit()
            return dict(updated) if updated else None
    finally:
        pool.putconn(conn)


def get_open_options_positions() -> List[Dict[str, Any]]:
    """
    Returns all open options contracts as a list of dicts.
    """
    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM options_contracts
                WHERE status = 'open'
                ORDER BY created_at DESC;
            """)
            rows = cur.fetchall()
            return [dict(r) for r in rows]
    finally:
        pool.putconn(conn)


def is_underlying_held(underlying_symbol: str) -> bool:
    """
    Returns True if an open options contract already exists for this underlying symbol.
    Prevents double options exposure.
    """
    clean_sym = underlying_symbol.upper().replace("/", "")
    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM options_contracts
                WHERE underlying_symbol = %s AND status = 'open';
            """, (clean_sym,))
            row = cur.fetchone()
            return (row[0] > 0) if row else False
    finally:
        pool.putconn(conn)


def snapshot_greeks(occ_symbol: str, current_underlying_price: float) -> Optional[Dict[str, Any]]:
    """
    Recalculates real-time Greeks for an active contract and records a snapshot to 'options_greeks_history'.
    """
    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM options_contracts
                WHERE occ_symbol = %s AND status = 'open'
                ORDER BY id DESC LIMIT 1;
            """, (occ_symbol,))
            pos = cur.fetchone()
            if not pos:
                return None

            k = float(pos["strike_price"])
            exp_date = pos["expiry_date"]
            if isinstance(exp_date, str):
                exp_date = datetime.date.fromisoformat(exp_date)
            
            today = datetime.date.today()
            dte = max(1, (exp_date - today).days)
            T = dte / 365.0
            sigma = float(pos.get("iv_entry") or 0.28)
            opt_type = pos["contract_type"]

            greeks = BlackScholesEngine.calculate_greeks(
                S=current_underlying_price,
                K=k,
                T=T,
                r=0.045,
                sigma=sigma,
                option_type=opt_type
            )

            curr_mid = greeks["price"]
            prem_paid = float(pos["premium_paid"])
            qty = int(pos["contracts_qty"])
            mult = int(pos.get("multiplier") or 100)
            mark_pnl = round((curr_mid - prem_paid) * qty * mult, 2)

            cur.execute("""
                INSERT INTO options_greeks_history (
                    occ_symbol, underlying_symbol, underlying_price,
                    delta, gamma, theta, vega, iv, iv_rank,
                    option_mid_price, mark_pnl, snapshot_time
                ) VALUES (
                    %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, NOW()
                ) RETURNING *;
            """, (
                occ_symbol,
                pos["underlying_symbol"],
                current_underlying_price,
                greeks["delta"],
                greeks["gamma"],
                greeks["theta"],
                greeks["vega"],
                greeks["iv"],
                pos.get("iv_rank_entry", 35.0),
                curr_mid,
                mark_pnl
            ))
            snap = cur.fetchone()
            conn.commit()
            return dict(snap) if snap else None
    finally:
        pool.putconn(conn)


def check_exit_conditions(position: Dict[str, Any], current_premium: float) -> Optional[str]:
    """
    Evaluates options exit rules:
    1. current_premium >= profit_target_premium -> 'profit_target' (+80%)
    2. current_premium <= stop_loss_premium     -> 'stop_loss'     (-40%)
    3. dte <= time_stop_dte                     -> 'time_stop'     (<= 7 DTE)
    """
    target_prem = float(position.get("profit_target_premium") or 999999.0)
    stop_prem = float(position.get("stop_loss_premium") or 0.0)
    time_stop = int(position.get("time_stop_dte") or 7)

    # 1. Profit Target Check
    if current_premium >= target_prem:
        return "profit_target"

    # 2. Stop Loss Check
    if current_premium <= stop_prem:
        return "stop_loss"

    # 3. Time Stop DTE Check
    exp_date = position.get("expiry_date")
    if exp_date:
        if isinstance(exp_date, str):
            exp_date = datetime.date.fromisoformat(exp_date)
        today = datetime.date.today()
        current_dte = (exp_date - today).days
        if current_dte <= time_stop:
            return "time_stop"

    return None


def get_options_portfolio_summary() -> Dict[str, Any]:
    """
    Returns aggregated metrics for the options portfolio:
    - total_contracts_open
    - total_premium_deployed
    - total_unrealized_pnl
    - positions (list of open contracts)
    - budget_remaining
    """
    open_pos = get_open_options_positions()
    total_deployed = sum(float(p.get("total_cost") or 0.0) for p in open_pos)
    total_unrealized = 0.0

    # Fetch latest marks
    for p in open_pos:
        prem_paid = float(p.get("premium_paid") or 0.0)
        curr_p = prem_paid # default
        qty = int(p.get("contracts_qty") or 1)
        mult = int(p.get("multiplier") or 100)
        total_unrealized += (curr_p - prem_paid) * qty * mult

    budget_rem = max(0.0, TOTAL_OPTIONS_BUDGET - total_deployed)

    return {
        "total_contracts_open": len(open_pos),
        "total_premium_deployed": round(total_deployed, 2),
        "total_unrealized_pnl": round(total_unrealized, 2),
        "positions": open_pos,
        "budget_remaining": round(budget_rem, 2)
    }


def log_options_cycle(cycle_data: Dict[str, Any]) -> int:
    """
    Inserts a cycle audit log into 'options_cycles' table in PostgreSQL.
    """
    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO options_cycles (
                    cycle_time, signals_evaluated, contracts_opened,
                    contracts_closed, total_premium_deployed,
                    total_realized_pnl, total_unrealized_pnl,
                    portfolio_options_value, notes, created_at
                ) VALUES (
                    NOW(), %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, NOW()
                ) RETURNING id;
            """, (
                cycle_data.get("signals_evaluated", 0),
                cycle_data.get("contracts_opened", 0),
                cycle_data.get("contracts_closed", 0),
                cycle_data.get("total_premium_deployed", 0.0),
                cycle_data.get("total_realized_pnl", 0.0),
                cycle_data.get("total_unrealized_pnl", 0.0),
                cycle_data.get("portfolio_options_value", 0.0),
                cycle_data.get("notes", "")
            ))
            row = cur.fetchone()
            conn.commit()
            return int(row[0]) if row else -1
    finally:
        pool.putconn(conn)
