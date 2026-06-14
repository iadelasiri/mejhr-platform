from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update

from app.core.database import get_db
from app.core.security import require_admin
from app.models.job import ImportJob
from app.schemas.common import PaginatedResponse, SingleResponse, PipelineMeta
from app.schemas.job import ImportJobOut, TriggerJobRequest

router = APIRouter()

# Only fetch_companies is wired to a real Celery task in Phase 2C.
# Other types are accepted and recorded but not yet dispatched.
_CELERY_WIRED = {"fetch_companies"}

VALID_JOB_TYPES = {
    "fetch_companies",
    "fetch_sectors",
    "fetch_prices",
    "fetch_announcements",
    "xbrl_discovery",
    "xbrl_download",
    "xbrl_render",
    "xbrl_parse",
    "normalize",
    "calculate_ratios",
    "build_screener",
    "build_quality_report",
    "full_refresh",
}


@router.get("/", response_model=PaginatedResponse[ImportJobOut])
async def list_jobs(
    job_type: str | None = Query(None),
    job_status: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    query = select(ImportJob).order_by(ImportJob.created_at.desc())
    if job_type:
        query = query.where(ImportJob.job_type == job_type)
    if job_status:
        query = query.where(ImportJob.status == job_status)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    jobs = result.scalars().all()

    meta = PipelineMeta(
        pipeline_status="populated" if total > 0 else "not_configured",
        message=None if total > 0 else "No jobs have been run yet.",
    )

    return PaginatedResponse(
        data=[ImportJobOut.model_validate(j) for j in jobs],
        total=total,
        page=page,
        per_page=per_page,
        meta=meta,
    )


@router.get("/{job_id}", response_model=SingleResponse[ImportJobOut])
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await db.execute(select(ImportJob).where(ImportJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    return SingleResponse(
        data=ImportJobOut.model_validate(job),
        meta=PipelineMeta(pipeline_status="populated"),
    )


@router.post("/trigger", status_code=status.HTTP_202_ACCEPTED)
async def trigger_job(
    request: TriggerJobRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    if request.job_type not in VALID_JOB_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown job type. Valid types: {sorted(VALID_JOB_TYPES)}",
        )

    # Non-wired types: no job record created — a pending record that never
    # transitions is misleading. Return immediately with dispatched=False.
    if request.job_type not in _CELERY_WIRED:
        return {
            "job_id": None,
            "job_type": request.job_type,
            "status": "not_configured",
            "celery_task_id": None,
            "dispatched": False,
            "message": (
                f"Job type '{request.job_type}' has no worker configured in Phase 2C. "
                "No job record was created. Implemented: fetch_companies."
            ),
        }

    # Wired type: create the ImportJob record first so the Celery task can update it.
    job = ImportJob(
        job_type=request.job_type,
        status="pending",
        triggered_by="admin",
    )
    db.add(job)
    await db.flush()
    job_id = str(job.id)
    # Commit before dispatch so the row is visible to the Celery worker.
    await db.commit()

    from app.workers.tasks_companies import fetch_saudi_exchange_companies_task
    task = fetch_saudi_exchange_companies_task.apply_async(kwargs={"job_id": job_id})
    celery_task_id = task.id

    await db.execute(
        update(ImportJob)
        .where(ImportJob.id == job_id)
        .values(celery_task_id=celery_task_id)
    )
    await db.commit()

    return {
        "job_id": job_id,
        "job_type": request.job_type,
        "status": "pending",
        "celery_task_id": celery_task_id,
        "dispatched": True,
        "message": "Job dispatched to worker. Poll GET /api/v1/jobs/{job_id} for status.",
    }
