"""Phase 2G.1 — Add reporting_scale and source_map to normalized_financials.

reporting_scale: integer scale factor applied (1, 1000, or 1000000) — read from
  filing_info label 'مستوى التقريب المستخدم في القوائم المالية'.
source_map: JSONB dict of field_name → {raw_item_id, label_ar, context_ref} —
  provides per-field traceability back to the raw XBRL item.

Revision ID: 007
Revises: 006
Create Date: 2026-06-17 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "normalized_financials",
        sa.Column("reporting_scale", sa.Integer, nullable=True),
    )
    op.add_column(
        "normalized_financials",
        sa.Column("source_map", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("normalized_financials", "source_map")
    op.drop_column("normalized_financials", "reporting_scale")
