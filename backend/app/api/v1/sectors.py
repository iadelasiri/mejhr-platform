from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.models.sector import Sector
from app.schemas.common import PaginatedResponse, PipelineMeta
from app.schemas.sector import SectorOut

router = APIRouter()


@router.get("/", response_model=PaginatedResponse[SectorOut])
async def list_sectors(
    market: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(Sector)
    if market:
        query = query.where((Sector.market == market) | (Sector.market == "both"))

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    sectors = result.scalars().all()

    meta = PipelineMeta(
        pipeline_status="populated" if total > 0 else "not_configured",
        message=None if total > 0 else (
            "No sectors imported yet. Run fetch_sectors pipeline to populate."
        ),
    )

    return PaginatedResponse(
        data=[SectorOut.model_validate(s) for s in sectors],
        total=total,
        page=page,
        per_page=per_page,
        meta=meta,
    )
