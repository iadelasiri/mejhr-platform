from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.company import Company
from app.models.job import ImportJob
from app.schemas.common import PaginatedResponse, SingleResponse, PipelineMeta, LastImportJob
from app.schemas.company import CompanySummary, CompanyOut

router = APIRouter()

_NO_DATA_MESSAGE = (
    "No official Saudi Exchange company data imported yet. "
    "Run the Saudi Exchange connectivity test and companies refresh job: "
    "GET /api/v1/system/saudi-exchange-health  then  "
    "POST /api/v1/jobs/trigger {job_type: fetch_companies}"
)


def _last_import_job_summary(job: ImportJob) -> LastImportJob:
    """Extract a LastImportJob summary from an ImportJob ORM record."""
    s = job.stats or {}
    return LastImportJob(
        job_id=str(job.id),
        status=job.status,
        records_found=s.get("records_found", 0),
        records_inserted=s.get("records_inserted", 0),
        records_updated=s.get("records_updated", 0),
        endpoint_blocked=s.get("endpoint_blocked", False),
        error_message=job.error_message,
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        duration_seconds=job.duration_seconds,
    )


@router.get("/", response_model=PaginatedResponse[CompanySummary])
async def list_companies(
    market: str | None = Query(None, description="Filter by market: tadawul or nomu"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(Company).options(selectinload(Company.sector))
    if market:
        query = query.where(Company.market == market)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    companies = result.scalars().all()

    # Fetch the latest fetch_companies import job for meta reporting.
    job_result = await db.execute(
        select(ImportJob)
        .where(ImportJob.job_type == "fetch_companies")
        .order_by(ImportJob.created_at.desc())
        .limit(1)
    )
    last_job = job_result.scalar_one_or_none()

    # Determine pipeline_status and message.
    if total > 0:
        pipeline_status = "populated"
        message = None
    elif last_job and last_job.status == "failed":
        pipeline_status = "import_failed"
        stats = last_job.stats or {}
        if stats.get("endpoint_blocked"):
            message = (
                "Last import failed: Saudi Exchange blocked this environment "
                f"({last_job.error_message or 'Akamai/geo block'}). "
                "Deploy on a Saudi/GCC server to import official data."
            )
        else:
            message = (
                f"Last import failed: {last_job.error_message or 'unknown error'}. "
                "Check GET /api/v1/system/saudi-exchange-health for details."
            )
    elif last_job and last_job.status in ("pending", "running"):
        pipeline_status = "import_running"
        message = "Import job is currently running. Refresh in a moment."
    else:
        pipeline_status = "not_configured"
        message = _NO_DATA_MESSAGE

    meta = PipelineMeta(
        pipeline_status=pipeline_status,
        message=message,
        sample_data=any(c.data_status == "sample_not_official" for c in companies),
        last_import_job=_last_import_job_summary(last_job) if last_job else None,
    )

    rows = [
        CompanySummary(
            id=c.id,
            symbol=c.symbol,
            arabic_name=c.arabic_name,
            english_name=c.english_name,
            market=c.market,
            sector_ar=c.sector.arabic_name if c.sector else None,
            sector_en=c.sector.english_name if c.sector else None,
            mapping_status=c.mapping_status,
            data_status=c.data_status,
        )
        for c in companies
    ]

    return PaginatedResponse(data=rows, total=total, page=page, per_page=per_page, meta=meta)


@router.get("/{symbol}", response_model=SingleResponse[CompanyOut])
async def get_company(symbol: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Company).where(Company.symbol == symbol.upper())
    )
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {symbol.upper()} not found",
        )

    meta = PipelineMeta(
        pipeline_status="populated",
        sample_data=company.data_status == "sample_not_official",
    )

    return SingleResponse(data=CompanyOut.model_validate(company), meta=meta)
