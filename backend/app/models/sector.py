from sqlalchemy import String, DateTime, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

from app.models.base import Base


class Sector(Base):
    """Official Saudi Exchange sector. Source: Saudi Exchange only."""

    __tablename__ = "sectors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    code: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True, index=True)
    arabic_name: Mapped[str] = mapped_column(String(500), nullable=False)
    english_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # market: tadawul | nomu | both
    market: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )

    industry_groups: Mapped[list["IndustryGroup"]] = relationship(
        "IndustryGroup", back_populates="sector", lazy="selectin"
    )


class IndustryGroup(Base):
    """Official Saudi Exchange industry group under a sector."""

    __tablename__ = "industry_groups"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    code: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True, index=True)
    sector_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sectors.id"), nullable=True, index=True
    )
    arabic_name: Mapped[str] = mapped_column(String(500), nullable=False)
    english_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )

    sector: Mapped["Sector | None"] = relationship("Sector", back_populates="industry_groups")
    industries: Mapped[list["Industry"]] = relationship(
        "Industry", back_populates="industry_group", lazy="selectin"
    )


class Industry(Base):
    """Official Saudi Exchange industry under an industry group."""

    __tablename__ = "industries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    code: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True, index=True)
    industry_group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("industry_groups.id"), nullable=True, index=True
    )
    arabic_name: Mapped[str] = mapped_column(String(500), nullable=False)
    english_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )

    industry_group: Mapped["IndustryGroup | None"] = relationship(
        "IndustryGroup", back_populates="industries"
    )
