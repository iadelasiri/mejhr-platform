"""
Phase 2D.1 tests — company-to-sector mapping pipeline.

All tests are offline: CSV operations use tmp_path, DB operations are mocked.

Required scenarios (per Phase 2D.1 spec):
  1. Valid mapping updates company.sector_id and mapping_status='mapped'
  2. Invalid sector_code is rejected and reported
  3. Unknown symbol is reported in unknown_symbols
  4. source_url is required — empty source_url causes row to be skipped
  5. Duplicate import does not duplicate mappings — second run updates, not inserts
  6. Unmapped companies remain visible in /companies/unmapped report
  7. API includes sector fields for mapped companies (?mapping_status=mapped)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import get_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _api_db_override(db_mock):
    async def _override():
        yield db_mock
    return _override


def _make_sector_mock(code: str) -> MagicMock:
    s = MagicMock()
    s.code = code
    s.id = uuid.uuid4()
    return s


def _make_company_mock(symbol: str, sector_id=None) -> MagicMock:
    c = MagicMock()
    c.symbol = symbol
    c.sector_id = sector_id
    c.mapping_status = "unmapped_sector" if sector_id is None else "mapped"
    c.sector_mapping_info = None
    return c


def _make_mapping_row(
    symbol: str = "1010",
    sector_code: str = "TBNI",
    source_url: str = "https://www.saudiexchange.sa/company-profile?companySymbol=1010",
    confidence: str = "verified",
):
    from app.pipeline.sector_mapping.importer import MappingRow
    return MappingRow(
        symbol=symbol,
        company_name="Test Company",
        sector_code=sector_code,
        sector_name="Banks",
        source_url=source_url,
        mapping_source="manual_review",
        reviewed_at="2026-06-15",
        confidence=confidence,
    )


def _make_apply_db(sectors: list, company=None) -> AsyncMock:
    """Build a mock DB session for apply_mappings tests."""
    db = AsyncMock()

    sector_result = MagicMock()
    sector_result.scalars.return_value.all.return_value = sectors

    company_result = MagicMock()
    company_result.scalar_one_or_none.return_value = company

    # First execute: select(Sector). Subsequent: select(Company).
    db.execute.side_effect = [sector_result] + [company_result] * 20
    return db


# ---------------------------------------------------------------------------
# 1. Valid mapping updates company.sector_id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_valid_mapping_updates_sector_id():
    """apply_mappings sets sector_id and mapping_status='mapped' on the company."""
    from app.pipeline.sector_mapping.importer import apply_mappings

    sector = _make_sector_mock("TBNI")
    company = _make_company_mock("1010", sector_id=None)
    db = _make_apply_db(sectors=[sector], company=company)

    rows = [_make_mapping_row(symbol="1010", sector_code="TBNI")]
    stats = await apply_mappings(rows, db)

    assert stats["companies_mapped"] == 1
    assert stats["companies_updated"] == 0
    assert stats["companies_not_found"] == 0
    assert company.sector_id == sector.id
    assert company.mapping_status == "mapped"
    assert company.sector_mapping_info is not None
    assert company.sector_mapping_info["source_url"].startswith("https://")
    assert company.sector_mapping_info["confidence"] == "verified"


# ---------------------------------------------------------------------------
# 2. Invalid sector_code rejected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invalid_sector_code_rejected():
    """Rows referencing a sector_code not in the DB are skipped and reported."""
    from app.pipeline.sector_mapping.importer import apply_mappings

    # No sectors in DB → every sector_code is invalid
    db = _make_apply_db(sectors=[], company=None)

    rows = [_make_mapping_row(symbol="1010", sector_code="BOGUS_CODE")]
    stats = await apply_mappings(rows, db)

    assert stats["companies_mapped"] == 0
    assert "BOGUS_CODE" in stats["invalid_sector_codes"]
    # Company execute should never be called — rejected at sector lookup
    # The first execute is select(Sector), no more calls expected for rejected rows
    assert db.execute.call_count == 1  # only the sector query


# ---------------------------------------------------------------------------
# 3. Unknown symbol reported
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_symbol_reported():
    """Symbol not found in companies table is reported in unknown_symbols."""
    from app.pipeline.sector_mapping.importer import apply_mappings

    sector = _make_sector_mock("TBNI")
    # Company not found
    db = _make_apply_db(sectors=[sector], company=None)

    rows = [_make_mapping_row(symbol="9999", sector_code="TBNI")]
    stats = await apply_mappings(rows, db)

    assert stats["companies_mapped"] == 0
    assert stats["companies_not_found"] == 1
    assert "9999" in stats["unknown_symbols"]
    assert stats["invalid_sector_codes"] == []


# ---------------------------------------------------------------------------
# 4. source_url required
# ---------------------------------------------------------------------------

def test_source_url_required(tmp_path: Path):
    """load_csv skips rows where source_url is empty and reports an error."""
    from app.pipeline.sector_mapping.importer import load_csv

    csv_file = tmp_path / "test.csv"
    csv_file.write_text(
        "symbol,company_name,sector_code,sector_name,source_url,"
        "mapping_source,reviewed_at,confidence\n"
        "1010,Al Rajhi,TBNI,Banks,,manual_review,2026-06-15,verified\n",
        encoding="utf-8",
    )

    rows, errors = load_csv(csv_file)

    assert len(rows) == 0
    assert any("source_url required" in e for e in errors)


def test_load_csv_accepts_valid_row(tmp_path: Path):
    """load_csv accepts rows with all required fields present."""
    from app.pipeline.sector_mapping.importer import load_csv

    csv_file = tmp_path / "test.csv"
    csv_file.write_text(
        "symbol,company_name,sector_code,sector_name,source_url,"
        "mapping_source,reviewed_at,confidence\n"
        "1010,Al Rajhi,TBNI,Banks,https://example.com/,"
        "manual_review,2026-06-15,verified\n",
        encoding="utf-8",
    )

    rows, errors = load_csv(csv_file)

    assert len(rows) == 1
    assert rows[0].symbol == "1010"
    assert rows[0].sector_code == "TBNI"
    assert rows[0].confidence == "verified"
    assert errors == []


def test_load_csv_skips_needs_review_rows(tmp_path: Path):
    """load_csv still reads needs_review rows (confidence filter is in apply_mappings)."""
    from app.pipeline.sector_mapping.importer import load_csv

    csv_file = tmp_path / "test.csv"
    csv_file.write_text(
        "symbol,company_name,sector_code,sector_name,source_url,"
        "mapping_source,reviewed_at,confidence\n"
        "1010,Al Rajhi,TBNI,Banks,https://example.com/,"
        "manual_review,2026-06-15,needs_review\n",
        encoding="utf-8",
    )

    rows, errors = load_csv(csv_file)

    # load_csv reads all syntactically valid rows; apply_mappings filters confidence
    assert len(rows) == 1
    assert rows[0].confidence == "needs_review"
    assert errors == []


@pytest.mark.asyncio
async def test_needs_review_rows_skipped_by_apply_mappings():
    """apply_mappings skips rows with confidence='needs_review'."""
    from app.pipeline.sector_mapping.importer import apply_mappings

    sector = _make_sector_mock("TBNI")
    company = _make_company_mock("1010")
    db = _make_apply_db(sectors=[sector], company=company)

    rows = [_make_mapping_row(symbol="1010", sector_code="TBNI", confidence="needs_review")]
    stats = await apply_mappings(rows, db)

    assert stats["rows_skipped_confidence"] == 1
    assert stats["companies_mapped"] == 0
    assert company.mapping_status == "unmapped_sector"  # untouched


# ---------------------------------------------------------------------------
# 5. Duplicate import does not duplicate mappings
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_duplicate_import_updates_not_duplicates():
    """
    Second import run for an already-mapped company increments companies_updated,
    not companies_mapped, and does not create duplicate records.
    """
    from app.pipeline.sector_mapping.importer import apply_mappings

    sector = _make_sector_mock("TBNI")
    # Company already has a sector_id from a prior import
    company = _make_company_mock("1010", sector_id=uuid.uuid4())
    db = _make_apply_db(sectors=[sector], company=company)

    rows = [_make_mapping_row(symbol="1010", sector_code="TBNI")]
    stats = await apply_mappings(rows, db)

    assert stats["companies_mapped"] == 0
    assert stats["companies_updated"] == 1
    # sector_id updated to latest sector
    assert company.sector_id == sector.id
    # mapping_status stays mapped
    assert company.mapping_status == "mapped"


# ---------------------------------------------------------------------------
# 6. Unmapped companies visible in /companies/unmapped
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unmapped_companies_visible_in_report():
    """GET /api/v1/companies/unmapped returns companies with mapping_status='unmapped_sector'."""
    unmapped_co = MagicMock()
    unmapped_co.id = uuid.uuid4()
    unmapped_co.symbol = "3333"
    unmapped_co.arabic_name = "شركة غير مصنفة"
    unmapped_co.english_name = "Unclassified Co"
    unmapped_co.market = "tadawul"
    unmapped_co.sector = None
    unmapped_co.mapping_status = "unmapped_sector"
    unmapped_co.data_status = "official"

    count_result = MagicMock()
    count_result.scalar.return_value = 1

    companies_result = MagicMock()
    companies_result.scalars.return_value.all.return_value = [unmapped_co]

    db = AsyncMock()
    db.execute.side_effect = [count_result, companies_result]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/unmapped")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["data"][0]["symbol"] == "3333"
        assert body["data"][0]["mapping_status"] == "unmapped_sector"
        assert body["data"][0]["sector_en"] is None
        assert body["data"][0]["sector_ar"] is None
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 7. API includes sector fields for mapped companies
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_includes_sector_fields_for_mapped_companies():
    """
    GET /api/v1/companies/?mapping_status=mapped returns companies where sector
    fields are populated from the linked Sector record.
    """
    sector_mock = MagicMock()
    sector_mock.arabic_name = None  # not available from source
    sector_mock.english_name = "Banks"

    mapped_co = MagicMock()
    mapped_co.id = uuid.uuid4()
    mapped_co.symbol = "1010"
    mapped_co.arabic_name = "الراجحي"
    mapped_co.english_name = "Al Rajhi"
    mapped_co.market = "tadawul"
    mapped_co.sector = sector_mock
    mapped_co.mapping_status = "mapped"
    mapped_co.data_status = "official"

    count_result = MagicMock()
    count_result.scalar.return_value = 1

    companies_result = MagicMock()
    companies_result.scalars.return_value.all.return_value = [mapped_co]

    job_result = MagicMock()
    job_result.scalar_one_or_none.return_value = None

    db = AsyncMock()
    db.execute.side_effect = [count_result, companies_result, job_result]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/?mapping_status=mapped")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        co = body["data"][0]
        assert co["mapping_status"] == "mapped"
        assert co["sector_en"] == "Banks"
        assert co["sector_ar"] is None  # not available from Saudi Exchange source
        # sector fields are always present (never missing key)
        assert "sector_ar" in co
        assert "sector_en" in co
    finally:
        app.dependency_overrides.clear()
