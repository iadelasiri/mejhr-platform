"""
Phase 2G.4 — Read-only response schemas for GET /companies/{symbol}/financials.

No ratios, no EPS, no valuation fields. Only normalized fields populated by
Phase 2G.1 / 2G.2 / 2G.3 are exposed.
"""
from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal


class CompanyFinancialSummary(BaseModel):
    symbol: str
    arabic_name: str
    english_name: str | None
    market: str | None
    sector_ar: str | None = None
    sector_en: str | None = None

    model_config = {"from_attributes": True}


class ConflictSummary(BaseModel):
    field_name: str
    resolution_status: str
    candidate_count: int


class NormalizedFinancialFields(BaseModel):
    """The 17 fields normalized through Phase 2G.1–2G.3. No ratios, no EPS."""

    # Income Statement
    revenue: Decimal | None = None
    finance_cost: Decimal | None = None
    profit_before_tax: Decimal | None = None
    zakat_tax: Decimal | None = None
    net_income: Decimal | None = None
    # Balance Sheet
    total_assets: Decimal | None = None
    total_liabilities: Decimal | None = None
    equity: Decimal | None = None
    cash_and_equivalents: Decimal | None = None
    short_term_debt: Decimal | None = None
    long_term_debt: Decimal | None = None
    total_debt: Decimal | None = None
    # Cash Flow
    operating_cash_flow: Decimal | None = None
    investing_cash_flow: Decimal | None = None
    financing_cash_flow: Decimal | None = None
    capex: Decimal | None = None
    free_cash_flow: Decimal | None = None

    model_config = {"from_attributes": True}


class CompanyFinancialsOut(BaseModel):
    company: CompanyFinancialSummary
    fiscal_year: int | None
    fiscal_period: str | None
    reporting_scale: int | None
    financials: NormalizedFinancialFields
    source_map: dict | None
    missing_fields: list[str]
    conflicts: list[ConflictSummary]
    data_status: str
    imported_at: datetime | None
    created_at: datetime | None
