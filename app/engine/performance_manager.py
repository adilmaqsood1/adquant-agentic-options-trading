import os
import math
import datetime
from typing import Dict, Any, Optional, List, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor
from app.core.database import get_pool

# ═════════════════════════════════════════════════════════════════════════════
# 100% OPTIONS ALPHA DYNAMIC PORTFOLIO PARTITIONING
# Fetched directly from live Alpaca account equity:
# ├── Active Options Trading    75% of Live Equity
# │   ├── High Conviction       max $5,000 (Confidence >= 85%)
# │   ├── Medium Conviction     max $3,000 (Confidence 75-84%)
# │   └── Options Reserve       25% of Active Budget always undeployed
# └── Cash Reserve              25% of Live Equity — never touched
#     └── Releases only on RSI Oversold >= 85% confidence
# ═════════════════════════════════════════════════════════════════════════════

TOTAL_PORTFOLIO = 100_000.0

def fetch_live_alpaca_equity() -> float:
    """
    Fetches real-time account equity directly from Alpaca Trading API.
    Falls back to latest portfolio_state DB record or starting balance ($100k).
    """
    try:
        from app.core.config import ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_BASE_URL
        if ALPACA_API_KEY and ALPACA_API_SECRET:
            import httpx
            headers = {"APCA-API-KEY-ID": ALPACA_API_KEY, "APCA-API-SECRET-KEY": ALPACA_API_SECRET}
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(f"{ALPACA_BASE_URL}/account", headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    equity = float(data.get("equity") or data.get("portfolio_value") or 100_000.0)
                    if equity > 0:
                        return equity
    except Exception as e:
        print(f"[PerformanceManager] Alpaca account equity fetch notice: {e}")

    # Fallback to latest portfolio_state from DB
    try:
        pool = get_pool()
        conn = pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT portfolio_value FROM portfolio_state ORDER BY id DESC LIMIT 1;")
                row = cur.fetchone()
                if row and float(row["portfolio_value"]) > 0:
                    return float(row["portfolio_value"])
        finally:
            pool.putconn(conn)
    except Exception:
        pass

    return TOTAL_PORTFOLIO


def _reserve_release_allowed() -> bool:
    """Check if 48 hours have passed since last reserve release."""
    try:
        pool = get_pool()
        if pool is None:
            return True
        conn = pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT recorded_at FROM portfolio_state 
                    WHERE notes LIKE '%reserve_released%'
                    ORDER BY id DESC LIMIT 1;
                """)
                row = cur.fetchone()
                if not row or not row[0]:
                    return True
                last_release = row[0]
                if isinstance(last_release, str):
                    last_release = datetime.datetime.fromisoformat(last_release.replace("Z", "+00:00"))
                
                if hasattr(last_release, "tzinfo") and last_release.tzinfo is not None:
                    now = datetime.datetime.now(datetime.timezone.utc)
                else:
                    now = datetime.datetime.utcnow()
                hours_elapsed = (now - last_release).total_seconds() / 3600
                return hours_elapsed >= 48
        finally:
            pool.putconn(conn)
    except Exception as e:
        print(f"[PerformanceManager] Notice checking reserve release: {e}")
        return True



def get_active_budget_with_reserve(
    groq_confidence: int,
    strategy_id: str,
    live_equity: float
) -> float:
    """
    Returns active options budget.
    Base: 75% of live equity.
    Reserve release: if strategy is rsi_oversold_reversal 
    AND confidence >= 85 → temporarily use 85% of equity (releases 10% of cash reserve).
    Max one release per 48 hours.
    """
    base_budget = live_equity * 0.75
    
    if (strategy_id == "rsi_oversold_reversal" 
        and groq_confidence >= 85
        and _reserve_release_allowed()):
        print(f"[PerformanceManager] 🚀 Cash Reserve Released (+10% equity) for high-conviction RSI Oversold Reversal!")

        # Log the release to PostgreSQL so 48h gate works
        try:
            pool = get_pool()
            conn = pool.getconn()
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO portfolio_state 
                        (portfolio_value, peak_value, drawdown_pct, circuit_breaker_level, notes)
                        SELECT portfolio_value, peak_value, drawdown_pct, circuit_breaker_level,
                               'reserve_released'
                        FROM portfolio_state ORDER BY id DESC LIMIT 1;
                    """)
                    conn.commit()
            finally:
                pool.putconn(conn)
        except Exception as log_err:
            print(f"[PerformanceManager] Warning logging reserve release: {log_err}")

        return live_equity * 0.85  # releases 10% of reserve
    
    return base_budget


