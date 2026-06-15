from pydantic import BaseModel
from typing import Generic, TypeVar, Any

T = TypeVar("T")


class LastImportJob(BaseModel):
    """Summary of the most recent import job, embedded in PipelineMeta."""
    job_id: str
    status: str                    # pending | running | completed | failed
    companies_found: int = 0
    companies_inserted: int = 0
    companies_updated: int = 0
    endpoint_blocked: bool
    error_message: str | None
    started_at: str | None         # ISO-8601
    completed_at: str | None       # ISO-8601
    duration_seconds: int | None


class PipelineMeta(BaseModel):
    data_source: str = "official_pipeline"
    pipeline_status: str = "not_configured"
    message: str | None = None
    sample_data: bool = False
    last_updated: str | None = None
    last_import_job: LastImportJob | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    success: bool = True
    data: list[T]
    total: int
    page: int
    per_page: int
    meta: PipelineMeta


class SingleResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T | None
    meta: PipelineMeta


class EmptyPaginatedResponse(PaginatedResponse[Any]):
    data: list = []
    total: int = 0
    page: int = 1
    per_page: int = 50
    meta: PipelineMeta = PipelineMeta(
        pipeline_status="not_configured",
        message="No data available. Run the data ingestion pipeline to populate.",
    )


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    detail: str | None = None
