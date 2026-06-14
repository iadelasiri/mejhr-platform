"""
Seeds the database with clearly-marked sample data for UI testing.

Usage (development only):
  docker compose exec backend python -m app.sample_data.seed

WARNING: Never run against a production database.
         All records are clearly marked sample_not_official.
"""

import asyncio
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.config import settings
from app.models.sector import Sector, IndustryGroup
from app.models.company import Company
from app.models.screener import ScreenerSnapshot
from app.sample_data import sample_data_guard

SAMPLE_SECTORS = [
    {
        "code": "SMPL-BANK",
        "arabic_name": "البنوك (عينة)",
        "english_name": "Banking (Sample)",
        "market": "tadawul",
    },
    {
        "code": "SMPL-PETRO",
        "arabic_name": "البتروكيماويات (عينة)",
        "english_name": "Petrochemicals (Sample)",
        "market": "tadawul",
    },
]

SAMPLE_COMPANIES = [
    {
        "symbol": "SMPL1",
        "arabic_name": "شركة عينة أ [غير رسمي]",
        "english_name": "Sample Company A [NOT OFFICIAL]",
        "market": "tadawul",
        "sector_code": "SMPL-BANK",
    },
    {
        "symbol": "SMPL2",
        "arabic_name": "شركة عينة ب [غير رسمي]",
        "english_name": "Sample Company B [NOT OFFICIAL]",
        "market": "tadawul",
        "sector_code": "SMPL-PETRO",
    },
    {
        "symbol": "SMPL3",
        "arabic_name": "شركة عينة ج [غير رسمي]",
        "english_name": "Sample Company C [NOT OFFICIAL]",
        "market": "nomu",
        "sector_code": None,
    },
]


async def seed(db: AsyncSession):
    sample_data_guard()

    now = datetime.now(timezone.utc)
    sector_map = {}

    for s in SAMPLE_SECTORS:
        sector = Sector(
            code=s["code"],
            arabic_name=s["arabic_name"],
            english_name=s["english_name"],
            market=s["market"],
            source="sample_data_seed",
            source_url=None,
            imported_at=now,
        )
        db.add(sector)
        await db.flush()
        sector_map[s["code"]] = sector.id

    for c in SAMPLE_COMPANIES:
        sector_id = sector_map.get(c["sector_code"]) if c["sector_code"] else None
        company = Company(
            symbol=c["symbol"],
            arabic_name=c["arabic_name"],
            english_name=c["english_name"],
            market=c["market"],
            sector_id=sector_id,
            source="sample_data_seed",
            source_url=None,
            mapping_status="mapped" if sector_id else "pending_official_mapping",
            data_status="sample_not_official",
            imported_at=now,
        )
        db.add(company)

    await db.flush()

    for c in SAMPLE_COMPANIES:
        sector_name = next(
            (s["arabic_name"] for s in SAMPLE_SECTORS if s["code"] == c.get("sector_code")),
            None,
        )
        snap = ScreenerSnapshot(
            symbol=c["symbol"],
            company_name_ar=c["arabic_name"],
            company_name_en=c["english_name"],
            market=c["market"],
            sector_ar=sector_name,
            sector_en=None,
            latest_price=None,
            change_pct=None,
            market_cap=None,
            revenue=None,
            net_income=None,
            roic=None,
            ev_ic=None,
            pe=None,
            pb=None,
            ps=None,
            debt_equity=None,
            fcf=None,
            price_source="sample_data_seed",
            financial_source="sample_data_seed",
            last_price_update=None,
            last_financial_update=None,
            data_quality_status="sample_not_official",
        )
        db.add(snap)

    await db.commit()
    print(f"[sample_data] Seeded {len(SAMPLE_COMPANIES)} sample companies (sample_not_official).")
    print("[sample_data] These are NOT official Saudi Exchange companies.")


async def main():
    async with AsyncSessionLocal() as db:
        await seed(db)


if __name__ == "__main__":
    if not settings.ENABLE_SAMPLE_DATA:
        print("ERROR: ENABLE_SAMPLE_DATA is false. Set it to true to seed sample data.")
        exit(1)
    asyncio.run(main())
