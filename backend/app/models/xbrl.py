from sqlalchemy import String, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, date
from decimal import Decimal
import uuid

from app.models.base import Base


class XBRLFiling(Base):
    """Discovered XBRL financial filing from Saudi Exchange announcements."""

    __tablename__ = "xbrl_filings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    fiscal_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # period: Q1 | Q2 | Q3 | Q4 | Annual | H1 | H2
    period: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # period_type: quarterly | annual | semi_annual
    period_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # period_status: confirmed | needs_manual_confirmation
    period_status: Mapped[str] = mapped_column(String(50), nullable=False, default="confirmed")
    # language: ar | en
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # filing_type: html | xhtml | xml | xbrl | xls | xlsx
    filing_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    xbrl_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    announcement_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    announcement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("announcements.id"), nullable=True
    )
    reported_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # import_status: pending | downloaded | rendered | parsed | failed
    import_status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )

    files: Mapped[list["XBRLFile"]] = relationship("XBRLFile", back_populates="filing", lazy="selectin")


class XBRLFile(Base):
    """Downloaded or rendered XBRL file associated with a filing."""

    __tablename__ = "xbrl_files"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    filing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("xbrl_filings.id"), nullable=False, index=True
    )
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    local_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # download_status: pending | downloaded | failed
    download_status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    # render_status: not_required | pending | rendered | failed
    render_status: Mapped[str] = mapped_column(String(50), nullable=False, default="not_required")
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )

    filing: Mapped["XBRLFiling"] = relationship("XBRLFiling", back_populates="files")


class XBRLRawItem(Base):
    """
    Raw line item extracted from an XBRL filing.
    Every item retains its original label, section, and value.
    Nothing is inferred or guessed at this stage.
    """

    __tablename__ = "xbrl_raw_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    filing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("xbrl_filings.id"), nullable=False, index=True
    )
    xbrl_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("xbrl_files.id"), nullable=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # Saudi XBRL section codes: 300200=balance_sheet, 300300=income_statement, 300700=cash_flow, etc.
    section_code: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    section_name_ar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    section_name_en: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # statement_type: balance_sheet | income_statement | cash_flow | changes_in_equity | notes | other
    statement_type: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    label_ar: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    label_en: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    value: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="SAR")
    decimals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    # parse_confidence: 0.0 to 1.0
    parse_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    local_file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # parse_status: extracted | mapped | unmatched | conflict
    parse_status: Mapped[str] = mapped_column(String(50), nullable=False, default="extracted")
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