def get_portfolio_budget_breakdown(
    live_equity: Optional[float] = None,
    strategy_id: Optional[str] = None,
    groq_confidence: int = 80
) -> Dict[str, Any]:
    """
    Dynamically partitions portfolio based on live Alpaca equity:
      - Active Options Budget: 75% (or 85% if RSI oversold >= 85% releases reserve)
      - Cash Reserve: 25% (or 15% during temporary release)
      - High Conviction Cap: max $5,000 or 5% of equity
      - Medium Conviction Cap: max $3,000 or 3% of equity
      - Options Reserve Buffer: 25% of Active Options Budget
    """
    equity = live_equity if live_equity is not None else fetch_live_alpaca_equity()
    if strategy_id:
        active_options = get_active_budget_with_reserve(groq_confidence, strategy_id, equity)
    else:
        active_options = equity * 0.75

    cash_reserve = equity - active_options
    high_conviction = min(5_000.0, max(500.0, equity * 0.05))
    medium_conviction = min(3_000.0, max(500.0, equity * 0.03))
    options_reserve = active_options * 0.25

    return {
        "live_equity": round(equity, 2),
        "active_options_budget": round(active_options, 2),
        "cash_reserve_budget": round(cash_reserve, 2),
        "high_conviction_max": round(high_conviction, 2),
        "medium_conviction_max": round(medium_conviction, 2),
        "options_reserve_buffer": round(options_reserve, 2),
        "reserve_released": round(active_options, 2) > round(equity * 0.75, 2)
    }

CIRCUIT_BREAKER_LEVELS = {
    0: {"threshold": -0.03, "label": "Green (Normal)",     "cb_multiplier": 1.0, "action": "Full normal operation"},
    1: {"threshold": -0.06, "label": "Yellow (Caution)",   "cb_multiplier": 0.8, "action": "All sizes -20%"},
    2: {"threshold": -0.10, "label": "Orange (Defensive)", "cb_multiplier": 0.5, "action": "All sizes -50%, REDUCE blocked"},
    3: {"threshold": -0.15, "label": "Red (Crisis)",       "cb_multiplier": 0.0, "action": "No new entries"},
    4: {"threshold": -1.00, "label": "Black (Shutdown)",   "cb_multiplier": 0.0, "action": "Close all positions, 24h pause"},
}

MODE_MULTIPLIERS = {
    "GROWTH": 1.5,
    "NORMAL": 1.0,
    "REDUCE": 0.5,
    "PAUSE":  0.0,
}

# Minimum trade sizes — below this, fees eat the edge
MIN_TRADE_SIZE = {
    "option": 500.0
}

BENCHMARK_ATR_PCT = 0.02  # 2% daily ATR = volatility ratio 1.0



