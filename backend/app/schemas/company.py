from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal
import uuid


class CompanyProfileOut(BaseModel):
    shares_outstanding: Decimal | None
    par_value: Decimal | None
    listing_date: str | None
    isin: str | None
    source: str | None
    source_url: str | None
    imported_at: datetime | None

    model_config = {"from_attributes": True}


class CompanyOut(BaseModel):
    id: uuid.UUID
    symbol: str
    arabic_name: str
    english_name: str | None
    market: str | None
    sector: dict | None = None
    industry_group: dict | None = None
    industry: dict | None = None
    mapping_status: str
    data_status: str
    source: str | None
    source_url: str | None
    last_updated: datetime | None
    imported_at: datetime | None
    profile: CompanyProfileOut | None = None

    model_config = {"from_attributes": True}


class CompanySummary(BaseModel):
    id: uuid.UUID
    symbol: str
    arabic_name: str
    english_name: str | None
    market: str | None
    sector_ar: str | None = None
    sector_en: str | None = None
    mapping_status: str
    data_status: str

    model_config = {"from_attributes": True}
