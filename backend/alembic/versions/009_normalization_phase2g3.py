"""Phase 2G.3 — Add free_cash_flow to normalized_financials.

Derived field: operating_cash_flow + capex (capex stored as negative outflow).
Stored here rather than in calculated_ratios because it is a direct pipeline
output from XBRL data, not a market-data ratio.

Revision ID: 009
Revises: 008
Create Date: 2026-06-17 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "normalized_financials",
        sa.Column("free_cash_flow", sa.Numeric(28, 4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("normalized_financials", "free_cash_flow")
