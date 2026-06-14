from pydantic import BaseModel
from datetime import datetime
from typing import Any
import uuid


class ImportJobOut(BaseModel):
    id: uuid.UUID
    job_type: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    duration_seconds: int | None
    error_message: str | None
    stats: dict[str, Any] | None
    triggered_by: str
    celery_task_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TriggerJobRequest(BaseModel):
    job_type: str
    symbol: str | None = None