def compute_kelly_score(strategy_id: str, n: int = 10) -> Dict[str, Any]:
    """
    Computes Quarter Kelly score from last N closed trades for a specific strategy.
    Pulls realized_pnl and realized_pnl_pct from the positions table.

    Returns:
        mode:              GROWTH | NORMAL | REDUCE | PAUSE
        kelly_pct:         Full Kelly fraction (e.g., 0.35)
        quarter_kelly_pct: Quarter Kelly (kelly_pct * 0.25)
        size_multiplier:   Mode multiplier (1.5 | 1.0 | 0.5 | 0.0)
        win_rate:          Fraction of winning trades
        consecutive_losses:Running losing streak counter
    """
    trades = []
    try:
        pool = get_pool()
        if pool is not None:
            conn = pool.getconn()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT realized_pnl, realized_pnl_pct, exit_price, entry_price
                        FROM positions
                        WHERE strategy_id = %s
                          AND status = 'closed'
                          AND realized_pnl IS NOT NULL
                        ORDER BY id DESC
                        LIMIT %s;
                    """, (strategy_id, n))
                    trades = cur.fetchall()
            finally:
                pool.putconn(conn)
    except Exception as e:
        print(f"[PerformanceManager] Notice on get_strategy_performance: {e}")


    # Insufficient data — conservative NORMAL at 0.75x until proven
    if len(trades) < 3:
        return {
            "mode": "NORMAL",
            "kelly_pct": 0.10,
            "quarter_kelly_pct": 0.025,
            "size_multiplier": 0.75,
            "win_rate": 0.50,
            "win_loss_ratio": 2.0,
            "avg_win_pct": 0.05,
            "avg_loss_pct": 0.025,
            "consecutive_losses": 0,
            "consecutive_wins": 0,
            "total_trades": len(trades),
            "winning_trades": 0,
            "losing_trades": 0,
            "data_note": f"Insufficient history ({len(trades)} trades). Need >= 3 closed trades."
        }

    wins   = [t for t in trades if float(t["realized_pnl"] or 0) > 0]
    losses = [t for t in trades if float(t["realized_pnl"] or 0) <= 0]

    win_rate  = len(wins) / len(trades)
    loss_rate = 1.0 - win_rate

    avg_win_pct  = (sum(float(t["realized_pnl_pct"] or 0) for t in wins)   / len(wins))   / 100.0 if wins   else 0.0
    avg_loss_pct = (sum(abs(float(t["realized_pnl_pct"] or 0)) for t in losses) / len(losses)) / 100.0 if losses else 0.0

    win_loss_ratio = (avg_win_pct / avg_loss_pct) if avg_loss_pct > 0 else max(avg_win_pct, 1.0)

    # Full Kelly = W - (L / WL_ratio)
    kelly_pct = win_rate - (loss_rate / win_loss_ratio) if win_loss_ratio > 0 else -0.10
    kelly_pct = max(-0.50, min(kelly_pct, 0.50))  # hard clamp

    # Consecutive loss/win streak
    consecutive_losses = 0
    for t in trades:  # trades already reversed (DESC order)
        if float(t["realized_pnl"] or 0) <= 0:
            consecutive_losses += 1
        else:
            break

    consecutive_wins = 0
    for t in trades:
        if float(t["realized_pnl"] or 0) > 0:
            consecutive_wins += 1
        else:
            break

    # ── Mode Assignment ──────────────────────────────────────────────
    if kelly_pct > 0.15 and win_rate >= 0.60 and consecutive_losses == 0:
        mode = "GROWTH"
    elif kelly_pct > 0 and win_rate >= 0.45 and consecutive_losses <= 2:
        mode = "NORMAL"
    elif kelly_pct > 0 and consecutive_losses <= 3:
        mode = "REDUCE"
    else:
        mode = "PAUSE"

    return {
        "mode": mode,
        "kelly_pct": round(kelly_pct, 4),
        "quarter_kelly_pct": round(kelly_pct * 0.25, 4),
        "size_multiplier": MODE_MULTIPLIERS[mode],
        "win_rate": round(win_rate, 4),
        "win_loss_ratio": round(win_loss_ratio, 4),
        "avg_win_pct": round(avg_win_pct * 100, 4),
        "avg_loss_pct": round(avg_loss_pct * 100, 4),
        "consecutive_losses": consecutive_losses,
        "consecutive_wins": consecutive_wins,
        "total_trades": len(trades),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
    }


def update_portfolio_state(current_value: float) -> Dict[str, Any]:
    """
    Updates portfolio_state with current value, refreshes peak, computes drawdown,
    and assigns circuit breaker level.
    """
    peak_value = current_value
    drawdown_pct = 0.0
    cb_level = 0

    try:
        pool = get_pool()
        if pool is not None:
            conn = pool.getconn()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT * FROM portfolio_state ORDER BY id DESC LIMIT 1;")
                    row = cur.fetchone()
                    peak_value = float(row["peak_value"]) if row else current_value
                    peak_value = max(peak_value, current_value)

                    drawdown_pct = (current_value - peak_value) / peak_value

                    if drawdown_pct > -0.03:
                        cb_level = 0
                    elif drawdown_pct > -0.06:
                        cb_level = 1
                    elif drawdown_pct > -0.10:
                        cb_level = 2
                    elif drawdown_pct > -0.15:
                        cb_level = 3
                    else:
                        cb_level = 4

                    cur.execute("""
                        INSERT INTO portfolio_state (portfolio_value, peak_value, drawdown_pct, circuit_breaker_level)
                        VALUES (%s, %s, %s, %s);
                    """, (round(current_value, 2), round(peak_value, 2), round(drawdown_pct, 6), cb_level))
                    conn.commit()
            finally:
                pool.putconn(conn)
    except Exception as e:
        print(f"[PerformanceManager] Notice on update_portfolio_state: {e}")

    cb_info = CIRCUIT_BREAKER_LEVELS.get(cb_level, CIRCUIT_BREAKER_LEVELS[0])
    return {
        "portfolio_value": round(current_value, 2),
        "peak_value": round(peak_value, 2),
        "drawdown_pct": round(drawdown_pct * 100, 4),
        "circuit_breaker_level": cb_level,
        "circuit_breaker_label": cb_info["label"],
        "circuit_breaker_action": cb_info["action"],
        "cb_multiplier": cb_info["cb_multiplier"],
    }


def get_current_circuit_breaker() -> Dict[str, Any]:
    """Returns the latest circuit breaker state without updating."""
    live_eq = fetch_live_alpaca_equity()
    try:
        pool = get_pool()
        if pool is not None:
            conn = pool.getconn()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT * FROM portfolio_state ORDER BY id DESC LIMIT 1;")
                    row = cur.fetchone()
                    if row:
                        cb_level = int(row["circuit_breaker_level"])
                        cb_info = CIRCUIT_BREAKER_LEVELS.get(cb_level, CIRCUIT_BREAKER_LEVELS[0])
                        drawdown_pct = float(row["drawdown_pct"]) * 100.0 if row["drawdown_pct"] is not None else 0.0
                        return {
                            "circuit_breaker_level": cb_level,
                            "cb_multiplier": cb_info["cb_multiplier"],
                            "drawdown_pct": round(drawdown_pct, 4),
                            "portfolio_value": float(row["portfolio_value"]),
                            "peak_value": float(row["peak_value"]),
                            "circuit_breaker_label": cb_info["label"],
                            "action": cb_info["action"]
                        }
            finally:
                pool.putconn(conn)
    except Exception as e:
        print(f"[PerformanceManager] Notice on get_current_circuit_breaker: {e}")

    return {
        "circuit_breaker_level": 0,
        "cb_multiplier": 1.0,
        "drawdown_pct": 0.0,
        "portfolio_value": live_eq,
        "peak_value": live_eq,
        "circuit_breaker_label": "Green (Normal)",
        "action": "Full normal operation"
    }



# ═════════════════════════════════════════════════════════════════════════════════
# 4. ASSET VOLATILITY RATIO — ATR-Based Normalization
# ═════════════════════════════════════════════════════════════════════════════════

def compute_volatility_ratio(atr_14: float, current_price: float) -> float:
    """
    Normalizes asset volatility against the 2% ATR benchmark.

    BTC ATR% = 3.5%  → ratio = 0.02/0.035 = 0.57 (smaller position)
    AAPL ATR% = 1.2% → ratio = 0.02/0.012 = 1.67 → capped at 1.5
    SPY ATR% = 0.8%  → ratio = 0.02/0.008 = 2.5  → capped at 1.5

    Returns value clamped to [0.5, 1.5].
    """
    if current_price <= 0 or atr_14 <= 0:
        return 1.0

    atr_pct = atr_14 / current_price
    ratio = BENCHMARK_ATR_PCT / atr_pct
    return max(0.5, min(ratio, 1.5))


# ═════════════════════════════════════════════════════════════════════════════════
# 5. MASTER ALLOCATION FORMULA
# ═════════════════════════════════════════════════════════════════════════════════

def get_dynamic_allocation(
    strategy_id: str,
    symbol: str,
    atr_14: Optional[float] = None,
    current_price: Optional[float] = None,
    groq_confidence: int = 80,
    asset_class: str = "option",
    override_kelly: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Master Dynamic Allocation Formula for 100% Options Alpha Trading:
      1. Quarter Kelly base (from live strategy performance)
      2. Strategy performance mode multiplier (GROWTH 1.5x → PAUSE 0.0x)
      3. Five-level circuit breaker multiplier
      4. Asset volatility ratio (ATR-normalized to 2% benchmark)
      5. Groq confidence scalar (>=85: 1.0, 75-84: 0.7, <75: BLOCK)
      6. Hard conviction caps: High Conviction ($5,000 max), Medium Conviction ($3,000 max)
      7. Hard portfolio risk cap (max 3%)
      8. Minimum trade size gate ($500)
    """
    # 1. Portfolio state & live dynamic breakdown
    cb_state = get_current_circuit_breaker()
    portfolio_value = cb_state["portfolio_value"]
    cb_level = cb_state["circuit_breaker_level"]
    cb_multiplier = cb_state["cb_multiplier"]

    # Circuit breaker immediate blocks
    if cb_level >= 3:
        return {
            "approved": False,
            "final_allocation": 0.0,
            "block_reason": f"Circuit Breaker Level {cb_level} ({cb_state['circuit_breaker_label']}) — {cb_state['action']}",
            "circuit_breaker_level": cb_level,
        }

    # 2. Kelly score for this strategy
    kelly_data = override_kelly or compute_kelly_score(strategy_id)
    mode = kelly_data["mode"]
    size_multiplier = kelly_data["size_multiplier"]
    quarter_kelly = kelly_data["quarter_kelly_pct"]

    if mode == "PAUSE" or size_multiplier == 0.0:
        return {
            "approved": False,
            "final_allocation": 0.0,
            "block_reason": f"Strategy {strategy_id} is in PAUSE mode (consecutive losses: {kelly_data.get('consecutive_losses', '?')}). No new entries until edge recovers.",
            "mode": "PAUSE",
        }

    # Level 2: REDUCE mode strategies blocked at Circuit Breaker Level 2+
    if cb_level >= 2 and mode == "REDUCE":
        return {
            "approved": False,
            "final_allocation": 0.0,
            "block_reason": f"Circuit Breaker Level {cb_level} blocks REDUCE mode strategies.",
            "mode": mode,
            "circuit_breaker_level": cb_level,
        }

    # 3. Dynamic budget partitioning derived from live Alpaca account equity
    # (Releases 10% reserve if RSI Oversold Reversal with confidence >= 85%)
    breakdown = get_portfolio_budget_breakdown(
        live_equity=portfolio_value,
        strategy_id=strategy_id,
        groq_confidence=groq_confidence
    )
    active_base = breakdown["active_options_budget"]
    base_allocation = active_base * max(quarter_kelly, 0.01)
    base_allocation = max(base_allocation, active_base * 0.01)   # floor 1%
    base_allocation = min(base_allocation, active_base * 0.08)   # ceiling 8%

    # 4. Volatility ratio
    vol_ratio = 1.0
    if atr_14 and current_price:
        vol_ratio = compute_volatility_ratio(atr_14, current_price)

    # 5. Groq confidence scalar and conviction caps
    if groq_confidence >= 85:
        confidence_scalar = 1.0
        max_conviction_cap = breakdown["high_conviction_max"]  # max $5,000
    elif groq_confidence >= 75:
        confidence_scalar = 0.7
        max_conviction_cap = breakdown["medium_conviction_max"] # max $3,000
    else:
        return {
            "approved": False,
            "final_allocation": 0.0,
            "block_reason": f"Groq confidence ({groq_confidence}%) is below minimum threshold of 75%.",
        }

    # 6. Master formula
    final_allocation = (
        base_allocation
        * size_multiplier
        * cb_multiplier
        * vol_ratio
        * confidence_scalar
    )

    # 7. Apply conviction bucket caps ($5k / $3k) and hard portfolio risk cap
    final_allocation = min(final_allocation, max_conviction_cap)

    # For options, max loss is strictly the premium outlay (total dollar cost).
    # The 3% portfolio risk cap directly limits the maximum position cost.
    max_portfolio_risk = portfolio_value * 0.03  # Max $3,000 on $100K portfolio
    final_allocation = min(final_allocation, max_portfolio_risk)

    final_allocation = round(final_allocation, 2)

    # 8. Minimum trade size gate ($500 for options)
    min_size = MIN_TRADE_SIZE.get(asset_class, 500.0)
    if final_allocation < min_size:
        return {
            "approved": False,
            "final_allocation": final_allocation,
            "block_reason": f"Position too small after dynamic sizing (${final_allocation:.2f} < ${min_size:.0f} minimum for options). Not worth transaction costs.",
            "mode": mode,
        }

    # Note: For options, contract quantity is computed in risk_gate_agent.py
    # using floor(final_allocation / cost_per_contract).
    # Performance Manager only determines the dollar budget allocation.

    return {
        "approved": True,
        "strategy_id": strategy_id,
        "symbol": symbol,
        "mode": mode,
        "final_allocation": final_allocation,
        "reserve_released": breakdown.get("reserve_released", False),

        # Audit trail — every factor visible to judges
        "audit_trail": {
            "portfolio_value": round(portfolio_value, 2),
            "active_options_budget": breakdown["active_options_budget"],
            "cash_reserve_budget": breakdown["cash_reserve_budget"],
            "base_allocation": round(base_allocation, 2),
            "quarter_kelly_pct": quarter_kelly,
            "kelly_pct": kelly_data["kelly_pct"],
            "performance_mode": mode,
            "size_multiplier": size_multiplier,
            "circuit_breaker_level": cb_level,
            "cb_multiplier": cb_multiplier,
            "vol_ratio": round(vol_ratio, 3),
            "confidence_scalar": confidence_scalar,
            "groq_confidence": groq_confidence,
            "max_portfolio_risk_cap": round(max_portfolio_risk, 2),
        },
        "kelly_stats": kelly_data,
    }


