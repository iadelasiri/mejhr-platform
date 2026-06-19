"""
Phase 2D.4 tests — Partial company prices pipeline (TickerServlet).
Phase 2D.6 extended the upsert section below — bulk INSERT ... ON CONFLICT
replacing the original per-record SELECT-then-INSERT/UPDATE loop.

All tests use saved fixture payloads modeled on the records captured during
Phase 2D.2 discovery (see PHASE_2D2_DISCOVERY.md). No live network calls.
Covers: field mapping (close/change/change_pct/volume/turnover/trades),
NULL handling for open/high/low/previous_close (never fabricated),
defensive parsing of malformed/duplicate/non-numeric entries, trade_date
derivation reuse, schema-fit source composition, and bulk idempotent upsert
(insert/update/mixed/empty/chunking/NULL persistence/duplicate-key handling).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.pipeline.exchange import company_prices as cp_module
from app.pipeline.exchange.company_prices import (
    CompanyPriceRecord,
    _compose_source_value,
    _parse_ticker_stock_data,
    fetch_company_prices,
    upsert_company_prices,
)
from app.pipeline.exchange.index_prices import TradeDateDerivation


def _trade_date_info() -> TradeDateDerivation:
    return TradeDateDerivation(trade_date=date(2026, 6, 18), method="riyadh_fixed_utc+3_same_day")


def _company_price_record(**overrides) -> CompanyPriceRecord:
    defaults = dict(
        symbol="2222", trade_date=date(2026, 6, 18),
        trade_date_derivation="riyadh_fixed_utc+3_same_day",
        open=None, high=None, low=None, previous_close=None,
        close=Decimal("26.52"), change_amount=Decimal("-0.08"),
        change_pct=Decimal("-0.3"), volume=Decimal("22849767"),
        turnover=Decimal("604947114.32"), trades=15755,
        source="saudi_exchange_ticker_servlet",
        source_url="https://example.com",
    )
    defaults.update(overrides)
    return CompanyPriceRecord(**defaults)


# ── Fixtures (modeled on records captured during Phase 2D.2 discovery) ───────

_ARAMCO_ENTRY = {
    "pk_rf_company": "2222",
    "companyShortNameEn": "SAUDI ARAMCO",
    "companyShortNameAr": "أرامكو السعودية",
    "companyLongNameEn": "Saudi Arabian Oil Co.",
    "companyLongNameAr": "شركة الزيت العربية السعودية",
    "highPrice": None,
    "lowPrice": None,
    "noOfTrades": 15755,
    "previousClosePrice": None,
    "todaysOpen": None,
    "transactionDate": None,
    "turnOver": 604947114.32,
    "volumeTraded": 22849767,
    "aveTradeSize": 1450.32,
    "change": -0.08,
    "changePercent": -0.3,
    "lastTradePrice": 26.52,
    "transactionDateStr": None,
}

_FUND_ENTRY_STRING_NOOFTRADES = {
    "pk_rf_company": "4700",
    "companyShortNameEn": "ALKHABEER INCOME",
    "highPrice": None,
    "lowPrice": None,
    "noOfTrades": "117",
    "previousClosePrice": None,
    "todaysOpen": None,
    "transactionDate": None,
    "turnOver": 321005.95,
    "volumeTraded": 66886,
    "change": 0,
    "changePercent": 0,
    "lastTradePrice": 4.8,
}

_COMMA_FORMATTED_ENTRY = {
    "pk_rf_company": "1010",
    "highPrice": None,
    "lowPrice": None,
    "noOfTrades": "7,943",
    "previousClosePrice": None,
    "todaysOpen": None,
    "turnOver": "604,947,114.32",
    "volumeTraded": "22,849,767",
    "change": "-0.08",
    "changePercent": "-0.3",
    "lastTradePrice": "26.52",
}

_EMPTY_VALUE_ENTRY = {
    "pk_rf_company": "2030",
    "highPrice": None,
    "lowPrice": None,
    "noOfTrades": "",
    "previousClosePrice": None,
    "todaysOpen": None,
    "turnOver": "",
    "volumeTraded": None,
    "change": None,
    "changePercent": None,
    "lastTradePrice": "",
}

_MALFORMED_NOOFTRADES_ENTRY = {
    "pk_rf_company": "2040",
    "highPrice": None,
    "lowPrice": None,
    "noOfTrades": "N/A",
    "turnOver": "not-a-number",
    "volumeTraded": 1000,
    "change": 0.5,
    "changePercent": 0.1,
    "lastTradePrice": 10.0,
}

_FULL_FIXTURE_RESPONSE = {
    "message": None,
    "stockData": [
        _ARAMCO_ENTRY,
        _FUND_ENTRY_STRING_NOOFTRADES,
        "not-a-dict-entry",          # malformed: non-dict
        {"companyShortNameEn": "No symbol"},  # malformed: missing pk_rf_company
        dict(_ARAMCO_ENTRY, lastTradePrice=999.0),  # malformed: duplicate symbol
        _COMMA_FORMATTED_ENTRY,
        _EMPTY_VALUE_ENTRY,
        _MALFORMED_NOOFTRADES_ENTRY,
    ],
    "tickerStockData": [],
}


# ── _parse_ticker_stock_data: field mapping ───────────────────────────────────

def test_parses_close_change_volume_turnover_trades():
    info = _trade_date_info()
    records, skipped = _parse_ticker_stock_data(_FULL_FIXTURE_RESPONSE, info)
    aramco = next(r for r in records if r.symbol == "2222")
    assert aramco.close == Decimal("26.52")
    assert aramco.change_amount == Decimal("-0.08")
    assert aramco.change_pct == Decimal("-0.3")
    assert aramco.volume == Decimal("22849767")
    assert aramco.turnover == Decimal("604947114.32")
    assert aramco.trades == 15755
    assert aramco.trade_date == date(2026, 6, 18)
    assert aramco.trade_date_derivation == "riyadh_fixed_utc+3_same_day"
    assert aramco.source == cp_module._SOURCE


def test_open_high_low_previous_close_always_none():
    """Never available from this source — must be NULL, never fabricated."""
    info = _trade_date_info()
    records, _ = _parse_ticker_stock_data(_FULL_FIXTURE_RESPONSE, info)
    assert records, "fixture must yield at least one record"
    for r in records:
        assert r.open is None
        assert r.high is None
        assert r.low is None
        assert r.previous_close is None


# ── Defensive parsing: malformed / duplicate / inconsistent-type entries ─────

def test_skips_non_dict_entry():
    info = _trade_date_info()
    records, skipped = _parse_ticker_stock_data(_FULL_FIXTURE_RESPONSE, info)
    symbols = {r.symbol for r in records}
    assert "not-a-dict-entry" not in symbols


def test_skips_entry_missing_symbol():
    info = _trade_date_info()
    records, skipped = _parse_ticker_stock_data(_FULL_FIXTURE_RESPONSE, info)
    # The entry with no pk_rf_company must not produce a record with symbol=None
    assert all(r.symbol for r in records)


def test_skips_duplicate_symbol_keeps_first():
    info = _trade_date_info()
    records, skipped = _parse_ticker_stock_data(_FULL_FIXTURE_RESPONSE, info)
    aramco_records = [r for r in records if r.symbol == "2222"]
    assert len(aramco_records) == 1
    assert aramco_records[0].close == Decimal("26.52")  # first occurrence, not the duplicate's 999.0


def test_skipped_malformed_count_reported():
    info = _trade_date_info()
    records, skipped = _parse_ticker_stock_data(_FULL_FIXTURE_RESPONSE, info)
    # non-dict entry, missing-symbol entry, duplicate-symbol entry = 3 skipped
    assert skipped == 3


def test_coerces_string_noOfTrades():
    """Fund entries can return noOfTrades as a quoted string, not an int."""
    info = _trade_date_info()
    records, _ = _parse_ticker_stock_data(_FULL_FIXTURE_RESPONSE, info)
    fund = next(r for r in records if r.symbol == "4700")
    assert fund.trades == 117
    assert isinstance(fund.trades, int)


def test_handles_comma_formatted_numeric_strings():
    info = _trade_date_info()
    records, _ = _parse_ticker_stock_data(_FULL_FIXTURE_RESPONSE, info)
    rec = next(r for r in records if r.symbol == "1010")
    assert rec.turnover == Decimal("604947114.32")
    assert rec.volume == Decimal("22849767")
    assert rec.trades == 7943
    assert rec.close == Decimal("26.52")
    assert rec.change_amount == Decimal("-0.08")


def test_handles_empty_string_values_as_none():
    info = _trade_date_info()
    records, _ = _parse_ticker_stock_data(_FULL_FIXTURE_RESPONSE, info)
    rec = next(r for r in records if r.symbol == "2030")
    assert rec.close is None
    assert rec.turnover is None
    assert rec.trades is None
    assert rec.volume is None


def test_handles_unparseable_values_as_none_not_crash():
    info = _trade_date_info()
    records, _ = _parse_ticker_stock_data(_FULL_FIXTURE_RESPONSE, info)
    rec = next(r for r in records if r.symbol == "2040")
    assert rec.trades is None       # "N/A" unparseable
    assert rec.turnover is None     # "not-a-number" unparseable
    assert rec.volume == Decimal("1000")  # still parses the valid field on the same record
    assert rec.close == Decimal("10.0")


def test_missing_stock_data_key_returns_empty():
    info = _trade_date_info()
    records, skipped = _parse_ticker_stock_data({"message": None}, info)
    assert records == []
    assert skipped == 0


def test_non_dict_top_level_response_returns_empty():
    info = _trade_date_info()
    records, skipped = _parse_ticker_stock_data(["unexpected", "list"], info)
    assert records == []
    assert skipped == 0


def test_stock_data_not_a_list_returns_empty():
    info = _trade_date_info()
    records, skipped = _parse_ticker_stock_data({"stockData": "not-a-list"}, info)
    assert records == []
    assert skipped == 0


# ── _compose_source_value (schema-fit decision) ───────────────────────────────

def test_compose_source_value_includes_derivation_method():
    rec = _company_price_record(trade_date_derivation="riyadh_fixed_utc+3_weekend_rollback_friday_to_thursday")
    composed = _compose_source_value(rec)
    assert "saudi_exchange_ticker_servlet" in composed
    assert "riyadh_fixed_utc+3_weekend_rollback_friday_to_thursday" in composed
    assert len(composed) < 255, "must fit within MarketData.source VARCHAR(255)"


# ── fetch_company_prices (integration, mocked _http_get) ─────────────────────

def test_fetch_company_prices_success():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = _FULL_FIXTURE_RESPONSE
    resp.text = ""

    with patch.object(cp_module, "_http_get", return_value=resp):
        result = fetch_company_prices()

    assert result.reachable is True
    assert result.blocked is False
    assert result.error is None
    symbols = {r.symbol for r in result.records}
    assert "2222" in symbols
    assert "4700" in symbols
    assert result.skipped_malformed == 3


def test_fetch_company_prices_blocked():
    resp = MagicMock()
    resp.status_code = 403
    resp.text = "Access Denied"

    with patch.object(cp_module, "_http_get", return_value=resp):
        result = fetch_company_prices()

    assert result.blocked is True
    assert result.reachable is False
    assert result.records == []
    assert result.error is not None


def test_fetch_company_prices_server_error():
    resp = MagicMock()
    resp.status_code = 500
    resp.text = ""

    with patch.object(cp_module, "_http_get", return_value=resp):
        result = fetch_company_prices()

    assert result.reachable is False
    assert result.records == []


def test_fetch_company_prices_network_exception():
    with patch.object(cp_module, "_http_get", side_effect=ConnectionError("boom")):
        result = fetch_company_prices()

    assert result.reachable is False
    assert result.records == []
    assert "boom" in result.error


# ── upsert_company_prices (Phase 2D.6 — bulk INSERT ... ON CONFLICT) ─────────
#
# Each chunk now costs exactly 2 db.execute() calls regardless of chunk size:
#   1. the pre-query SELECT (existing-keys lookup, the "safe pre-query
#      strategy" used to report exact inserted/updated counts)
#   2. the bulk INSERT ... ON CONFLICT DO UPDATE
# Mocks below provide db.execute.side_effect as [select_result, insert_result]
# pairs, one pair per expected chunk.

def _existing_keys_result(keys: list[tuple[str, date]]):
    """Mock SELECT result whose .all() yields rows with .symbol/.trade_date."""
    rows = [SimpleNamespace(symbol=s, trade_date=d) for s, d in keys]
    result = MagicMock()
    result.all.return_value = rows
    return result


def _compiled_insert_params(call_args) -> dict:
    """Compile the bulk INSERT...ON CONFLICT statement passed to db.execute()."""
    stmt = call_args.args[0]
    return stmt.compile().params


@pytest.mark.asyncio
async def test_upsert_bulk_insert_new_records():
    """All keys absent from the pre-query -> all counted as inserted, one chunk."""
    records = [_company_price_record(symbol=s) for s in ("2222", "4700", "1010")]

    db = AsyncMock()
    db.execute.side_effect = [_existing_keys_result([]), MagicMock()]

    stats = await upsert_company_prices(records, db)

    assert stats == {"inserted": 3, "updated": 0, "total": 3}
    assert db.execute.await_count == 2  # 1 SELECT + 1 bulk INSERT, not 2-per-record
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_upsert_bulk_update_existing_records():
    """All keys present in the pre-query -> all counted as updated, one chunk."""
    records = [_company_price_record(symbol=s) for s in ("2222", "4700", "1010")]
    keys = [(r.symbol, r.trade_date) for r in records]

    db = AsyncMock()
    db.execute.side_effect = [_existing_keys_result(keys), MagicMock()]

    stats = await upsert_company_prices(records, db)

    assert stats == {"inserted": 0, "updated": 3, "total": 3}
    assert db.execute.await_count == 2


@pytest.mark.asyncio
async def test_upsert_mixed_insert_update():
    new_record = _company_price_record(symbol="4700")
    existing_record = _company_price_record(symbol="2222")

    db = AsyncMock()
    db.execute.side_effect = [
        _existing_keys_result([(existing_record.symbol, existing_record.trade_date)]),
        MagicMock(),
    ]

    stats = await upsert_company_prices([new_record, existing_record], db)

    assert stats == {"inserted": 1, "updated": 1, "total": 2}


@pytest.mark.asyncio
async def test_upsert_empty_input_is_a_noop():
    db = AsyncMock()
    stats = await upsert_company_prices([], db)
    assert stats == {"inserted": 0, "updated": 0, "total": 0}
    db.execute.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_upsert_chunk_boundary():
    """5 records with chunk_size=2 -> 3 chunks (2, 2, 1), 6 total db.execute() calls."""
    records = [_company_price_record(symbol=f"SYM{i}") for i in range(5)]

    db = AsyncMock()
    # 3 chunks => 3 (select, insert) pairs
    db.execute.side_effect = [
        _existing_keys_result([]), MagicMock(),
        _existing_keys_result([(records[2].symbol, records[2].trade_date)]), MagicMock(),
        _existing_keys_result([]), MagicMock(),
    ]

    stats = await upsert_company_prices(records, db, chunk_size=2)

    assert stats == {"inserted": 4, "updated": 1, "total": 5}
    assert db.execute.await_count == 6


@pytest.mark.asyncio
async def test_upsert_chunk_boundary_exact_multiple():
    """4 records with chunk_size=2 -> exactly 2 chunks, no trailing partial chunk."""
    records = [_company_price_record(symbol=f"SYM{i}") for i in range(4)]

    db = AsyncMock()
    db.execute.side_effect = [
        _existing_keys_result([]), MagicMock(),
        _existing_keys_result([]), MagicMock(),
    ]

    stats = await upsert_company_prices(records, db, chunk_size=2)

    assert stats == {"inserted": 4, "updated": 0, "total": 4}
    assert db.execute.await_count == 4


@pytest.mark.asyncio
async def test_upsert_stores_open_high_low_previous_close_as_null():
    """Confirms the NULL fields actually reach the persistence layer as None for every
    row in the bulk VALUES list, not omitted."""
    records = [_company_price_record(symbol=s) for s in ("2222", "4700")]

    db = AsyncMock()
    db.execute.side_effect = [_existing_keys_result([]), MagicMock()]

    await upsert_company_prices(records, db)

    insert_call = db.execute.call_args_list[1]
    params = _compiled_insert_params(insert_call)
    for i in range(len(records)):
        assert params[f"open_m{i}"] is None
        assert params[f"high_m{i}"] is None
        assert params[f"low_m{i}"] is None
        assert params[f"previous_close_m{i}"] is None


@pytest.mark.asyncio
async def test_upsert_duplicate_input_symbol_deduplicated():
    """
    Same (symbol, trade_date) appearing twice in one batch must not be sent
    to PostgreSQL twice in the same statement (which would raise "ON CONFLICT
    DO UPDATE command cannot affect row a second time") -- it must be
    deduplicated up front, with the last occurrence winning.
    """
    first = _company_price_record(symbol="2222", close=Decimal("1.0"))
    duplicate = _company_price_record(symbol="2222", close=Decimal("2.0"))

    db = AsyncMock()
    db.execute.side_effect = [_existing_keys_result([]), MagicMock()]

    stats = await upsert_company_prices([first, duplicate], db)

    assert stats == {"inserted": 1, "updated": 0, "total": 1}
    insert_call = db.execute.call_args_list[1]
    params = _compiled_insert_params(insert_call)
    # Only one row (_m0) in the VALUES list -- no _m1 key should exist.
    assert "close_m1" not in params
    assert params["close_m0"] == Decimal("2.0")  # last occurrence wins


@pytest.mark.asyncio
async def test_upsert_duplicate_symbols_across_different_trade_dates_not_deduplicated():
    """Same symbol but different trade_date is a different conflict target -- both kept."""
    rec_day1 = _company_price_record(symbol="2222", trade_date=date(2026, 6, 17))
    rec_day2 = _company_price_record(symbol="2222", trade_date=date(2026, 6, 18))

    db = AsyncMock()
    db.execute.side_effect = [_existing_keys_result([]), MagicMock()]

    stats = await upsert_company_prices([rec_day1, rec_day2], db)

    assert stats == {"inserted": 2, "updated": 0, "total": 2}
