from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal
import uuid


class ScreenerRow(BaseModel):
    id: uuid.UUID
    symbol: str
    company_name_ar: str | None
    company_name_en: str | None
    market: str | None
    sector_ar: str | None
    sector_en: str | None
    latest_price: Decimal | None
    change_pct: Decimal | None
    market_cap: Decimal | None
    revenue: Decimal | None
    net_income: Decimal | None
    roic: Decimal | None
    ev_ic: Decimal | None
    pe: Decimal | None
    pb: Decimal | None
    ps: Decimal | None
    debt_equity: Decimal | None
    fcf: Decimal | None
    price_source: str | None
    financial_source: str | None
    last_price_update: datetime | None
    last_financial_update: datetime | None
    data_quality_status: str

    model_config = {"from_attributes": True}


class ScreenerFilters(BaseModel):
    market: str | None = None
    sector: str | None = None
    min_market_cap: Decimal | None = None
    max_market_cap: Decimal | None = None
    min_roic: Decimal | None = None
    max_pe: Decimal | None = None
    min_fcf: Decimal | None = None
    data_quality_status: str | None = None
    page: int = 1
    per_page: int = 50
