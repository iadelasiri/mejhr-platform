"""
Saudi Exchange endpoint probe — safe candidate verification tool.

Purpose:
  When deployed on a GCC/Saudi server (where Saudi Exchange is reachable),
  this tool tests a small set of manually-configured candidate endpoint paths
  to find which one returns structured company data (JSON).

Rules:
  - Only tests paths explicitly listed in config or the default companies path.
  - One polite request per path. No brute force. No crawling. No retries here.
  - If the server is unreachable or blocked, reports that honestly.
  - Never bypasses login, CAPTCHA, paywall, or access controls.
  - Reports status code, content type, response size, JSON parse result,
    and whether the response looks like it contains company records.

CLI usage::

    docker compose exec backend python -m app.pipeline.exchange.endpoint_probe

Exit codes:
  0 — at least one candidate returned a parseable JSON company list
  1 — no candidate returned usable data (blocked, HTML, empty, etc.)
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.pipeline.exchange.client import SaudiExchangeClient

log = logging.getLogger(__name__)

# Field names that suggest a company record — used for heuristic detection.
_COMPANY_FIELD_HINTS = frozenset(
    ["symbol", "stockSymbol", "tickerSymbol", "nameAr", "arabicName",
     "companyNameAr", "nameEn", "englishName", "tasi", "code"]
)


@dataclass
class ProbeResult:
    """Result of probing one candidate endpoint path."""
    path: str
    full_url: str
    status_code: int | None
    content_type: str
    response_size_bytes: int | None
    latency_ms: float | None
    blocked_by_akamai: bool
    block_reason: str | None
    json_parseable: bool
    record_count: int          # number of items in the top-level list (or 0)
    appears_to_have_companies: bool
    top_level_keys: list[str]  # first 10 keys if JSON object
    sample_fields: list[str]   # field names from first record if list of objects
    recommendation: str
    error: str | None
    probed_at: str


def _detect_companies(parsed: Any) -> tuple[int, list[str], bool]:
    """
    Return (record_count, sample_fields, appears_to_have_companies).
    Handles top-level list or wrapped envelope (data/companies/stocks/items/...).
    """
    records: list[Any] = []

    if isinstance(parsed, list):
        records = parsed
    elif isinstance(parsed, dict):
        for key in ("data", "companies", "stocks", "items", "result",
                    "results", "companyList", "stockList"):
            if key in parsed and isinstance(parsed[key], list):
                records = parsed[key]
                break

    if not records:
        return 0, [], False

    first = records[0] if records else {}
    if not isinstance(first, dict):
        return len(records), [], False

    sample_fields = list(first.keys())[:15]
    has_companies = bool(_COMPANY_FIELD_HINTS & set(sample_fields))
    return len(records), sample_fields, has_companies


def probe_endpoint(path: str) -> ProbeResult:
    """
    Probe a single candidate path. Always returns a ProbeResult — never raises.
    """
    probed_at = datetime.now(timezone.utc).isoformat()
    full_url = settings.SAUDI_EXCHANGE_BASE_URL.rstrip("/") + path

    with SaudiExchangeClient() as client:
        # Use retry_attempts=1 here — this is a probe, not production import.
        resp = client.get(path)

    if resp.status_code is None:
        return ProbeResult(
            path=path,
            full_url=full_url,
            status_code=None,
            content_type="",
            response_size_bytes=None,
            latency_ms=resp.latency_ms,
            blocked_by_akamai=False,
            block_reason=None,
            json_parseable=False,
            record_count=0,
            appears_to_have_companies=False,
            top_level_keys=[],
            sample_fields=[],
            recommendation=(
                f"Network error reaching {full_url}: {resp.error}. "
                "Deploy on a Saudi/GCC server or configure SAUDI_EXCHANGE_PROXY."
            ),
            error=resp.error,
            probed_at=probed_at,
        )

    content_type = resp.headers.get("content-type", "")
    size = len(resp.body) if resp.body else 0

    if resp.blocked_by_akamai:
        return ProbeResult(
            path=path,
            full_url=full_url,
            status_code=resp.status_code,
            content_type=content_type,
            response_size_bytes=size,
            latency_ms=resp.latency_ms,
            blocked_by_akamai=True,
            block_reason=resp.block_reason,
            json_parseable=False,
            record_count=0,
            appears_to_have_companies=False,
            top_level_keys=[],
            sample_fields=[],
            recommendation=(
                f"Blocked at {full_url} (reason: {resp.block_reason}). "
                "Deploy on a Saudi/GCC server or use SAUDI_EXCHANGE_PROXY."
            ),
            error=resp.block_reason,
            probed_at=probed_at,
        )

    if not resp.ok:
        return ProbeResult(
            path=path,
            full_url=full_url,
            status_code=resp.status_code,
            content_type=content_type,
            response_size_bytes=size,
            latency_ms=resp.latency_ms,
            blocked_by_akamai=False,
            block_reason=None,
            json_parseable=False,
            record_count=0,
            appears_to_have_companies=False,
            top_level_keys=[],
            sample_fields=[],
            recommendation=(
                f"HTTP {resp.status_code} at {full_url}. "
                "Path may be wrong or require authentication. "
                "Inspect browser DevTools Network tab on the Saudi Exchange website "
                "to find the correct JSON API path."
            ),
            error=f"HTTP {resp.status_code}",
            probed_at=probed_at,
        )

    # Try to parse JSON
    body = resp.body or b""
    json_parseable = False
    record_count = 0
    appears_to_have_companies = False
    top_level_keys: list[str] = []
    sample_fields: list[str] = []

    try:
        import json as _json
        parsed = _json.loads(body)
        json_parseable = True

        if isinstance(parsed, dict):
            top_level_keys = list(parsed.keys())[:10]
        record_count, sample_fields, appears_to_have_companies = _detect_companies(parsed)
    except Exception:
        pass

    # Build recommendation
    if not json_parseable:
        if "html" in content_type:
            recommendation = (
                f"{full_url} returned HTML (portal page, not a JSON API). "
                "Open the Saudi Exchange website in a browser, go to the "
                "All Shares / Listed Companies section, and use DevTools → "
                "Network → XHR to find the JSON endpoint that loads company data. "
                "Set SAUDI_EXCHANGE_COMPANIES_PATH to that path."
            )
        else:
            recommendation = (
                f"{full_url} returned non-JSON content ({content_type!r}, "
                f"{size} bytes). Not a usable JSON API endpoint."
            )
    elif not record_count:
        recommendation = (
            f"{full_url} returned valid JSON but with 0 records "
            f"(top-level keys: {top_level_keys}). "
            "The endpoint may be correct but empty, or the response envelope "
            "structure is not recognised. Inspect raw response and adjust "
            "the parser in companies.py."
        )
    elif not appears_to_have_companies:
        recommendation = (
            f"{full_url} returned {record_count} JSON records, "
            f"but field names do not look like companies "
            f"(sample fields: {sample_fields[:5]}). "
            "Endpoint may need field name mapping adjustment."
        )
    else:
        recommendation = (
            f"CONFIRMED: {full_url} returned {record_count} records "
            f"with company field names ({sample_fields[:5]}). "
            "Set SAUDI_EXCHANGE_COMPANIES_PATH to this path and run "
            "python -m app.pipeline.exchange.companies to import."
        )

    return ProbeResult(
        path=path,
        full_url=full_url,
        status_code=resp.status_code,
        content_type=content_type,
        response_size_bytes=size,
        latency_ms=resp.latency_ms,
        blocked_by_akamai=False,
        block_reason=None,
        json_parseable=json_parseable,
        record_count=record_count,
        appears_to_have_companies=appears_to_have_companies,
        top_level_keys=top_level_keys,
        sample_fields=sample_fields,
        recommendation=recommendation,
        error=None,
        probed_at=probed_at,
    )


def build_candidate_list() -> list[str]:
    """
    Build the deduplicated list of paths to probe.

    Always includes SAUDI_EXCHANGE_COMPANIES_PATH first.
    Additional candidates come from SAUDI_EXCHANGE_ENDPOINT_CANDIDATES.
    """
    seen: set[str] = set()
    candidates: list[str] = []

    for path in [settings.SAUDI_EXCHANGE_COMPANIES_PATH] + list(
        settings.SAUDI_EXCHANGE_ENDPOINT_CANDIDATES
    ):
        if path and path not in seen:
            seen.add(path)
            candidates.append(path)

    return candidates


def probe_all_candidates() -> list[ProbeResult]:
    """Probe every candidate path and return all results."""
    candidates = build_candidate_list()
    results: list[ProbeResult] = []
    for path in candidates:
        log.info("Probing candidate: %s", path)
        results.append(probe_endpoint(path))
    return results


def print_report(results: list[ProbeResult]) -> None:
    W = 70
    print("=" * W)
    print("  Saudi Exchange — Endpoint Probe Report")
    print("=" * W)
    print(f"  Base URL : {settings.SAUDI_EXCHANGE_BASE_URL}")
    print(f"  Probed   : {len(results)} candidate(s)")
    print()

    for i, r in enumerate(results, 1):
        print(f"  [{i}] {r.path}")
        print(f"      URL          : {r.full_url}")
        print(f"      Status       : {r.status_code if r.status_code is not None else 'N/A'}")
        if r.latency_ms is not None:
            print(f"      Latency      : {r.latency_ms:.0f} ms")
        print(f"      Content-Type : {r.content_type or 'N/A'}")
        if r.response_size_bytes is not None:
            print(f"      Size         : {r.response_size_bytes:,} bytes")
        print(f"      Blocked      : {r.blocked_by_akamai}")
        print(f"      JSON OK      : {r.json_parseable}")
        print(f"      Records      : {r.record_count}")
        print(f"      Has companies: {r.appears_to_have_companies}")
        if r.sample_fields:
            print(f"      Sample fields: {r.sample_fields[:6]}")
        if r.error:
            print(f"      Error        : {r.error}")
        print(f"      Verdict:")
        # Wrap recommendation
        words = r.recommendation.split()
        line = "        "
        for word in words:
            if len(line) + len(word) + 1 > W - 2:
                print(line)
                line = "        " + word + " "
            else:
                line += word + " "
        if line.strip():
            print(line)
        print()

    confirmed = [r for r in results if r.appears_to_have_companies]
    print("-" * W)
    if confirmed:
        print(f"  RESULT: {len(confirmed)} confirmed endpoint(s) with company data.")
        for r in confirmed:
            print(f"    Set SAUDI_EXCHANGE_COMPANIES_PATH={r.path}")
    else:
        print("  RESULT: No confirmed endpoint found.")
        if any(r.blocked_by_akamai for r in results):
            print("  NOTE: Blocked by Akamai. Deploy on Saudi/GCC server first.")
        else:
            print("  NOTE: Add candidate paths via SAUDI_EXCHANGE_ENDPOINT_CANDIDATES")
            print("        after inspecting browser DevTools on saudiexchange.sa.")
    print("=" * W)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    results = probe_all_candidates()
    print_report(results)
    confirmed = any(r.appears_to_have_companies for r in results)
    sys.exit(0 if confirmed else 1)
