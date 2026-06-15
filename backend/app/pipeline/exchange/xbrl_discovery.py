"""
XBRL filing discovery — Saudi Exchange announcements API.

For each Main Market company, queries the Saudi Exchange announcement search
endpoint (ci_anncmnt/annWdgtSearch) to find financial statement announcements
that carry XBRL/iXBRL attachments.

Only official Saudi Exchange URLs are used.
No third-party data sources (Argaam, StockAnalysis, yfinance, etc.).
No financial values are parsed here — metadata only.

Source:
  https://www.saudiexchange.sa/wps/pa/ci_anncmnt/annWdgtSearch
  Parameters: companyShortName, lang, pageNumber, pageSize

Filing URL format (observed in Saudi Exchange attachments):
  https://www.saudiexchange.sa/wps/wcm/connect/<UUID>/<filename>.xhtml

CLI usage::
    docker compose exec backend python -m app.pipeline.exchange.xbrl_discovery 1010

Exit codes:
  0 — completed (even if 0 filings found)
  1 — unexpected error
"""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, date, timezone
from typing import Any

log = logging.getLogger(__name__)

# Saudi Exchange announcement search endpoint.
# Returns JSON: {"totalRecord": N, "announcements": [...]}
_ANNOUNCEMENT_SEARCH_URL = (
    "https://www.saudiexchange.sa/wps/pa/ci_anncmnt/annWdgtSearch"
)

# Announcement category IDs that indicate financial statement filings.
# Saudi Exchange uses Arabic category names; we match on any that reference
# quarterly, semi-annual, or annual financial statements.
_FINANCIAL_STATEMENT_KEYWORDS = frozenset({
    "financial statements",
    "financial results",
    "quarterly financial",
    "annual financial",
    "interim financial",
    "نتائج مالية",
    "قوائم مالية",
    "بيانات مالية",
})

# File extensions and MIME-type patterns that identify XBRL/iXBRL files.
_XBRL_EXTENSIONS = frozenset({".xhtml", ".xbrl", ".xml", ".ifrs"})

# Regex to infer period from a filename like FS_Q3_2024.xhtml or Annual_2023.xhtml
_PERIOD_RE = re.compile(
    r"(?P<period>Q[1-4]|H[12]|Annual|Interim|annual|interim|q[1-4]|h[12])",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"(?P<year>20[1-9]\d)")


@dataclass
class DiscoveredFiling:
    """Metadata for one XBRL filing found via the announcements API."""
    symbol: str
    # Direct URL to the XBRL/iXBRL file (maps to XBRLFiling.xbrl_url)
    filing_url: str
    # Announcement page from which this filing was found (maps to XBRLFiling.announcement_url)
    source_url: str
    # Announcement publish date
    announcement_date: date | None
    fiscal_year: int | None
    # Q1 | Q2 | Q3 | Q4 | H1 | H2 | Annual
    fiscal_period: str | None
    # xhtml | xml | xbrl
    filing_type: str
    # en | ar | unknown
    language: str
    # Raw announcement title for logging/debug
    announcement_title: str


@dataclass
class DiscoveryResult:
    """Result of running discovery for one company symbol."""
    symbol: str
    filings: list[DiscoveredFiling]
    reachable: bool
    blocked: bool
    status_code: int | None
    parse_note: str
    error: str | None
    fetched_at: str


def _http_get(url: str, params: dict | None = None):
    """GET via curl_cffi Chrome124 TLS impersonation. Isolated for testability."""
    from curl_cffi import requests as cffi_requests
    return cffi_requests.get(
        url,
        params=params,
        impersonate="chrome124",
        timeout=30,
    )


def _detect_block(status_code: int, text: str) -> bool:
    if status_code == 403:
        return True
    lower = text.lower()
    return any(kw in lower for kw in (
        "access denied", "you have been blocked",
        "enable javascript and cookies", "reference #",
    ))


def _infer_language(filename: str, title: str) -> str:
    """Return 'ar' if the filename or title look Arabic, else 'en'."""
    arabic_re = re.compile(r"[؀-ۿ]")
    if arabic_re.search(title):
        return "ar"
    lower = filename.lower()
    if "_ar" in lower or "arabic" in lower or "عربي" in lower:
        return "ar"
    return "en"


