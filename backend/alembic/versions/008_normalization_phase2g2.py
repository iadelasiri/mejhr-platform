"""Phase 2G.2 — Add profit_before_tax to normalized_financials.

Missing from the initial schema; required for IS normalization.
Separate from zakat_tax and net_income so each line item is traceable.

Revision ID: 008
Revises: 007
Create Date: 2026-06-17 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "normalized_financials",
        sa.Column("profit_before_tax", sa.Numeric(28, 4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("normalized_financials", "profit_before_tax")
