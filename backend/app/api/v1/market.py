from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.models.market_index import IndexPrice, MarketIndex
from app.schemas.common import PaginatedResponse, PipelineMeta
from app.schemas.market_data import IndexPriceOut

router = APIRouter()


@router.get("/indices/latest", response_model=PaginatedResponse[IndexPriceOut])
async def get_latest_index_prices(
    page: int = Query(1, ge=1),
    per_page: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """
    Read-only latest row per index_code from index_prices, left-joined
    with market_indices for display names when a catalogue entry exists
    (index_code is not an FK, so a price row may have no catalogue match).

    high/low are NULL for indices where Saudi Exchange does not provide
    full OHLCV (only TASI/MT30 do) — never fabricated. See
    PHASE_2D2_DISCOVERY.md and the IndexPrice model docstring.
    """
    # One row per index_code: the most recent trade_date for that code.
    # uq_index_price_code_date guarantees the subsequent join below yields
    # at most one IndexPrice row per index_code.
    latest_dates = (
        select(
            IndexPrice.index_code,
            func.max(IndexPrice.trade_date).label("max_trade_date"),
        )
        .group_by(IndexPrice.index_code)
        .subquery()
    )

    count_result = await db.execute(select(func.count()).select_from(latest_dates))
    total = count_result.scalar() or 0

    query = (
        select(IndexPrice, MarketIndex)
        .join(
            latest_dates,
            (IndexPrice.index_code == latest_dates.c.index_code)
            & (IndexPrice.trade_date == latest_dates.c.max_trade_date),
        )
        .outerjoin(MarketIndex, MarketIndex.code == IndexPrice.index_code)
        .order_by(IndexPrice.index_code)
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(query)
    rows = result.all()

    data = [
        IndexPriceOut(
            index_code=price.index_code,
            index_name_ar=idx.arabic_name if idx else None,
            index_name_en=idx.english_name if idx else None,
            trade_date=price.trade_date,
            open=price.open,
            high=price.high,
            low=price.low,
            close=price.close,
            previous_close=price.previous_close,
            change_amount=price.change_amount,
            change_pct=price.change_pct,
            volume=price.volume,
            turnover=price.turnover,
            trades_count=price.trades_count,
            trade_date_derivation=price.trade_date_derivation,
            source=price.source,
            source_url=price.source_url,
        )
        for price, idx in rows
    ]

    meta = PipelineMeta(
        pipeline_status="populated" if total > 0 else "not_configured",
        message=None if total > 0 else "No index price data found. Run the index prices import job.",
    )

    return PaginatedResponse(data=data, total=total, page=page, per_page=per_page, meta=meta)
