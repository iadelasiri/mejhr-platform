from sqlalchemy import String, DateTime, Date, Numeric, ForeignKey, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, date
from decimal import Decimal
import uuid

from app.models.base import Base


class MarketIndex(Base):
    """Official TASI market index (main, sector, size, IPO, MSCI)."""

    __tablename__ = "market_indices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    code: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )
    arabic_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    english_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # "main" | "sector" | "size" | "ipo" | "msci" | "other"
    index_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sector_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sectors.id"), nullable=True, index=True
    )
    market: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )

    sector: Mapped["Sector | None"] = relationship(  # type: ignore[name-defined]
        "Sector", foreign_keys=[sector_id], lazy="selectin"
    )


class IndexPrice(Base):
    """
    Daily OHLCV price history for a Saudi Exchange index.
    Source: Saudi Exchange only (ThemeTASIUtilityServlet for TASI/MT30 full
    OHLCV; the indicesJson widget for other sector/market indices — high/low
    are NULL for those, never fabricated). See PHASE_2D2_DISCOVERY.md.

    `index_code` is a plain string, not an FK to market_indices.code — this
    mirrors MarketData.symbol (no FK to companies) and avoids an insert-order
    dependency between the catalogue and the price pipeline.
    """

    __tablename__ = "index_prices"
    __table_args__ = (UniqueConstraint("index_code", "trade_date", name="uq_index_price_code_date"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    index_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    open: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    high: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    low: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    close: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    previous_close: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    change_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    change_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    volume: Mapped[Decimal | None] = mapped_column(Numeric(24, 0), nullable=True)
    turnover: Mapped[Decimal | None] = mapped_column(Numeric(24, 4), nullable=True)
    trades_count: Mapped[Decimal | None] = mapped_column(Numeric(14, 0), nullable=True)
    # How trade_date was computed — never silent. e.g.
    # "riyadh_fixed_utc+3_same_day" | "riyadh_fixed_utc+3_weekend_rollback_friday_to_thursday"
    trade_date_derivation: Mapped[str] = mapped_column(String(80), nullable=False)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
