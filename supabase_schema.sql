-- 1. POSITIONS TABLE (Main Live & Paper Positions)
CREATE TABLE IF NOT EXISTS positions (
    id                    SERIAL PRIMARY KEY,
    strategy_id           VARCHAR(50) NOT NULL,
    symbol                VARCHAR(20) NOT NULL,
    source                VARCHAR(20) NOT NULL DEFAULT 'alpaca',
    timeframe             VARCHAR(10) NOT NULL DEFAULT '1D',
    signal_type           VARCHAR(20) NOT NULL,
    entry_price           DECIMAL(20, 8) NOT NULL,
    entry_time            TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    allocated_capital     DECIMAL(20, 2) NOT NULL,
    quantity              DECIMAL(20, 8) NOT NULL,
    status                VARCHAR(10) NOT NULL DEFAULT 'open',
    exit_price            DECIMAL(20, 8),
    exit_time             TIMESTAMP WITH TIME ZONE,
    realized_pnl          DECIMAL(20, 2),
    realized_pnl_pct      DECIMAL(10, 4),
    groq_confidence       INTEGER,
    groq_reasoning        TEXT,
    groq_go               BOOLEAN,
    risk_approved         BOOLEAN,
    risk_block_reason     TEXT,
    asset_class           VARCHAR(20) NOT NULL DEFAULT 'stock',
    option_symbol         VARCHAR(30),
    option_type           VARCHAR(10),
    strike_price          DECIMAL(15, 4),
    expiration_date       VARCHAR(20),
    contracts             INTEGER,
    contract_premium      DECIMAL(15, 4),
    delta                 DECIMAL(10, 4),
    gamma                 DECIMAL(10, 4),
    theta                 DECIMAL(10, 4),
    vega                  DECIMAL(10, 4),
    implied_volatility    DECIMAL(10, 4),
    underlying_price      DECIMAL(20, 8),
    created_at            TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_positions_strategy_symbol ON positions(strategy_id, symbol);
CREATE INDEX IF NOT EXISTS idx_positions_option_symbol ON positions(option_symbol);


-- 2. AGENT CYCLES TABLE (Autonomous Orchestrator Scans)
CREATE TABLE IF NOT EXISTS agent_cycles (
    id                    SERIAL PRIMARY KEY,
    cycle_time            TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    timeframe_scope       VARCHAR(10) NOT NULL,
    symbols_scanned       INTEGER DEFAULT 0,
    signals_detected      INTEGER DEFAULT 0,
    groq_approved         INTEGER DEFAULT 0,
    risk_approved         INTEGER DEFAULT 0,
    orders_placed         INTEGER DEFAULT 0,
    portfolio_value       DECIMAL(20, 2) DEFAULT 100000.00,
    notes                 TEXT,
    created_at            TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_cycles_time ON agent_cycles(cycle_time DESC);


-- 3. OPTIONS CONTRACTS TABLE (Options Specifications & Greeks)
CREATE TABLE IF NOT EXISTS options_contracts (
    id                    SERIAL PRIMARY KEY,
    signal_id             VARCHAR(50),
    strategy_id           VARCHAR(50) NOT NULL,
    underlying_symbol     VARCHAR(20) NOT NULL,
    occ_symbol            VARCHAR(30) NOT NULL,
    contract_type         VARCHAR(10) NOT NULL,
    strategy_type         VARCHAR(20) NOT NULL,
    strike_price          DECIMAL(10, 2) NOT NULL,
    expiry_date           DATE NOT NULL,
    dte_at_entry          INTEGER NOT NULL,
    underlying_price      DECIMAL(10, 2) NOT NULL,
    premium_paid          DECIMAL(10, 4) NOT NULL,
    contracts_qty         INTEGER NOT NULL,
    total_cost            DECIMAL(10, 2) NOT NULL,
    multiplier            INTEGER DEFAULT 100,
    delta_entry           DECIMAL(6, 4),
    gamma_entry           DECIMAL(6, 4),
    theta_entry           DECIMAL(6, 4),
    vega_entry            DECIMAL(6, 4),
    iv_entry              DECIMAL(6, 4),
    iv_rank_entry         DECIMAL(6, 2),
    profit_target_premium DECIMAL(10, 4),
    stop_loss_premium     DECIMAL(10, 4),
    time_stop_dte         INTEGER DEFAULT 14,
    breakeven_price       DECIMAL(10, 2),
    status                VARCHAR(10) NOT NULL DEFAULT 'open',
    entry_time            TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    exit_time             TIMESTAMP WITH TIME ZONE,
    exit_premium          DECIMAL(10, 4),
    exit_reason           VARCHAR(30),
    realized_pnl          DECIMAL(10, 2),
    realized_pnl_pct      DECIMAL(8, 4),
    groq_confidence       INTEGER,
    groq_reasoning        TEXT,
    iv_regime             VARCHAR(10),
    created_at            TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_options_contracts_occ ON options_contracts(occ_symbol);
CREATE INDEX IF NOT EXISTS idx_options_contracts_status ON options_contracts(status);
CREATE INDEX IF NOT EXISTS idx_options_contracts_underlying ON options_contracts(underlying_symbol);


-- 4. OPTIONS GREEKS HISTORY (Lifecycle Monitoring)
CREATE TABLE IF NOT EXISTS options_greeks_history (
    id                    SERIAL PRIMARY KEY,
    contract_id           INTEGER REFERENCES options_contracts(id) ON DELETE CASCADE,
    occ_symbol            VARCHAR(30) NOT NULL,
    recorded_at           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    underlying_price      DECIMAL(10, 2),
    option_market_price   DECIMAL(10, 4),
    dte_remaining         INTEGER,
    delta                 DECIMAL(6, 4),
    gamma                 DECIMAL(6, 4),
    theta                 DECIMAL(6, 4),
    vega                  DECIMAL(6, 4),
    implied_volatility    DECIMAL(6, 4),
    unrealized_pnl        DECIMAL(10, 2),
    unrealized_pnl_pct    DECIMAL(8, 4)
);

CREATE INDEX IF NOT EXISTS idx_greeks_history_contract ON options_greeks_history(contract_id, recorded_at DESC);


-- 5. OPTIONS DAILY SNAPSHOTS
CREATE TABLE IF NOT EXISTS options_daily_snapshots (
    id                    SERIAL PRIMARY KEY,
    snapshot_date         DATE NOT NULL UNIQUE,
    total_positions       INTEGER DEFAULT 0,
    total_capital_deployed DECIMAL(10, 2) DEFAULT 0.00,
    total_current_value   DECIMAL(10, 2) DEFAULT 0.00,
    unrealized_pnl        DECIMAL(10, 2) DEFAULT 0.00,
    realized_pnl_today    DECIMAL(10, 2) DEFAULT 0.00,
    portfolio_delta       DECIMAL(8, 4) DEFAULT 0.00,
    portfolio_theta       DECIMAL(8, 4) DEFAULT 0.00,
    portfolio_vega        DECIMAL(8, 4) DEFAULT 0.00,
    cash_balance          DECIMAL(10, 2) DEFAULT 100000.00,
    recorded_at           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);


-- 6. OPTIONS CYCLE LOGS
CREATE TABLE IF NOT EXISTS options_cycle_logs (
    id                    SERIAL PRIMARY KEY,
    cycle_time            TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    underlyings_evaluated INTEGER DEFAULT 0,
    signals_received      INTEGER DEFAULT 0,
    contracts_evaluated   INTEGER DEFAULT 0,
    gates_passed          INTEGER DEFAULT 0,
    orders_submitted      INTEGER DEFAULT 0,
    orders_filled         INTEGER DEFAULT 0,
    active_monitored      INTEGER DEFAULT 0,
    exits_triggered       INTEGER DEFAULT 0,
    notes                 TEXT
);


-- 7. STRATEGY PERFORMANCE (Kelly Criterion & Performance Modes)
CREATE TABLE IF NOT EXISTS strategy_performance (
    id                    SERIAL PRIMARY KEY,
    strategy_id           VARCHAR(50) UNIQUE NOT NULL,
    mode                  VARCHAR(10) NOT NULL DEFAULT 'NORMAL',
    kelly_pct             DECIMAL(8, 4) DEFAULT 0.10,
    quarter_kelly_pct     DECIMAL(8, 4) DEFAULT 0.025,
    win_rate              DECIMAL(8, 4) DEFAULT 0.50,
    avg_win_pct           DECIMAL(8, 4) DEFAULT 0.05,
    avg_loss_pct          DECIMAL(8, 4) DEFAULT 0.025,
    win_loss_ratio        DECIMAL(8, 4) DEFAULT 2.00,
    total_trades          INTEGER DEFAULT 0,
    winning_trades        INTEGER DEFAULT 0,
    losing_trades         INTEGER DEFAULT 0,
    consecutive_wins      INTEGER DEFAULT 0,
    consecutive_losses    INTEGER DEFAULT 0,
    size_multiplier       DECIMAL(4, 2) DEFAULT 1.00,
    peak_pnl              DECIMAL(10, 2) DEFAULT 0.00,
    current_drawdown_pct  DECIMAL(8, 4) DEFAULT 0.00,
    last_updated          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);


-- 8. PORTFOLIO STATE (Peak Tracking & 5-Level Circuit Breaker)
CREATE TABLE IF NOT EXISTS portfolio_state (
    id                    SERIAL PRIMARY KEY,
    portfolio_value       DECIMAL(10, 2) NOT NULL DEFAULT 100000.00,
    peak_value            DECIMAL(10, 2) NOT NULL DEFAULT 100000.00,
    drawdown_pct          DECIMAL(8, 4) NOT NULL DEFAULT 0.00,
    circuit_breaker_level INTEGER NOT NULL DEFAULT 0,
    recorded_at           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Seed initial portfolio baseline state
INSERT INTO portfolio_state (portfolio_value, peak_value, drawdown_pct, circuit_breaker_level)
VALUES (100000.00, 100000.00, 0.00, 0)
ON CONFLICT DO NOTHING;
