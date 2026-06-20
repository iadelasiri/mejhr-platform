"""
Read-only Prices API tests — GET /companies/{symbol}/prices/latest and
GET /market/indices/latest.

All tests mock the DB session via app.dependency_overrides[get_db], same
pattern as test_phase2g5.py. No real DB connection. No ratios, EPS, P/E,
ROIC, EBIT, or EBITDA fields are exposed or tested here.
"""
from __future__ import annotations

from datetime import date
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


def _make_company(symbol="2240"):
    company = MagicMock()
    company.symbol = symbol
    return company


def _make_market_data(symbol="2240", **overrides):
    md = MagicMock()
    md.symbol = symbol
    md.trade_date = overrides.get("trade_date", date(2026, 6, 18))
    md.close = overrides.get("close", Decimal("42.5000"))
    md.change_amount = overrides.get("change_amount", Decimal("0.5000"))
    md.change_pct = overrides.get("change_pct", Decimal("1.1900"))
    md.volume = overrides.get("volume", Decimal("1234567"))
    md.turnover = overrides.get("turnover", Decimal("52468847.5000"))
    md.trades = overrides.get("trades", Decimal("3210"))
    md.source = overrides.get("source", "saudi_exchange")
    md.source_url = overrides.get("source_url", "https://www.saudiexchange.sa/...")
    return md


def _make_index_price(index_code="TASI", **overrides):
    ip = MagicMock()
    ip.index_code = index_code
    ip.trade_date = overrides.get("trade_date", date(2026, 6, 18))
    ip.open = overrides.get("open", None)
    ip.high = overrides.get("high", None)
    ip.low = overrides.get("low", None)
    ip.close = overrides.get("close", Decimal("11500.0000"))
    ip.previous_close = overrides.get("previous_close", Decimal("11450.0000"))
    ip.change_amount = overrides.get("change_amount", Decimal("50.0000"))
    ip.change_pct = overrides.get("change_pct", Decimal("0.4400"))
    ip.volume = overrides.get("volume", Decimal("98765432"))
    ip.turnover = overrides.get("turnover", Decimal("5012345678.0000"))
    ip.trades_count = overrides.get("trades_count", Decimal("87654"))
    ip.trade_date_derivation = overrides.get("trade_date_derivation", "riyadh_fixed_utc+3_same_day")
    ip.source = overrides.get("source", "saudi_exchange")
    ip.source_url = overrides.get("source_url", "https://www.saudiexchange.sa/...")
    return ip


def _make_market_index(code="TASI", arabic_name="المؤشر العام", english_name="TASI"):
    mi = MagicMock()
    mi.code = code
    mi.arabic_name = arabic_name
    mi.english_name = english_name
    return mi


def _scalar_one_or_none_result(obj):
    r = MagicMock()
    r.scalar_one_or_none.return_value = obj
    return r


def _scalars_first_result(obj):
    r = MagicMock()
    r.scalars.return_value.first.return_value = obj
    return r


def _scalar_count_result(n):
    r = MagicMock()
    r.scalar.return_value = n
    return r


def _rows_result(pairs):
    """Mock db.execute(...).all() returning a list of (IndexPrice, MarketIndex|None) tuples."""
    r = MagicMock()
    r.all.return_value = pairs
    return r


