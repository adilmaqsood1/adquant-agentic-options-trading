from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Numeric, DateTime, Boolean, Text, func
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Position(Base):
    """
    Table 1: positions
    Tracks live and paper trading positions across strategies and timeframes.
    """
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(String(50), nullable=False, index=True)        # "cross_sectional_momentum", "supertrend", etc.
    symbol = Column(String(20), nullable=False, index=True)             # "BTCUSDT", "AAPL", "SPY"
    source = Column(String(20), nullable=False)                         # "binance", "alpaca", "kaggle"
    timeframe = Column(String(10), nullable=False)                      # "2H", "4H", "1D"
    signal_type = Column(String(20), nullable=False)                    # "ENTER_LONG", "EXIT_LONG"
    entry_price = Column(Numeric(20, 8), nullable=False)
    entry_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    allocated_capital = Column(Numeric(20, 2), nullable=False)          # Dollar amount allocated
    quantity = Column(Numeric(20, 8), nullable=False)                   # allocated_capital / entry_price
    status = Column(String(10), nullable=False, default="open", index=True) # "open" or "closed"
    exit_price = Column(Numeric(20, 8), nullable=True)                  # NULL until closed
    exit_time = Column(DateTime, nullable=True)                         # NULL until closed
    realized_pnl = Column(Numeric(20, 2), nullable=True)                # Dollar PnL
    realized_pnl_pct = Column(Numeric(10, 4), nullable=True)            # Percentage PnL
    groq_confidence = Column(Integer, nullable=True)                    # 0 - 100
    groq_reasoning = Column(Text, nullable=True)
    groq_go = Column(Boolean, nullable=True)
    # Options-Specific Execution Columns
    asset_class = Column(String(20), nullable=False, default="stock")     # "option", "stock", "crypto"
    option_symbol = Column(String(30), nullable=True, index=True)         # "AAPL260918C00230000"
    option_type = Column(String(10), nullable=True)                       # "call", "put"
    strike_price = Column(Numeric(15, 4), nullable=True)
    expiration_date = Column(String(20), nullable=True)                   # "2026-09-18"
    contracts = Column(Integer, nullable=True)                            # Number of 100-share option contracts
    contract_premium = Column(Numeric(15, 4), nullable=True)              # Option entry price per share
    delta = Column(Numeric(10, 4), nullable=True)                         # 0.70
    gamma = Column(Numeric(10, 4), nullable=True)
    theta = Column(Numeric(10, 4), nullable=True)
    vega = Column(Numeric(10, 4), nullable=True)
    implied_volatility = Column(Numeric(10, 4), nullable=True)            # 32.5%
    underlying_price = Column(Numeric(20, 8), nullable=True)              # Spot price of underlying equity

    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "source": self.source,
            "timeframe": self.timeframe,
            "signal_type": self.signal_type,
            "entry_price": float(self.entry_price) if self.entry_price is not None else None,
            "entry_time": self.entry_time.isoformat() if self.entry_time else None,
            "allocated_capital": float(self.allocated_capital) if self.allocated_capital is not None else None,
            "quantity": float(self.quantity) if self.quantity is not None else None,
            "status": self.status,
            "exit_price": float(self.exit_price) if self.exit_price is not None else None,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "realized_pnl": float(self.realized_pnl) if self.realized_pnl is not None else None,
            "realized_pnl_pct": float(self.realized_pnl_pct) if self.realized_pnl_pct is not None else None,
            "groq_confidence": self.groq_confidence,
            "groq_reasoning": self.groq_reasoning,
            "groq_go": self.groq_go,
            "risk_approved": self.risk_approved,
            "risk_block_reason": self.risk_block_reason,
            "asset_class": self.asset_class,
            "option_symbol": self.option_symbol,
            "option_type": self.option_type,
            "strike_price": float(self.strike_price) if self.strike_price is not None else None,
            "expiration_date": self.expiration_date,
            "contracts": self.contracts,
            "contract_premium": float(self.contract_premium) if self.contract_premium is not None else None,
            "delta": float(self.delta) if self.delta is not None else None,
            "gamma": float(self.gamma) if self.gamma is not None else None,
            "theta": float(self.theta) if self.theta is not None else None,
            "vega": float(self.vega) if self.vega is not None else None,
            "underlying_price": float(self.underlying_price) if self.underlying_price is not None else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }



class AgentCycle(Base):
    """
    Table 2: agent_cycles
    Logs each scheduler and orchestrator cycle.
    """
    __tablename__ = "agent_cycles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cycle_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    timeframe_scope = Column(String(10), nullable=False)                # "2H", "4H", "1D"
    symbols_scanned = Column(Integer, default=0)
    signals_detected = Column(Integer, default=0)
    groq_approved = Column(Integer, default=0)
    risk_approved = Column(Integer, default=0)
    orders_placed = Column(Integer, default=0)
    portfolio_value = Column(Numeric(20, 2), default=0.0)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "cycle_time": self.cycle_time.isoformat() if self.cycle_time else None,
            "timeframe_scope": self.timeframe_scope,
            "symbols_scanned": self.symbols_scanned,
            "signals_detected": self.signals_detected,
            "groq_approved": self.groq_approved,
            "risk_approved": self.risk_approved,
            "orders_placed": self.orders_placed,
            "portfolio_value": float(self.portfolio_value) if self.portfolio_value is not None else 0.0,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
