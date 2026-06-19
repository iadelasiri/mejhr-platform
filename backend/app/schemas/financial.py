"""
Phase 2G.5 — Read-only response schemas for GET /companies/{symbol}/financials.

Response is organized into sections matching the future company page layout:
company, filing, balance_sheet, income_statement, cash_flow, data_quality,
metadata. No ratios, no EPS, no EBITDA, no gross_profit/operating_profit, no
valuation. Only normalized fields populated by Phase 2G.1-2G.3 are exposed.
"""
from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal


class CompanySection(BaseModel):
    symbol: str
    name_ar: str
    name_en: str | None
    market: str | None
    sector_ar: str | None = None
    sector_en: str | None = None


class FilingSection(BaseModel):
    fiscal_year: int | None
    # Literal filing period label, e.g. "Annual", "Q1" — kept alongside
    # period_type since period_type alone ("annual") cannot distinguish Q1
    # from Q2 for quarterly filings.
    period: str | None
    period_type: str | None
    reporting_scale: int | None
    # Not yet captured by the normalization pipeline (no schema column).
    # Always None until a future phase adds it — see NORMALIZATION_SPEC §12A.
    is_consolidated: bool | None = None
    normalization_status: str


class BalanceSheetSection(BaseModel):
    total_assets: Decimal | None = None
    total_liabilities: Decimal | None = None
    equity: Decimal | None = None
    cash_and_equivalents: Decimal | None = None
    short_term_debt: Decimal | None = None
    long_term_debt: Decimal | None = None
    total_debt: Decimal | None = None

    model_config = {"from_attributes": True}


class IncomeStatementSection(BaseModel):
    revenue: Decimal | None = None
    finance_cost: Decimal | None = None
    profit_before_tax: Decimal | None = None
    zakat_tax: Decimal | None = None
    net_income: Decimal | None = None

    model_config = {"from_attributes": True}


class CashFlowSection(BaseModel):
    operating_cash_flow: Decimal | None = None
    investing_cash_flow: Decimal | None = None
    financing_cash_flow: Decimal | None = None
    capex: Decimal | None = None
    free_cash_flow: Decimal | None = None

    model_config = {"from_attributes": True}


class ConflictSummary(BaseModel):
    field_name: str
    resolution_status: str
    candidate_count: int


class DataQualitySection(BaseModel):
    missing_fields: list[str]
    conflict_count: int
    conflicts: list[ConflictSummary]
    source_map_available: bool
    source_map: dict | None = None


class ResponseMetadata(BaseModel):
    generated_at: datetime
    data_source: str = "saudi_exchange_xbrl"
    manual_override: bool = False


class CompanyFinancialsOut(BaseModel):
    company: CompanySection
    filing: FilingSection
    balance_sheet: BalanceSheetSection
    income_statement: IncomeStatementSection
    cash_flow: CashFlowSection
    data_quality: DataQualitySection
    metadata: ResponseMetadata
