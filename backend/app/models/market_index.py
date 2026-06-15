from sqlalchemy import String, DateTime, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
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
