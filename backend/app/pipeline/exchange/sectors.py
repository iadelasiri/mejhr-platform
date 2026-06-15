"""
Official TASI sector and market-index fetcher — Saudi Exchange.

Source: Saudi Exchange portal HTML pages embed a JSON array of sector/index
        data for their sidebar widget. We extract this to build the official
        sector and index catalogue.

No clean JSON API exists for company-to-sector mapping on Saudi Exchange.
The HTML JSON blob is the only machine-readable source for sector names/codes.

CLI usage::
    docker compose exec backend python -m app.pipeline.exchange.sectors

Exit codes:
  0 — completed (even if 0 sectors — honest empty is a success)
  1 — unexpected error
"""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

log = logging.getLogger(__name__)

SOURCE_URL = (
    "https://www.saudiexchange.sa"
    "/wps/portal/tadawul/markets/equities/equities-securities/listed-securities"
)
SOURCE_NAME = "saudi_exchange_html_widget"

# Market-wide / size / special indices — stored as MarketIndex, NOT as Sector.
# These represent cross-sector baskets, not individual GICS-style sectors.
_INDEX_CODES: frozenset[str] = frozenset({
    "TASI",    # Tadawul All Share Index (main)
    "MT30",    # MSCI Tadawul 30 Index
    "TLCIC",   # Tadawul Large Cap Index
    "TMCIC",   # Tadawul Medium Cap Index
    "TSCIC",   # Tadawul Small Cap Index
    "TIPOC",   # Tadawul IPO Index
    "TT50CI",  # TASI50 Index
})

# Individual GICS-style sector indices — stored as Sector records.
# Verified from live Saudi Exchange HTML (2026-06-15).
_SECTOR_CODES: frozenset[str] = frozenset({
    "TCPI",  # Commercial & Professional Svc
    "TTNI",  # Transportation
    "TDAI",  # Consumer Durables & Apparel
    "TCSI",  # Consumer Services
    "TMDI",  # Media and Entertainment
    "TRLI",  # Consumer Discretionary Distribution & Retail
    "TFSI",  # Consumer Staples Distribution & Retail
    "TFBI",  # Food & Beverages
    "THEI",  # Health Care Equipment & Svc
    "TPBI",  # Pharma, Biotech & Life Science
    "TBNI",  # Banks
    "TDFI",  # Financial Services
    "TISI",  # Insurance
    "TTSI",  # Telecommunication Services
    "TUTI",  # Utilities
    "TRTI",  # REITs
    "TENI",  # Energy
    "TMTI",  # Materials
    "TCGI",  # Capital Goods
    "TRMI",  # Real Estate Mgmt & Dev't
    "TSSI",  # Software & Services
    "THPI",  # Household & Personal Products Index
})

# Regex to find sector/index JSON blobs embedded in every Saudi Exchange HTML page.
# Pattern: {"symbol":"TBNI","name":"Banks","price":12933.68,...}
# Matches T-prefixed codes (all sectors + most indices) AND MT30 (MSCI index).
_JSON_BLOB_RE = re.compile(
    r'\{"symbol":"([A-Z][A-Z0-9]{2,7})","name":"([^"]+)","price":[\d.]'
)


@dataclass
class SectorRecord:
    """One official TASI sector extracted from Saudi Exchange HTML widget."""
    code: str
    english_name: str
    arabic_name: str | None   # not available from HTML source
    market: str
    source: str
    source_url: str
    imported_at: datetime


@dataclass
class IndexRecord:
    """One official TASI market or size index extracted from Saudi Exchange HTML widget."""
    code: str
    english_name: str
    arabic_name: str | None
    index_type: str            # "main" | "sector" | "size" | "ipo" | "msci" | "other"
    sector_code: str | None    # FK to a SectorRecord.code if sector-specific (None here)
    market: str
    source: str
    source_url: str
    imported_at: datetime


@dataclass
class SectorFetchResult:
    sectors: list[SectorRecord]
    indices: list[IndexRecord]
    reachable: bool
    blocked: bool
    status_code: int | None
    parse_note: str
    error: str | None
    fetched_at: str


def _http_get(url: str):
    """GET via curl_cffi Chrome124 TLS impersonation. Isolated for testability."""
    from curl_cffi import requests as cffi_requests
    return cffi_requests.get(url, impersonate="chrome124", timeout=30)


