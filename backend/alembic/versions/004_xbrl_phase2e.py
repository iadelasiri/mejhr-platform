"""Phase 2E — XBRL filing discovery and download columns.

Adds:
  xbrl_filings:
    - company_id   UUID FK → companies.id   (nullable, populated on discovery)
    - data_status  VARCHAR(50)  default='official'
    - unique constraint on (symbol, xbrl_url) for idempotent discovery

  xbrl_files:
    - file_hash        VARCHAR(64)   SHA-256 hex digest for dedup
    - file_size_bytes  BIGINT        nullable
    - data_status      VARCHAR(50)   default='official'
    - unique constraint on file_hash (non-null) handled at app layer

Revision ID: 004
Revises: 003
Create Date: 2026-06-15 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── xbrl_filings ──────────────────────────────────────────────────────────
    op.add_column(
        "xbrl_filings",
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", name="fk_xbrl_filings_company"),
            nullable=True,
        ),
    )
    op.add_column(
        "xbrl_filings",
        sa.Column("data_status", sa.String(50), nullable=False, server_default="official"),
    )
    op.create_index("ix_xbrl_filings_company_id", "xbrl_filings", ["company_id"])

    # Unique constraint: one filing record per (symbol, xbrl_url) — prevents
    # duplicate discovery rows for the same XBRL file URL.
    # NULL xbrl_url rows are excluded (NULLS are not equal in unique constraints).
    op.create_index(
        "uq_xbrl_filings_symbol_url",
        "xbrl_filings",
        ["symbol", "xbrl_url"],
        unique=True,
        postgresql_where=sa.text("xbrl_url IS NOT NULL"),
    )

    # ── xbrl_files ────────────────────────────────────────────────────────────
    op.add_column(
        "xbrl_files",
        sa.Column("file_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "xbrl_files",
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "xbrl_files",
        sa.Column("data_status", sa.String(50), nullable=False, server_default="official"),
    )
    op.create_index("ix_xbrl_files_file_hash", "xbrl_files", ["file_hash"])


def downgrade() -> None:
    op.drop_index("ix_xbrl_files_file_hash", table_name="xbrl_files")
    op.drop_column("xbrl_files", "data_status")
    op.drop_column("xbrl_files", "file_size_bytes")
    op.drop_column("xbrl_files", "file_hash")

    op.drop_index("uq_xbrl_filings_symbol_url", table_name="xbrl_filings")
    op.drop_index("ix_xbrl_filings_company_id", table_name="xbrl_filings")
    op.drop_column("xbrl_filings", "data_status")
    op.drop_column("xbrl_filings", "company_id")
