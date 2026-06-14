from sqlalchemy import String, Boolean, DateTime, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

from app.models.base import Base


class Announcement(Base):
    """Saudi Exchange company announcement."""

    __tablename__ = "announcements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    symbol: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    market: Mapped[str | None] = mapped_column(String(50), nullable=True)
    title_ar: Mapped[str] = mapped_column(String(2000), nullable=False)
    title_en: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    announced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    announcement_type: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    attachment_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    xbrl_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    has_xbrl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