def _classify_index_type(code: str) -> str:
    if code == "TASI":
        return "main"
    if code == "MT30":
        return "msci"
    if code in ("TLCIC", "TMCIC", "TSCIC"):
        return "size"
    if code == "TIPOC":
        return "ipo"
    return "other"


def fetch_sectors() -> SectorFetchResult:
    """
    Fetch official sector and market-index catalogue from Saudi Exchange HTML.

    Always returns a SectorFetchResult — never raises.
    """
    now = datetime.now(timezone.utc)
    fetched_at = now.isoformat()

    try:
        resp = _http_get(SOURCE_URL)
    except Exception as exc:
        return SectorFetchResult(
            sectors=[], indices=[],
            reachable=False, blocked=False, status_code=None,
            parse_note=f"Network error: {exc}",
            error=str(exc),
            fetched_at=fetched_at,
        )

    if resp.status_code == 403:
        return SectorFetchResult(
            sectors=[], indices=[],
            reachable=False, blocked=True, status_code=403,
            parse_note=(
                "Saudi Exchange blocked this request (HTTP 403 — Akamai bot detection). "
                "No sector data imported."
            ),
            error="HTTP 403 — Akamai block",
            fetched_at=fetched_at,
        )

    if resp.status_code != 200:
        return SectorFetchResult(
            sectors=[], indices=[],
            reachable=True, blocked=False, status_code=resp.status_code,
            parse_note=f"Saudi Exchange returned HTTP {resp.status_code}.",
            error=f"HTTP {resp.status_code}",
            fetched_at=fetched_at,
        )

    html = resp.text
    seen_codes: set[str] = set()
    sectors: list[SectorRecord] = []
    indices: list[IndexRecord] = []

    for match in _JSON_BLOB_RE.finditer(html):
        code = match.group(1)
        name = match.group(2)

        if code in seen_codes:
            continue
        seen_codes.add(code)

        if code in _SECTOR_CODES:
            sectors.append(SectorRecord(
                code=code,
                english_name=name,
                arabic_name=None,
                market="tadawul",
                source=SOURCE_NAME,
                source_url=SOURCE_URL,
                imported_at=now,
            ))
        elif code in _INDEX_CODES:
            indices.append(IndexRecord(
                code=code,
                english_name=name,
                arabic_name=None,
                index_type=_classify_index_type(code),
                sector_code=None,
                market="tadawul",
                source=SOURCE_NAME,
                source_url=SOURCE_URL,
                imported_at=now,
            ))
        # Unknown T-prefixed codes are silently skipped — they may be new additions.

    parse_note = (
        f"Parsed {len(sectors)} sector indices and {len(indices)} market indices "
        f"from Saudi Exchange HTML widget (source: {SOURCE_URL}). "
        f"Total unique T-codes found: {len(seen_codes)}. "
        f"Note: Arabic names not available from this HTML source."
    )

    return SectorFetchResult(
        sectors=sectors,
        indices=indices,
        reachable=True,
        blocked=False,
        status_code=200,
        parse_note=parse_note,
        error=None,
        fetched_at=fetched_at,
    )


def print_report(result: SectorFetchResult) -> None:
    W = 64
    print("=" * W)
    print("  Saudi Exchange — Sectors & Indices Fetch (Phase 2D)")
    print("=" * W)
    print(f"  Source URL    : {SOURCE_URL}")
    print(f"  Fetched at    : {result.fetched_at}")
    print(f"  Reachable     : {result.reachable}")
    print(f"  Blocked       : {result.blocked}")
    print(f"  HTTP status   : {result.status_code or 'N/A'}")
    print(f"  Sectors found : {len(result.sectors)}")
    print(f"  Indices found : {len(result.indices)}")
    print("-" * W)
    for sentence in result.parse_note.split(". "):
        sentence = sentence.strip()
        if sentence:
            print(f"  {sentence}.")
    if result.sectors:
        print("-" * W)
        print("  Sectors:")
        for s in result.sectors:
            print(f"    [{s.code:8s}] {s.english_name}")
    if result.indices:
        print("-" * W)
        print("  Market indices:")
        for idx in result.indices:
            print(f"    [{idx.code:8s}] {idx.english_name} ({idx.index_type})")
    print("=" * W)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    result = fetch_sectors()
    print_report(result)
    sys.exit(0)
