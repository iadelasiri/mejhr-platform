from sqlalchemy import String, DateTime, ForeignKey, Date, Numeric, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime, date
from decimal import Decimal
import uuid

from app.models.base import Base


class Company(Base):
    """Master record for a Saudi-listed company. Names and sector from Saudi Exchange only."""

    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    symbol: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    arabic_name: Mapped[str] = mapped_column(String(500), nullable=False)
    english_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # market: tadawul | nomu
    market: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    sector_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sectors.id"), nullable=True, index=True
    )
    industry_group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("industry_groups.id"), nullable=True
    )
    industry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("industries.id"), nullable=True
    )
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # mapping_status: mapped | pending_official_mapping | pending
    mapping_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending_official_mapping"
    )
    # data_status: sample_not_official | official | pending
    data_status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    # Provenance for sector mapping: {source_url, mapping_source, reviewed_at, confidence}
    sector_mapping_info: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )

    sector: Mapped["Sector | None"] = relationship("Sector", lazy="selectin")  # type: ignore[name-defined]
    industry_group: Mapped["IndustryGroup | None"] = relationship("IndustryGroup", lazy="selectin")  # type: ignore[name-defined]
    industry: Mapped["Industry | None"] = relationship("Industry", lazy="selectin")  # type: ignore[name-defined]
    profile: Mapped["CompanyProfile | None"] = relationship(
        "CompanyProfile", back_populates="company", uselist=False, lazy="selectin"
    )


class CompanyProfile(Base):
    """Extended profile for a company (shares outstanding, listing info, etc.)."""

    __tablename__ = "company_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), unique=True, nullable=False
    )
    shares_outstanding: Mapped[Decimal | None] = mapped_column(Numeric(24, 0), nullable=True)
    par_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    listing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    isin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )

    company: Mapped["Company"] = relationship("Company", back_populates="profile")
