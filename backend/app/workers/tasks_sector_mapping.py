"""
Celery task: apply company-to-sector mappings from the seed CSV.

Task name: tasks.apply_sector_mapping

Reads backend/data/sector_mapping.csv, validates sector codes against
the sectors table, and updates company.sector_id + mapping_status for
every row with confidence='verified' or 'approximate'.

Job stats contract (always present in ImportJob.stats):
    rows_read               int
    rows_accepted           int
    rows_skipped_confidence int
    companies_mapped        int    — new mappings applied
    companies_updated       int    — existing mappings refreshed
    companies_not_found     int    — symbols not in companies table
    invalid_sector_codes    list   — sector codes not found in sectors table
    unknown_symbols         list   — symbols skipped (not found)
    error                   str|None
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool

from app.workers.celery_app import app as celery_app
from app.core.config import settings
from app.pipeline.sector_mapping.importer import load_csv, apply_mappings, DEFAULT_CSV_PATH

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
            job_type="apply_sector_mapping",
            status="pending",
            triggered_by=triggered_by,
            celery_task_id=celery_task_id,
        )
        db.add(job)
        await db.flush()
        job_id = str(job.id)
        await db.commit()
    return job_id


async def _run_mapping_import(job_id: str, csv_path: Path) -> dict:
    from sqlalchemy import update
    from app.models.job import ImportJob

    stats: dict = {
        "rows_read": 0,
        "rows_accepted": 0,
        "rows_skipped_confidence": 0,
        "companies_mapped": 0,
        "companies_updated": 0,
        "companies_not_found": 0,
        "invalid_sector_codes": [],
        "unknown_symbols": [],
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
            rows, load_errors = load_csv(csv_path)

            if load_errors and not rows:
                stats["error"] = "; ".join(load_errors)
                final_status = "failed"
            else:
                mapping_stats = await apply_mappings(rows, db)
                await db.commit()

                stats.update(mapping_stats)
                if load_errors:
                    stats["error"] = "; ".join(load_errors)

                final_status = "completed"

        except Exception as exc:
            log.exception("Unexpected error in _run_mapping_import job_id=%s: %s", job_id, exc)
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


@celery_app.task(name="tasks.apply_sector_mapping", bind=True)
def apply_sector_mapping_task(self, job_id: str | None = None, csv_path: str | None = None):
    """
    Apply company-to-sector mappings from the seed CSV.
    Returns the stats dict.
    """
    _provided_job_id = job_id
    _celery_task_id = self.request.id
    _csv_path = Path(csv_path) if csv_path else DEFAULT_CSV_PATH

    async def _execute() -> dict:
        _job_id = _provided_job_id
        if _job_id is None:
            _job_id = await _create_job("scheduler", _celery_task_id)
        return await _run_mapping_import(_job_id, _csv_path)

    stats = asyncio.run(_execute())

    log.info(
        "tasks.apply_sector_mapping done "
        "mapped=%d updated=%d not_found=%d skipped_confidence=%d",
        stats["companies_mapped"],
        stats["companies_updated"],
        stats["companies_not_found"],
        stats["rows_skipped_confidence"],
    )
    return stats
