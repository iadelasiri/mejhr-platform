from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from decimal import Decimal

from app.core.database import get_db
from app.models.screener import ScreenerSnapshot
from app.schemas.common import PaginatedResponse, PipelineMeta
from app.schemas.screener import ScreenerRow

router = APIRouter()


@router.get("/", response_model=PaginatedResponse[ScreenerRow])
async def screener(
    market: str | None = Query(None),
    sector: str | None = Query(None),
    min_market_cap: Decimal | None = Query(None),
    max_market_cap: Decimal | None = Query(None),
    min_roic: Decimal | None = Query(None),
    max_pe: Decimal | None = Query(None),
    data_quality_status: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(ScreenerSnapshot)

    if market:
        query = query.where(ScreenerSnapshot.market == market)
    if sector:
        query = query.where(
            (ScreenerSnapshot.sector_ar == sector) | (ScreenerSnapshot.sector_en == sector)
        )
    if min_market_cap is not None:
        query = query.where(ScreenerSnapshot.market_cap >= min_market_cap)
    if max_market_cap is not None:
        query = query.where(ScreenerSnapshot.market_cap <= max_market_cap)
    if min_roic is not None:
        query = query.where(ScreenerSnapshot.roic >= min_roic)
    if max_pe is not None:
        query = query.where(ScreenerSnapshot.pe <= max_pe)
    if data_quality_status:
        query = query.where(ScreenerSnapshot.data_quality_status == data_quality_status)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    rows = result.scalars().all()

    meta = PipelineMeta(
        pipeline_status="populated" if total > 0 else "not_configured",
        message=None if total > 0 else (
            "Screener snapshot is empty. Run the full pipeline to populate: "
            "fetch_companies → normalize → calculate_ratios → build_screener"
        ),
        sample_data=any(r.data_quality_status == "sample_not_official" for r in rows),
    )

    return PaginatedResponse(
        data=[ScreenerRow.model_validate(r) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
        meta=meta,
    )
