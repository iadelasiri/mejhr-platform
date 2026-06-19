"""
Phase 2G.5 tests — GET /api/v1/companies/{symbol}/financials response structure.

Supersedes test_phase2g4.py: the response shape changed from a flat
"financials" object to nested sections (company, filing, balance_sheet,
income_statement, cash_flow, data_quality, metadata) matching the future
company page layout. All tests mock the DB session via
app.dependency_overrides[get_db]. No real DB connection.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import get_db


# ── Helpers ───────────────────────────────────────────────────────────────────

def _api_db_override(db_mock):
    async def _override():
        yield db_mock
    return _override


def _make_company(symbol="2240", sector_ar="مواد أساسية", sector_en="Basic Materials"):
    sector = MagicMock()
    sector.arabic_name = sector_ar
    sector.english_name = sector_en

    company = MagicMock()
    company.id = uuid.uuid4()
    company.symbol = symbol
    company.arabic_name = "شركة اختبار"
    company.english_name = "Test Co"
    company.market = "tadawul"
    company.sector = sector
    company.data_status = "official"
    return company


def _make_normalized_financial(symbol="2240", **overrides):
    nf = MagicMock()
    nf.symbol = symbol
    nf.fiscal_year = overrides.get("fiscal_year", 2025)
    nf.period = overrides.get("period", "Annual")
    nf.period_type = overrides.get("period_type", "annual")
    nf.reporting_scale = overrides.get("reporting_scale", 1000)
    nf.revenue = Decimal("6200549000.0000")
    nf.finance_cost = Decimal("166184000.0000")
    nf.profit_before_tax = Decimal("186752000.0000")
    nf.zakat_tax = Decimal("4888000.0000")
    nf.net_income = Decimal("168320000.0000")
    nf.total_assets = Decimal("5918589000.0000")
    nf.total_liabilities = Decimal("5224804000.0000")
    nf.equity = Decimal("693785000.0000")
    nf.cash_and_equivalents = Decimal("299300000.0000")
    nf.short_term_debt = None
    nf.long_term_debt = Decimal("217310000.0000")
    nf.total_debt = None
    nf.operating_cash_flow = Decimal("128760000.0000")
    nf.investing_cash_flow = Decimal("-283267000.0000")
    nf.financing_cash_flow = Decimal("-97928000.0000")
    nf.capex = Decimal("-181206000.0000")
    nf.free_cash_flow = Decimal("-52446000.0000")
    nf.source_map = overrides.get("source_map", {
        "revenue": {"raw_item_id": "abc-123", "label_ar": "الإيرادات", "context_ref": "PERIOD__2025-01-01__2025-12-31"},
        "free_cash_flow": {
            "calculated": True,
            "formula": "operating_cash_flow + capex",
            "components": {"operating_cash_flow": 128760000.0, "capex": -181206000.0},
        },
    })
    nf.missing_fields = overrides.get("missing_fields", {"fields": ["total_debt"]})
    nf.normalization_status = overrides.get("normalization_status", "conflict")
    nf.imported_at = None
    nf.created_at = datetime(2026, 6, 17, tzinfo=timezone.utc)
    nf.conflicts = overrides.get("conflicts", [])
    return nf


def _make_conflict(field_name="short_term_debt", resolution_status="unresolved", candidates=None):
    c = MagicMock()
    c.field_name = field_name
    c.resolution_status = resolution_status
    c.conflicting_values = candidates or [
        {"raw_item_id": "id1", "label_ar": "قروض قصيرة الأجل", "value": 200000.0},
        {"raw_item_id": "id2", "label_ar": "قسط متداول من قروض طويلة الأجل", "value": 80000.0},
    ]
    return c


def _scalar_one_or_none_result(obj):
    r = MagicMock()
    r.scalar_one_or_none.return_value = obj
    return r


def _scalars_first_result(obj):
    r = MagicMock()
    r.scalars.return_value.first.return_value = obj
    return r


def _collect_keys(obj, keys=None):
    """Recursively collect every dict key in a JSON-decoded structure."""
    if keys is None:
        keys = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            _collect_keys(v, keys)
    elif isinstance(obj, list):
        for item in obj:
            _collect_keys(item, keys)
    return keys


_FORBIDDEN_KEYS = frozenset({
    "eps", "ebitda", "ebit", "operating_profit", "gross_profit",
    "cost_of_revenue", "ratio", "ratios", "pe", "pb", "ps", "roe", "roic",
    "roa", "ev_ic", "ev_ebit", "debt_equity", "fcf_yield", "gross_margin",
    "operating_margin", "net_margin", "market_cap", "enterprise_value",
    "fair_value_estimate", "valuation", "screener", "upside_downside",
})


# ── 1. Returns expected sections ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_returns_expected_sections():
    company = _make_company(symbol="2240")
    nf = _make_normalized_financial(symbol="2240")
    nf.conflicts = [_make_conflict()]

    db = AsyncMock()
    db.execute.side_effect = [
        _scalar_one_or_none_result(company),
        _scalars_first_result(nf),
    ]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/2240/financials")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert set(data.keys()) == {
            "company", "filing", "balance_sheet", "income_statement",
            "cash_flow", "data_quality", "metadata",
        }
    finally:
        app.dependency_overrides.clear()


# ── 2. company section ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_company_section_fields():
    company = _make_company(symbol="2240")
    nf = _make_normalized_financial(symbol="2240")

    db = AsyncMock()
    db.execute.side_effect = [_scalar_one_or_none_result(company), _scalars_first_result(nf)]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/2240/financials")
        co = resp.json()["data"]["company"]
        assert co["symbol"] == "2240"
        assert co["name_ar"] == "شركة اختبار"
        assert co["name_en"] == "Test Co"
        assert co["market"] == "tadawul"
        assert co["sector_ar"] == "مواد أساسية"
        assert co["sector_en"] == "Basic Materials"
    finally:
        app.dependency_overrides.clear()


# ── 3. filing section ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_filing_section_fields():
    company = _make_company(symbol="2222")
    nf = _make_normalized_financial(
        symbol="2222", fiscal_year=2025, period="Annual", period_type="annual",
        reporting_scale=1000000, normalization_status="normalized",
    )

    db = AsyncMock()
    db.execute.side_effect = [_scalar_one_or_none_result(company), _scalars_first_result(nf)]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/2222/financials")
        filing = resp.json()["data"]["filing"]
        assert filing["fiscal_year"] == 2025
        assert filing["period"] == "Annual"
        assert filing["period_type"] == "annual"
        assert filing["reporting_scale"] == 1000000
        assert filing["normalization_status"] == "normalized"
        assert filing["is_consolidated"] is None
    finally:
        app.dependency_overrides.clear()


# ── 4. balance_sheet / income_statement / cash_flow sections ─────────────────

@pytest.mark.asyncio
async def test_financial_sections_values():
    company = _make_company(symbol="4263")
    nf = _make_normalized_financial(symbol="4263")

    db = AsyncMock()
    db.execute.side_effect = [_scalar_one_or_none_result(company), _scalars_first_result(nf)]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/4263/financials")
        data = resp.json()["data"]

        bs = data["balance_sheet"]
        assert set(bs.keys()) == {
            "total_assets", "total_liabilities", "equity", "cash_and_equivalents",
            "short_term_debt", "long_term_debt", "total_debt",
        }
        assert bs["total_assets"] == "5918589000.0000"

        is_ = data["income_statement"]
        assert set(is_.keys()) == {
            "revenue", "finance_cost", "profit_before_tax", "zakat_tax", "net_income",
        }
        assert is_["net_income"] == "168320000.0000"

        cf = data["cash_flow"]
        assert set(cf.keys()) == {
            "operating_cash_flow", "investing_cash_flow", "financing_cash_flow",
            "capex", "free_cash_flow",
        }
        assert cf["free_cash_flow"] == "-52446000.0000"
    finally:
        app.dependency_overrides.clear()


# ── 5. Forbidden fields absent ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_forbidden_fields_absent():
    """No EPS, EBITDA, operating_profit, gross_profit, ratios, valuation, or screener keys anywhere."""
    company = _make_company(symbol="2240")
    nf = _make_normalized_financial(symbol="2240")
    nf.conflicts = [_make_conflict()]

    db = AsyncMock()
    db.execute.side_effect = [_scalar_one_or_none_result(company), _scalars_first_result(nf)]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/2240/financials")
        body = resp.json()
        all_keys = {k.lower() for k in _collect_keys(body)}
        offending = all_keys & _FORBIDDEN_KEYS
        assert not offending, f"forbidden keys present: {offending}"
    finally:
        app.dependency_overrides.clear()


# ── 6. missing_fields appear in data_quality ──────────────────────────────────

@pytest.mark.asyncio
async def test_missing_fields_in_data_quality():
    company = _make_company(symbol="2050")
    nf = _make_normalized_financial(
        symbol="2050",
        missing_fields={"fields": ["short_term_debt", "total_debt"]},
        normalization_status="conflict",
    )
    nf.conflicts = [_make_conflict(field_name="long_term_debt")]

    db = AsyncMock()
    db.execute.side_effect = [_scalar_one_or_none_result(company), _scalars_first_result(nf)]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/2050/financials")
        dq = resp.json()["data"]["data_quality"]
        assert dq["missing_fields"] == ["short_term_debt", "total_debt"]
    finally:
        app.dependency_overrides.clear()


# ── 7. conflicts appear in data_quality ───────────────────────────────────────

@pytest.mark.asyncio
async def test_conflicts_in_data_quality():
    company = _make_company(symbol="2020")
    nf = _make_normalized_financial(symbol="2020", normalization_status="conflict")
    nf.conflicts = [_make_conflict(field_name="revenue", resolution_status="unresolved")]

    db = AsyncMock()
    db.execute.side_effect = [_scalar_one_or_none_result(company), _scalars_first_result(nf)]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/2020/financials")
        dq = resp.json()["data"]["data_quality"]
        assert dq["conflict_count"] == 1
        assert len(dq["conflicts"]) == 1
        assert dq["conflicts"][0]["field_name"] == "revenue"
        assert dq["conflicts"][0]["resolution_status"] == "unresolved"
        assert dq["conflicts"][0]["candidate_count"] == 2
    finally:
        app.dependency_overrides.clear()


# ── 8. No conflicts → empty list, zero count ──────────────────────────────────

@pytest.mark.asyncio
async def test_no_conflicts_when_normalized_cleanly():
    company = _make_company(symbol="4263")
    nf = _make_normalized_financial(symbol="4263", missing_fields=None, normalization_status="normalized")
    nf.conflicts = []

    db = AsyncMock()
    db.execute.side_effect = [_scalar_one_or_none_result(company), _scalars_first_result(nf)]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/4263/financials")
        dq = resp.json()["data"]["data_quality"]
        assert dq["conflict_count"] == 0
        assert dq["conflicts"] == []
        assert dq["missing_fields"] == []
    finally:
        app.dependency_overrides.clear()


# ── 9. source_map preserved and availability flag correct ────────────────────

@pytest.mark.asyncio
async def test_source_map_preserved_and_flagged_available():
    company = _make_company(symbol="1120")
    nf = _make_normalized_financial(symbol="1120")

    db = AsyncMock()
    db.execute.side_effect = [_scalar_one_or_none_result(company), _scalars_first_result(nf)]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/1120/financials")
        dq = resp.json()["data"]["data_quality"]
        assert dq["source_map_available"] is True
        assert dq["source_map"]["revenue"]["label_ar"] == "الإيرادات"
        assert dq["source_map"]["free_cash_flow"]["calculated"] is True
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_source_map_unavailable_flag_false_when_null():
    company = _make_company(symbol="2050")
    nf = _make_normalized_financial(symbol="2050", source_map=None)
    nf.source_map = None

    db = AsyncMock()
    db.execute.side_effect = [_scalar_one_or_none_result(company), _scalars_first_result(nf)]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/2050/financials")
        dq = resp.json()["data"]["data_quality"]
        assert dq["source_map_available"] is False
        assert dq["source_map"] is None
    finally:
        app.dependency_overrides.clear()


# ── 10. metadata section ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_metadata_section():
    company = _make_company(symbol="2240")
    nf = _make_normalized_financial(symbol="2240")

    db = AsyncMock()
    db.execute.side_effect = [_scalar_one_or_none_result(company), _scalars_first_result(nf)]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/2240/financials")
        meta = resp.json()["data"]["metadata"]
        assert meta["data_source"] == "saudi_exchange_xbrl"
        assert meta["manual_override"] is False
        assert "generated_at" in meta
    finally:
        app.dependency_overrides.clear()


# ── 11. Unknown symbol returns 404 ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unknown_symbol_returns_404():
    db = AsyncMock()
    db.execute.side_effect = [_scalar_one_or_none_result(None)]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/9999/financials")
        assert resp.status_code == 404
        assert "9999" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


# ── 12. No financials found → success=false, no crash ────────────────────────

@pytest.mark.asyncio
async def test_no_financials_returns_success_false():
    company = _make_company(symbol="3030")

    db = AsyncMock()
    db.execute.side_effect = [_scalar_one_or_none_result(company), _scalars_first_result(None)]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/3030/financials")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["data"] is None
    finally:
        app.dependency_overrides.clear()


# ── 13. Filters by fiscal_year ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_filters_by_fiscal_year():
    company = _make_company(symbol="2222")
    nf = _make_normalized_financial(symbol="2222", fiscal_year=2024)

    db = AsyncMock()
    db.execute.side_effect = [_scalar_one_or_none_result(company), _scalars_first_result(nf)]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/2222/financials?fiscal_year=2024")
        assert resp.json()["data"]["filing"]["fiscal_year"] == 2024
        nf_query = db.execute.call_args_list[1].args[0]
        compiled = str(nf_query.compile(compile_kwargs={"literal_binds": True}))
        assert "fiscal_year = 2024" in compiled
    finally:
        app.dependency_overrides.clear()


# ── 14. All 6 sample symbols produce well-formed, forbidden-field-free responses ─

@pytest.mark.asyncio
@pytest.mark.parametrize("symbol", ["2240", "2222", "2020", "4263", "2050", "1120"])
async def test_sample_symbols_produce_valid_structure(symbol):
    company = _make_company(symbol=symbol)
    nf = _make_normalized_financial(symbol=symbol)
    if symbol in ("2240", "2050"):
        nf.conflicts = [_make_conflict()]
    if symbol == "1120":
        nf.finance_cost = None
        nf.cash_and_equivalents = None
        nf.short_term_debt = None
        nf.long_term_debt = None
        nf.total_debt = None
        nf.missing_fields = {"fields": ["finance_cost", "cash_and_equivalents", "short_term_debt", "long_term_debt", "total_debt"]}

    db = AsyncMock()
    db.execute.side_effect = [_scalar_one_or_none_result(company), _scalars_first_result(nf)]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(f"/api/v1/companies/{symbol}/financials")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert set(data.keys()) == {
            "company", "filing", "balance_sheet", "income_statement",
            "cash_flow", "data_quality", "metadata",
        }
        assert data["company"]["symbol"] == symbol
        all_keys = {k.lower() for k in _collect_keys(body)}
        assert not (all_keys & _FORBIDDEN_KEYS)
    finally:
        app.dependency_overrides.clear()
