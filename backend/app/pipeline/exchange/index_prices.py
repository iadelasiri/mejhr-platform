"""
Official daily index price fetcher — Saudi Exchange (Phase 2D.3).

Sources (confirmed in PHASE_2D2_DISCOVERY.md, approved spec):
  1. ThemeTASIUtilityServlet — full OHLCV for TASI and MT30 only.
  2. The `indicesJson` blob embedded in the listed-securities page — open/
     close/change/volume/turnover/trades for the 22 GICS sector indices
     plus the 5 other market-wide indices (TLCIC, TMCIC, TSCIC, TIPOC,
     TT50CI). High/low are NOT available from this source — stored as
     NULL, never fabricated. TASI/MT30 entries from this source are
     skipped: ThemeTASIUtilityServlet already provides richer data for
     them, and writing both would let the weaker source clobber the
     stronger one depending on run order.

trade_date is never returned explicitly by either source. We do NOT trust
the API's own `currentTime` field (a bare time-of-day string with no date
and no UTC offset — see PHASE_2D2_DISCOVERY.md review addendum). Instead
we compute the Saudi trading day from our own UTC clock using a fixed,
documented UTC+3 offset (Saudi Arabia has observed no DST since abolishing
it), then roll back to the most recent Thursday if that lands on the
Friday/Saturday weekend. The derivation method is recorded on every row.
Public holidays are not accounted for — a known limitation, not hidden.

noOfTrades has an inconsistent JSON type across the two sources (a real
int from ThemeTASIUtilityServlet, a quoted numeric string from
indicesJson) — coerced defensively; unparseable values become NULL, never
zero, never a crash.

CLI usage (fetch + print only, no DB write)::
    docker compose exec backend python -m app.pipeline.exchange.index_prices

Exit codes:
  0 — completed (even if 0 records — honest empty is a success)
  1 — both sources blocked or unreachable
"""
from __future__ import annotations

import json
import logging
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

log = logging.getLogger(__name__)

_TASI_MT30_URL = (
    "https://www.saudiexchange.sa/tadawul.eportal.theme.helper/ThemeTASIUtilityServlet"
)
_LISTED_SECURITIES_URL = (
    "https://www.saudiexchange.sa"
    "/wps/portal/tadawul/markets/equities/equities-securities/listed-securities"
)
_SOURCE_TASI_MT30 = "saudi_exchange_theme_tasi_servlet"
_SOURCE_INDICES_JSON = "saudi_exchange_indices_json_widget"

# Already covered with full OHLCV via ThemeTASIUtilityServlet — skip these
# when parsing indicesJson so the weaker source never overwrites the
# stronger one.
_FULL_OHLCV_CODES = frozenset({"TASI", "MT30"})

# Saudi Arabia has observed no daylight saving time since abolishing it in
# 1986. Fixed offset, not derived from any live API field.
_RIYADH_UTC_OFFSET = timedelta(hours=3)

# Saudi trading week is Sunday-Thursday. Python date.weekday(): Mon=0 ... Sun=6.
_FRIDAY = 4
_SATURDAY = 5

# Matches one full indicesJson object, e.g.:
#   {"symbol":"TCPI","name":"Commercial & Professional Svc","price":4011.03,
#    "volume":5223906,"turnover":60598540.31,"netChange":-24.22,
#    "netPercentChange":-0.6,"priceIndicatorCssClass":"priceDown","open":4030.54,
#    "noOfTrades":"7943"}
# Anchored on a T-prefixed index code (letter-starting) so it never matches
# 4-digit company symbols. No nested objects inside an entry, so [^{}]* is
# safe up to the closing brace. The matched text is parsed with json.loads
# rather than positional field capture — robust to field reordering or new
# fields, and correctly decodes \uXXXX escapes in `name`.
_OBJECT_RE = re.compile(
    r'\{"symbol":"[A-Z][A-Z0-9]{2,7}","name":"(?:[^"\\]|\\.)*"[^{}]*\}'
)


# ── Pure helpers (no network, fully unit-testable) ────────────────────────────

