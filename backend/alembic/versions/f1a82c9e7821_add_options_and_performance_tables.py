"""add options and performance tables

Revision ID: f1a82c9e7821
Revises: e079da9eee24
Create Date: 2026-08-29 17:37:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f1a82c9e7821'
down_revision: Union[str, None] = 'e079da9eee24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Options Contracts
    op.create_table('options_contracts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('signal_id', sa.String(length=50), nullable=True),
        sa.Column('strategy_id', sa.String(length=50), nullable=False),
        sa.Column('underlying_symbol', sa.String(length=20), nullable=False),
        sa.Column('occ_symbol', sa.String(length=30), nullable=False),
        sa.Column('contract_type', sa.String(length=10), nullable=False),
        sa.Column('strategy_type', sa.String(length=20), nullable=False),
        sa.Column('strike_price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('expiry_date', sa.Date(), nullable=False),
        sa.Column('dte_at_entry', sa.Integer(), nullable=False),
        sa.Column('underlying_price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('premium_paid', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('contracts_qty', sa.Integer(), nullable=False),
        sa.Column('total_cost', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('multiplier', sa.Integer(), server_default='100', nullable=True),
        sa.Column('delta_entry', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('gamma_entry', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('theta_entry', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('vega_entry', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('iv_entry', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('iv_rank_entry', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('profit_target_premium', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('stop_loss_premium', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('time_stop_dte', sa.Integer(), server_default='14', nullable=True),
        sa.Column('breakeven_price', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('status', sa.String(length=10), server_default='open', nullable=False),
        sa.Column('entry_time', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('exit_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('exit_premium', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('exit_reason', sa.String(length=30), nullable=True),
        sa.Column('realized_pnl', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('realized_pnl_pct', sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column('groq_confidence', sa.Integer(), nullable=True),
        sa.Column('groq_reasoning', sa.Text(), nullable=True),
        sa.Column('iv_regime', sa.String(length=10), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_options_contracts_occ', 'options_contracts', ['occ_symbol'], unique=False)
    op.create_index('idx_options_contracts_status', 'options_contracts', ['status'], unique=False)
    op.create_index('idx_options_contracts_underlying', 'options_contracts', ['underlying_symbol'], unique=False)

    # 2. Options Greeks History
    op.create_table('options_greeks_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('contract_id', sa.Integer(), sa.ForeignKey('options_contracts.id', ondelete='CASCADE'), nullable=True),
        sa.Column('occ_symbol', sa.String(length=30), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('underlying_price', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('option_market_price', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('dte_remaining', sa.Integer(), nullable=True),
        sa.Column('delta', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('gamma', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('theta', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('vega', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('implied_volatility', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('unrealized_pnl', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('unrealized_pnl_pct', sa.Numeric(precision=8, scale=4), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # 3. Strategy Performance (Kelly Criterion)
    op.create_table('strategy_performance',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('strategy_id', sa.String(length=50), nullable=False),
        sa.Column('mode', sa.String(length=10), server_default='NORMAL', nullable=False),
        sa.Column('kelly_pct', sa.Numeric(precision=8, scale=4), server_default='0.10', nullable=True),
        sa.Column('quarter_kelly_pct', sa.Numeric(precision=8, scale=4), server_default='0.025', nullable=True),
        sa.Column('win_rate', sa.Numeric(precision=8, scale=4), server_default='0.50', nullable=True),
        sa.Column('avg_win_pct', sa.Numeric(precision=8, scale=4), server_default='0.05', nullable=True),
        sa.Column('avg_loss_pct', sa.Numeric(precision=8, scale=4), server_default='0.025', nullable=True),
        sa.Column('win_loss_ratio', sa.Numeric(precision=8, scale=4), server_default='2.00', nullable=True),
        sa.Column('total_trades', sa.Integer(), server_default='0', nullable=True),
        sa.Column('winning_trades', sa.Integer(), server_default='0', nullable=True),
        sa.Column('losing_trades', sa.Integer(), server_default='0', nullable=True),
        sa.Column('consecutive_wins', sa.Integer(), server_default='0', nullable=True),
        sa.Column('consecutive_losses', sa.Integer(), server_default='0', nullable=True),
        sa.Column('size_multiplier', sa.Numeric(precision=4, scale=2), server_default='1.00', nullable=True),
        sa.Column('peak_pnl', sa.Numeric(precision=10, scale=2), server_default='0.00', nullable=True),
        sa.Column('current_drawdown_pct', sa.Numeric(precision=8, scale=4), server_default='0.00', nullable=True),
        sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('strategy_id')
    )

    # 4. Portfolio State (Circuit Breakers)
    op.create_table('portfolio_state',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('portfolio_value', sa.Numeric(precision=10, scale=2), server_default='100000.00', nullable=False),
        sa.Column('peak_value', sa.Numeric(precision=10, scale=2), server_default='100000.00', nullable=False),
        sa.Column('drawdown_pct', sa.Numeric(precision=8, scale=4), server_default='0.00', nullable=False),
        sa.Column('circuit_breaker_level', sa.Integer(), server_default='0', nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('portfolio_state')
    op.drop_table('strategy_performance')
    op.drop_table('options_greeks_history')
    op.drop_table('options_contracts')
