from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime

from app.core.database import get_db
from app.models.announcement import Announcement
from app.schemas.common import PaginatedResponse, PipelineMeta

router = APIRouter()


@router.get("/")
async def list_announcements(
    symbol: str | None = Query(None),
    market: str | None = Query(None),
    announcement_type: str | None = Query(None),
    has_xbrl: bool | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(Announcement).order_by(Announcement.announced_at.desc())

    if symbol:
        query = query.where(Announcement.symbol == symbol.upper())
    if market:
        query = query.where(Announcement.market == market)
    if announcement_type:
        query = query.where(Announcement.announcement_type == announcement_type)
    if has_xbrl is not None:
        query = query.where(Announcement.has_xbrl == has_xbrl)
    if date_from:
        query = query.where(Announcement.announced_at >= date_from)
    if date_to:
        query = query.where(Announcement.announced_at <= date_to)
    if keyword:
        query = query.where(
            Announcement.title_ar.ilike(f"%{keyword}%")
            | Announcement.title_en.ilike(f"%{keyword}%")
        )

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    rows = result.scalars().all()

    meta = PipelineMeta(
        pipeline_status="populated" if total > 0 else "not_configured",
        message=None if total > 0 else (
            "No announcements imported yet. Run fetch_announcements pipeline to populate."
        ),
    )

    data = [
        {
            "id": str(r.id),
            "symbol": r.symbol,
            "market": r.market,
            "title_ar": r.title_ar,
            "title_en": r.title_en,
            "announced_at": r.announced_at.isoformat() if r.announced_at else None,
            "announcement_type": r.announcement_type,
            "source_url": r.source_url,
            "has_xbrl": r.has_xbrl,
            "xbrl_url": r.xbrl_url,
        }
        for r in rows
    ]

    return PaginatedResponse(data=data, total=total, page=page, per_page=per_page, meta=meta)
