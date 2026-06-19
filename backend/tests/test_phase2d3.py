"""
Phase 2D.3 tests — Index prices pipeline (TASI/MT30 + sector/market indices).

All tests use saved fixture payloads captured during Phase 2D.2 discovery
(see PHASE_2D2_DISCOVERY.md). No live network calls. Covers: TASI/MT30
parsing, indicesJson parsing, TASI/MT30 dedup, noOfTrades type coercion
(the source's inconsistent JSON type), trade_date derivation (weekday +
weekend rollback, no timezone assumption on currentTime), and idempotent
upsert behavior.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.pipeline.exchange import index_prices as ip_module
from app.pipeline.exchange.index_prices import (
    IndexPriceRecord,
    TradeDateDerivation,
    _coerce_trades_count,
    _derive_trade_date,
    _parse_indices_json,
    _parse_tasi_mt30,
    _to_decimal,
    fetch_index_prices,
    upsert_index_prices,
)


# ── Fixtures (captured during Phase 2D.2 discovery) ──────────────────────────

_TASI_MT30_FIXTURE = {
    "tasiValue": "11,121.13",
    "tasiBean": {
        "symbol": "TASI",
        "tasiTodaysSummaryBean": {
            "openPrice": 11117.12,
            "indexPrice": 11121.13,
            "netChange": 6.23,
            "percentChange": 0.06,
            "previouseIndexPrice": 11114.9,
            "volumeTraded": 275069403,
            "highPrice": 11136.26,
            "lowPrice": 11099.8,
            "turnOver": 6541910657.19,
            "noOfTrades": 412822,
            "noOfCompaniesTraded": 268,
            "status": 2,
        },
    },
    "mt30Bean": {
        "symbol": "MT30",
        "tasiTodaysSummaryBean": {
            "openPrice": 1485.74,
            "indexPrice": 1488.72,
            "netChange": 2.69,
            "percentChange": 0.18,
            "previouseIndexPrice": 1488.72,
            "volumeTraded": 0,
            "highPrice": 1490.27,
            "lowPrice": 1484.56,
            "turnOver": 0.0,
            "noOfTrades": 30,
            "noOfCompaniesTraded": 0,
            "status": 2,
        },
    },
}

_INDICES_JSON_HTML_FIXTURE = (
    'var indicesJson =\'[{"symbol":"TCPI","name":"Commercial \\u0026 Professional Svc",'
    '"price":4011.03,"volume":5223906,"turnover":60598540.31,"netChange":-24.22,'
    '"netPercentChange":-0.6,"priceIndicatorCssClass":"priceDown","open":4030.54,'
    '"noOfTrades":"7943"},'
    '{"symbol":"TASI","name":"Tadawul All Share Index (TASI)","price":11121.13,'
    '"volume":275069403,"turnover":6541910657.19,"netChange":6.23,'
    '"netPercentChange":0.06,"priceIndicatorCssClass":"priceUp","open":11117.12,'
    '"noOfTrades":"412822"},'
    '{"symbol":"TTNI","name":"Transportation","price":4626.3,"volume":3506036,'
    '"turnover":172365409.97,"netChange":46.75,"netPercentChange":1.02,'
    '"priceIndicatorCssClass":"priceUp","open":4594.32,"noOfTrades":"18449"}]\';'
)


def _trade_date_info() -> TradeDateDerivation:
    return TradeDateDerivation(trade_date=date(2026, 6, 18), method="riyadh_fixed_utc+3_same_day")


def _index_price_record(**overrides) -> IndexPriceRecord:
    defaults = dict(
        index_code="TASI", trade_date=date(2026, 6, 18),
        trade_date_derivation="riyadh_fixed_utc+3_same_day",
        open=Decimal("11117.12"), high=Decimal("11136.26"), low=Decimal("11099.8"),
        close=Decimal("11121.13"), previous_close=Decimal("11114.9"),
        change_amount=Decimal("6.23"), change_pct=Decimal("0.06"),
        volume=Decimal("275069403"), turnover=Decimal("6541910657.19"),
        trades_count=412822, source="saudi_exchange_theme_tasi_servlet",
        source_url="https://example.com",
    )
    defaults.update(overrides)
    return IndexPriceRecord(**defaults)


# ── _to_decimal ────────────────────────────────────────────────────────────────

def test_to_decimal_handles_float_int_string_none():
    assert _to_decimal(11121.13) == Decimal("11121.13")
    assert _to_decimal(412822) == Decimal("412822")
    assert _to_decimal("4011.03") == Decimal("4011.03")
    assert _to_decimal(None) is None
    assert _to_decimal("not-a-number") is None


# ── _coerce_trades_count (defensive, inconsistent source type) ───────────────

def test_coerce_trades_count_int_passthrough():
    """ThemeTASIUtilityServlet returns noOfTrades as a real int."""
    assert _coerce_trades_count(412822) == 412822


def test_coerce_trades_count_numeric_string():
    """indicesJson returns noOfTrades as a quoted numeric string."""
    assert _coerce_trades_count("7943") == 7943


def test_coerce_trades_count_string_with_comma():
    assert _coerce_trades_count("7,943") == 7943


def test_coerce_trades_count_unparseable_returns_none():
    assert _coerce_trades_count("N/A") is None
    assert _coerce_trades_count("") is None


def test_coerce_trades_count_none_and_bool_return_none():
    assert _coerce_trades_count(None) is None
    assert _coerce_trades_count(True) is None


# ── trade_date derivation ──────────────────────────────────────────────────────

def test_derive_trade_date_weekday_same_day():
    """Wednesday 2026-06-17: fetched at 14:00 UTC -> 17:00 Riyadh, same date."""
    fetched_at = datetime(2026, 6, 17, 14, 0, tzinfo=timezone.utc)
    result = _derive_trade_date(fetched_at)
    assert result.trade_date == date(2026, 6, 17)
    assert result.method == "riyadh_fixed_utc+3_same_day"


def test_derive_trade_date_rolls_back_from_friday():
    """2026-06-19 is a Friday in Riyadh -> rolls back to Thursday 2026-06-18."""
    fetched_at = datetime(2026, 6, 19, 10, 0, tzinfo=timezone.utc)
    result = _derive_trade_date(fetched_at)
    assert result.trade_date == date(2026, 6, 18)
    assert "friday" in result.method.lower()


def test_derive_trade_date_rolls_back_from_saturday():
    """2026-06-20 is a Saturday in Riyadh -> rolls back to Thursday 2026-06-18."""
    fetched_at = datetime(2026, 6, 20, 10, 0, tzinfo=timezone.utc)
    result = _derive_trade_date(fetched_at)
    assert result.trade_date == date(2026, 6, 18)
    assert "saturday" in result.method.lower()


def test_derive_trade_date_utc_to_riyadh_day_rollover():
    """Late UTC evening rolls into the next Riyadh calendar day — confirms the
    fixed offset is actually applied, not a passthrough of the UTC date."""
    fetched_at = datetime(2026, 6, 17, 22, 0, tzinfo=timezone.utc)
    result = _derive_trade_date(fetched_at)
    assert result.trade_date == date(2026, 6, 18)


def test_derive_trade_date_requires_timezone_aware_input():
    with pytest.raises(ValueError):
        _derive_trade_date(datetime(2026, 6, 17, 14, 0))


# ── _parse_tasi_mt30 ────────────────────────────────────────────────────────────

def test_parse_tasi_mt30_full_ohlcv():
    info = _trade_date_info()
    records = _parse_tasi_mt30(_TASI_MT30_FIXTURE, info)
    assert len(records) == 2

    tasi = next(r for r in records if r.index_code == "TASI")
    assert tasi.open == Decimal("11117.12")
    assert tasi.high == Decimal("11136.26")
    assert tasi.low == Decimal("11099.8")
    assert tasi.close == Decimal("11121.13")
    assert tasi.previous_close == Decimal("11114.9")
    assert tasi.change_amount == Decimal("6.23")
    assert tasi.change_pct == Decimal("0.06")
    assert tasi.volume == Decimal("275069403")
    assert tasi.turnover == Decimal("6541910657.19")
    assert tasi.trades_count == 412822
    assert tasi.trade_date == date(2026, 6, 18)
    assert tasi.trade_date_derivation == "riyadh_fixed_utc+3_same_day"
    assert tasi.source == ip_module._SOURCE_TASI_MT30


def test_parse_tasi_mt30_mt30_present_with_high_low():
    info = _trade_date_info()
    records = _parse_tasi_mt30(_TASI_MT30_FIXTURE, info)
    mt30 = next(r for r in records if r.index_code == "MT30")
    assert mt30.close == Decimal("1488.72")
    assert mt30.high == Decimal("1490.27")
    assert mt30.low == Decimal("1484.56")


def test_parse_tasi_mt30_missing_bean_handled_gracefully():
    info = _trade_date_info()
    records = _parse_tasi_mt30({"tasiBean": _TASI_MT30_FIXTURE["tasiBean"]}, info)
    assert len(records) == 1
    assert records[0].index_code == "TASI"


def test_parse_tasi_mt30_empty_dict_returns_empty_list():
    info = _trade_date_info()
    assert _parse_tasi_mt30({}, info) == []


# ── _parse_indices_json ──────────────────────────────────────────────────────

def test_parse_indices_json_extracts_sector_index():
    info = _trade_date_info()
    records = _parse_indices_json(_INDICES_JSON_HTML_FIXTURE, info)
    tcpi = next(r for r in records if r.index_code == "TCPI")
    assert tcpi.open == Decimal("4030.54")
    assert tcpi.close == Decimal("4011.03")
    assert tcpi.change_amount == Decimal("-24.22")
    assert tcpi.change_pct == Decimal("-0.6")
    assert tcpi.volume == Decimal("5223906")
    assert tcpi.turnover == Decimal("60598540.31")
    assert tcpi.trades_count == 7943
    assert tcpi.source == ip_module._SOURCE_INDICES_JSON


def test_parse_indices_json_high_low_are_null():
    """High/low are never available from this source — must be NULL, never fabricated."""
    info = _trade_date_info()
    records = _parse_indices_json(_INDICES_JSON_HTML_FIXTURE, info)
    assert records, "fixture must yield at least one record"
    for r in records:
        assert r.high is None
        assert r.low is None


def test_parse_indices_json_derives_previous_close_from_same_source():
    """previous_close = close - change_amount, basic arithmetic from the same object."""
    info = _trade_date_info()
    records = _parse_indices_json(_INDICES_JSON_HTML_FIXTURE, info)
    tcpi = next(r for r in records if r.index_code == "TCPI")
    assert tcpi.previous_close == tcpi.close - tcpi.change_amount


def test_parse_indices_json_skips_tasi_mt30_duplicate():
    """
    TASI appears in the indicesJson blob too, but it's already covered with
    richer data via ThemeTASIUtilityServlet — must not produce a second,
    weaker TASI record here.
    """
    info = _trade_date_info()
    records = _parse_indices_json(_INDICES_JSON_HTML_FIXTURE, info)
    codes = {r.index_code for r in records}
    assert "TASI" not in codes
    assert "TCPI" in codes
    assert "TTNI" in codes
    assert len(records) == 2


def test_parse_indices_json_noOfTrades_string_coerced_to_int():
    info = _trade_date_info()
    records = _parse_indices_json(_INDICES_JSON_HTML_FIXTURE, info)
    tcpi = next(r for r in records if r.index_code == "TCPI")
    assert isinstance(tcpi.trades_count, int)
    assert tcpi.trades_count == 7943


def test_parse_indices_json_decodes_unicode_escape_in_name():
    """Confirms json.loads-based parsing (not positional regex) handles \\u0026 etc."""
    info = _trade_date_info()
    records = _parse_indices_json(_INDICES_JSON_HTML_FIXTURE, info)
    assert any(r.index_code == "TCPI" for r in records)


def test_parse_indices_json_no_match_returns_empty_list():
    info = _trade_date_info()
    assert _parse_indices_json("no json here", info) == []


# ── fetch_index_prices (integration, mocked _http_get) ────────────────────────

def test_fetch_index_prices_combines_both_sources():
    tasi_resp = MagicMock()
    tasi_resp.status_code = 200
    tasi_resp.json.return_value = _TASI_MT30_FIXTURE
    tasi_resp.text = ""

    indices_resp = MagicMock()
    indices_resp.status_code = 200
    indices_resp.text = _INDICES_JSON_HTML_FIXTURE

    with patch.object(ip_module, "_http_get", side_effect=[tasi_resp, indices_resp]):
        result = fetch_index_prices()

    assert result.reachable_tasi_mt30 is True
    assert result.reachable_indices_json is True
    assert result.blocked_tasi_mt30 is False
    assert result.blocked_indices_json is False
    assert result.error is None

    codes = {r.index_code for r in result.records}
    assert codes == {"TASI", "MT30", "TCPI", "TTNI"}
    assert len(result.records) == 4


def test_fetch_index_prices_records_trade_date_derivation_method():
    tasi_resp = MagicMock()
    tasi_resp.status_code = 200
    tasi_resp.json.return_value = _TASI_MT30_FIXTURE
    tasi_resp.text = ""
    indices_resp = MagicMock()
    indices_resp.status_code = 200
    indices_resp.text = _INDICES_JSON_HTML_FIXTURE

    with patch.object(ip_module, "_http_get", side_effect=[tasi_resp, indices_resp]):
        result = fetch_index_prices()

    derivations = {r.trade_date_derivation for r in result.records}
    assert len(derivations) == 1, "all records in one fetch run share the same derivation"


def test_fetch_index_prices_handles_blocked_tasi_source():
    blocked_resp = MagicMock()
    blocked_resp.status_code = 403
    blocked_resp.text = "Access Denied"

    ok_resp = MagicMock()
    ok_resp.status_code = 200
    ok_resp.text = _INDICES_JSON_HTML_FIXTURE

    with patch.object(ip_module, "_http_get", side_effect=[blocked_resp, ok_resp]):
        result = fetch_index_prices()

    assert result.blocked_tasi_mt30 is True
    assert result.reachable_tasi_mt30 is False
    assert result.reachable_indices_json is True
    assert result.error is not None

    codes = {r.index_code for r in result.records}
    assert "TASI" not in codes  # source 1 blocked; TASI deduped out of source 2 regardless
    assert "TCPI" in codes


def test_fetch_index_prices_handles_both_sources_unreachable():
    error_resp = MagicMock()
    error_resp.status_code = 500
    error_resp.text = ""

    with patch.object(ip_module, "_http_get", side_effect=[error_resp, error_resp]):
        result = fetch_index_prices()

    assert result.records == []
    assert result.reachable_tasi_mt30 is False
    assert result.reachable_indices_json is False
    assert result.error is not None


# ── upsert_index_prices (idempotency) ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_upsert_inserts_new_record():
    record = _index_price_record()

    db = AsyncMock()
    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None
    db.execute.return_value = no_existing

    stats = await upsert_index_prices([record], db)

    assert stats == {"inserted": 1, "updated": 0, "total": 1}
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_upsert_updates_existing_record_not_duplicate():
    """Re-running with the same (index_code, trade_date) must update, not insert a duplicate."""
    record = _index_price_record()

    existing_id = uuid.uuid4()
    db = AsyncMock()
    has_existing = MagicMock()
    has_existing.scalar_one_or_none.return_value = existing_id
    db.execute.return_value = has_existing

    stats = await upsert_index_prices([record], db)

    assert stats == {"inserted": 0, "updated": 1, "total": 1}
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_upsert_mixed_batch_inserts_and_updates():
    new_record = _index_price_record(index_code="MT30")
    existing_record = _index_price_record(index_code="TASI")

    db = AsyncMock()
    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None
    has_existing = MagicMock()
    has_existing.scalar_one_or_none.return_value = uuid.uuid4()
    # Each record costs 2 execute() calls: the SELECT check, then INSERT/UPDATE.
    db.execute.side_effect = [no_existing, MagicMock(), has_existing, MagicMock()]

    stats = await upsert_index_prices([new_record, existing_record], db)

    assert stats == {"inserted": 1, "updated": 1, "total": 2}


@pytest.mark.asyncio
async def test_upsert_empty_list_is_a_noop():
    db = AsyncMock()
    stats = await upsert_index_prices([], db)
    assert stats == {"inserted": 0, "updated": 0, "total": 0}