# ═════════════════════════════════════════════════════════════════════════════════
# 6. PERSIST STRATEGY PERFORMANCE — Called after each closed trade
# ═════════════════════════════════════════════════════════════════════════════════

def upsert_strategy_performance(strategy_id: str) -> Dict[str, Any]:
    """
    Recomputes and upserts strategy_performance row from latest closed trades.
    Call this every time a position closes.
    """
    kelly = compute_kelly_score(strategy_id)

    try:
        pool = get_pool()
        if pool is not None:
            conn = pool.getconn()
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO strategy_performance
                            (strategy_id, mode, kelly_pct, quarter_kelly_pct, win_rate, avg_win_pct,
                             avg_loss_pct, win_loss_ratio, total_trades, winning_trades, losing_trades,
                             consecutive_wins, consecutive_losses, size_multiplier, last_updated)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, NOW())
                        ON CONFLICT (strategy_id) DO UPDATE SET
                            mode               = EXCLUDED.mode,
                            kelly_pct          = EXCLUDED.kelly_pct,
                            quarter_kelly_pct  = EXCLUDED.quarter_kelly_pct,
                            win_rate           = EXCLUDED.win_rate,
                            avg_win_pct        = EXCLUDED.avg_win_pct,
                            avg_loss_pct       = EXCLUDED.avg_loss_pct,
                            win_loss_ratio     = EXCLUDED.win_loss_ratio,
                            total_trades       = EXCLUDED.total_trades,
                            winning_trades     = EXCLUDED.winning_trades,
                            losing_trades      = EXCLUDED.losing_trades,
                            consecutive_wins   = EXCLUDED.consecutive_wins,
                            consecutive_losses = EXCLUDED.consecutive_losses,
                            size_multiplier    = EXCLUDED.size_multiplier,
                            last_updated       = NOW();
                    """, (
                        strategy_id,
                        kelly["mode"],
                        kelly["kelly_pct"],
                        kelly["quarter_kelly_pct"],
                        kelly["win_rate"],
                        kelly["avg_win_pct"],
                        kelly["avg_loss_pct"],
                        kelly["win_loss_ratio"],
                        kelly["total_trades"],
                        kelly["winning_trades"],
                        kelly["losing_trades"],
                        kelly.get("consecutive_wins", 0),
                        kelly.get("consecutive_losses", 0),
                        kelly["size_multiplier"],
                    ))
                    conn.commit()
            finally:
                pool.putconn(conn)
    except Exception as e:
        print(f"[PerformanceManager] Notice on upsert_strategy_performance: {e}")

    return kelly


def get_all_strategy_performance() -> List[Dict[str, Any]]:
    """Returns all strategy_performance rows for dashboard display."""
    try:
        pool = get_pool()
        if pool is not None:
            conn = pool.getconn()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT * FROM strategy_performance ORDER BY mode, strategy_id;")
                    return [dict(r) for r in cur.fetchall()]
            finally:
                pool.putconn(conn)
    except Exception as e:
        print(f"[PerformanceManager] Notice on get_all_strategy_performance: {e}")

    return []



def get_portfolio_health_report() -> Dict[str, Any]:
    """
    Returns a comprehensive snapshot of portfolio health for judge evaluation,
    automated email reporting, and telemetry in one structured output.
    """
    live_eq = fetch_live_alpaca_equity()
    return {
        "live_equity": live_eq,
        "circuit_breaker": get_current_circuit_breaker(),
        "budget_breakdown": get_portfolio_budget_breakdown(live_eq),
        "strategy_performance": get_all_strategy_performance(),
        "timestamp": datetime.datetime.utcnow().isoformat()
    }
