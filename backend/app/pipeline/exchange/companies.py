"""
Official listed-companies fetcher — Saudi Exchange.

Source: Saudi Exchange (www.saudiexchange.sa) — official data only.

ENDPOINT STATUS: NEEDS VERIFICATION
--------------------------------------
The exact JSON API path for listed companies has not yet been confirmed.
This fetcher:
  1. Connects to SAUDI_EXCHANGE_BASE_URL + SAUDI_EXCHANGE_COMPANIES_PATH.
  2. If the response is structured JSON with recognisable company fields,
     parses and returns company records.
  3. If the response is HTML, a block page, or an unrecognised format,
     returns an empty list with an honest diagnostic message.
  4. Never fabricates, invents, or approximates company data.

How to find the correct endpoint:
  1. Open https://www.saudiexchange.sa in a browser with DevTools → Network.
  2. Navigate to the "Listed Companies" or "All Shares" section.
  3. Find the JSON XHR/fetch request that returns the company list.
  4. Set SAUDI_EXCHANGE_COMPANIES_PATH in .env to that path.
  5. Re-run: docker compose exec backend python -m app.pipeline.exchange.companies

CLI usage::

    docker compose exec backend python -m app.pipeline.exchange.companies

Exit codes:
  0 — completed (even if 0 companies imported — honest empty is a success)
  1 — unexpected error
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.pipeline.exchange.client import SaudiExchangeClient

log = logging.getLogger(__name__)


@dataclass
class CompanyRecord:
    """One company record extracted from the Saudi Exchange API response."""
    symbol: str
    arabic_name: str
    english_name: str | None
    market: str | None  # "tadawul" | "nomu" | None
    source: str
    source_url: str | None
    imported_at: datetime
    data_status: str = "official"
    mapping_status: str = "pending_official_mapping"


@dataclass
class FetchResult:
    companies: list[CompanyRecord]
    reachable: bool
    blocked: bool
    status_code: int | None
    raw_format: str          # "json" | "html" | "unknown" | "error"
    parse_note: str          # human-readable diagnostic
    error: str | None
    fetched_at: str


# ---------------------------------------------------------------------------
# Known JSON field name mappings (extend as we learn the actual API structure)
# ---------------------------------------------------------------------------
_SYMBOL_KEYS = ("symbol", "stockSymbol", "tickerSymbol", "code", "tasi")
_NAME_AR_KEYS = ("nameAr", "arabicName", "companyNameAr", "name_ar", "arabic_name")
_NAME_EN_KEYS = ("nameEn", "englishName", "companyNameEn", "name_en", "english_name")
_MARKET_KEYS = ("market", "marketType", "boardId", "exchange")

_MARKET_MAP = {
    # Tadawul main market codes we might encounter
    "a": "tadawul", "main": "tadawul", "tadawul": "tadawul", "1": "tadawul",
    # Nomu parallel market
    "p": "nomu", "nomu": "nomu", "parallel": "nomu", "2": "nomu",
}


def _pick(obj: dict, keys: tuple[str, ...]) -> str | None:
    for k in keys:
        v = obj.get(k)
        if v is not None:
            return str(v).strip() or None
    return None


def _parse_company(raw: dict, source_url: str, now: datetime) -> CompanyRecord | None:
    """Extract a CompanyRecord from a raw dict. Returns None if unusable."""
    symbol = _pick(raw, _SYMBOL_KEYS)
    arabic_name = _pick(raw, _NAME_AR_KEYS)
    if not symbol or not arabic_name:
        return None

    market_raw = _pick(raw, _MARKET_KEYS)
    market = _MARKET_MAP.get(market_raw.lower(), None) if market_raw else None

    return CompanyRecord(
        symbol=symbol,
        arabic_name=arabic_name,
        english_name=_pick(raw, _NAME_EN_KEYS),
        market=market,
        source="saudi_exchange_official",
        source_url=source_url,
        imported_at=now,
    )


def _parse_response(body: bytes, content_type: str) -> tuple[list[dict], str, str]:
    """
    Try to extract a list of raw company dicts from the response body.

    Returns:
        (records, raw_format, parse_note)
    """
    import json

    # Is it JSON?
    if "json" in content_type or body.lstrip()[:1] in (b"{", b"["):
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            return [], "unknown", f"Body starts like JSON but failed to parse: {exc}"

        # Unwrap common envelope patterns
        if isinstance(parsed, list):
            return parsed, "json", "Top-level JSON array"
        if isinstance(parsed, dict):
            for key in ("data", "companies", "stocks", "items", "result", "results",
                        "companyList", "stockList"):
                if key in parsed and isinstance(parsed[key], list):
                    return parsed[key], "json", f"JSON object, records under '{key}'"
            # Single-level dict that might itself be a company
            if _pick(parsed, _SYMBOL_KEYS):
                return [parsed], "json", "JSON object looks like a single company record"
            return [], "json", (
                f"JSON object received but no recognisable companies key found. "
                f"Top-level keys: {list(parsed.keys())[:10]}"
            )
        return [], "json", f"Unexpected JSON root type: {type(parsed).__name__}"

    # HTML page
    if "html" in content_type:
        return [], "html", (
            "Response is an HTML page, not a JSON API. "
            "SAUDI_EXCHANGE_COMPANIES_PATH points to a portal page. "
            "Inspect the browser's Network tab on the Saudi Exchange website "
            "to find the JSON endpoint that backs the companies list, "
            "then set SAUDI_EXCHANGE_COMPANIES_PATH accordingly."
        )

    return [], "unknown", (
        f"Unrecognised content-type: {content_type!r}. "
        "Cannot parse company records."
    )


def fetch_companies() -> FetchResult:
    """
    Fetch official listed companies from Saudi Exchange.

    Always returns a FetchResult — never raises.
    If no companies can be imported, the result explains why.
    """
    now = datetime.now(timezone.utc)
    fetched_at = now.isoformat()
    source_url = (
        settings.SAUDI_EXCHANGE_BASE_URL.rstrip("/")
        + settings.SAUDI_EXCHANGE_COMPANIES_PATH
    )

    with SaudiExchangeClient() as client:
        resp = client.get(settings.SAUDI_EXCHANGE_COMPANIES_PATH)

    # Connectivity failure
    if resp.status_code is None:
        return FetchResult(
            companies=[],
            reachable=False,
            blocked=False,
            status_code=None,
            raw_format="error",
            parse_note=f"Network error: {resp.error}",
            error=resp.error,
            fetched_at=fetched_at,
        )

    # Blocked
    if resp.blocked_by_akamai:
        return FetchResult(
            companies=[],
            reachable=False,
            blocked=True,
            status_code=resp.status_code,
            raw_format="error",
            parse_note=(
                "Saudi Exchange is blocking this environment. "
                f"Reason: {resp.block_reason}. "
                "No official company records imported. "
                "Deploy on a Saudi/GCC server or configure SAUDI_EXCHANGE_PROXY."
            ),
            error=resp.block_reason,
            fetched_at=fetched_at,
        )

    # Non-success HTTP status
    if not resp.ok:
        return FetchResult(
            companies=[],
            reachable=True,
            blocked=False,
            status_code=resp.status_code,
            raw_format="error",
            parse_note=(
                f"Saudi Exchange returned HTTP {resp.status_code}. "
                "No official company records imported. "
                "Endpoint needs verification."
            ),
            error=f"HTTP {resp.status_code}",
            fetched_at=fetched_at,
        )

    # Parse the body
    content_type = resp.headers.get("content-type", "")
    raw_records, raw_format, parse_note = _parse_response(resp.body or b"", content_type)

    companies: list[CompanyRecord] = []
    for raw in raw_records:
        if isinstance(raw, dict):
            record = _parse_company(raw, source_url, now)
            if record:
                companies.append(record)

    if raw_records and not companies:
        parse_note += (
            f" Received {len(raw_records)} raw records but could not extract "
            "symbol/arabic_name from any of them. "
            "Field name mapping needs adjustment — inspect the raw response."
        )

    if companies:
        parse_note = (
            f"Successfully parsed {len(companies)} company records "
            f"from {len(raw_records)} raw entries."
        )

    return FetchResult(
        companies=companies,
        reachable=True,
        blocked=False,
        status_code=resp.status_code,
        raw_format=raw_format,
        parse_note=parse_note,
        error=None,
        fetched_at=fetched_at,
    )


def print_report(result: FetchResult) -> None:
    W = 62
    print("=" * W)
    print("  Saudi Exchange — Companies Fetch Report")
    print("=" * W)
    print(f"  Fetched at     : {result.fetched_at}")
    print(f"  Reachable      : {result.reachable}")
    print(f"  Blocked        : {result.blocked}")
    print(f"  HTTP status    : {result.status_code if result.status_code is not None else 'N/A'}")
    print(f"  Response format: {result.raw_format}")
    print(f"  Companies found: {len(result.companies)}")
    print("-" * W)
    print(f"  Diagnostic:")
    for sentence in result.parse_note.split(". "):
        sentence = sentence.strip()
        if sentence:
            print(f"    {sentence}.")
    if result.companies:
        print("-" * W)
        print("  Sample (first 5):")
        for c in result.companies[:5]:
            print(f"    [{c.symbol}] {c.arabic_name} | {c.english_name or '—'} | {c.market or '—'}")
    print("=" * W)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    result = fetch_companies()
    print_report(result)
    sys.exit(0)  # always exit 0 — empty result is honest, not an error
