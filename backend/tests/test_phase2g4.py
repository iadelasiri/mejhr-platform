"""
Phase 2G.4 tests — GET /api/v1/companies/{symbol}/financials.

All tests mock the DB session via app.dependency_overrides[get_db]. No real
DB connection. Covers: happy path, fiscal_year filter, missing company,
missing financials, source_map passthrough, conflicts/missing_fields
passthrough, and absence of any ratio fields in the response.
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


# ── 1. Returns financials for 2240 ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_returns_financials_for_2240():
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
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["company"]["symbol"] == "2240"
        assert data["fiscal_year"] == 2025
        assert data["fiscal_period"] == "Annual"
        assert data["reporting_scale"] == 1000
        assert data["financials"]["revenue"] == "6200549000.0000"
        assert data["financials"]["net_income"] == "168320000.0000"
        assert data["data_status"] == "conflict"
    finally:
        app.dependency_overrides.clear()


# ── 2. Filters by fiscal_year ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_filters_by_fiscal_year():
    company = _make_company(symbol="2222")
    nf = _make_normalized_financial(symbol="2222", fiscal_year=2024)

    db = AsyncMock()
    db.execute.side_effect = [
        _scalar_one_or_none_result(company),
        _scalars_first_result(nf),
    ]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/2222/financials?fiscal_year=2024")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["fiscal_year"] == 2024

        # Confirm the fiscal_year filter was actually applied to the query (2nd execute call)
        nf_query = db.execute.call_args_list[1].args[0]
        compiled = str(nf_query.compile(compile_kwargs={"literal_binds": True}))
        assert "fiscal_year = 2024" in compiled
    finally:
        app.dependency_overrides.clear()


# ── 3. Handles missing company ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handles_missing_company():
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


# ── 4. Handles no financials (company exists, no normalized record) ──────────

@pytest.mark.asyncio
async def test_handles_no_financials():
    company = _make_company(symbol="3030")

    db = AsyncMock()
    db.execute.side_effect = [
        _scalar_one_or_none_result(company),
        _scalars_first_result(None),
    ]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/3030/financials")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["data"] is None
        assert "3030" in body["meta"]["message"]
    finally:
        app.dependency_overrides.clear()


# ── 5. Includes source_map ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_includes_source_map():
    company = _make_company(symbol="4263")
    nf = _make_normalized_financial(symbol="4263")

    db = AsyncMock()
    db.execute.side_effect = [
        _scalar_one_or_none_result(company),
        _scalars_first_result(nf),
    ]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/4263/financials")
        data = resp.json()["data"]
        assert "source_map" in data
        assert data["source_map"]["revenue"]["label_ar"] == "الإيرادات"
        assert data["source_map"]["free_cash_flow"]["calculated"] is True
        assert data["source_map"]["free_cash_flow"]["formula"] == "operating_cash_flow + capex"
    finally:
        app.dependency_overrides.clear()


# ── 6. Includes conflicts and missing_fields ──────────────────────────────────

@pytest.mark.asyncio
async def test_includes_conflicts_and_missing_fields():
    company = _make_company(symbol="2050")
    nf = _make_normalized_financial(
        symbol="2050",
        missing_fields={"fields": ["short_term_debt", "total_debt"]},
        normalization_status="conflict",
    )
    nf.conflicts = [_make_conflict(field_name="long_term_debt")]

    db = AsyncMock()
    db.execute.side_effect = [
        _scalar_one_or_none_result(company),
        _scalars_first_result(nf),
    ]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/2050/financials")
        data = resp.json()["data"]
        assert data["missing_fields"] == ["short_term_debt", "total_debt"]
        assert len(data["conflicts"]) == 1
        assert data["conflicts"][0]["field_name"] == "long_term_debt"
        assert data["conflicts"][0]["resolution_status"] == "unresolved"
        assert data["conflicts"][0]["candidate_count"] == 2
    finally:
        app.dependency_overrides.clear()


# ── 7. Does not calculate ratios ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_does_not_calculate_ratios():
    """Response must not contain any ratio, EPS, or valuation fields."""
    company = _make_company(symbol="2240")
    nf = _make_normalized_financial(symbol="2240")

    db = AsyncMock()
    db.execute.side_effect = [
        _scalar_one_or_none_result(company),
        _scalars_first_result(nf),
    ]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/2240/financials")
        data = resp.json()["data"]
        forbidden_keys = {
            "pe", "pb", "ps", "roe", "roic", "roa", "eps",
            "ev_ic", "ev_ebit", "debt_equity", "fcf_yield",
            "gross_margin", "operating_margin", "net_margin",
            "market_cap", "enterprise_value", "fair_value_estimate",
        }
        financials_keys = set(data["financials"].keys())
        assert financials_keys.isdisjoint(forbidden_keys)
        assert set(data.keys()).isdisjoint(forbidden_keys)
    finally:
        app.dependency_overrides.clear()
