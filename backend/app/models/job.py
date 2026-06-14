from sqlalchemy import String, DateTime, Integer, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid

from app.models.base import Base


class ImportJob(Base):
    """Tracks every data import/refresh job run by the pipeline or scheduler."""

    __tablename__ = "import_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # job_type: fetch_companies | fetch_sectors | fetch_prices | fetch_announcements |
    #           xbrl_discovery | xbrl_download | xbrl_render | xbrl_parse |
    #           normalize | calculate_ratios | build_screener | build_quality_report
    job_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # status: pending | running | completed | failed | cancelled
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    # stats: {records_processed, records_created, records_updated, records_failed, ...}
    stats: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # triggered_by: scheduler | admin | manual | system
    triggered_by: Mapped[str] = mapped_column(String(100), nullable=False, default="scheduler")
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )


class AuditLog(Base):
    """Records admin and user actions for security and accountability."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
