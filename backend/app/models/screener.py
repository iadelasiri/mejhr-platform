from sqlalchemy import String, DateTime, Numeric, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
from decimal import Decimal
import uuid

from app.models.base import Base


class ScreenerSnapshot(Base):
    """
    Denormalized screener row rebuilt nightly.
    The screener UI reads ONLY from this table — never calculates on the fly.
    Missing values are NULL, never fabricated.
    """

    __tablename__ = "screener_snapshot"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    company_name_ar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    company_name_en: Mapped[str | None] = mapped_column(String(500), nullable=True)
    market: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    sector_ar: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    sector_en: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Market data
    latest_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    change_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    market_cap: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)

    # Financial summary
    revenue: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)
    net_income: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)

    # Ratios
    roic: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    ev_ic: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    pe: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    pb: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    ps: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    debt_equity: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    fcf: Mapped[Decimal | None] = mapped_column(Numeric(28, 4), nullable=True)

    # Source tracking
    price_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    financial_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_price_update: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_financial_update: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # data_quality_status: complete | partial | missing_financials | missing_price | poor | sample_not_official
    data_quality_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="missing_financials"
    )
    snapshot_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
