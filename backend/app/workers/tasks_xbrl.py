"""
Celery tasks: XBRL discovery, download, render, and parse for Main Market companies.

Task names:
  tasks.xbrl_discovery  — scan all Main Market companies, find XBRL filings
  tasks.xbrl_download   — download pending XBRL files, dedup by SHA-256
  tasks.xbrl_render     — render SA XBRL HTML viewer files with Playwright
  tasks.xbrl_parse      — parse XBRL/iXBRL/SA-viewer files into xbrl_raw_items

Job stats contract (always present in ImportJob.stats):

  tasks.xbrl_discovery:
    companies_scanned     int
    filings_found         int
    filings_inserted      int
    filings_updated       int
    files_downloaded      int   (always 0)
    files_skipped         int   (always 0)
    endpoint_blocked      bool
    error                 str|None

  tasks.xbrl_download:
    companies_scanned     int   (always 0)
    filings_found         int   (always 0)
    filings_inserted      int   (always 0)
    filings_updated       int   (always 0)
    files_downloaded      int
    files_skipped         int   (hash-matched duplicates)
    endpoint_blocked      bool
    error                 str|None

  tasks.xbrl_render:
    files_scanned         int
    files_rendered        int
    files_skipped         int   (non-SA-viewer files)
    files_failed          int
    sections_found        int   (cumulative across all rendered files)
    sections_missing      int
    warnings              str|None
    error                 str|None

  tasks.xbrl_parse:
    files_scanned         int
    files_parsed          int
    files_failed          int
    facts_found           int
    facts_inserted        int
    facts_updated         int
    endpoint_blocked      bool
    error                 str|None
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
from app.pipeline.exchange.xbrl_discovery import discover_filings
from app.pipeline.exchange.xbrl_downloader import download_file
from app.pipeline.exchange.xbrl_parser import parse_xbrl_file, _is_sa_html_viewer
from app.pipeline.exchange.xbrl_renderer import (
    render_xbrl_html,
    rendered_output_path,
    sections_to_json,
    REQUIRED_SECTIONS,
)

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

_EMPTY_STATS: dict = {
    "companies_scanned": 0,
    "filings_found": 0,
    "filings_inserted": 0,
    "filings_updated": 0,
    "files_downloaded": 0,
    "files_skipped": 0,
    "endpoint_blocked": False,
    "error": None,
}


async def _create_job(job_type: str, triggered_by: str, celery_task_id: str | None = None) -> str:
    from app.models.job import ImportJob

    async with AsyncSessionLocal() as db:
        job = ImportJob(
            job_type=job_type,
            status="pending",
            triggered_by=triggered_by,
            celery_task_id=celery_task_id,
        )
        db.add(job)
        await db.flush()
        job_id = str(job.id)
        await db.commit()
    return job_id


async def _update_job(
    job_id: str,
    status: str,
    stats: dict,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    duration_seconds: int | None = None,
) -> None:
    from sqlalchemy import update
    from app.models.job import ImportJob

    async with AsyncSessionLocal() as db:
        values: dict = {"status": status, "stats": stats, "error_message": stats.get("error")}
        if started_at:
            values["started_at"] = started_at
        if completed_at:
            values["completed_at"] = completed_at
        if duration_seconds is not None:
            values["duration_seconds"] = duration_seconds
        await db.execute(update(ImportJob).where(ImportJob.id == job_id).values(**values))
        await db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Discovery task
# ─────────────────────────────────────────────────────────────────────────────

async def _run_xbrl_discovery(job_id: str, target_symbol: str | None = None) -> dict:
    """
    Async core for xbrl_discovery task.

    Loads Main Market companies (optionally filtered to target_symbol),
    runs discover_filings() for each, and upserts XBRLFiling records
    (idempotent on symbol + xbrl_url).

    Args:
        target_symbol: If set, scan only this symbol. None = all tadawul companies.
    """
    from sqlalchemy import select
    from app.models.company import Company
    from app.models.xbrl import XBRLFiling

    stats = {**_EMPTY_STATS}
    start = datetime.now(timezone.utc)

    await _update_job(job_id, "running", stats, started_at=start)

    final_status = "failed"
    any_blocked = False

    try:
        async with AsyncSessionLocal() as db:
            q = select(Company).where(Company.market == "tadawul")
            if target_symbol:
                q = q.where(Company.symbol == target_symbol)
            result = await db.execute(q)
            companies = result.scalars().all()

        for company in companies:
            stats["companies_scanned"] += 1
            symbol = company.symbol

            # Run discovery in a thread to isolate curl_cffi event loop
            discovery = await asyncio.to_thread(discover_filings, symbol)

            if discovery.blocked:
                any_blocked = True
                stats["endpoint_blocked"] = True
                log.warning("Blocked fetching XBRL for %s — stopping scan", symbol)
                stats["error"] = discovery.error
                break

            if discovery.error:
                # Covers both unreachable (network error) and reachable-but-failed
                # (e.g. HTTP 404 when the endpoint has changed, HTTP 5xx, etc.)
                log.warning(
                    "Discovery failed for %s (HTTP %s): %s",
                    symbol, discovery.status_code, discovery.error,
                )
                stats["error"] = (stats["error"] or "") + f"{symbol}: {discovery.error}; "
                continue

            stats["filings_found"] += len(discovery.filings)

            async with AsyncSessionLocal() as db:
                for filing in discovery.filings:
                    # Idempotent upsert: key is (symbol, xbrl_url)
                    existing_result = await db.execute(
                        select(XBRLFiling).where(
                            XBRLFiling.symbol == symbol,
                            XBRLFiling.xbrl_url == filing.filing_url,
                        )
                    )
                    existing = existing_result.scalar_one_or_none()

                    if existing is None:
                        db.add(XBRLFiling(
                            company_id=company.id,
                            symbol=symbol,
                            xbrl_url=filing.filing_url,
                            announcement_url=filing.source_url,
                            reported_date=filing.announcement_date,
                            fiscal_year=filing.fiscal_year,
                            period=filing.fiscal_period,
                            filing_type=filing.filing_type,
                            language=filing.language,
                            import_status="pending",
                            data_status="official",
                            imported_at=datetime.now(timezone.utc),
                        ))
                        stats["filings_inserted"] += 1
                    else:
                        # Update mutable fields (announcement date, period, language)
                        existing.announcement_url = filing.source_url
                        existing.reported_date = filing.announcement_date
                        existing.fiscal_year = filing.fiscal_year
                        existing.period = filing.fiscal_period
                        existing.filing_type = filing.filing_type
                        existing.language = filing.language
                        existing.imported_at = datetime.now(timezone.utc)
                        stats["filings_updated"] += 1

                await db.commit()

        final_status = "completed"

    except Exception as exc:
        log.exception("Unexpected error in xbrl_discovery job_id=%s: %s", job_id, exc)
        stats["error"] = str(exc)
        final_status = "failed"

    end = datetime.now(timezone.utc)
    await _update_job(
        job_id, final_status, stats,
        completed_at=end,
        duration_seconds=int((end - start).total_seconds()),
    )
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# Download task
# ─────────────────────────────────────────────────────────────────────────────

async def _run_xbrl_download(job_id: str, target_symbol: str | None = None) -> dict:
    """
    Async core for xbrl_download task.

    Finds pending XBRLFiling records (optionally filtered to target_symbol),
    downloads their files, records XBRLFile rows, and marks filings as downloaded.

    Args:
        target_symbol: If set, download only filings for this symbol.
    """
    from sqlalchemy import select
    from app.models.xbrl import XBRLFiling, XBRLFile

    stats = {**_EMPTY_STATS}
    start = datetime.now(timezone.utc)
    storage_base = Path(settings.STORAGE_PATH)

    await _update_job(job_id, "running", stats, started_at=start)

    final_status = "failed"

    try:
        async with AsyncSessionLocal() as db:
            q = select(XBRLFiling).where(XBRLFiling.import_status == "pending")
            if target_symbol:
                q = q.where(XBRLFiling.symbol == target_symbol)
            result = await db.execute(q)
            pending_filings = result.scalars().all()

        for filing in pending_filings:
            if not filing.xbrl_url:
                continue

            async with AsyncSessionLocal() as db:
                # Collect existing hashes for this filing (for dedup)
                hash_result = await db.execute(
                    select(XBRLFile.file_hash).where(
                        XBRLFile.filing_id == filing.id,
                        XBRLFile.file_hash.isnot(None),
                    )
                )
                existing_hashes = frozenset(
                    r for r in hash_result.scalars().all() if r
                )

            # Download in thread to isolate curl_cffi
            result = await asyncio.to_thread(
                download_file,
                filing.xbrl_url,
                filing.symbol,
                filing.fiscal_year,
                filing.period,
                storage_base,
                existing_hashes,
            )

            if result.download_status == "skipped_duplicate":
                stats["files_skipped"] += 1
                log.info("Duplicate skipped for filing %s", filing.id)
            elif result.download_status == "downloaded":
                stats["files_downloaded"] += 1
            else:
                log.warning("Download failed for %s: %s", filing.xbrl_url, result.error)

            async with AsyncSessionLocal() as db:
                # Check if a file record with this hash already exists for the filing
                if result.download_status == "skipped_duplicate":
                    # Update import_status on the filing itself to downloaded
                    # (the file was already downloaded in a previous run)
                    from sqlalchemy import update
                    await db.execute(
                        update(XBRLFiling)
                        .where(XBRLFiling.id == filing.id)
                        .values(import_status="downloaded")
                    )
                    await db.commit()
                    continue

                # Record the file download (or failure)
                xbrl_file = XBRLFile(
                    filing_id=filing.id,
                    source_url=filing.xbrl_url,
                    local_path=result.local_path,
                    file_type=filing.filing_type,
                    file_hash=result.file_hash,
                    file_size_bytes=result.file_size_bytes,
                    download_status=result.download_status,
                    data_status="official",
                    error_message=result.error,
                    imported_at=datetime.now(timezone.utc),
                )
                db.add(xbrl_file)

                # Update filing status
                from sqlalchemy import update
                new_import_status = (
                    "downloaded" if result.download_status == "downloaded" else "failed"
                )
                await db.execute(
                    update(XBRLFiling)
                    .where(XBRLFiling.id == filing.id)
                    .values(import_status=new_import_status)
                )
                await db.commit()

            if result.download_status == "failed" and result.error and "blocked" in result.error.lower():
                stats["endpoint_blocked"] = True
                stats["error"] = result.error
                break

        final_status = "completed"

    except Exception as exc:
        log.exception("Unexpected error in xbrl_download job_id=%s: %s", job_id, exc)
        stats["error"] = str(exc)
        final_status = "failed"

    end = datetime.now(timezone.utc)
    await _update_job(
        job_id, final_status, stats,
        completed_at=end,
        duration_seconds=int((end - start).total_seconds()),
    )
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# Celery task wrappers
# ─────────────────────────────────────────────────────────────────────────────

@celery_app.task(name="tasks.xbrl_discovery", bind=True)
def xbrl_discovery_task(self, job_id: str | None = None, symbol: str | None = None):
    """
    Discover XBRL filings for Main Market companies.
    symbol: optional — if provided, scan only that symbol.
    Returns the stats dict.
    """
    _provided_job_id = job_id
    _celery_task_id = self.request.id

    async def _execute() -> dict:
        _job_id = _provided_job_id
        if _job_id is None:
            _job_id = await _create_job("xbrl_discovery", "scheduler", _celery_task_id)
        return await _run_xbrl_discovery(_job_id, target_symbol=symbol)

    stats = asyncio.run(_execute())

    log.info(
        "tasks.xbrl_discovery done "
        "companies_scanned=%d filings_found=%d inserted=%d updated=%d blocked=%s",
        stats["companies_scanned"],
        stats["filings_found"],
        stats["filings_inserted"],
        stats["filings_updated"],
        stats["endpoint_blocked"],
    )
    return stats


@celery_app.task(name="tasks.xbrl_download", bind=True)
def xbrl_download_task(self, job_id: str | None = None, symbol: str | None = None):
    """
    Download pending XBRL files (hash-based dedup).
    symbol: optional — if provided, download only filings for that symbol.
    Returns the stats dict.
    """
    _provided_job_id = job_id
    _celery_task_id = self.request.id

    async def _execute() -> dict:
        _job_id = _provided_job_id
        if _job_id is None:
            _job_id = await _create_job("xbrl_download", "scheduler", _celery_task_id)
        return await _run_xbrl_download(_job_id, target_symbol=symbol)

    stats = asyncio.run(_execute())

    log.info(
        "tasks.xbrl_download done "
        "downloaded=%d skipped=%d blocked=%s",
        stats["files_downloaded"],
        stats["files_skipped"],
        stats["endpoint_blocked"],
    )
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# Render task (Phase 2E.1 — SA HTML viewer Playwright rendering)
# ─────────────────────────────────────────────────────────────────────────────

_EMPTY_RENDER_STATS: dict = {
    "files_scanned": 0,
    "files_rendered": 0,
    "files_skipped": 0,
    "files_failed": 0,
    "sections_found": 0,
    "sections_missing": 0,
    "warnings": None,
    "error": None,
}


async def _run_xbrl_render(job_id: str, target_symbol: str | None = None) -> dict:
    """
    Async core for xbrl_render task.

    Finds downloaded XBRLFile records whose local file is an SA HTML viewer,
    renders each with Playwright (select required sections → click submit →
    capture HTML), and stores the rendered snapshot path + metadata.

    Non-SA-viewer files are skipped (counted in files_skipped).

    Args:
        target_symbol: If set, render only files for this symbol.
    """
    from sqlalchemy import select, update
    from app.models.xbrl import XBRLFile, XBRLFiling

    stats = {**_EMPTY_RENDER_STATS}
    start = datetime.now(timezone.utc)
    all_warnings: list[str] = []

    await _update_job(job_id, "running", stats, started_at=start)

    final_status = "failed"

    try:
        async with AsyncSessionLocal() as db:
            q = (
                select(XBRLFile, XBRLFiling)
                .join(XBRLFiling, XBRLFile.filing_id == XBRLFiling.id)
                .where(XBRLFile.download_status == "downloaded")
            )
            if target_symbol:
                q = q.where(XBRLFiling.symbol == target_symbol)
            result = await db.execute(q)
            rows = result.all()

        for xbrl_file, filing in rows:
            stats["files_scanned"] += 1

            if not xbrl_file.local_path:
                stats["files_skipped"] += 1
                continue

            local_path = Path(xbrl_file.local_path)

            # Check if this is an SA HTML viewer file
            try:
                head = local_path.read_bytes()[:8192]
            except OSError:
                stats["files_skipped"] += 1
                continue

            if not _is_sa_html_viewer(head):
                stats["files_skipped"] += 1
                continue

            # Already rendered — skip
            if xbrl_file.rendered_path and Path(xbrl_file.rendered_path).exists():
                stats["files_skipped"] += 1
                log.debug("Already rendered: %s", xbrl_file.rendered_path)
                continue

            output_path = rendered_output_path(local_path)

            render_result = await render_xbrl_html(
                source_path=local_path,
                output_path=output_path,
                section_codes=REQUIRED_SECTIONS,
            )

            now = datetime.now(timezone.utc)

            if render_result.error:
                stats["files_failed"] += 1
                all_warnings.append(f"{filing.symbol}: {render_result.error}")
                log.warning(
                    "Render failed for XBRLFile %s: %s", xbrl_file.id, render_result.error
                )
                async with AsyncSessionLocal() as db:
                    await db.execute(
                        update(XBRLFile)
                        .where(XBRLFile.id == xbrl_file.id)
                        .values(
                            render_status="failed",
                            error_message=(render_result.error or "")[:2000],
                            render_warnings="; ".join(render_result.warnings) or None,
                            rendered_at=now,
                        )
                    )
                    await db.commit()
                continue

            stats["files_rendered"] += 1
            stats["sections_found"] += len(render_result.sections_found)
            stats["sections_missing"] += len(render_result.sections_missing)

            if render_result.warnings:
                all_warnings.extend(
                    f"{filing.symbol}: {w}" for w in render_result.warnings
                )

            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(XBRLFile)
                    .where(XBRLFile.id == xbrl_file.id)
                    .values(
                        render_status="rendered",
                        rendered_path=str(render_result.rendered_path),
                        selected_sections=sections_to_json(render_result.sections_found),
                        rendered_at=now,
                        render_warnings=(
                            "; ".join(render_result.warnings) if render_result.warnings else None
                        ),
                    )
                )
                await db.commit()

            log.info(
                "Rendered %s: %d sections found, %d missing",
                filing.symbol,
                len(render_result.sections_found),
                len(render_result.sections_missing),
            )

        if all_warnings:
            stats["warnings"] = "; ".join(all_warnings[:20])

        final_status = "completed"

    except Exception as exc:
        log.exception("Unexpected error in xbrl_render job_id=%s", job_id)
        stats["error"] = str(exc)
        final_status = "failed"

    end = datetime.now(timezone.utc)
    await _update_job(
        job_id, final_status, stats,
        completed_at=end,
        duration_seconds=int((end - start).total_seconds()),
    )
    return stats


@celery_app.task(name="tasks.xbrl_render", bind=True)
def xbrl_render_task(self, job_id: str | None = None, symbol: str | None = None):
    """
    Render SA XBRL HTML viewer files with Playwright.
    symbol: optional — if provided, render only files for that symbol.
    Returns the stats dict.
    """
    _provided_job_id = job_id
    _celery_task_id = self.request.id

    async def _execute() -> dict:
        _job_id = _provided_job_id
        if _job_id is None:
            _job_id = await _create_job("xbrl_render", "scheduler", _celery_task_id)
        return await _run_xbrl_render(_job_id, target_symbol=symbol)

    stats = asyncio.run(_execute())

    log.info(
        "tasks.xbrl_render done "
        "scanned=%d rendered=%d skipped=%d failed=%d sections_found=%d missing=%d",
        stats["files_scanned"],
        stats["files_rendered"],
        stats["files_skipped"],
        stats["files_failed"],
        stats["sections_found"],
        stats["sections_missing"],
    )
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# Parse task
# ─────────────────────────────────────────────────────────────────────────────

_EMPTY_PARSE_STATS: dict = {
    "files_scanned": 0,
    "files_parsed": 0,
    "files_failed": 0,
    "facts_found": 0,
    "facts_inserted": 0,
    "facts_updated": 0,
    "endpoint_blocked": False,
    "error": None,
}


async def _run_xbrl_parse(job_id: str, target_symbol: str | None = None) -> dict:
    """
    Async core for xbrl_parse task.

    Finds downloaded XBRLFile records (optionally filtered to target_symbol),
    parses each XBRL/iXBRL file, and upserts XBRLRawItem records.

    Dedup key: (xbrl_file_id, concept_name, context_ref, unit_ref).
    Existing facts are updated; new facts are inserted.
    A single file parse failure is recorded and the task continues.

    Args:
        target_symbol: If set, parse only files for this symbol.
    """
    from sqlalchemy import select, update
    from app.models.xbrl import XBRLFile, XBRLFiling, XBRLRawItem

    stats = {**_EMPTY_PARSE_STATS}
    start = datetime.now(timezone.utc)

    await _update_job(job_id, "running", stats, started_at=start)

    final_status = "failed"

    try:
        async with AsyncSessionLocal() as db:
            q = (
                select(XBRLFile, XBRLFiling)
                .join(XBRLFiling, XBRLFile.filing_id == XBRLFiling.id)
                .where(XBRLFile.download_status == "downloaded")
            )
            if target_symbol:
                q = q.where(XBRLFiling.symbol == target_symbol)
            result = await db.execute(q)
            rows = result.all()

        for xbrl_file, filing in rows:
            stats["files_scanned"] += 1

            if not xbrl_file.local_path:
                stats["files_failed"] += 1
                log.warning("XBRLFile %s has no local_path — skipping", xbrl_file.id)
                continue

            # Prefer the rendered snapshot for SA HTML viewer files
            if xbrl_file.rendered_path and Path(xbrl_file.rendered_path).exists():
                file_path = Path(xbrl_file.rendered_path)
            else:
                file_path = Path(xbrl_file.local_path)

            # Parse in a thread to keep the event loop free
            parse_result = await asyncio.to_thread(parse_xbrl_file, file_path)

            if parse_result.error:
                stats["files_failed"] += 1
                log.warning("Parse failed for file %s: %s", xbrl_file.id, parse_result.error)
                async with AsyncSessionLocal() as db:
                    await db.execute(
                        update(XBRLFile)
                        .where(XBRLFile.id == xbrl_file.id)
                        .values(error_message=parse_result.error[:2000])
                    )
                    await db.commit()
                continue

            stats["facts_found"] += len(parse_result.facts)

            # Load existing dedup keys for this file
            async with AsyncSessionLocal() as db:
                existing_result = await db.execute(
                    select(
                        XBRLRawItem.concept_name,
                        XBRLRawItem.context_ref,
                        XBRLRawItem.unit_ref,
                        XBRLRawItem.id,
                    ).where(XBRLRawItem.xbrl_file_id == xbrl_file.id)
                )
                existing: dict[tuple, object] = {
                    (row.concept_name, row.context_ref, row.unit_ref): row.id
                    for row in existing_result
                }

            now = datetime.now(timezone.utc)

            async with AsyncSessionLocal() as db:
                for fact in parse_result.facts:
                    key = (fact.concept_name, fact.context_ref, fact.unit_ref)

                    if key in existing:
                        await db.execute(
                            update(XBRLRawItem)
                            .where(XBRLRawItem.id == existing[key])
                            .values(
                                value_raw=fact.value_raw,
                                value_numeric=fact.value_numeric,
                                value=fact.value_numeric,
                                period_start=fact.period_start,
                                period_end=fact.period_end,
                                instant_date=fact.instant_date,
                                statement_type=fact.statement_type,
                                imported_at=now,
                            )
                        )
                        stats["facts_updated"] += 1
                    else:
                        db.add(XBRLRawItem(
                            filing_id=filing.id,
                            xbrl_file_id=xbrl_file.id,
                            company_id=filing.company_id,
                            symbol=filing.symbol,
                            concept_name=fact.concept_name,
                            concept_namespace=fact.concept_namespace,
                            label_ar=fact.label_ar,
                            label_en=fact.label_en,
                            value_raw=fact.value_raw,
                            value_numeric=fact.value_numeric,
                            value=fact.value_numeric,
                            unit_ref=fact.unit_ref,
                            decimals=fact.decimals,
                            context_ref=fact.context_ref,
                            period_start=fact.period_start,
                            period_end=fact.period_end,
                            instant_date=fact.instant_date,
                            fiscal_year=filing.fiscal_year,
                            fiscal_period=filing.period,
                            statement_type=fact.statement_type,
                            source_url=filing.xbrl_url,
                            local_file_path=str(file_path),
                            data_status="official",
                            parse_status="extracted",
                            imported_at=now,
                        ))
                        stats["facts_inserted"] += 1

                await db.commit()

            stats["files_parsed"] += 1

        final_status = "completed"

    except Exception as exc:
        log.exception("Unexpected error in xbrl_parse job_id=%s", job_id)
        stats["error"] = str(exc)
        final_status = "failed"

    end = datetime.now(timezone.utc)
    await _update_job(
        job_id, final_status, stats,
        completed_at=end,
        duration_seconds=int((end - start).total_seconds()),
    )
    return stats


@celery_app.task(name="tasks.xbrl_parse", bind=True)
def xbrl_parse_task(self, job_id: str | None = None, symbol: str | None = None):
    """
    Parse downloaded XBRL files into raw facts (xbrl_raw_items).
    symbol: optional — if provided, parse only files for that symbol.
    Idempotent: re-running updates existing facts, does not duplicate.
    Returns the stats dict.
    """
    _provided_job_id = job_id
    _celery_task_id = self.request.id

    async def _execute() -> dict:
        _job_id = _provided_job_id
        if _job_id is None:
            _job_id = await _create_job("xbrl_parse", "scheduler", _celery_task_id)
        return await _run_xbrl_parse(_job_id, target_symbol=symbol)

    stats = asyncio.run(_execute())

    log.info(
        "tasks.xbrl_parse done "
        "files_scanned=%d parsed=%d failed=%d "
        "facts_found=%d inserted=%d updated=%d",
        stats["files_scanned"],
        stats["files_parsed"],
        stats["files_failed"],
        stats["facts_found"],
        stats["facts_inserted"],
        stats["facts_updated"],
    )
    return stats
