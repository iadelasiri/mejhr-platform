"""Add sector_mapping_info JSONB to companies.

Stores provenance metadata for company→sector mapping:
  source_url, mapping_source, reviewed_at, confidence.

Revision ID: 003
Revises: 002
Create Date: 2026-06-15 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("sector_mapping_info", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("companies", "sector_mapping_info")