def _infer_period(filename: str, title: str) -> str | None:
    """Extract Q1/Q2/Q3/Q4/H1/H2/Annual from filename or title."""
    for text in (filename, title):
        m = _PERIOD_RE.search(text)
        if m:
            raw = m.group("period").upper()
            return raw if raw in ("Q1", "Q2", "Q3", "Q4", "H1", "H2", "ANNUAL") else raw
    return None


def _infer_year(filename: str, title: str, announce_date: date | None) -> int | None:
    """Extract 4-digit year from filename, title, or fall back to announcement date."""
    for text in (filename, title):
        m = _YEAR_RE.search(text)
        if m:
            return int(m.group("year"))
    if announce_date:
        return announce_date.year
    return None


def _is_xbrl_attachment(name: str, mime: str) -> bool:
    """Return True if an attachment looks like an XBRL/iXBRL file."""
    lower_name = name.lower()
    for ext in _XBRL_EXTENSIONS:
        if lower_name.endswith(ext):
            return True
    if "xbrl" in lower_name or "ixbrl" in lower_name or "ifrs" in lower_name:
        return True
    if "xhtml" in mime or "xbrl" in mime:
        return True
    return False


def _is_financial_announcement(category: str, title: str) -> bool:
    """Return True if this announcement is a financial statement filing."""
    combined = (category + " " + title).lower()
    return any(kw in combined for kw in _FINANCIAL_STATEMENT_KEYWORDS)


def _parse_date(date_str: str | None) -> date | None:
    if not date_str:
        return None
    # Try ISO 8601: "2024-11-12" or "2024-11-12T00:00:00"
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str[:len(fmt)], fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _extract_filings_from_response(
    symbol: str,
    data: Any,
    source_base_url: str,
) -> list[DiscoveredFiling]:
    """
    Parse the announcement API JSON response and return DiscoveredFiling records.

    The Saudi Exchange announcement search API returns payloads in the shape:
      {"totalRecord": N, "announcements": [...]}
    or
      {"hits": {"total": {"value": N}, "hits": [{"_source": {...}}]}}

    We handle both shapes.
    """
    filings: list[DiscoveredFiling] = []

    # Normalise to a flat list of announcement dicts.
    announcements: list[dict] = []

    if isinstance(data, dict):
        # Shape 1: {"totalRecord": N, "announcements": [...]}
        if "announcements" in data and isinstance(data["announcements"], list):
            announcements = data["announcements"]
        # Shape 2: {"hits": {"hits": [{"_source": {...}}]}}
        elif "hits" in data and isinstance(data.get("hits"), dict):
            hits = data["hits"].get("hits", [])
            announcements = [h.get("_source", h) for h in hits if isinstance(h, dict)]
        # Shape 3: direct list
    elif isinstance(data, list):
        announcements = data

    for ann in announcements:
        if not isinstance(ann, dict):
            continue

        category = str(ann.get("categoryName", ann.get("type", "")))
        title = str(ann.get("title", ann.get("titleEn", ann.get("titleAr", ""))))
        date_str = ann.get("announcementDate", ann.get("date", ""))
        ann_date = _parse_date(str(date_str) if date_str else None)

        if not _is_financial_announcement(category, title):
            continue

        # Collect attachments
        attachments = ann.get("attachments", ann.get("documents", []))
        if not isinstance(attachments, list):
            attachments = []

        for att in attachments:
            if not isinstance(att, dict):
                continue
            att_name = str(att.get("attachmentName", att.get("name", att.get("fileName", ""))))
            att_url = str(att.get("attachmentUrl", att.get("url", att.get("fileUrl", ""))))
            att_mime = str(att.get("mimeType", att.get("contentType", "")))

            if not att_url or att_url == "None":
                continue
            if not _is_xbrl_attachment(att_name, att_mime):
                continue

            ext = att_name.rsplit(".", 1)[-1].lower() if "." in att_name else "xhtml"
            lang = _infer_language(att_name, title)
            period = _infer_period(att_name, title)
            year = _infer_year(att_name, title, ann_date)

            # Build announcement page URL from announcement ID if we have it
            ann_id = ann.get("announcementId", ann.get("id", ""))
            source_url = (
                f"https://www.saudiexchange.sa/wps/portal/tadawul/markets/equities/"
                f"equities-securities/equities-security-details/company-announcements?"
                f"companySymbol={symbol}&announcementId={ann_id}"
                if ann_id else source_base_url
            )

            filings.append(DiscoveredFiling(
                symbol=symbol,
                filing_url=att_url,
                source_url=source_url,
                announcement_date=ann_date,
                fiscal_year=year,
                fiscal_period=period,
                filing_type=ext,
                language=lang,
                announcement_title=title,
            ))

    return filings


