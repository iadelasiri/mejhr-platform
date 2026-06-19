"""Phase 2D.3 — Add index_prices table.

Daily OHLCV price history for TASI, MT30, and other Saudi Exchange indices.
MarketIndex remains a catalogue table (code/name/type); this table holds
the daily time series. See PHASE_2D2_DISCOVERY.md for the source spec.

Revision ID: 010
Revises: 009
Create Date: 2026-06-20 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "index_prices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("index_code", sa.String(20), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(14, 4), nullable=True),
        sa.Column("high", sa.Numeric(14, 4), nullable=True),
        sa.Column("low", sa.Numeric(14, 4), nullable=True),
        sa.Column("close", sa.Numeric(14, 4), nullable=True),
        sa.Column("previous_close", sa.Numeric(14, 4), nullable=True),
        sa.Column("change_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("change_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("volume", sa.Numeric(24, 0), nullable=True),
        sa.Column("turnover", sa.Numeric(24, 4), nullable=True),
        sa.Column("trades_count", sa.Numeric(14, 0), nullable=True),
        sa.Column("trade_date_derivation", sa.String(80), nullable=False),
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column("source_url", sa.String(2048), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("index_code", "trade_date", name="uq_index_price_code_date"),
    )
    op.create_index("ix_index_prices_index_code", "index_prices", ["index_code"])
    op.create_index("ix_index_prices_trade_date", "index_prices", ["trade_date"])


def downgrade() -> None:
    op.drop_index("ix_index_prices_trade_date", table_name="index_prices")
    op.drop_index("ix_index_prices_index_code", table_name="index_prices")
    op.drop_table("index_prices")
