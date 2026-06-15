"""Phase 2E.1 — XBRL renderer fields on xbrl_files.

Adds columns to track Playwright-based rendering of Saudi Exchange HTML viewer
files:
  rendered_path       — path to the saved rendered HTML snapshot
  selected_sections   — JSON list of section codes that were selected
  rendered_at         — timestamp when rendering completed
  render_warnings     — semicolon-separated list of any render warnings

Revision ID: 006
Revises: 005
Create Date: 2026-06-16 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "xbrl_files",
        sa.Column("rendered_path", sa.String(1024), nullable=True),
    )
    op.add_column(
        "xbrl_files",
        sa.Column("selected_sections", sa.Text, nullable=True),
    )
    op.add_column(
        "xbrl_files",
        sa.Column("rendered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "xbrl_files",
        sa.Column("render_warnings", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("xbrl_files", "render_warnings")
    op.drop_column("xbrl_files", "rendered_at")
    op.drop_column("xbrl_files", "selected_sections")
    op.drop_column("xbrl_files", "rendered_path")
