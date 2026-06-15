"""
Official listed-companies fetcher — Saudi Exchange.

Source:  ThemeSearchUtilityServlet
         https://www.saudiexchange.sa/tadawul.eportal.theme.helper/ThemeSearchUtilityServlet

Returns a JSON array of ~1900 securities.
Filter:  market_type == 'M' (Tadawul Main Market)
         market_type == 'S' (NOMU Parallel Market)
All other types (B=Bonds, D=Derivatives, E=ETFs, F=Funds, O=Options) are skipped.

Phase 2D confirmed: curl_cffi Chrome TLS impersonation bypasses Akamai bot detection.
Standard httpx still blocked. This fetcher always uses curl_cffi.

CLI usage::

    docker compose exec backend python -m app.pipeline.exchange.companies

Exit codes:
  0 — completed (even if 0 companies — honest empty is a success)
  1 — unexpected error
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

log = logging.getLogger(__name__)

SOURCE_URL = (
    "https://www.saudiexchange.sa"
    "/tadawul.eportal.theme.helper/ThemeSearchUtilityServlet"
)

_EQUITY_MARKET_TYPES = frozenset({"M", "S"})
_MARKET_TYPE_MAP = {"M": "tadawul", "S": "nomu"}


@dataclass
class CompanyRecord:
    """One equity company extracted from ThemeSearchUtilityServlet."""
    symbol: str
    arabic_name: str
    english_name: str | None
    market: str | None          # "tadawul" | "nomu"
    source: str
    source_url: str
    imported_at: datetime
    data_status: str = "official"
    mapping_status: str = "pending_official_mapping"
    isin: str | None = None
    trading_name_en: str | None = None
    trading_name_ar: str | None = None


@dataclass
class FetchResult:
    companies: list[CompanyRecord]
    reachable: bool
    blocked: bool
    status_code: int | None
    raw_format: str          # "json" | "html" | "error"
    parse_note: str
    error: str | None
    fetched_at: str


def _http_get(url: str):
    """GET url via curl_cffi Chrome124 TLS impersonation. Isolated here for testability."""
    from curl_cffi import requests as cffi_requests
    return cffi_requests.get(url, impersonate="chrome124", timeout=30)


def fetch_companies() -> FetchResult:
    """
    Fetch official listed equity companies from Saudi Exchange.

    Always returns a FetchResult — never raises.
    """
    now = datetime.now(timezone.utc)
    fetched_at = now.isoformat()

    try:
        resp = _http_get(SOURCE_URL)
    except Exception as exc:
        return FetchResult(
            companies=[],
            reachable=False,
            blocked=False,
            status_code=None,
            raw_format="error",
            parse_note=f"Network error: {exc}",
            error=str(exc),
            fetched_at=fetched_at,
        )

    if resp.status_code == 403:
        return FetchResult(
            companies=[],
            reachable=False,
            blocked=True,
            status_code=403,
            raw_format="error",
            parse_note=(
                "Saudi Exchange blocked this request (HTTP 403 — Akamai bot detection). "
                "No official company records imported. "
                "Ensure curl_cffi Chrome impersonation is active or deploy on a Saudi/GCC server."
            ),
            error="HTTP 403 — Akamai block",
            fetched_at=fetched_at,
        )

    if resp.status_code != 200:
        return FetchResult(
            companies=[],
            reachable=True,
            blocked=False,
            status_code=resp.status_code,
            raw_format="error",
            parse_note=(
                f"Saudi Exchange returned HTTP {resp.status_code}. "
                "Endpoint needs verification."
            ),
            error=f"HTTP {resp.status_code}",
            fetched_at=fetched_at,
        )

    content_type = resp.headers.get("content-type", "")

    if "html" in content_type:
        return FetchResult(
            companies=[],
            reachable=True,
            blocked=False,
            status_code=200,
            raw_format="html",
            parse_note=(
                "Expected JSON from ThemeSearchUtilityServlet but received HTML. "
                "The servlet URL may have changed."
            ),
            error=None,
            fetched_at=fetched_at,
        )

    try:
        data = resp.json()
    except Exception as exc:
        return FetchResult(
            companies=[],
            reachable=True,
            blocked=False,
            status_code=200,
            raw_format="unknown",
            parse_note=f"Response is not valid JSON: {exc}",
            error=str(exc),
            fetched_at=fetched_at,
        )

    if not isinstance(data, list):
        return FetchResult(
            companies=[],
            reachable=True,
            blocked=False,
            status_code=200,
            raw_format="json",
            parse_note=(
                f"Expected JSON array but got {type(data).__name__}. "
                f"Top-level keys: {list(data.keys())[:10] if isinstance(data, dict) else 'N/A'}"
            ),
            error=None,
            fetched_at=fetched_at,
        )

    companies: list[CompanyRecord] = []
    skipped = 0

    for entry in data:
        if not isinstance(entry, dict):
            skipped += 1
            continue

        market_type = (entry.get("market_type") or "").strip()
        if market_type not in _EQUITY_MARKET_TYPES:
            skipped += 1
            continue

        symbol = (entry.get("symbol") or "").strip()
        arabic_name = (
            entry.get("companyNameAR") or entry.get("companyName") or ""
        ).strip()

        if not symbol or not arabic_name:
            skipped += 1
            continue

        english_name = (entry.get("companyNameEN") or "").strip() or None

        companies.append(CompanyRecord(
            symbol=symbol,
            arabic_name=arabic_name,
            english_name=english_name,
            market=_MARKET_TYPE_MAP.get(market_type),
            isin=(entry.get("isin") or "").strip() or None,
            trading_name_en=(entry.get("tradingNameEn") or "").strip() or None,
            trading_name_ar=(entry.get("tradingNameAr") or "").strip() or None,
            source="saudi_exchange_official",
            source_url=SOURCE_URL,
            imported_at=now,
        ))

    main_count = sum(1 for c in companies if c.market == "tadawul")
    nomu_count = sum(1 for c in companies if c.market == "nomu")

    parse_note = (
        f"Parsed {len(companies)} equity companies "
        f"({main_count} Tadawul, {nomu_count} NOMU) "
        f"from {len(data)} total securities. "
        f"Skipped {skipped} non-equity entries (bonds, funds, derivatives, options)."
    )

    return FetchResult(
        companies=companies,
        reachable=True,
        blocked=False,
        status_code=200,
        raw_format="json",
        parse_note=parse_note,
        error=None,
        fetched_at=fetched_at,
    )


def print_report(result: FetchResult) -> None:
    W = 64
    print("=" * W)
    print("  Saudi Exchange — Companies Fetch Report (Phase 2D)")
    print("=" * W)
    print(f"  Source URL     : {SOURCE_URL}")
    print(f"  Fetched at     : {result.fetched_at}")
    print(f"  Reachable      : {result.reachable}")
    print(f"  Blocked        : {result.blocked}")
    print(f"  HTTP status    : {result.status_code if result.status_code is not None else 'N/A'}")
    print(f"  Response format: {result.raw_format}")
    print(f"  Companies found: {len(result.companies)}")
    print("-" * W)
    print("  Diagnostic:")
    for sentence in result.parse_note.split(". "):
        sentence = sentence.strip()
        if sentence:
            print(f"    {sentence}.")
    if result.companies:
        print("-" * W)
        print("  Sample (first 5):")
        for c in result.companies[:5]:
            print(
                f"    [{c.symbol}] {c.arabic_name} | "
                f"{c.english_name or '—'} | {c.market or '—'} | "
                f"ISIN={c.isin or '—'}"
            )
    print("=" * W)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    result = fetch_companies()
    print_report(result)
    sys.exit(0)
