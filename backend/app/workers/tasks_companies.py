"""
Celery task: fetch official listed companies from Saudi Exchange.

Task name: tasks.fetch_companies

Design rules (Phase 2C):
  - Creates or accepts an ImportJob record.
  - Calls pipeline.exchange.companies.fetch_companies() — never fabricates data.
  - Upserts returned CompanyRecords into the companies table.
  - Records every result field in ImportJob.stats — including blocks.
  - Never overwrites data_status='sample_not_official' with official data.
  - Never inserts fake, synthetic, or placeholder company rows.
  - Sets status='failed' when the endpoint is blocked or unreachable.
  - Sets status='completed' only when the fetch ran to completion
    (even if records_found=0 — the endpoint was reachable but empty).

Job stats contract (always present in ImportJob.stats):
    records_found       int   — companies returned by the API
    records_inserted    int   — new rows added to DB
    records_updated     int   — existing rows refreshed in DB
    records_failed      int   — rows that raised an upsert exception
    endpoint_reachable  bool
    endpoint_blocked    bool
    parse_note          str
    error               str|None
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.workers.celery_app import app as celery_app
from app.core.database import AsyncSessionLocal
from app.pipeline.exchange.companies import fetch_companies

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------

async def _create_job(triggered_by: str, celery_task_id: str | None = None) -> str:
    """Create a pending ImportJob and return its UUID string."""
    from app.models.job import ImportJob

    async with AsyncSessionLocal() as db:
        job = ImportJob(
            job_type="fetch_companies",
            status="pending",
            triggered_by=triggered_by,
            celery_task_id=celery_task_id,
        )
        db.add(job)
        await db.flush()
        job_id = str(job.id)
        await db.commit()
    return job_id


async def _run_import(job_id: str) -> dict:
    """
    Async core: fetch → upsert → update job record.

    Returns the stats dict regardless of outcome so the Celery task
    can log and return it.
    """
    from sqlalchemy import select, update
    from app.models.company import Company
    from app.models.job import ImportJob

    stats: dict = {
        "records_found": 0,
        "records_inserted": 0,
        "records_updated": 0,
        "records_failed": 0,
        "endpoint_reachable": False,
        "endpoint_blocked": False,
        "parse_note": "",
        "error": None,
    }

    async with AsyncSessionLocal() as db:
        # ── Step 1: mark job as running ────────────────────────────────
        import_start = datetime.now(timezone.utc)
        await db.execute(
            update(ImportJob)
            .where(ImportJob.id == job_id)
            .values(status="running", started_at=import_start)
        )
        await db.commit()

        final_status = "failed"

        try:
            # ── Step 2: fetch from Saudi Exchange ──────────────────────
            result = fetch_companies()

            stats["endpoint_reachable"] = result.reachable
            stats["endpoint_blocked"] = result.blocked
            stats["parse_note"] = result.parse_note
            stats["records_found"] = len(result.companies)

            # ── Step 3: determine final status before upsert ───────────
            if result.blocked:
                stats["error"] = result.parse_note
                final_status = "failed"
            elif result.status_code is None and result.error:
                # Network-level failure (no HTTP response at all)
                stats["error"] = result.error
                final_status = "failed"
            elif not result.reachable and result.error:
                # Reachable but non-success HTTP (wrong endpoint, 500, etc.)
                stats["error"] = result.error
                final_status = "failed"
            else:
                # Fetch completed (may have 0 records — that is honest)
                final_status = "completed"

            # ── Step 4: upsert company rows ────────────────────────────
            for rec in result.companies:
                try:
                    existing = await db.execute(
                        select(Company).where(Company.symbol == rec.symbol)
                    )
                    company = existing.scalar_one_or_none()

                    if company is None:
                        new_company = Company(
                            symbol=rec.symbol,
                            arabic_name=rec.arabic_name,
                            english_name=rec.english_name,
                            market=rec.market,
                            source=rec.source,
                            source_url=rec.source_url,
                            mapping_status=rec.mapping_status,
                            data_status=rec.data_status,
                            imported_at=rec.imported_at,
                        )
                        db.add(new_company)
                        stats["records_inserted"] += 1
                    else:
                        # Safety guard: never overwrite sample records
                        # with official data — the reverse is also wrong.
                        if company.data_status == "sample_not_official":
                            log.debug(
                                "Skip sample company %s — will not overwrite with official",
                                rec.symbol,
                            )
                            continue
                        company.arabic_name = rec.arabic_name
                        company.english_name = rec.english_name
                        company.market = rec.market
                        company.source = rec.source
                        company.source_url = rec.source_url
                        company.data_status = rec.data_status
                        company.imported_at = rec.imported_at
                        stats["records_updated"] += 1

                except Exception as exc:
                    log.error("Upsert failed for symbol %s: %s", rec.symbol, exc)
                    stats["records_failed"] += 1

            await db.commit()

        except Exception as exc:
            log.exception("Unexpected error in _run_import job_id=%s: %s", job_id, exc)
            stats["error"] = str(exc)
            final_status = "failed"

        # ── Step 5: finalise job record ────────────────────────────────
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


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(name="tasks.fetch_companies", bind=True)
def fetch_saudi_exchange_companies_task(self, job_id: str | None = None):
    """
    Import official listed companies from Saudi Exchange.

    Called with job_id when triggered via the API (the job record is
    pre-created by the caller).  Called without job_id by the beat
    scheduler — creates its own ImportJob.

    Returns the stats dict.  Always completes without raising so
    Celery marks the task as SUCCESS; the job record status field
    carries the real outcome.
    """
    if job_id is None:
        job_id = asyncio.run(_create_job("scheduler", self.request.id))

    log.info("tasks.fetch_companies started job_id=%s celery_task_id=%s",
             job_id, self.request.id)

    stats = asyncio.run(_run_import(job_id))

    log.info(
        "tasks.fetch_companies done job_id=%s "
        "found=%d inserted=%d updated=%d failed=%d blocked=%s",
        job_id,
        stats["records_found"],
        stats["records_inserted"],
        stats["records_updated"],
        stats["records_failed"],
        stats["endpoint_blocked"],
    )
    return stats