def _to_decimal(value: Any) -> Decimal | None:
    """
    Coerce a numeric or numeric-string field to Decimal. None on failure or
    blank input. Strips comma thousands-separators from string input
    defensively (Saudi Exchange endpoints have shown inconsistent numeric
    string formatting — see _coerce_trades_count below).
    """
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip().replace(",", "")
        if not stripped:
            return None
        value = stripped
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _coerce_trades_count(value: Any) -> int | None:
    """
    Defensively coerce noOfTrades to int.

    Source type is inconsistent across the two endpoints: a real int from
    ThemeTASIUtilityServlet, a quoted numeric string (sometimes with comma
    separators) from indicesJson. Unparseable values become None — never
    zero, never a crash.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip().replace(",", "")
        if not stripped:
            return None
        try:
            return int(float(stripped))
        except (ValueError, TypeError):
            log.warning("Could not coerce noOfTrades value %r to int", value)
            return None
    return None


@dataclass
class TradeDateDerivation:
    trade_date: date
    method: str


def _derive_trade_date(fetched_at: datetime) -> TradeDateDerivation:
    """
    Derive the Saudi trading day for data fetched at `fetched_at` (must be
    timezone-aware). Never trusts the API's own `currentTime` field — see
    module docstring. Uses a fixed Asia/Riyadh offset computed from our own
    clock, then rolls back to the most recent Thursday if that lands on the
    Saudi weekend (Friday/Saturday). Does not account for public holidays.
    """
    if fetched_at.tzinfo is None:
        raise ValueError("fetched_at must be timezone-aware (UTC)")

    riyadh_date = (fetched_at.astimezone(timezone.utc) + _RIYADH_UTC_OFFSET).date()
    weekday = riyadh_date.weekday()

    if weekday == _FRIDAY:
        return TradeDateDerivation(
            trade_date=riyadh_date - timedelta(days=1),
            method="riyadh_fixed_utc+3_weekend_rollback_friday_to_thursday",
        )
    if weekday == _SATURDAY:
        return TradeDateDerivation(
            trade_date=riyadh_date - timedelta(days=2),
            method="riyadh_fixed_utc+3_weekend_rollback_saturday_to_thursday",
        )
    return TradeDateDerivation(trade_date=riyadh_date, method="riyadh_fixed_utc+3_same_day")


# ── Result types ───────────────────────────────────────────────────────────────

@dataclass
class IndexPriceRecord:
    index_code: str
    trade_date: date
    trade_date_derivation: str
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    previous_close: Decimal | None
    change_amount: Decimal | None
    change_pct: Decimal | None
    volume: Decimal | None
    turnover: Decimal | None
    trades_count: int | None
    source: str
    source_url: str


@dataclass
class IndexPriceFetchResult:
    records: list[IndexPriceRecord]
    reachable_tasi_mt30: bool
    reachable_indices_json: bool
    blocked_tasi_mt30: bool
    blocked_indices_json: bool
    parse_note: str
    error: str | None
    fetched_at: str


# ── Network + block detection ─────────────────────────────────────────────────

def _http_get(url: str, **kwargs):
    """GET via curl_cffi Chrome124 TLS impersonation. Isolated for testability."""
    from curl_cffi import requests as cffi_requests
    return cffi_requests.get(url, impersonate="chrome124", timeout=30, **kwargs)


def _detect_block(status_code: int, text: str) -> bool:
    if status_code == 403:
        return True
    lower = (text or "").lower()
    return any(kw in lower for kw in (
        "access denied", "you have been blocked",
        "enable javascript and cookies", "reference #",
    ))


# ── Parsers (pure, given already-fetched data) ────────────────────────────────

def _parse_tasi_mt30(data: dict, trade_date_info: TradeDateDerivation) -> list[IndexPriceRecord]:
    records: list[IndexPriceRecord] = []
    for bean_key in ("tasiBean", "mt30Bean"):
        bean = data.get(bean_key)
        if not isinstance(bean, dict):
            continue
        code = bean.get("symbol")
        summary = bean.get("tasiTodaysSummaryBean")
        if not code or not isinstance(summary, dict):
            continue
        records.append(IndexPriceRecord(
            index_code=code,
            trade_date=trade_date_info.trade_date,
            trade_date_derivation=trade_date_info.method,
            open=_to_decimal(summary.get("openPrice")),
            high=_to_decimal(summary.get("highPrice")),
            low=_to_decimal(summary.get("lowPrice")),
            close=_to_decimal(summary.get("indexPrice")),
            previous_close=_to_decimal(summary.get("previouseIndexPrice")),
            change_amount=_to_decimal(summary.get("netChange")),
            change_pct=_to_decimal(summary.get("percentChange")),
            volume=_to_decimal(summary.get("volumeTraded")),
            turnover=_to_decimal(summary.get("turnOver")),
            trades_count=_coerce_trades_count(summary.get("noOfTrades")),
            source=_SOURCE_TASI_MT30,
            source_url=_TASI_MT30_URL,
        ))
    return records


def _parse_indices_json(html: str, trade_date_info: TradeDateDerivation) -> list[IndexPriceRecord]:
    records: list[IndexPriceRecord] = []
    seen: set[str] = set()

    for match in _OBJECT_RE.finditer(html):
        try:
            obj = json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            continue

        code = obj.get("symbol")
        if not code or code in seen:
            continue
        seen.add(code)

        if code in _FULL_OHLCV_CODES:
            continue  # richer data already provided by ThemeTASIUtilityServlet

        close = _to_decimal(obj.get("price"))
        change_amount = _to_decimal(obj.get("netChange"))
        previous_close = (
            close - change_amount if close is not None and change_amount is not None else None
        )

        records.append(IndexPriceRecord(
            index_code=code,
            trade_date=trade_date_info.trade_date,
            trade_date_derivation=trade_date_info.method,
            open=_to_decimal(obj.get("open")),
            high=None,
            low=None,
            close=close,
            previous_close=previous_close,
            change_amount=change_amount,
            change_pct=_to_decimal(obj.get("netPercentChange")),
            volume=_to_decimal(obj.get("volume")),
            turnover=_to_decimal(obj.get("turnover")),
            trades_count=_coerce_trades_count(obj.get("noOfTrades")),
            source=_SOURCE_INDICES_JSON,
            source_url=_LISTED_SECURITIES_URL,
        ))

    return records


# ── Main fetch entry point ────────────────────────────────────────────────────

def fetch_index_prices() -> IndexPriceFetchResult:
    """Fetch from both sources and combine. Always returns a result — never raises."""
    fetched_at_dt = datetime.now(timezone.utc)
    trade_date_info = _derive_trade_date(fetched_at_dt)

    records: list[IndexPriceRecord] = []
    notes: list[str] = []
    error_parts: list[str] = []
    reachable_tasi_mt30 = False
    reachable_indices_json = False
    blocked_tasi_mt30 = False
    blocked_indices_json = False

    try:
        resp = _http_get(_TASI_MT30_URL)
        if resp.status_code == 403 or _detect_block(resp.status_code, getattr(resp, "text", "")):
            blocked_tasi_mt30 = True
            error_parts.append(f"TASI/MT30 source blocked (HTTP {resp.status_code})")
        elif resp.status_code != 200:
            error_parts.append(f"TASI/MT30 source returned HTTP {resp.status_code}")
        else:
            reachable_tasi_mt30 = True
            tasi_records = _parse_tasi_mt30(resp.json(), trade_date_info)
            records.extend(tasi_records)
            notes.append(f"TASI/MT30: {len(tasi_records)} record(s)")
    except Exception as exc:
        error_parts.append(f"TASI/MT30 source network error: {exc}")

    try:
        resp = _http_get(_LISTED_SECURITIES_URL)
        if resp.status_code == 403 or _detect_block(resp.status_code, getattr(resp, "text", "")):
            blocked_indices_json = True
            error_parts.append(f"indicesJson source blocked (HTTP {resp.status_code})")
        elif resp.status_code != 200:
            error_parts.append(f"indicesJson source returned HTTP {resp.status_code}")
        else:
            reachable_indices_json = True
            sector_records = _parse_indices_json(resp.text, trade_date_info)
            records.extend(sector_records)
            notes.append(f"sector/market indices: {len(sector_records)} record(s)")
    except Exception as exc:
        error_parts.append(f"indicesJson source network error: {exc}")

    parse_note = f"trade_date={trade_date_info.trade_date} ({trade_date_info.method})."
    if notes:
        parse_note += " " + "; ".join(notes) + "."
    else:
        parse_note += " No records parsed."

    return IndexPriceFetchResult(
        records=records,
        reachable_tasi_mt30=reachable_tasi_mt30,
        reachable_indices_json=reachable_indices_json,
        blocked_tasi_mt30=blocked_tasi_mt30,
        blocked_indices_json=blocked_indices_json,
        parse_note=parse_note,
        error="; ".join(error_parts) if error_parts else None,
        fetched_at=fetched_at_dt.isoformat(),
    )


# ── Idempotent upsert ──────────────────────────────────────────────────────────

async def upsert_index_prices(records: list[IndexPriceRecord], db) -> dict:
    """
    Idempotent upsert into index_prices, keyed on (index_code, trade_date).

    SELECT-then-UPDATE-or-INSERT — consistent with the pattern already used
    in xbrl_normalizer.normalize_symbol (avoids ON CONFLICT/NULL unique-
    constraint edge cases and keeps behavior explicit and easy to test).
    """
    from sqlalchemy import select, insert, update
    from app.models.market_index import IndexPrice

    inserted = 0
    updated = 0

    for rec in records:
        existing_row = await db.execute(
            select(IndexPrice.id)
            .where(IndexPrice.index_code == rec.index_code)
            .where(IndexPrice.trade_date == rec.trade_date)
        )
        existing_id = existing_row.scalar_one_or_none()

        values = dict(
            open=rec.open, high=rec.high, low=rec.low, close=rec.close,
            previous_close=rec.previous_close, change_amount=rec.change_amount,
            change_pct=rec.change_pct, volume=rec.volume, turnover=rec.turnover,
            trades_count=rec.trades_count,
            trade_date_derivation=rec.trade_date_derivation,
            source=rec.source, source_url=rec.source_url,
            imported_at=datetime.now(timezone.utc),
        )

        if existing_id:
            await db.execute(
                update(IndexPrice).where(IndexPrice.id == existing_id).values(**values)
            )
            updated += 1
        else:
            await db.execute(
                insert(IndexPrice).values(
                    index_code=rec.index_code, trade_date=rec.trade_date, **values
                )
            )
            inserted += 1

    await db.commit()
    return {"inserted": inserted, "updated": updated, "total": len(records)}


# ── CLI (fetch + print only — no DB write) ────────────────────────────────────

def print_report(result: IndexPriceFetchResult) -> None:
    W = 70
    print("=" * W)
    print("  Saudi Exchange — Index Prices Fetch (Phase 2D.3)")
    print("=" * W)
    print(f"  Fetched at            : {result.fetched_at}")
    print(f"  TASI/MT30 reachable   : {result.reachable_tasi_mt30}")
    print(f"  TASI/MT30 blocked     : {result.blocked_tasi_mt30}")
    print(f"  indicesJson reachable : {result.reachable_indices_json}")
    print(f"  indicesJson blocked   : {result.blocked_indices_json}")
    print(f"  Records parsed        : {len(result.records)}")
    print("-" * W)
    print(f"  {result.parse_note}")
    if result.error:
        print(f"  Error: {result.error}")
    print("-" * W)
    for r in sorted(result.records, key=lambda x: x.index_code):
        print(
            f"    [{r.index_code:8s}] close={r.close} high={r.high} low={r.low} "
            f"change={r.change_amount} trades={r.trades_count} src={r.source}"
        )
    print("=" * W)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    result = fetch_index_prices()
    print_report(result)
    sys.exit(0 if result.records else 1)
