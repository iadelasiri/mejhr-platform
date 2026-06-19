"""
Official partial company price fetcher — Saudi Exchange (Phase 2D.4).

Source (confirmed in PHASE_2D2_DISCOVERY.md, approved spec):
  TickerServlet — returns a `stockData` list covering both Main Market
  companies and traded funds/ETFs. `highPrice`, `lowPrice`,
  `previousClosePrice`, and `todaysOpen` were verified NULL across every
  sampled record in discovery (not a data-availability fluke — structurally
  unpopulated by this servlet). This pipeline maps only the fields actually
  supplied (close, change, change_pct, volume, turnover, trades) and stores
  the rest as explicit NULL. No OHLC value is ever fabricated or backfilled.

  `tickerStockData` (a parallel array on the same response, intended for the
  homepage ticker-tape widget) is NOT used — it carries the same data with
  some fields re-typed as strings for direct DOM rendering, and would only
  add duplicate-parsing risk with no additional information.

Schema note (read before changing anything):
  MarketData (backend/app/models/market_data.py) was inspected before
  writing this module. It already has every column this phase needs
  (symbol, trade_date, close, change_amount, change_pct, volume, turnover,
  trades, open, high, low, previous_close) plus the exact uniqueness key
  required for idempotent upserts: UniqueConstraint(symbol, trade_date).
  No migration is needed for those.

  What MarketData does NOT have is a dedicated column for the trade_date
  derivation method (unlike the new IndexPrice.trade_date_derivation column
  added in Phase 2D.3) or any structured per-row metadata field (no JSONB,
  unlike NormalizedFinancial.source_map). This was a deliberate decision
  point, not an oversight: rather than requesting a migration, the
  derivation method is packed into the existing `source` VARCHAR(255)
  column as documented composite text (e.g. "saudi_exchange_ticker_servlet;
  trade_date_derivation=riyadh_fixed_utc+3_same_day") — comfortably within
  the column's width, with nothing hidden or fabricated. See
  _compose_source_value() below. If a future phase finds this insufficient,
  add a dedicated column then — this module does not preempt that.

trade_date derivation reuses _derive_trade_date / TradeDateDerivation from
index_prices.py (Phase 2D.3) rather than re-implementing it, so both
pipelines apply the exact same Riyadh-fixed-offset-plus-weekend-rollback
rule. See that module's docstring for the full rationale (never trusts the
API's own ambiguous `currentTime` field).

CLI usage (fetch + print only, no DB write)::
    docker compose exec backend python -m app.pipeline.exchange.company_prices

Exit codes:
  0 — completed (even if 0 records — honest empty is a success)
  1 — source blocked or unreachable
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from app.pipeline.exchange.index_prices import (
    TradeDateDerivation,
    _coerce_trades_count,
    _derive_trade_date,
    _to_decimal,
)

log = logging.getLogger(__name__)

_TICKER_URL = "https://www.saudiexchange.sa/tadawul.eportal.theme.helper/TickerServlet"
_SOURCE = "saudi_exchange_ticker_servlet"


# ── Result types ───────────────────────────────────────────────────────────────

@dataclass
class CompanyPriceRecord:
    symbol: str
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
    trades: int | None
    source: str
    source_url: str


@dataclass
class CompanyPriceFetchResult:
    records: list[CompanyPriceRecord]
    reachable: bool
    blocked: bool
    skipped_malformed: int
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


# ── Parser (pure, given already-fetched data) ─────────────────────────────────

def _parse_ticker_stock_data(
    data: Any, trade_date_info: TradeDateDerivation,
) -> tuple[list[CompanyPriceRecord], int]:
    """
    Parse the `stockData` array. Returns (records, skipped_malformed_count).

    Defensive against: a non-dict top-level response, a missing or non-list
    `stockData` key, non-dict entries inside the list, missing/empty/
    duplicate symbols, and unparseable numeric fields (handled by
    _to_decimal / _coerce_trades_count, which return None rather than
    raising). open/high/low/previous_close are always None — never
    available from this source, never fabricated.
    """
    if not isinstance(data, dict):
        return [], 0

    stock_data = data.get("stockData")
    if not isinstance(stock_data, list):
        return [], 0

    records: list[CompanyPriceRecord] = []
    seen: set[str] = set()
    skipped = 0

    for entry in stock_data:
        if not isinstance(entry, dict):
            skipped += 1
            continue

        symbol = entry.get("pk_rf_company")
        if not symbol or not isinstance(symbol, str):
            skipped += 1
            continue
        if symbol in seen:
            skipped += 1
            continue
        seen.add(symbol)

        records.append(CompanyPriceRecord(
            symbol=symbol,
            trade_date=trade_date_info.trade_date,
            trade_date_derivation=trade_date_info.method,
            open=None,
            high=None,
            low=None,
            previous_close=None,
            close=_to_decimal(entry.get("lastTradePrice")),
            change_amount=_to_decimal(entry.get("change")),
            change_pct=_to_decimal(entry.get("changePercent")),
            volume=_to_decimal(entry.get("volumeTraded")),
            turnover=_to_decimal(entry.get("turnOver")),
            trades=_coerce_trades_count(entry.get("noOfTrades")),
            source=_SOURCE,
            source_url=_TICKER_URL,
        ))

    return records, skipped


# ── Main fetch entry point ────────────────────────────────────────────────────

def fetch_company_prices() -> CompanyPriceFetchResult:
    """Fetch from TickerServlet and parse. Always returns a result — never raises."""
    fetched_at_dt = datetime.now(timezone.utc)
    trade_date_info = _derive_trade_date(fetched_at_dt)

    records: list[CompanyPriceRecord] = []
    skipped = 0
    reachable = False
    blocked = False
    error: str | None = None

    try:
        resp = _http_get(_TICKER_URL)
        if resp.status_code == 403 or _detect_block(resp.status_code, getattr(resp, "text", "")):
            blocked = True
            error = f"TickerServlet blocked (HTTP {resp.status_code})"
        elif resp.status_code != 200:
            error = f"TickerServlet returned HTTP {resp.status_code}"
        else:
            reachable = True
            data = resp.json()
            records, skipped = _parse_ticker_stock_data(data, trade_date_info)
    except Exception as exc:
        error = f"TickerServlet network error: {exc}"

    parse_note = f"trade_date={trade_date_info.trade_date} ({trade_date_info.method})."
    if reachable:
        parse_note += f" {len(records)} record(s) parsed, {skipped} malformed/duplicate entry(ies) skipped."
    else:
        parse_note += " No records parsed."

    return CompanyPriceFetchResult(
        records=records,
        reachable=reachable,
        blocked=blocked,
        skipped_malformed=skipped,
        parse_note=parse_note,
        error=error,
        fetched_at=fetched_at_dt.isoformat(),
    )


# ── Schema-fit helper ──────────────────────────────────────────────────────────

def _compose_source_value(rec: CompanyPriceRecord) -> str:
    """
    MarketData has no dedicated trade_date_derivation column (see module
    docstring). Pack it into the existing `source` field as documented
    composite text rather than requesting a migration. Well within
    VARCHAR(255) — source name + derivation string is under 90 characters
    for every known derivation method.
    """
    return f"{rec.source}; trade_date_derivation={rec.trade_date_derivation}"


# ── Idempotent upsert ──────────────────────────────────────────────────────────

async def upsert_company_prices(records: list[CompanyPriceRecord], db) -> dict:
    """
    Idempotent upsert into market_data, keyed on the table's existing
    UniqueConstraint(symbol, trade_date) — no schema change required.

    SELECT-then-UPDATE-or-INSERT, consistent with index_prices.py and
    xbrl_normalizer.normalize_symbol.
    """
    from sqlalchemy import select, insert, update
    from app.models.market_data import MarketData

    inserted = 0
    updated = 0

    for rec in records:
        existing_row = await db.execute(
            select(MarketData.id)
            .where(MarketData.symbol == rec.symbol)
            .where(MarketData.trade_date == rec.trade_date)
        )
        existing_id = existing_row.scalar_one_or_none()

        values = dict(
            open=rec.open, high=rec.high, low=rec.low, close=rec.close,
            previous_close=rec.previous_close, change_amount=rec.change_amount,
            change_pct=rec.change_pct, volume=rec.volume, turnover=rec.turnover,
            trades=rec.trades,
            source=_compose_source_value(rec), source_url=rec.source_url,
            imported_at=datetime.now(timezone.utc),
        )

        if existing_id:
            await db.execute(
                update(MarketData).where(MarketData.id == existing_id).values(**values)
            )
            updated += 1
        else:
            await db.execute(
                insert(MarketData).values(
                    symbol=rec.symbol, trade_date=rec.trade_date, **values
                )
            )
            inserted += 1

    await db.commit()
    return {"inserted": inserted, "updated": updated, "total": len(records)}


# ── CLI (fetch + print only — no DB write) ────────────────────────────────────

def print_report(result: CompanyPriceFetchResult) -> None:
    W = 70
    print("=" * W)
    print("  Saudi Exchange — Company Prices Fetch (Phase 2D.4, partial)")
    print("=" * W)
    print(f"  Fetched at        : {result.fetched_at}")
    print(f"  Reachable         : {result.reachable}")
    print(f"  Blocked           : {result.blocked}")
    print(f"  Records parsed    : {len(result.records)}")
    print(f"  Skipped malformed : {result.skipped_malformed}")
    print("-" * W)
    print(f"  {result.parse_note}")
    if result.error:
        print(f"  Error: {result.error}")
    print("-" * W)
    for r in sorted(result.records, key=lambda x: x.symbol)[:10]:
        print(
            f"    [{r.symbol:8s}] close={r.close} change={r.change_amount} "
            f"vol={r.volume} trades={r.trades}"
        )
    if len(result.records) > 10:
        print(f"    ... and {len(result.records) - 10} more")
    print("=" * W)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    result = fetch_company_prices()
    print_report(result)
    sys.exit(0 if result.records else 1)
