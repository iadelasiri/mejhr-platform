from sqlalchemy import String, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, BigInteger, text
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
    # company_id links to companies.id; populated during discovery
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    fiscal_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # fiscal_period: Q1 | Q2 | Q3 | Q4 | Annual | H1 | H2  (maps to 'period' column)
    period: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # period_type: quarterly | annual | semi_annual
    period_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # period_status: confirmed | needs_manual_confirmation
    period_status: Mapped[str] = mapped_column(String(50), nullable=False, default="confirmed")
    # language: ar | en
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # filing_type: xhtml | xml | xbrl | pdf
    filing_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # filing_url: direct URL to the XBRL/iXBRL file
    xbrl_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # source_url: announcement page from which the filing was discovered
    announcement_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    announcement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("announcements.id"), nullable=True
    )
    # announcement_date: when the filing was announced
    reported_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # import_status: pending | downloaded | rendered | parsed | failed
    import_status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    # data_status: official (all XBRL filings from Saudi Exchange are official)
    data_status: Mapped[str] = mapped_column(String(50), nullable=False, default="official")
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )

    files: Mapped[list["XBRLFile"]] = relationship("XBRLFile", back_populates="filing", lazy="selectin")


class XBRLFile(Base):
    """Downloaded XBRL file associated with a filing."""

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
    # file_hash: SHA-256 hex digest of the downloaded content — used for dedup
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # download_status: pending | downloaded | failed | skipped_duplicate
    download_status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    # render_status: not_required | pending | rendered | failed
    render_status: Mapped[str] = mapped_column(String(50), nullable=False, default="not_required")
    # rendered_path: path to the Playwright-rendered HTML snapshot (SA viewer only)
    rendered_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # selected_sections: JSON list of section codes selected before rendering
    selected_sections: Mapped[str | None] = mapped_column(String, nullable=True)
    # rendered_at: timestamp when rendering completed
    rendered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # render_warnings: semicolon-separated list of warnings (missing sections, etc.)
    render_warnings: Mapped[str | None] = mapped_column(String, nullable=True)
    # data_status: official
    data_status: Mapped[str] = mapped_column(String(50), nullable=False, default="official")
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )

    filing: Mapped["XBRLFiling"] = relationship("XBRLFiling", back_populates="files")


class XBRLRawItem(Base):
    """
    Raw fact extracted from an XBRL or iXBRL filing.
    Every field reflects the source file verbatim — nothing is inferred or normalised.
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
    # company_id populated from xbrl_filings.company_id at parse time
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # concept_name: XBRL element local name (e.g. "Revenue", "Assets")
    concept_name: Mapped[str] = mapped_column(String(500), nullable=False, default="", index=True)
    # concept_namespace: full taxonomy namespace URI (e.g. "http://xbrl.ifrs.org/taxonomy/...")
    concept_namespace: Mapped[str | None] = mapped_column(String(500), nullable=True)
    label_ar: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    label_en: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # value_raw: verbatim string from the XBRL source (may be formatted, e.g. "1,234,567")
    value_raw: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # value_numeric: parsed numeric Decimal; None for non-numeric facts
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    # value: legacy alias for value_numeric (kept for backward compat)
    value: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    # unit_ref: resolved unit string (e.g. "iso4217:SAR")
    unit_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="SAR")
    decimals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # context_ref: raw context ID from XBRL source
    context_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    # instant_date: populated for XBRL instant contexts (balance sheet dates)
    instant_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # fiscal_year / fiscal_period copied from the parent XBRLFiling at parse time
    fiscal_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fiscal_period: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # statement_type: heuristic detection — balance_sheet | income_statement | cash_flow | unknown
    statement_type: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    # Saudi XBRL section codes (populated in Phase 2G normalisation, not here)
    section_code: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    section_name_ar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    section_name_en: Mapped[str | None] = mapped_column(String(500), nullable=True)
    parse_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    local_file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # data_status: official (all XBRL facts from Saudi Exchange)
    data_status: Mapped[str] = mapped_column(String(50), nullable=False, default="official")
    # parse_status: extracted | mapped | unmatched | conflict
    parse_status: Mapped[str] = mapped_column(String(50), nullable=False, default="extracted")
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