def _scalars_all_result(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


# ── 1. Latest company price — found ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_latest_company_price_found():
    company = _make_company(symbol="2240")
    price = _make_market_data(
        symbol="2240",
        close=Decimal("42.5000"),
        change_amount=Decimal("0.5000"),
        change_pct=Decimal("1.1900"),
        volume=Decimal("1234567"),
        turnover=Decimal("52468847.5000"),
        trades=Decimal("3210"),
    )

    db = AsyncMock()
    db.execute.side_effect = [_scalar_one_or_none_result(company), _scalars_first_result(price)]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/2240/prices/latest")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["symbol"] == "2240"
        assert data["trade_date"] == "2026-06-18"
        assert data["close"] == "42.5000"
        assert data["change_amount"] == "0.5000"
        assert data["change_pct"] == "1.1900"
        assert data["volume"] == "1234567"
        assert data["turnover"] == "52468847.5000"
        assert data["trades_count"] == "3210"
        assert data["source"] == "saudi_exchange"
        # open/high/low/previous_close must not be exposed at all
        assert "open" not in data
        assert "high" not in data
        assert "low" not in data
        assert "previous_close" not in data
    finally:
        app.dependency_overrides.clear()


# ── 2. Latest company price — symbol exists, no price row ────────────────────

@pytest.mark.asyncio
async def test_latest_company_price_not_found_no_rows():
    company = _make_company(symbol="3030")

    db = AsyncMock()
    db.execute.side_effect = [_scalar_one_or_none_result(company), _scalars_first_result(None)]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/3030/prices/latest")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["data"] is None
    finally:
        app.dependency_overrides.clear()


# ── 3. Latest company price — unknown symbol → 404 ────────────────────────────

@pytest.mark.asyncio
async def test_latest_company_price_unknown_symbol_404():
    db = AsyncMock()
    db.execute.side_effect = [_scalar_one_or_none_result(None)]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/9999/prices/latest")
        assert resp.status_code == 404
        assert "9999" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


# ── 3b. Latest company prices (bulk) — one row per symbol ────────────────────

@pytest.mark.asyncio
async def test_bulk_latest_company_prices_one_row_per_symbol():
    p2240 = _make_market_data(symbol="2240", close=Decimal("34.3000"), change_amount=Decimal("-0.4000"))
    p2222 = _make_market_data(symbol="2222", close=Decimal("26.5200"), change_amount=Decimal("-0.0800"))

    db = AsyncMock()
    db.execute.side_effect = [
        _scalar_count_result(2),
        _scalars_all_result([p2240, p2222]),
    ]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/prices/latest")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["total"] == 2
        symbols = {row["symbol"] for row in body["data"]}
        assert symbols == {"2240", "2222"}
        row_2240 = next(r for r in body["data"] if r["symbol"] == "2240")
        assert row_2240["close"] == "34.3000"
        assert row_2240["change_amount"] == "-0.4000"
    finally:
        app.dependency_overrides.clear()


# ── 3c. Bulk company prices — omits OHLC ──────────────────────────────────────

@pytest.mark.asyncio
async def test_bulk_latest_company_prices_omits_ohlc():
    price = _make_market_data(symbol="2240")

    db = AsyncMock()
    db.execute.side_effect = [_scalar_count_result(1), _scalars_all_result([price])]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/prices/latest")
        row = resp.json()["data"][0]
        for field in ("open", "high", "low", "previous_close"):
            assert field not in row
    finally:
        app.dependency_overrides.clear()


# ── 3d. Bulk company prices — empty market_data → empty list ─────────────────

@pytest.mark.asyncio
async def test_bulk_latest_company_prices_empty():
    db = AsyncMock()
    db.execute.side_effect = [_scalar_count_result(0), _scalars_all_result([])]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/prices/latest")
        body = resp.json()
        assert body["data"] == []
        assert body["total"] == 0
        assert body["meta"]["pipeline_status"] == "not_configured"
    finally:
        app.dependency_overrides.clear()


# ── 3e. Bulk company prices — no duplicate symbols + structural dedup check ──

@pytest.mark.asyncio
async def test_bulk_latest_company_prices_no_duplicate_symbols():
    p1 = _make_market_data(symbol="2240")
    p2 = _make_market_data(symbol="2222")
    p3 = _make_market_data(symbol="1120")

    db = AsyncMock()
    db.execute.side_effect = [_scalar_count_result(3), _scalars_all_result([p1, p2, p3])]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/prices/latest")
        symbols = [row["symbol"] for row in resp.json()["data"]]
        assert len(symbols) == len(set(symbols))
    finally:
        app.dependency_overrides.clear()

    # Structural guarantee: the query groups by symbol and takes MAX(trade_date)
    # per symbol before joining back to market_data — the SQL itself cannot
    # produce more than one row per symbol, regardless of how many price rows
    # exist for that symbol (mirrors the index-prices endpoint's same pattern).
    from app.api.v1.companies import get_latest_company_prices
    import inspect
    source = inspect.getsource(get_latest_company_prices)
    assert "func.max(MarketData.trade_date)" in source
    assert "group_by(MarketData.symbol)" in source


# ── 3f. Bulk company prices — Tadawul-only filter present ────────────────────

@pytest.mark.asyncio
async def test_bulk_latest_company_prices_tadawul_only_filter():
    """
    market_data also contains Nomu and orphaned symbols (confirmed by direct
    DB query before implementing this endpoint: 399 total rows = 270
    Tadawul + 125 Nomu + 4 orphaned). With a fully mocked DB session this
    test can only verify the query construction actually filters by
    Company.market == "tadawul" — the real exclusion is exercised by the
    live manual verification in the report, not by this unit test.
    """
    db = AsyncMock()
    db.execute.side_effect = [_scalar_count_result(0), _scalars_all_result([])]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/prices/latest")
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.clear()

    from app.api.v1.companies import get_latest_company_prices
    import inspect
    source = inspect.getsource(get_latest_company_prices)
    assert 'Company.market == "tadawul"' in source
    assert "join(Company" in source


# ── 4. Latest index prices — latest-per-code, names joined ───────────────────

@pytest.mark.asyncio
async def test_latest_index_prices_per_code_with_names():
    tasi_price = _make_index_price(
        index_code="TASI", high=Decimal("11600.0000"), low=Decimal("11400.0000"),
        close=Decimal("11500.0000"),
    )
    tasi_idx = _make_market_index(code="TASI", arabic_name="المؤشر العام", english_name="TASI")

    db = AsyncMock()
    db.execute.side_effect = [
        _scalar_count_result(1),
        _rows_result([(tasi_price, tasi_idx)]),
    ]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/market/indices/latest")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        rows = body["data"]
        assert len(rows) == 1
        assert rows[0]["index_code"] == "TASI"
        assert rows[0]["index_name_ar"] == "المؤشر العام"
        assert rows[0]["index_name_en"] == "TASI"
        assert rows[0]["high"] == "11600.0000"
        assert rows[0]["low"] == "11400.0000"
    finally:
        app.dependency_overrides.clear()


# ── 5. Latest index prices — no market_indices catalogue match ───────────────

@pytest.mark.asyncio
async def test_latest_index_prices_no_catalogue_match_names_null():
    price = _make_index_price(index_code="SASEAGRI")

    db = AsyncMock()
    db.execute.side_effect = [
        _scalar_count_result(1),
        _rows_result([(price, None)]),
    ]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/market/indices/latest")
        row = resp.json()["data"][0]
        assert row["index_code"] == "SASEAGRI"
        assert row["index_name_ar"] is None
        assert row["index_name_en"] is None
    finally:
        app.dependency_overrides.clear()


# ── 6. NULL high/low remain NULL for sector indices ───────────────────────────

@pytest.mark.asyncio
async def test_sector_index_null_high_low_remain_null():
    sector_price = _make_index_price(index_code="SASEAGRI", high=None, low=None, open=None)

    db = AsyncMock()
    db.execute.side_effect = [
        _scalar_count_result(1),
        _rows_result([(sector_price, None)]),
    ]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/market/indices/latest")
        row = resp.json()["data"][0]
        assert row["high"] is None
        assert row["low"] is None
        assert row["open"] is None
        # close/previous_close still populated — not blanked out wholesale
        assert row["close"] is not None
    finally:
        app.dependency_overrides.clear()


# ── 7. No duplicate index_code in response ────────────────────────────────────

@pytest.mark.asyncio
async def test_no_duplicate_index_code_in_response():
    tasi = _make_index_price(index_code="TASI")
    mt30 = _make_index_price(index_code="MT30")
    sector = _make_index_price(index_code="SASEAGRI")

    db = AsyncMock()
    db.execute.side_effect = [
        _scalar_count_result(3),
        _rows_result([(tasi, None), (mt30, None), (sector, None)]),
    ]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/market/indices/latest")
        codes = [row["index_code"] for row in resp.json()["data"]]
        assert len(codes) == len(set(codes))
    finally:
        app.dependency_overrides.clear()

    # Structural guarantee: the query groups by index_code and takes the max
    # trade_date per code before joining back to index_prices, so the SQL
    # itself cannot produce more than one row per index_code regardless of
    # how many price rows exist for that code.
    from app.api.v1.market import get_latest_index_prices
    import inspect
    source = inspect.getsource(get_latest_index_prices)
    assert "group_by(IndexPrice.index_code)" in source


# ── 8. Empty index_prices table → empty list, not_configured meta ────────────

@pytest.mark.asyncio
async def test_latest_index_prices_empty():
    db = AsyncMock()
    db.execute.side_effect = [
        _scalar_count_result(0),
        _rows_result([]),
    ]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/market/indices/latest")
        body = resp.json()
        assert body["data"] == []
        assert body["total"] == 0
        assert body["meta"]["pipeline_status"] == "not_configured"
    finally:
        app.dependency_overrides.clear()


# ── 9. Forbidden fields absent from both endpoints ────────────────────────────

_FORBIDDEN_KEYS = frozenset({
    "eps", "ebitda", "ebit", "operating_profit", "gross_profit",
    "ratio", "ratios", "pe", "pb", "ps", "roe", "roic", "roa",
    "ev_ic", "ev_ebit", "market_cap", "enterprise_value", "valuation", "screener",
})


def _collect_keys(obj, keys=None):
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


@pytest.mark.asyncio
async def test_forbidden_fields_absent_company_price():
    company = _make_company(symbol="2222")
    price = _make_market_data(symbol="2222")

    db = AsyncMock()
    db.execute.side_effect = [_scalar_one_or_none_result(company), _scalars_first_result(price)]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/2222/prices/latest")
        all_keys = {k.lower() for k in _collect_keys(resp.json())}
        assert not (all_keys & _FORBIDDEN_KEYS)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_forbidden_fields_absent_bulk_company_prices():
    price = _make_market_data(symbol="2240")

    db = AsyncMock()
    db.execute.side_effect = [_scalar_count_result(1), _scalars_all_result([price])]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/companies/prices/latest")
        all_keys = {k.lower() for k in _collect_keys(resp.json())}
        assert not (all_keys & _FORBIDDEN_KEYS)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_forbidden_fields_absent_index_prices():
    price = _make_index_price(index_code="TASI")

    db = AsyncMock()
    db.execute.side_effect = [_scalar_count_result(1), _rows_result([(price, None)])]

    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/market/indices/latest")
        all_keys = {k.lower() for k in _collect_keys(resp.json())}
        assert not (all_keys & _FORBIDDEN_KEYS)
    finally:
        app.dependency_overrides.clear()
