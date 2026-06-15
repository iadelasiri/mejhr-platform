"""Phase 2F — XBRL raw fact columns on xbrl_raw_items.

Adds the columns required to store parsed XBRL facts with full traceability:
  company_id, concept_name, concept_namespace,
  value_raw, value_numeric, unit_ref, context_ref,
  instant_date, fiscal_year, fiscal_period, data_status

Existing rows (none in production yet) receive empty-string default for
concept_name and 'official' default for data_status.

Revision ID: 005
Revises: 004
Create Date: 2026-06-16 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "xbrl_raw_items",
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", name="fk_xbrl_raw_items_company"),
            nullable=True,
        ),
    )
    op.add_column(
        "xbrl_raw_items",
        sa.Column("concept_name", sa.String(500), nullable=False, server_default=""),
    )
    op.add_column(
        "xbrl_raw_items",
        sa.Column("concept_namespace", sa.String(500), nullable=True),
    )
    op.add_column(
        "xbrl_raw_items",
        sa.Column("value_raw", sa.String(2000), nullable=True),
    )
    op.add_column(
        "xbrl_raw_items",
        sa.Column("value_numeric", sa.Numeric(28, 4), nullable=True),
    )
    op.add_column(
        "xbrl_raw_items",
        sa.Column("unit_ref", sa.String(100), nullable=True),
    )
    op.add_column(
        "xbrl_raw_items",
        sa.Column("context_ref", sa.String(500), nullable=True),
    )
    op.add_column(
        "xbrl_raw_items",
        sa.Column("instant_date", sa.Date, nullable=True),
    )
    op.add_column(
        "xbrl_raw_items",
        sa.Column("fiscal_year", sa.Integer, nullable=True),
    )
    op.add_column(
        "xbrl_raw_items",
        sa.Column("fiscal_period", sa.String(20), nullable=True),
    )
    op.add_column(
        "xbrl_raw_items",
        sa.Column("data_status", sa.String(50), nullable=False, server_default="official"),
    )

    op.create_index("ix_xbrl_raw_items_company_id", "xbrl_raw_items", ["company_id"])
    op.create_index("ix_xbrl_raw_items_concept_name", "xbrl_raw_items", ["concept_name"])


def downgrade() -> None:
    op.drop_index("ix_xbrl_raw_items_concept_name", table_name="xbrl_raw_items")
    op.drop_index("ix_xbrl_raw_items_company_id", table_name="xbrl_raw_items")

    op.drop_column("xbrl_raw_items", "data_status")
    op.drop_column("xbrl_raw_items", "fiscal_period")
    op.drop_column("xbrl_raw_items", "fiscal_year")
    op.drop_column("xbrl_raw_items", "instant_date")
    op.drop_column("xbrl_raw_items", "context_ref")
    op.drop_column("xbrl_raw_items", "unit_ref")
    op.drop_column("xbrl_raw_items", "value_numeric")
    op.drop_column("xbrl_raw_items", "value_raw")
    op.drop_column("xbrl_raw_items", "concept_namespace")
    op.drop_column("xbrl_raw_items", "concept_name")
    op.drop_column("xbrl_raw_items", "company_id")
