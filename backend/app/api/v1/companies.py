from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.company import Company
from app.models.financial import NormalizedFinancial
from app.models.job import ImportJob
from app.schemas.common import PaginatedResponse, SingleResponse, PipelineMeta, LastImportJob
from app.schemas.company import CompanySummary, CompanyOut
from app.schemas.financial import (
    BalanceSheetSection,
    CashFlowSection,
    CompanyFinancialsOut,
    CompanySection,
    ConflictSummary,
    DataQualitySection,
    FilingSection,
    IncomeStatementSection,
    ResponseMetadata,
)

router = APIRouter()

_NO_DATA_MESSAGE = (
    "No official Saudi Exchange company data imported yet. "
    "Run the Saudi Exchange connectivity test and companies refresh job: "
    "GET /api/v1/system/saudi-exchange-health  then  "
    "POST /api/v1/jobs/trigger {job_type: fetch_companies}"
)


def _last_import_job_summary(job: ImportJob) -> LastImportJob:
    """Extract a LastImportJob summary from an ImportJob ORM record."""
    s = job.stats or {}
    return LastImportJob(
        job_id=str(job.id),
        status=job.status,
        companies_found=s.get("companies_found", 0),
        companies_inserted=s.get("companies_inserted", 0),
        companies_updated=s.get("companies_updated", 0),
        endpoint_blocked=s.get("endpoint_blocked", False),
        error_message=job.error_message,
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        duration_seconds=job.duration_seconds,
    )


