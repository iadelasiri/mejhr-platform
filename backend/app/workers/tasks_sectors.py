"""
Celery task: fetch official TASI sectors and market indices from Saudi Exchange.

Task name: tasks.fetch_sectors

Imports:
  - Sector records (22 GICS-style sector indices) into the sectors table.
  - MarketIndex records (TASI main + size/IPO/MSCI indices) into market_indices.

Sector source: Saudi Exchange portal HTML widget (no clean JSON API exists).
Arabic names are not available from this source (field stored as NULL).

Job stats contract (always present in ImportJob.stats):
    sectors_found       int
    sectors_inserted    int
    sectors_updated     int
    indices_found       int
    indices_inserted    int
    indices_updated     int
    endpoint_reachable  bool
    endpoint_blocked    bool
    parse_note          str
    error               str|None
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool

from app.workers.celery_app import app as celery_app
from app.core.config import settings
from app.pipeline.exchange.sectors import fetch_sectors

log = logging.getLogger(__name__)

_connect_args: dict = {}
if "pooler.supabase.com" in settings.DATABASE_URL:
    _connect_args["prepared_statement_cache_size"] = 0

_task_engine = create_async_engine(
    settings.DATABASE_URL,
    poolclass=NullPool,
    connect_args=_connect_args,
)
AsyncSessionLocal = async_sessionmaker(
    _task_engine, class_=AsyncSession, expire_on_commit=False
)


async def _create_job(triggered_by: str, celery_task_id: str | None = None) -> str:
    from app.models.job import ImportJob

    async with AsyncSessionLocal() as db:
        job = ImportJob(
            job_type="fetch_sectors",
            status="pending",
            triggered_by=triggered_by,
            celery_task_id=celery_task_id,
        )
        db.add(job)
        await db.flush()
        job_id = str(job.id)
        await db.commit()
    return job_id


async def _run_sector_import(job_id: str) -> dict:
    """
    Async core: fetch → upsert sectors + indices → update job record.
    Returns the stats dict.
    """
    from sqlalchemy import select, update
    from app.models.sector import Sector
    from app.models.market_index import MarketIndex
    from app.models.job import ImportJob

    stats: dict = {
        "sectors_found": 0,
        "sectors_inserted": 0,
        "sectors_updated": 0,
        "indices_found": 0,
        "indices_inserted": 0,
        "indices_updated": 0,
        "endpoint_reachable": False,
        "endpoint_blocked": False,
        "parse_note": "",
        "error": None,
    }

    async with AsyncSessionLocal() as db:
        import_start = datetime.now(timezone.utc)
        await db.execute(
            update(ImportJob)
            .where(ImportJob.id == job_id)
            .values(status="running", started_at=import_start)
        )
        await db.commit()

        final_status = "failed"

        try:
            result = await asyncio.to_thread(fetch_sectors)

            stats["endpoint_reachable"] = result.reachable
            stats["endpoint_blocked"] = result.blocked
            stats["parse_note"] = result.parse_note
            stats["sectors_found"] = len(result.sectors)
            stats["indices_found"] = len(result.indices)

            if result.blocked:
                stats["error"] = result.parse_note
                final_status = "failed"
            elif result.status_code is None and result.error:
                stats["error"] = result.error
                final_status = "failed"
            else:
                final_status = "completed"

            # ── Upsert sectors ─────────────────────────────────────────
            for rec in result.sectors:
                try:
                    existing = await db.execute(
                        select(Sector).where(Sector.code == rec.code)
                    )
                    sector = existing.scalar_one_or_none()

                    if sector is None:
                        db.add(Sector(
                            code=rec.code,
                            arabic_name=rec.arabic_name,
                            english_name=rec.english_name,
                            market=rec.market,
                            source=rec.source,
                            source_url=rec.source_url,
                            imported_at=rec.imported_at,
                        ))
                        stats["sectors_inserted"] += 1
                    else:
                        sector.english_name = rec.english_name
                        sector.market = rec.market
                        sector.source = rec.source
                        sector.source_url = rec.source_url
                        sector.imported_at = rec.imported_at
                        stats["sectors_updated"] += 1
                except Exception as exc:
                    log.error("Upsert failed for sector %s: %s", rec.code, exc)

            # ── Upsert market indices ───────────────────────────────────
            for rec in result.indices:
                try:
                    existing = await db.execute(
                        select(MarketIndex).where(MarketIndex.code == rec.code)
                    )
                    idx = existing.scalar_one_or_none()

                    if idx is None:
                        db.add(MarketIndex(
                            code=rec.code,
                            arabic_name=rec.arabic_name,
                            english_name=rec.english_name,
                            index_type=rec.index_type,
                            sector_id=None,
                            market=rec.market,
                            source=rec.source,
                            source_url=rec.source_url,
                            imported_at=rec.imported_at,
                        ))
                        stats["indices_inserted"] += 1
                    else:
                        idx.english_name = rec.english_name
                        idx.index_type = rec.index_type
                        idx.market = rec.market
                        idx.source = rec.source
                        idx.source_url = rec.source_url
                        idx.imported_at = rec.imported_at
                        stats["indices_updated"] += 1
                except Exception as exc:
                    log.error("Upsert failed for index %s: %s", rec.code, exc)

            await db.commit()

        except Exception as exc:
            log.exception("Unexpected error in _run_sector_import job_id=%s: %s", job_id, exc)
            stats["error"] = str(exc)
            final_status = "failed"

        import_end = datetime.now(timezone.utc)
        duration_seconds = int((import_end - import_start).total_seconds())

        await db.execute(
            update(ImportJob)
            .where(ImportJob.id == job_id)
            .values(
                status=final_status,
                completed_at=import_end,
                duration_seconds=duration_seconds,
                stats=stats,
                error_message=stats.get("error"),
            )
        )
        await db.commit()

    return stats


@celery_app.task(name="tasks.fetch_sectors", bind=True)
def fetch_tasi_sectors_task(self, job_id: str | None = None):
    """
    Import official TASI sectors and market indices from Saudi Exchange.
    Returns the stats dict.
    """
    _provided_job_id = job_id
    _celery_task_id = self.request.id

    async def _execute() -> dict:
        _job_id = _provided_job_id
        if _job_id is None:
            _job_id = await _create_job("scheduler", _celery_task_id)
        return await _run_sector_import(_job_id)

    stats = asyncio.run(_execute())

    log.info(
        "tasks.fetch_sectors done "
        "sectors_found=%d inserted=%d updated=%d "
        "indices_found=%d blocked=%s",
        stats["sectors_found"],
        stats["sectors_inserted"],
        stats["sectors_updated"],
        stats["indices_found"],
        stats["endpoint_blocked"],
    )
    return stats
