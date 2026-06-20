"""
Read-only response schemas for company daily prices (market_data) and
index daily prices (index_prices). Only stored columns are exposed — no
ratios, EPS, P/E, ROIC, EBIT, EBITDA, or any other calculated/valuation
field.
"""
from pydantic import BaseModel
from datetime import date
from decimal import Decimal


class CompanyPriceOut(BaseModel):
    """
    Latest known daily price for a company symbol.

    open/high/low/previous_close are intentionally NOT included as fields
    here (not even as always-null) — the Saudi Exchange ingestion path for
    company prices does not provide full OHLC, and exposing those keys
    (even null) would imply complete OHLC data exists. See
    PHASE_2D5_DISCOVERY.md.
    """
    symbol: str
    trade_date: date
    close: Decimal | None = None
    change_amount: Decimal | None = None
    change_pct: Decimal | None = None
    volume: Decimal | None = None
    turnover: Decimal | None = None
    trades_count: Decimal | None = None
    source: str | None = None
    source_url: str | None = None


class IndexPriceOut(BaseModel):
    """
    Latest known daily price for one market/sector index.

    high/low are populated only for indices where Saudi Exchange provides
    full OHLCV (TASI, MT30); other indices keep these NULL — never
    fabricated. index_name_ar/en are populated only when a matching
    market_indices catalogue row exists (index_code is not an FK).
    """
    index_code: str
    index_name_ar: str | None = None
    index_name_en: str | None = None
    trade_date: date
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    previous_close: Decimal | None = None
    change_amount: Decimal | None = None
    change_pct: Decimal | None = None
    volume: Decimal | None = None
    turnover: Decimal | None = None
    trades_count: Decimal | None = None
    trade_date_derivation: str | None = None
    source: str | None = None
    source_url: str | None = None
