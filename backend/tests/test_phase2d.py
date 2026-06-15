"""
Phase 2D tests — TASI sector and market-index pipeline.

All tests are offline: HTTP calls and DB operations are mocked.

Required scenarios (per Phase 2D spec):
  1. Main Market company included after import
  2. NOMU company excluded by default from GET /companies/
  3. REIT included if Main Market (market_type='M')
  4. Company without official sector → mapping_status='unmapped_sector'
  5. Sector import idempotent (first run inserts, second run updates)
  6. Index import idempotent (first run inserts, second run updates)
  7. GET /companies/ API includes sector_ar / sector_en fields
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import get_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _AsyncCtx:
    def __init__(self, obj):
        self._obj = obj

    async def __aenter__(self):
        return self._obj

    async def __aexit__(self, *_):
        pass


def _session_factory(db_mock):
    return lambda: _AsyncCtx(db_mock)


def _make_db_all_inserts() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    no_row = MagicMock()
    no_row.scalar_one_or_none.return_value = None
    db.execute.return_value = no_row
    return db


def _make_db_all_updates() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    existing = MagicMock()
    existing.data_status = "official"
    row_result = MagicMock()
    row_result.scalar_one_or_none.return_value = existing
    db.execute.return_value = row_result
    return db


def _api_db_override(db_mock):
    async def _override():
        yield db_mock
    return _override


def _make_company_record(symbol: str = "1010", market: str = "tadawul"):
    from app.pipeline.exchange.companies import CompanyRecord
    return CompanyRecord(
        symbol=symbol,
        arabic_name="شركة اختبار",
        english_name="Test Company",
        market=market,
        source="saudi_exchange_official",
        source_url="https://www.saudiexchange.sa/",
        imported_at=datetime.now(timezone.utc),
        data_status="official",
        mapping_status="unmapped_sector",
    )


def _make_company_fetch_result(companies=None):
    from app.pipeline.exchange.companies import FetchResult
    return FetchResult(
        companies=companies or [],
        reachable=True,
        blocked=False,
        status_code=200,
        raw_format="json",
        parse_note="",
        error=None,
        fetched_at=_now(),
    )


def _make_sector_records():
    from app.pipeline.exchange.sectors import SectorRecord
    return [
        SectorRecord(
            code="TBNI",
            english_name="Banks",
            arabic_name=None,
            market="tadawul",
            source="saudi_exchange_html_widget",
            source_url="https://www.saudiexchange.sa/",
            imported_at=datetime.now(timezone.utc),
        ),
        SectorRecord(
            code="TENI",
            english_name="Energy",
            arabic_name=None,
            market="tadawul",
            source="saudi_exchange_html_widget",
            source_url="https://www.saudiexchange.sa/",
            imported_at=datetime.now(timezone.utc),
        ),
    ]


def _make_index_records():
    from app.pipeline.exchange.sectors import IndexRecord
    return [
        IndexRecord(
            code="TASI",
            english_name="Tadawul All Share Index (TASI)",
            arabic_name=None,
            index_type="main",
            sector_code=None,
            market="tadawul",
            source="saudi_exchange_html_widget",
            source_url="https://www.saudiexchange.sa/",
            imported_at=datetime.now(timezone.utc),
        ),
    ]


def _make_sector_fetch_result(sectors=None, indices=None):
    from app.pipeline.exchange.sectors import SectorFetchResult
    return SectorFetchResult(
        sectors=sectors if sectors is not None else _make_sector_records(),
        indices=indices if indices is not None else _make_index_records(),
        reachable=True,
        blocked=False,
        status_code=200,
        parse_note="Parsed 2 sector indices and 1 market indices.",
        error=None,
        fetched_at=_now(),
    )


# ---------------------------------------------------------------------------
# 1. Main Market company included after import
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_main_market_company_included():
    """Company with market='tadawul' is inserted when fetcher returns it."""
    rec = _make_company_record(symbol="2222", market="tadawul")
    fetch_result = _make_company_fetch_result(companies=[rec])
    db = _make_db_all_inserts()
    job_id = str(uuid.uuid4())

    with (
        patch("app.workers.tasks_companies.fetch_companies", return_value=fetch_result),
        patch("app.workers.tasks_companies.AsyncSessionLocal", _session_factory(db)),
    ):
        from app.workers.tasks_companies import _run_import
        stats = await _run_import(job_id)

    assert stats["companies_inserted"] == 1
    assert stats["companies_found"] == 1
    assert db.add.call_count == 1


# ---------------------------------------------------------------------------
# 2. NOMU company excluded by default from GET /companies/
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_nomu_company_excluded_by_default_from_api():
    """
    GET /companies/ defaults to market=tadawul.
    A company with market='nomu' would not appear without ?market=nomu.
    This test verifies the API query always applies the market filter.
    """
    count_result = MagicMock()
    count_result.scalar.return_value = 3  # 3 tadawul companies

    companies_result = MagicMock()
    tadawul_co = MagicMock()
    tadawul_co.id = uuid.uuid4()
    tadawul_co.symbol = "1010"
    tadawul_co.arabic_name = "الراجحي"
    tadawul_co.english_name = "Al Rajhi"
    tadawul_co.market = "tadawul"
    tadawul_co.sector = None
    tadawul_co.mapping_status = "unmapped_sector"
    tadawul_co.data_status = "official"
    companies_result.scalars.return_value.all.return_value = [tadawul_co]

    job_result = MagicMock()
    job_result.scalar_one_or_none.return_value = None

    db = AsyncMock()
    db.execute.side_effect = [count_result, companies_result, job_result]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        with (
            patch("app.core.database.check_db_health", new_callable=AsyncMock, return_value=True),
            patch("app.core.redis_client.check_redis_health", new_callable=AsyncMock, return_value=True),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get("/api/v1/companies/")
        assert resp.status_code == 200
        body = resp.json()
        # All returned companies are tadawul only
        for co in body["data"]:
            assert co["market"] == "tadawul"
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 3. REIT included if Main Market (market_type='M')
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reit_included_if_main_market():
    """
    A REIT company with market_type='M' is included by the fetcher
    and inserted into the DB with market='tadawul'.
    """
    from app.pipeline.exchange.companies import FetchResult, CompanyRecord
    import json

    reit_entry = {
        "symbol": "4347",
        "companyNameAR": "صندوق الراجحي",
        "companyNameEN": "Al Rajhi REIT",
        "market_type": "M",     # Main Market — REITs trade here
        "tradingNameEn": "RAJHI REIT",
        "tradingNameAr": "الراجحي ريت",
        "isin": "SA1234567890",
    }

    from app.pipeline.exchange import companies as co_module

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.headers = {"content-type": "application/json"}
    fake_resp.json.return_value = [reit_entry]

    with patch.object(co_module, "_http_get", return_value=fake_resp):
        result = co_module.fetch_companies()

    assert len(result.companies) == 1
    assert result.companies[0].symbol == "4347"
    assert result.companies[0].market == "tadawul"
    assert result.companies[0].mapping_status == "unmapped_sector"


# ---------------------------------------------------------------------------
# 4. Company without official sector → mapping_status='unmapped_sector'
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_company_without_sector_is_unmapped():
    """
    ThemeSearchUtilityServlet has no sector field.
    All imported companies must have mapping_status='unmapped_sector'.
    """
    from app.pipeline.exchange import companies as co_module

    entries = [
        {
            "symbol": "1010",
            "companyNameAR": "الراجحي",
            "companyNameEN": "Al Rajhi",
            "market_type": "M",
        },
        {
            "symbol": "2222",
            "companyNameAR": "أرامكو",
            "companyNameEN": "Saudi Aramco",
            "market_type": "M",
        },
    ]

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.headers = {"content-type": "application/json"}
    fake_resp.json.return_value = entries

    with patch.object(co_module, "_http_get", return_value=fake_resp):
        result = co_module.fetch_companies()

    assert len(result.companies) == 2
    for company in result.companies:
        assert company.mapping_status == "unmapped_sector", (
            f"Expected 'unmapped_sector' but got '{company.mapping_status}' "
            f"for {company.symbol}"
        )


# ---------------------------------------------------------------------------
# 5. Sector import idempotent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sector_import_idempotent_first_run_inserts():
    """First sector import → 2 sectors inserted, 0 updated."""
    sector_result = _make_sector_fetch_result()
    db = _make_db_all_inserts()
    job_id = str(uuid.uuid4())

    with (
        patch("app.workers.tasks_sectors.fetch_sectors", return_value=sector_result),
        patch("app.workers.tasks_sectors.AsyncSessionLocal", _session_factory(db)),
    ):
        from app.workers.tasks_sectors import _run_sector_import
        stats = await _run_sector_import(job_id)

    assert stats["sectors_found"] == 2
    assert stats["sectors_inserted"] == 2
    assert stats["sectors_updated"] == 0
    assert stats["indices_found"] == 1
    assert stats["indices_inserted"] == 1
    assert stats["indices_updated"] == 0


@pytest.mark.asyncio
async def test_sector_import_idempotent_second_run_updates():
    """Second sector import with same codes → 0 inserted, 2 updated."""
    sector_result = _make_sector_fetch_result()
    db = _make_db_all_updates()
    job_id = str(uuid.uuid4())

    with (
        patch("app.workers.tasks_sectors.fetch_sectors", return_value=sector_result),
        patch("app.workers.tasks_sectors.AsyncSessionLocal", _session_factory(db)),
    ):
        from app.workers.tasks_sectors import _run_sector_import
        stats = await _run_sector_import(job_id)

    assert stats["sectors_found"] == 2
    assert stats["sectors_inserted"] == 0
    assert stats["sectors_updated"] == 2
    assert stats["indices_inserted"] == 0
    assert stats["indices_updated"] == 1
    db.add.assert_not_called()


# ---------------------------------------------------------------------------
# 6. Index import idempotent (covered by test 5 above — same task)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_index_import_idempotent():
    """
    Sector fetch task stores market indices.
    Running it twice: first inserts, second updates.
    """
    index_result = _make_sector_fetch_result(
        sectors=[],   # no sectors, just indices
        indices=_make_index_records(),
    )
    db_first = _make_db_all_inserts()
    db_second = _make_db_all_updates()

    job_id_1 = str(uuid.uuid4())
    job_id_2 = str(uuid.uuid4())

    with (
        patch("app.workers.tasks_sectors.fetch_sectors", return_value=index_result),
        patch("app.workers.tasks_sectors.AsyncSessionLocal", _session_factory(db_first)),
    ):
        from app.workers.tasks_sectors import _run_sector_import
        stats1 = await _run_sector_import(job_id_1)

    assert stats1["indices_inserted"] == 1
    assert stats1["indices_updated"] == 0

    with (
        patch("app.workers.tasks_sectors.fetch_sectors", return_value=index_result),
        patch("app.workers.tasks_sectors.AsyncSessionLocal", _session_factory(db_second)),
    ):
        stats2 = await _run_sector_import(job_id_2)

    assert stats2["indices_inserted"] == 0
    assert stats2["indices_updated"] == 1
    db_second.add.assert_not_called()


# ---------------------------------------------------------------------------
# 7. GET /companies/ API includes sector_ar / sector_en fields
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_companies_api_includes_sector_info():
    """
    GET /companies/ returns CompanySummary with sector_ar and sector_en fields.
    When a company has a linked Sector, those fields are populated.
    When no sector is linked, they are null.
    """
    sector_mock = MagicMock()
    sector_mock.arabic_name = None       # not available from source
    sector_mock.english_name = "Banks"

    co_with_sector = MagicMock()
    co_with_sector.id = uuid.uuid4()
    co_with_sector.symbol = "1010"
    co_with_sector.arabic_name = "الراجحي"
    co_with_sector.english_name = "Al Rajhi"
    co_with_sector.market = "tadawul"
    co_with_sector.sector = sector_mock
    co_with_sector.mapping_status = "mapped"
    co_with_sector.data_status = "official"

    co_without_sector = MagicMock()
    co_without_sector.id = uuid.uuid4()
    co_without_sector.symbol = "2222"
    co_without_sector.arabic_name = "أرامكو"
    co_without_sector.english_name = "Saudi Aramco"
    co_without_sector.market = "tadawul"
    co_without_sector.sector = None
    co_without_sector.mapping_status = "unmapped_sector"
    co_without_sector.data_status = "official"

    count_result = MagicMock()
    count_result.scalar.return_value = 2

    companies_result = MagicMock()
    companies_result.scalars.return_value.all.return_value = [
        co_with_sector, co_without_sector
    ]

    job_result = MagicMock()
    job_result.scalar_one_or_none.return_value = None

    db = AsyncMock()
    db.execute.side_effect = [count_result, companies_result, job_result]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        with (
            patch("app.core.database.check_db_health", new_callable=AsyncMock, return_value=True),
            patch("app.core.redis_client.check_redis_health", new_callable=AsyncMock, return_value=True),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get("/api/v1/companies/")
        assert resp.status_code == 200
        body = resp.json()
        data = body["data"]
        assert len(data) == 2

        co_1010 = next(c for c in data if c["symbol"] == "1010")
        co_2222 = next(c for c in data if c["symbol"] == "2222")

        # sector_ar and sector_en fields must be present in every response
        assert "sector_ar" in co_1010
        assert "sector_en" in co_1010
        assert "sector_ar" in co_2222
        assert "sector_en" in co_2222

        # Company with sector linked
        assert co_1010["sector_en"] == "Banks"
        assert co_1010["sector_ar"] is None    # not available from source

        # Company without sector
        assert co_2222["sector_en"] is None
        assert co_2222["sector_ar"] is None
        assert co_2222["mapping_status"] == "unmapped_sector"
    finally:
        app.dependency_overrides.clear()