def discover_filings(symbol: str) -> DiscoveryResult:
    """
    Discover XBRL filings for one company symbol via Saudi Exchange announcements API.

    Always returns a DiscoveryResult — never raises.
    """
    fetched_at = datetime.now(timezone.utc).isoformat()
    page = 1
    page_size = 50
    all_filings: list[DiscoveredFiling] = []

    source_base_url = (
        "https://www.saudiexchange.sa/wps/portal/tadawul/markets/equities/"
        "equities-securities/equities-security-details/company-announcements"
    )

    while True:
        params = {
            "companyShortName": symbol,
            "lang": "en",
            "pageNumber": page,
            "pageSize": page_size,
        }
        try:
            resp = _http_get(_ANNOUNCEMENT_SEARCH_URL, params=params)
        except Exception as exc:
            return DiscoveryResult(
                symbol=symbol, filings=[],
                reachable=False, blocked=False, status_code=None,
                parse_note=f"Network error: {exc}",
                error=str(exc),
                fetched_at=fetched_at,
            )

        if resp.status_code == 403 or _detect_block(resp.status_code, getattr(resp, "text", "")):
            return DiscoveryResult(
                symbol=symbol, filings=[],
                reachable=False, blocked=True, status_code=resp.status_code,
                parse_note=(
                    f"Saudi Exchange blocked request for {symbol} "
                    f"(HTTP {resp.status_code} — Akamai/geo block)."
                ),
                error=f"HTTP {resp.status_code} — blocked",
                fetched_at=fetched_at,
            )

        if resp.status_code != 200:
            return DiscoveryResult(
                symbol=symbol, filings=[],
                reachable=True, blocked=False, status_code=resp.status_code,
                parse_note=f"Saudi Exchange returned HTTP {resp.status_code} for {symbol}.",
                error=f"HTTP {resp.status_code}",
                fetched_at=fetched_at,
            )

        try:
            data = resp.json()
        except Exception as exc:
            return DiscoveryResult(
                symbol=symbol, filings=[],
                reachable=True, blocked=False, status_code=resp.status_code,
                parse_note=f"Response for {symbol} was not valid JSON: {exc}",
                error=f"JSON parse error: {exc}",
                fetched_at=fetched_at,
            )

        batch = _extract_filings_from_response(symbol, data, source_base_url)
        all_filings.extend(batch)

        # Check if there are more pages
        total = 0
        if isinstance(data, dict):
            total = int(data.get("totalRecord", data.get("totalRecords", 0)) or 0)

        if len(all_filings) >= total or len(batch) < page_size or page >= 20:
            break
        page += 1

    parse_note = (
        f"Scanned announcements for {symbol}: "
        f"found {len(all_filings)} XBRL filing attachment(s)."
    )

    return DiscoveryResult(
        symbol=symbol,
        filings=all_filings,
        reachable=True,
        blocked=False,
        status_code=200,
        parse_note=parse_note,
        error=None,
        fetched_at=fetched_at,
    )


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    symbol = sys.argv[1] if len(sys.argv) > 1 else "1010"
    result = discover_filings(symbol)

    print(f"Symbol      : {result.symbol}")
    print(f"Reachable   : {result.reachable}")
    print(f"Blocked     : {result.blocked}")
    print(f"HTTP status : {result.status_code}")
    print(f"Filings     : {len(result.filings)}")
    print(f"Note        : {result.parse_note}")
    if result.error:
        print(f"Error       : {result.error}")
    for f in result.filings[:5]:
        print(f"  [{f.fiscal_year} {f.fiscal_period}] {f.language} {f.filing_type} → {f.filing_url[:80]}")

    sys.exit(0 if result.reachable else 1)
