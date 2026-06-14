"""Initial schema — all Phase 1 tables

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # users
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="user"),
        sa.Column("plan", sa.String(50), nullable=False, server_default="free"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # ------------------------------------------------------------------
    # sectors
    # ------------------------------------------------------------------
    op.create_table(
        "sectors",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("code", sa.String(50), nullable=True),
        sa.Column("arabic_name", sa.String(500), nullable=False),
        sa.Column("english_name", sa.String(500), nullable=True),
        sa.Column("market", sa.String(50), nullable=True),
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column("source_url", sa.String(2048), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("code", name="uq_sectors_code"),
    )
    op.create_index("ix_sectors_code", "sectors", ["code"])

    # ------------------------------------------------------------------
    # industry_groups
    # ------------------------------------------------------------------
    op.create_table(
        "industry_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("code", sa.String(50), nullable=True),
        sa.Column("sector_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("arabic_name", sa.String(500), nullable=False),
        sa.Column("english_name", sa.String(500), nullable=True),
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column("source_url", sa.String(2048), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["sector_id"], ["sectors.id"], name="fk_industry_groups_sector"),
        sa.UniqueConstraint("code", name="uq_industry_groups_code"),
    )
    op.create_index("ix_industry_groups_code", "industry_groups", ["code"])
    op.create_index("ix_industry_groups_sector_id", "industry_groups", ["sector_id"])

    # ------------------------------------------------------------------
    # industries
    # ------------------------------------------------------------------
    op.create_table(
        "industries",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("code", sa.String(50), nullable=True),
        sa.Column("industry_group_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("arabic_name", sa.String(500), nullable=False),
        sa.Column("english_name", sa.String(500), nullable=True),
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column("source_url", sa.String(2048), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["industry_group_id"], ["industry_groups.id"], name="fk_industries_group"),
        sa.UniqueConstraint("code", name="uq_industries_code"),
    )
    op.create_index("ix_industries_code", "industries", ["code"])

    # ------------------------------------------------------------------
    # companies
    # ------------------------------------------------------------------
    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("arabic_name", sa.String(500), nullable=False),
        sa.Column("english_name", sa.String(500), nullable=True),
        sa.Column("market", sa.String(50), nullable=True),
        sa.Column("sector_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("industry_group_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("industry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column("source_url", sa.String(2048), nullable=True),
        sa.Column("mapping_status", sa.String(50), nullable=False, server_default="pending_official_mapping"),
        sa.Column("data_status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["sector_id"], ["sectors.id"], name="fk_companies_sector"),
        sa.ForeignKeyConstraint(["industry_group_id"], ["industry_groups.id"], name="fk_companies_industry_group"),
        sa.ForeignKeyConstraint(["industry_id"], ["industries.id"], name="fk_companies_industry"),
        sa.UniqueConstraint("symbol", name="uq_companies_symbol"),
    )
    op.create_index("ix_companies_symbol", "companies", ["symbol"])
    op.create_index("ix_companies_market", "companies", ["market"])
    op.create_index("ix_companies_sector_id", "companies", ["sector_id"])

    # ------------------------------------------------------------------
    # company_profiles
    # ------------------------------------------------------------------
    op.create_table(
        "company_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shares_outstanding", sa.Numeric(24, 0), nullable=True),
        sa.Column("par_value", sa.Numeric(12, 4), nullable=True),
        sa.Column("listing_date", sa.Date(), nullable=True),
        sa.Column("isin", sa.String(20), nullable=True),
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column("source_url", sa.String(2048), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_company_profiles_company"),
        sa.UniqueConstraint("company_id", name="uq_company_profiles_company"),
    )

    # ------------------------------------------------------------------
    # market_data
    # ------------------------------------------------------------------
    op.create_table(
        "market_data",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
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
        sa.Column("trades", sa.Numeric(14, 0), nullable=True),
        sa.Column("market_cap", sa.Numeric(28, 4), nullable=True),
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column("source_url", sa.String(2048), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("symbol", "trade_date", name="uq_market_data_symbol_date"),
    )
    op.create_index("ix_market_data_symbol", "market_data", ["symbol"])
    op.create_index("ix_market_data_trade_date", "market_data", ["trade_date"])

    # ------------------------------------------------------------------
    # announcements
    # ------------------------------------------------------------------
    op.create_table(
        "announcements",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=True),
        sa.Column("market", sa.String(50), nullable=True),
        sa.Column("title_ar", sa.String(2000), nullable=False),
        sa.Column("title_en", sa.String(2000), nullable=True),
        sa.Column("announced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("announcement_type", sa.String(200), nullable=True),
        sa.Column("source_url", sa.String(2048), nullable=True),
        sa.Column("attachment_url", sa.String(2048), nullable=True),
        sa.Column("xbrl_url", sa.String(2048), nullable=True),
        sa.Column("has_xbrl", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_announcements_symbol", "announcements", ["symbol"])
    op.create_index("ix_announcements_announced_at", "announcements", ["announced_at"])

    # ------------------------------------------------------------------
    # xbrl_filings
    # ------------------------------------------------------------------
    op.create_table(
        "xbrl_filings",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("period", sa.String(20), nullable=True),
        sa.Column("period_type", sa.String(30), nullable=True),
        sa.Column("period_status", sa.String(50), nullable=False, server_default="confirmed"),
        sa.Column("language", sa.String(10), nullable=True),
        sa.Column("filing_type", sa.String(20), nullable=True),
        sa.Column("xbrl_url", sa.String(2048), nullable=True),
        sa.Column("announcement_url", sa.String(2048), nullable=True),
        sa.Column("announcement_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reported_date", sa.Date(), nullable=True),
        sa.Column("import_status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["announcement_id"], ["announcements.id"], name="fk_xbrl_filings_announcement"),
    )
    op.create_index("ix_xbrl_filings_symbol", "xbrl_filings", ["symbol"])

    # ------------------------------------------------------------------
    # xbrl_files
    # ------------------------------------------------------------------
    op.create_table(
        "xbrl_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("filing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_url", sa.String(2048), nullable=False),
        sa.Column("local_path", sa.String(1024), nullable=True),
        sa.Column("file_type", sa.String(20), nullable=True),
        sa.Column("download_status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("render_status", sa.String(50), nullable=False, server_default="not_required"),
        sa.Column("error_message", sa.String(2000), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["filing_id"], ["xbrl_filings.id"], name="fk_xbrl_files_filing"),
    )
    op.create_index("ix_xbrl_files_filing_id", "xbrl_files", ["filing_id"])

    # ------------------------------------------------------------------
    # xbrl_raw_items
    # ------------------------------------------------------------------
    op.create_table(
        "xbrl_raw_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("filing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("xbrl_file_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("section_code", sa.String(20), nullable=True),
        sa.Column("section_name_ar", sa.String(500), nullable=True),
        sa.Column("section_name_en", sa.String(500), nullable=True),
        sa.Column("statement_type", sa.String(50), nullable=True),
        sa.Column("label_ar", sa.String(1000), nullable=True),
        sa.Column("label_en", sa.String(1000), nullable=True),
        sa.Column("value", sa.Numeric(28, 4), nullable=True),
        sa.Column("currency", sa.String(10), nullable=False, server_default="SAR"),
        sa.Column("decimals", sa.Integer(), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("parse_confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("source_url", sa.String(2048), nullable=True),
        sa.Column("local_file_path", sa.String(1024), nullable=True),
        sa.Column("parse_status", sa.String(50), nullable=False, server_default="extracted"),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["filing_id"], ["xbrl_filings.id"], name="fk_xbrl_raw_items_filing"),
        sa.ForeignKeyConstraint(["xbrl_file_id"], ["xbrl_files.id"], name="fk_xbrl_raw_items_file"),
    )
    op.create_index("ix_xbrl_raw_items_filing_id", "xbrl_raw_items", ["filing_id"])
    op.create_index("ix_xbrl_raw_items_symbol", "xbrl_raw_items", ["symbol"])
    op.create_index("ix_xbrl_raw_items_section_code", "xbrl_raw_items", ["section_code"])

    # ------------------------------------------------------------------
    # normalized_financials
    # ------------------------------------------------------------------
    op.create_table(
        "normalized_financials",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("period", sa.String(20), nullable=True),
        sa.Column("period_type", sa.String(30), nullable=True),
        sa.Column("filing_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("currency", sa.String(10), nullable=False, server_default="SAR"),
        # Income Statement
        sa.Column("revenue", sa.Numeric(28, 4), nullable=True),
        sa.Column("cost_of_revenue", sa.Numeric(28, 4), nullable=True),
        sa.Column("gross_profit", sa.Numeric(28, 4), nullable=True),
        sa.Column("operating_profit", sa.Numeric(28, 4), nullable=True),
        sa.Column("ebit", sa.Numeric(28, 4), nullable=True),
        sa.Column("finance_cost", sa.Numeric(28, 4), nullable=True),
        sa.Column("zakat_tax", sa.Numeric(28, 4), nullable=True),
        sa.Column("net_income", sa.Numeric(28, 4), nullable=True),
        sa.Column("eps", sa.Numeric(14, 4), nullable=True),
        # Balance Sheet — Assets
        sa.Column("total_assets", sa.Numeric(28, 4), nullable=True),
        sa.Column("current_assets", sa.Numeric(28, 4), nullable=True),
        sa.Column("non_current_assets", sa.Numeric(28, 4), nullable=True),
        sa.Column("cash_and_equivalents", sa.Numeric(28, 4), nullable=True),
        # Balance Sheet — Liabilities
        sa.Column("total_liabilities", sa.Numeric(28, 4), nullable=True),
        sa.Column("current_liabilities", sa.Numeric(28, 4), nullable=True),
        sa.Column("non_current_liabilities", sa.Numeric(28, 4), nullable=True),
        sa.Column("short_term_debt", sa.Numeric(28, 4), nullable=True),
        sa.Column("long_term_debt", sa.Numeric(28, 4), nullable=True),
        sa.Column("total_debt", sa.Numeric(28, 4), nullable=True),
        # Balance Sheet — Equity
        sa.Column("equity", sa.Numeric(28, 4), nullable=True),
        sa.Column("shares_outstanding", sa.Numeric(24, 0), nullable=True),
        # Cash Flow
        sa.Column("operating_cash_flow", sa.Numeric(28, 4), nullable=True),
        sa.Column("investing_cash_flow", sa.Numeric(28, 4), nullable=True),
        sa.Column("financing_cash_flow", sa.Numeric(28, 4), nullable=True),
        sa.Column("capex", sa.Numeric(28, 4), nullable=True),
        sa.Column("dividends_paid", sa.Numeric(28, 4), nullable=True),
        # Metadata
        sa.Column("normalization_status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("missing_fields", postgresql.JSONB(), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["filing_id"], ["xbrl_filings.id"], name="fk_norm_fin_filing"),
        sa.UniqueConstraint("symbol", "fiscal_year", "period", "period_type", name="uq_norm_fin"),
    )
    op.create_index("ix_normalized_financials_symbol", "normalized_financials", ["symbol"])

    # ------------------------------------------------------------------
    # normalization_conflicts
    # ------------------------------------------------------------------
    op.create_table(
        "normalization_conflicts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("normalized_financial_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("raw_item_ids", postgresql.JSONB(), nullable=True),
        sa.Column("conflicting_values", postgresql.JSONB(), nullable=True),
        sa.Column("resolution_status", sa.String(50), nullable=False, server_default="unresolved"),
        sa.Column("resolved_value", sa.Numeric(28, 4), nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["normalized_financial_id"], ["normalized_financials.id"], name="fk_conflicts_norm_fin"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], name="fk_conflicts_resolver"),
    )
    op.create_index("ix_norm_conflicts_norm_fin_id", "normalization_conflicts", ["normalized_financial_id"])

    # ------------------------------------------------------------------
    # calculated_ratios
    # ------------------------------------------------------------------
    op.create_table(
        "calculated_ratios",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("period", sa.String(20), nullable=True),
        sa.Column("period_type", sa.String(20), nullable=True),
        sa.Column("total_debt", sa.Numeric(28, 4), nullable=True),
        sa.Column("net_debt", sa.Numeric(28, 4), nullable=True),
        sa.Column("market_cap", sa.Numeric(28, 4), nullable=True),
        sa.Column("enterprise_value", sa.Numeric(28, 4), nullable=True),
        sa.Column("invested_capital", sa.Numeric(28, 4), nullable=True),
        sa.Column("nopat", sa.Numeric(28, 4), nullable=True),
        sa.Column("fcf", sa.Numeric(28, 4), nullable=True),
        sa.Column("roic", sa.Numeric(12, 6), nullable=True),
        sa.Column("roe", sa.Numeric(12, 6), nullable=True),
        sa.Column("roa", sa.Numeric(12, 6), nullable=True),
        sa.Column("pe", sa.Numeric(12, 4), nullable=True),
        sa.Column("pb", sa.Numeric(12, 4), nullable=True),
        sa.Column("ps", sa.Numeric(12, 4), nullable=True),
        sa.Column("ev_ic", sa.Numeric(12, 4), nullable=True),
        sa.Column("ev_ebit", sa.Numeric(12, 4), nullable=True),
        sa.Column("debt_equity", sa.Numeric(12, 4), nullable=True),
        sa.Column("fcf_yield", sa.Numeric(12, 6), nullable=True),
        sa.Column("gross_margin", sa.Numeric(12, 6), nullable=True),
        sa.Column("operating_margin", sa.Numeric(12, 6), nullable=True),
        sa.Column("net_margin", sa.Numeric(12, 6), nullable=True),
        sa.Column("tax_rate_used", sa.Numeric(6, 4), nullable=False, server_default="0.15"),
        sa.Column("calculation_date", sa.Date(), nullable=False),
        sa.Column("source_period", sa.String(50), nullable=True),
        sa.Column("missing_fields", postgresql.JSONB(), nullable=True),
        sa.Column("calculation_status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("requires_review", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("symbol", "period", "period_type", name="uq_calc_ratio"),
    )
    op.create_index("ix_calculated_ratios_symbol", "calculated_ratios", ["symbol"])

    # ------------------------------------------------------------------
    # screener_snapshot
    # ------------------------------------------------------------------
    op.create_table(
        "screener_snapshot",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("company_name_ar", sa.String(500), nullable=True),
        sa.Column("company_name_en", sa.String(500), nullable=True),
        sa.Column("market", sa.String(50), nullable=True),
        sa.Column("sector_ar", sa.String(500), nullable=True),
        sa.Column("sector_en", sa.String(500), nullable=True),
        sa.Column("latest_price", sa.Numeric(14, 4), nullable=True),
        sa.Column("change_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("market_cap", sa.Numeric(28, 4), nullable=True),
        sa.Column("revenue", sa.Numeric(28, 4), nullable=True),
        sa.Column("net_income", sa.Numeric(28, 4), nullable=True),
        sa.Column("roic", sa.Numeric(12, 6), nullable=True),
        sa.Column("ev_ic", sa.Numeric(12, 4), nullable=True),
        sa.Column("pe", sa.Numeric(12, 4), nullable=True),
        sa.Column("pb", sa.Numeric(12, 4), nullable=True),
        sa.Column("ps", sa.Numeric(12, 4), nullable=True),
        sa.Column("debt_equity", sa.Numeric(12, 4), nullable=True),
        sa.Column("fcf", sa.Numeric(28, 4), nullable=True),
        sa.Column("price_source", sa.String(255), nullable=True),
        sa.Column("financial_source", sa.String(255), nullable=True),
        sa.Column("last_price_update", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_financial_update", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_quality_status", sa.String(50), nullable=False, server_default="missing_financials"),
        sa.Column("snapshot_date", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("symbol", name="uq_screener_snapshot_symbol"),
    )
    op.create_index("ix_screener_snapshot_symbol", "screener_snapshot", ["symbol"])
    op.create_index("ix_screener_snapshot_market", "screener_snapshot", ["market"])
    op.create_index("ix_screener_snapshot_sector_ar", "screener_snapshot", ["sector_ar"])

    # ------------------------------------------------------------------
    # import_jobs
    # ------------------------------------------------------------------
    op.create_table(
        "import_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("job_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.String(4000), nullable=True),
        sa.Column("stats", postgresql.JSONB(), nullable=True),
        sa.Column("triggered_by", sa.String(100), nullable=False, server_default="scheduler"),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_import_jobs_job_type", "import_jobs", ["job_type"])
    op.create_index("ix_import_jobs_status", "import_jobs", ["status"])

    # ------------------------------------------------------------------
    # audit_logs
    # ------------------------------------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(200), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=True),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_audit_logs_user"),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("import_jobs")
    op.drop_table("screener_snapshot")
    op.drop_table("calculated_ratios")
    op.drop_table("normalization_conflicts")
    op.drop_table("normalized_financials")
    op.drop_table("xbrl_raw_items")
    op.drop_table("xbrl_files")
    op.drop_table("xbrl_filings")
    op.drop_table("announcements")
    op.drop_table("market_data")
    op.drop_table("company_profiles")
    op.drop_table("companies")
    op.drop_table("industries")
    op.drop_table("industry_groups")
    op.drop_table("sectors")
    op.drop_table("users")
