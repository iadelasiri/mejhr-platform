from sqlalchemy import String, DateTime, Date, Numeric, text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, date
from decimal import Decimal
import uuid

from app.models.base import Base


class MarketData(Base):
    """Daily market data per symbol. Source: Saudi Exchange only."""

    __tablename__ = "market_data"
    __table_args__ = (UniqueConstraint("symbol", "trade_date", name="uq_market_data_symbol_date"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
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
    trades: Mapped[Decimal | None] = mapped_column(Numeric(14, 0), nullable=True)
    market_cap: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
