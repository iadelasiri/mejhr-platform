from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timezone

from app.core.database import get_db
from app.models.company import Company
from app.models.xbrl import XBRLFiling, XBRLFile, XBRLRawItem
from app.models.financial import NormalizedFinancial, CalculatedRatio
from app.models.announcement import Announcement
from app.models.screener import ScreenerSnapshot

router = APIRouter()


@router.get("/")
async def data_quality_report(db: AsyncSession = Depends(get_db)):
    async def count(model):
        result = await db.execute(select(func.count()).select_from(model))
        return result.scalar() or 0

    async def count_where(model, condition):
        result = await db.execute(select(func.count()).select_from(model).where(condition))
        return result.scalar() or 0

    companies_total = await count(Company)
    sectors_mapped = await count_where(Company, Company.mapping_status == "mapped")
    pending_sector = await count_where(
        Company, Company.mapping_status == "pending_official_mapping"
    )
    sample_companies = await count_where(Company, Company.data_status == "sample_not_official")

    filings_total = await count(XBRLFiling)
    files_downloaded = await count_where(XBRLFile, XBRLFile.download_status == "downloaded")
    files_rendered = await count_where(XBRLFile, XBRLFile.render_status == "rendered")
    raw_items_total = await count(XBRLRawItem)
    raw_items_parsed = await count_where(XBRLRawItem, XBRLRawItem.parse_status == "extracted")

    normalized_total = await count(NormalizedFinancial)
    with_revenue = await count_where(NormalizedFinancial, NormalizedFinancial.revenue.isnot(None))
    with_net_income = await count_where(NormalizedFinancial, NormalizedFinancial.net_income.isnot(None))
    with_equity = await count_where(NormalizedFinancial, NormalizedFinancial.equity.isnot(None))

    ratios_total = await count(CalculatedRatio)
    with_roic = await count_where(CalculatedRatio, CalculatedRatio.roic.isnot(None))
    with_evic = await count_where(CalculatedRatio, CalculatedRatio.ev_ic.isnot(None))

    announcements_total = await count(Announcement)
    xbrl_announcements = await count_where(Announcement, Announcement.has_xbrl == True)

    screener_rows = await count(ScreenerSnapshot)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_status": "populated" if companies_total > 0 else "not_configured",
        "companies": {
            "total": companies_total,
            "sector_mapped": sectors_mapped,
            "pending_official_sector_mapping": pending_sector,
            "sample_not_official": sample_companies,
        },
        "announcements": {
            "total": announcements_total,
            "with_xbrl": xbrl_announcements,
        },
        "xbrl": {
            "filings_discovered": filings_total,
            "files_downloaded": files_downloaded,
            "files_rendered": files_rendered,
            "raw_items_extracted": raw_items_parsed,
            "raw_items_total": raw_items_total,
        },
        "financials": {
            "normalized_filings": normalized_total,
            "with_revenue": with_revenue,
            "with_net_income": with_net_income,
            "with_equity": with_equity,
        },
        "ratios": {
            "total": ratios_total,
            "with_roic": with_roic,
            "with_ev_ic": with_evic,
        },
        "screener": {
            "snapshot_rows": screener_rows,
        },
        "notes": (
            "All counts are zero until the data pipeline is configured and run. "
            "No data is fabricated. Missing data is shown as null or zero."
        ),
    }
