"""
System API — infrastructure diagnostics.

Endpoints:
  GET /api/v1/system/saudi-exchange-health
      Live connectivity probe to Saudi Exchange.
      Optional ?probe_companies=true also probes the companies path.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Query

from app.core.config import settings
from app.pipeline.exchange.connectivity import test_connectivity

log = logging.getLogger(__name__)
router = APIRouter()

# The unmodified default companies path — used to detect whether the operator
# has overridden it with a confirmed GCC-verified path.
_DEFAULT_COMPANIES_PATH = (
    "/wps/portal/saudiexchange/newsandreports/market-data/"
    "trading-data/all-shares"
)


@router.get("/saudi-exchange-health")
async def saudi_exchange_health(
    probe_companies: bool = Query(
        default=False,
        description=(
            "If true, also probe the configured companies endpoint path "
            "and include the result in companies_path_status. "
            "Makes a second HTTP request to Saudi Exchange — slower."
        ),
    ),
):
    """
    Probe connectivity to Saudi Exchange.

    Always returns HTTP 200. A 403 / Akamai block is an infrastructure
    finding, not an application error.

    Fields:
      base_url                    Configured SAUDI_EXCHANGE_BASE_URL
      dns_ok                      DNS resolution succeeded
      reachable                   HTTP request succeeded without block
      status_code                 HTTP status from Saudi Exchange (or null)
      blocked_by_akamai           Akamai / CDN block detected
      block_reason                Why it was flagged as blocked (or null)
      latency_ms                  Round-trip latency in ms (or null)
      headers_summary             Safe subset of response headers
      recommendation              Next action to take
      error                       Error string if request failed (or null)
      companies_path_configured   Value of SAUDI_EXCHANGE_COMPANIES_PATH
      companies_path_is_default   True if path has not been overridden
      companies_path_status       Probe result for companies path (or null)
      checked_at                  ISO-8601 timestamp
    """
    result = await asyncio.to_thread(test_connectivity)

    companies_path_status = None
    if probe_companies:
        from app.pipeline.exchange.endpoint_probe import probe_endpoint
        probe = await asyncio.to_thread(
            probe_endpoint, settings.SAUDI_EXCHANGE_COMPANIES_PATH
        )
        companies_path_status = {
            "path": probe.path,
            "status_code": probe.status_code,
            "content_type": probe.content_type,
            "response_size_bytes": probe.response_size_bytes,
            "latency_ms": probe.latency_ms,
            "blocked_by_akamai": probe.blocked_by_akamai,
            "block_reason": probe.block_reason,
            "json_parseable": probe.json_parseable,
            "record_count": probe.record_count,
            "appears_to_have_companies": probe.appears_to_have_companies,
            "sample_fields": probe.sample_fields[:10],
            "recommendation": probe.recommendation,
            "error": probe.error,
        }

    return {
        "base_url": settings.SAUDI_EXCHANGE_BASE_URL,
        "dns_ok": result.dns_ok,
        "reachable": result.reachable,
        "status_code": result.status_code,
        "blocked_by_akamai": result.blocked_by_akamai,
        "block_reason": result.block_reason,
        "latency_ms": result.latency_ms,
        "headers_summary": result.headers_summary,
        "recommendation": result.recommendation,
        "error": result.error,
        "companies_path_configured": settings.SAUDI_EXCHANGE_COMPANIES_PATH,
        "companies_path_is_default": (
            settings.SAUDI_EXCHANGE_COMPANIES_PATH == _DEFAULT_COMPANIES_PATH
        ),
        "companies_path_status": companies_path_status,
        "checked_at": result.checked_at,
    }
