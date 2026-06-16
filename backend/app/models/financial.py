from sqlalchemy import String, Date, DateTime, ForeignKey, Integer, Numeric, Boolean, text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime, date
from decimal import Decimal
import uuid

from app.models.base import Base


class NormalizedFinancial(Base):
    """
    Normalized financial statement for a company/period.
    Maps raw XBRL items to standard fields.
    No values are invented — missing fields remain NULL.
    """

    __tablename__ = "normalized_financials"
    __table_args__ = (
        UniqueConstraint("symbol", "fiscal_year", "period", "period_type", name="uq_norm_fin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    fiscal_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    period: Mapped[str | None] = mapped_column(String(20), nullable=True)
    period_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    filing_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("xbrl_filings.id"), nullable=True
    )
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="SAR")

    # Income Statement
    revenue: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    cost_of_revenue: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    gross_profit: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    operating_profit: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    ebit: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    finance_cost: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    profit_before_tax: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    zakat_tax: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    net_income: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    eps: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)

    # Balance Sheet — Assets
    total_assets: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    current_assets: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    non_current_assets: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    cash_and_equivalents: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)

    # Balance Sheet — Liabilities
    total_liabilities: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    current_liabilities: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    non_current_liabilities: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    short_term_debt: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    long_term_debt: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    total_debt: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)

    # Balance Sheet — Equity
    equity: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    shares_outstanding: Mapped[Decimal | None] = mapped_column(Numeric(24, 0), nullable=True)

    # Cash Flow Statement
    operating_cash_flow: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    investing_cash_flow: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    financing_cash_flow: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    capex: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    dividends_paid: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)

    # Normalization metadata
    reporting_scale: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_map: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # normalization_status: pending | normalized | partial | conflict | failed
    normalization_status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    missing_fields: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )

    conflicts: Mapped[list["NormalizationConflict"]] = relationship(
        "NormalizationConflict", back_populates="normalized_financial", lazy="selectin"
    )


class NormalizationConflict(Base):
    """
    Multiple raw XBRL items mapped to the same normalized field.
    Requires manual review before a value is accepted.
    """

    __tablename__ = "normalization_conflicts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    normalized_financial_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("normalized_financials.id"), nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Array of xbrl_raw_items IDs that conflict
    raw_item_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Array of {value, label_ar, label_en, source_url}
    conflicting_values: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # resolution_status: unresolved | manually_resolved | auto_resolved
    resolution_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="unresolved"
    )
    resolved_value: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )

    normalized_financial: Mapped["NormalizedFinancial"] = relationship(
        "NormalizedFinancial", back_populates="conflicts"
    )


class CalculatedRatio(Base):
    """
    Calculated financial ratios derived from normalized financials and market data.
    Missing input fields are stored in missing_fields — no values are invented.
    """

    __tablename__ = "calculated_ratios"
    __table_args__ = (
        UniqueConstraint("symbol", "period", "period_type", name="uq_calc_ratio"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    period: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # period_type: annual | quarterly | ttm | latest
    period_type: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Derived aggregates
    total_debt: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    net_debt: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    market_cap: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    enterprise_value: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    invested_capital: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    nopat: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    fcf: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)

    # Return metrics
    roic: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    roe: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    roa: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)

    # Valuation multiples
    pe: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    pb: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    ps: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    ev_ic: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    ev_ebit: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)

    # Leverage
    debt_equity: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)

    # Yields and margins
    fcf_yield: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    gross_margin: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    operating_margin: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    net_margin: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)

    # Calculation metadata
    tax_rate_used: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.15"))
    calculation_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_period: Mapped[str | None] = mapped_column(String(50), nullable=True)
    missing_fields: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # calculation_status: complete | partial | failed
    calculation_status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    # True if invested_capital <= 0 or other edge cases
    requires_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
