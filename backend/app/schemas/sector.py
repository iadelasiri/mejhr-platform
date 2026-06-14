from pydantic import BaseModel
from datetime import datetime
import uuid


class IndustryOut(BaseModel):
    id: uuid.UUID
    code: str | None
    arabic_name: str
    english_name: str | None

    model_config = {"from_attributes": True}


class IndustryGroupOut(BaseModel):
    id: uuid.UUID
    code: str | None
    arabic_name: str
    english_name: str | None
    industries: list[IndustryOut] = []

    model_config = {"from_attributes": True}


class SectorOut(BaseModel):
    id: uuid.UUID
    code: str | None
    arabic_name: str
    english_name: str | None
    market: str | None
    source: str | None
    source_url: str | None
    imported_at: datetime | None
    last_updated: datetime | None
    industry_groups: list[IndustryGroupOut] = []

    model_config = {"from_attributes": True}


class SectorSummary(BaseModel):
    id: uuid.UUID
    code: str | None
    arabic_name: str
    english_name: str | None
    market: str | None

    model_config = {"from_attributes": True}
