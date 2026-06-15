"""Add market_indices table; make sectors.arabic_name nullable.

Arabic names for TASI sectors are not available from the Saudi Exchange
HTML widget source (only English names are provided). Making arabic_name
nullable allows honest import without placeholder data.

Revision ID: 002
Revises: 001
Create Date: 2026-06-15 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # sectors.arabic_name: NOT NULL → nullable (no Arabic source found)
    op.alter_column("sectors", "arabic_name", existing_type=sa.String(500), nullable=True)

    op.create_table(
        "market_indices",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("arabic_name", sa.String(500), nullable=True),
        sa.Column("english_name", sa.String(500), nullable=True),
        sa.Column("index_type", sa.String(50), nullable=True),
        sa.Column("sector_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("market", sa.String(50), nullable=True),
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column("source_url", sa.String(2048), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["sector_id"], ["sectors.id"], name="fk_market_indices_sector"
        ),
        sa.UniqueConstraint("code", name="uq_market_indices_code"),
    )
    op.create_index("ix_market_indices_code", "market_indices", ["code"])
    op.create_index("ix_market_indices_sector_id", "market_indices", ["sector_id"])


def downgrade() -> None:
    op.drop_index("ix_market_indices_sector_id", table_name="market_indices")
    op.drop_index("ix_market_indices_code", table_name="market_indices")
    op.drop_table("market_indices")
    op.alter_column("sectors", "arabic_name", existing_type=sa.String(500), nullable=False)