@router.get("/unmapped", response_model=PaginatedResponse[CompanySummary])
async def list_unmapped_companies(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Return Main Market companies that have not yet been assigned a sector."""
    query = (
        select(Company)
        .options(selectinload(Company.sector))
        .where(Company.market == "tadawul")
        .where(Company.mapping_status == "unmapped_sector")
    )

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    companies = result.scalars().all()

    meta = PipelineMeta(
        pipeline_status="populated" if total > 0 else "not_configured",
        message=None,
        sample_data=False,
    )

    rows = [
        CompanySummary(
            id=c.id,
            symbol=c.symbol,
            arabic_name=c.arabic_name,
            english_name=c.english_name,
            market=c.market,
            sector_ar=None,
            sector_en=None,
            mapping_status=c.mapping_status,
            data_status=c.data_status,
        )
        for c in companies
    ]

    return PaginatedResponse(data=rows, total=total, page=page, per_page=per_page, meta=meta)


@router.get("/", response_model=PaginatedResponse[CompanySummary])
async def list_companies(
    market: str | None = Query(None, description="Filter by market: tadawul or nomu"),
    mapping_status: str | None = Query(None, description="Filter by mapping_status: mapped or unmapped_sector"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(Company).options(selectinload(Company.sector))
    # Default to Main Market / TASI only. Use ?market=nomu to explicitly query NOMU.
    effective_market = market or "tadawul"
    query = query.where(Company.market == effective_market)

    if mapping_status is not None:
        query = query.where(Company.mapping_status == mapping_status)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    companies = result.scalars().all()

    # Fetch the latest fetch_companies import job for meta reporting.
    job_result = await db.execute(
        select(ImportJob)
        .where(ImportJob.job_type == "fetch_companies")
        .order_by(ImportJob.created_at.desc())
        .limit(1)
    )
    last_job = job_result.scalar_one_or_none()

    # Determine pipeline_status and message.
    if total > 0:
        pipeline_status = "populated"
        message = None
    elif last_job and last_job.status == "failed":
        pipeline_status = "import_failed"
        stats = last_job.stats or {}
        if stats.get("endpoint_blocked"):
            message = (
                "Last import failed: Saudi Exchange blocked this environment "
                f"({last_job.error_message or 'Akamai/geo block'}). "
                "Deploy on a Saudi/GCC server to import official data."
            )
        else:
            message = (
                f"Last import failed: {last_job.error_message or 'unknown error'}. "
                "Check GET /api/v1/system/saudi-exchange-health for details."
            )
    elif last_job and last_job.status in ("pending", "running"):
        pipeline_status = "import_running"
        message = "Import job is currently running. Refresh in a moment."
    else:
        pipeline_status = "not_configured"
        message = _NO_DATA_MESSAGE

    meta = PipelineMeta(
        pipeline_status=pipeline_status,
        message=message,
        sample_data=any(c.data_status == "sample_not_official" for c in companies),
        last_import_job=_last_import_job_summary(last_job) if last_job else None,
    )

    rows = [
        CompanySummary(
            id=c.id,
            symbol=c.symbol,
            arabic_name=c.arabic_name,
            english_name=c.english_name,
            market=c.market,
            sector_ar=c.sector.arabic_name if c.sector else None,
            sector_en=c.sector.english_name if c.sector else None,
            mapping_status=c.mapping_status,
            data_status=c.data_status,
        )
        for c in companies
    ]

    return PaginatedResponse(data=rows, total=total, page=page, per_page=per_page, meta=meta)


@router.get("/{symbol}", response_model=SingleResponse[CompanyOut])
async def get_company(symbol: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Company).where(Company.symbol == symbol.upper())
    )
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {symbol.upper()} not found",
        )

    meta = PipelineMeta(
        pipeline_status="populated",
        sample_data=company.data_status == "sample_not_official",
    )

    return SingleResponse(data=CompanyOut.model_validate(company), meta=meta)


@router.get("/{symbol}/financials", response_model=SingleResponse[CompanyFinancialsOut])
async def get_company_financials(
    symbol: str,
    fiscal_year: int | None = Query(None, description="Filter by fiscal year, e.g. 2025"),
    fiscal_period: str | None = Query(None, description="Filter by period, e.g. Annual, Q1"),
    db: AsyncSession = Depends(get_db),
):
    """
    Read-only normalized financial data for a company page.

    Reads only from existing tables (companies, normalized_financials,
    normalization_conflicts). No ratios, EPS, EBITDA, gross_profit,
    operating_profit, or valuation fields are calculated or exposed here —
    see Phase 2G hard stop. If fiscal_year/fiscal_period are omitted, the
    most recent normalized period is returned.
    """
    symbol = symbol.upper()

    company_result = await db.execute(
        select(Company).options(selectinload(Company.sector)).where(Company.symbol == symbol)
    )
    company = company_result.scalar_one_or_none()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {symbol} not found",
        )

    query = select(NormalizedFinancial).where(NormalizedFinancial.symbol == symbol)
    if fiscal_year is not None:
        query = query.where(NormalizedFinancial.fiscal_year == fiscal_year)
    if fiscal_period is not None:
        query = query.where(NormalizedFinancial.period == fiscal_period)
    query = query.order_by(NormalizedFinancial.fiscal_year.desc().nulls_last()).limit(1)

    nf_result = await db.execute(query)
    nf = nf_result.scalars().first()

    if not nf:
        filters = []
        if fiscal_year is not None:
            filters.append(f"fiscal_year={fiscal_year}")
        if fiscal_period is not None:
            filters.append(f"fiscal_period={fiscal_period}")
        filter_note = f" ({', '.join(filters)})" if filters else ""
        meta = PipelineMeta(
            pipeline_status="not_configured",
            message=(
                f"No normalized financial data found for {symbol}{filter_note}. "
                "Run the XBRL normalization pipeline for this symbol."
            ),
        )
        return SingleResponse(success=False, data=None, meta=meta)

    company_section = CompanySection(
        symbol=company.symbol,
        name_ar=company.arabic_name,
        name_en=company.english_name,
        market=company.market,
        sector_ar=company.sector.arabic_name if company.sector else None,
        sector_en=company.sector.english_name if company.sector else None,
    )

    filing_section = FilingSection(
        fiscal_year=nf.fiscal_year,
        period=nf.period,
        period_type=nf.period_type,
        reporting_scale=nf.reporting_scale,
        is_consolidated=None,
        normalization_status=nf.normalization_status,
    )

    conflicts = [
        ConflictSummary(
            field_name=c.field_name,
            resolution_status=c.resolution_status,
            candidate_count=len(c.conflicting_values) if c.conflicting_values else 0,
        )
        for c in nf.conflicts
    ]

    data_quality_section = DataQualitySection(
        missing_fields=(nf.missing_fields or {}).get("fields", []),
        conflict_count=len(conflicts),
        conflicts=conflicts,
        source_map_available=bool(nf.source_map),
        source_map=nf.source_map,
    )

    out = CompanyFinancialsOut(
        company=company_section,
        filing=filing_section,
        balance_sheet=BalanceSheetSection.model_validate(nf),
        income_statement=IncomeStatementSection.model_validate(nf),
        cash_flow=CashFlowSection.model_validate(nf),
        data_quality=data_quality_section,
        metadata=ResponseMetadata(generated_at=datetime.now(timezone.utc)),
    )

    meta = PipelineMeta(pipeline_status="populated")

    return SingleResponse(data=out, meta=meta)
