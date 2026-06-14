"""
Saudi Exchange connectivity test.

Checks DNS resolution, HTTPS reachability, and Akamai/block detection
against the configured SAUDI_EXCHANGE_BASE_URL.

CLI usage (inside Docker)::

    docker compose exec backend python -m app.pipeline.exchange.connectivity

Exit codes:
  0 — reachable
  1 — not reachable (blocked, DNS failure, or network error)
"""

from __future__ import annotations

import socket
import sys
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

from app.core.config import settings
from app.pipeline.exchange.client import SaudiExchangeClient

log = logging.getLogger(__name__)

# Safe path for the reachability probe — just the homepage.
_TEST_PATH = "/"

# Headers whose values we surface in the report (no PII / session tokens).
_SAFE_HEADERS = frozenset([
    "server", "content-type", "x-cache", "cf-ray",
    "x-akamai-transformed", "akamai-cache-status", "x-check-cacheable",
    "akamai-origin-hop", "x-akamai-request-id",
])


@dataclass
class ConnectivityResult:
    dns_ok: bool
    reachable: bool
    status_code: int | None
    latency_ms: float | None
    blocked_by_akamai: bool
    block_reason: str | None
    headers_summary: dict[str, str]
    error: str | None
    recommendation: str
    checked_at: str


def _resolve_dns(hostname: str) -> bool:
    try:
        socket.getaddrinfo(hostname, 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
        return True
    except socket.gaierror as exc:
        log.warning("DNS resolution failed for %s: %s", hostname, exc)
        return False


def test_connectivity() -> ConnectivityResult:
    """Run the full connectivity check and return a structured result."""
    checked_at = datetime.now(timezone.utc).isoformat()
    parsed = urlparse(settings.SAUDI_EXCHANGE_BASE_URL)
    hostname = parsed.hostname or "www.saudiexchange.sa"

    # Step 1: DNS
    dns_ok = _resolve_dns(hostname)
    if not dns_ok:
        return ConnectivityResult(
            dns_ok=False,
            reachable=False,
            status_code=None,
            latency_ms=None,
            blocked_by_akamai=False,
            block_reason=None,
            headers_summary={},
            error=f"DNS resolution failed for {hostname}",
            recommendation=(
                "DNS resolution failed. The environment cannot reach "
                f"{hostname}. Check network access, DNS settings, or firewall rules. "
                "If this server is outside Saudi Arabia or GCC, the domain may be "
                "unreachable without a regional endpoint or proxy."
            ),
            checked_at=checked_at,
        )

    # Step 2: HTTPS + block detection
    with SaudiExchangeClient() as client:
        result = client.get(_TEST_PATH)

    headers_summary = {
        k: v for k, v in result.headers.items() if k in _SAFE_HEADERS
    }

    # Build recommendation
    if result.blocked_by_akamai:
        recommendation = (
            "Saudi Exchange is blocking this environment. "
            f"Reason: {result.block_reason}. "
            "Akamai geo/bot protection is active. "
            "To import official data, deploy on a server in Saudi Arabia or GCC, "
            "or request official API access from Saudi Exchange. "
            "Setting SAUDI_EXCHANGE_PROXY to a Saudi/GCC proxy may also work."
        )
    elif not result.ok and result.status_code is not None:
        recommendation = (
            f"Saudi Exchange returned HTTP {result.status_code}. "
            "This may be a temporary server issue. Retry later or inspect the URL. "
            f"Configured base URL: {settings.SAUDI_EXCHANGE_BASE_URL}"
        )
    elif not result.ok:
        recommendation = (
            f"Could not connect to Saudi Exchange: {result.error}. "
            "Check network access, firewall rules, and proxy configuration "
            f"(SAUDI_EXCHANGE_PROXY). Configured URL: {settings.SAUDI_EXCHANGE_BASE_URL}"
        )
    else:
        recommendation = (
            "Saudi Exchange is reachable from this environment. "
            "Run the companies fetcher next: "
            "docker compose exec backend python -m app.pipeline.exchange.companies"
        )

    return ConnectivityResult(
        dns_ok=dns_ok,
        reachable=result.ok,
        status_code=result.status_code,
        latency_ms=result.latency_ms,
        blocked_by_akamai=result.blocked_by_akamai,
        block_reason=result.block_reason,
        headers_summary=headers_summary,
        error=result.error,
        recommendation=recommendation,
        checked_at=checked_at,
    )


def print_report(result: ConnectivityResult) -> None:
    """Print a human-readable connectivity report to stdout."""
    W = 62
    print("=" * W)
    print("  Saudi Exchange — Connectivity Report")
    print("=" * W)
    print(f"  Checked at       : {result.checked_at}")
    print(f"  Base URL         : {settings.SAUDI_EXCHANGE_BASE_URL}")
    print(f"  DNS OK           : {result.dns_ok}")
    print(f"  Reachable        : {result.reachable}")
    print(f"  HTTP status      : {result.status_code if result.status_code is not None else 'N/A'}")
    print(f"  Latency          : {f'{result.latency_ms:.0f} ms' if result.latency_ms else 'N/A'}")
    print(f"  Blocked (Akamai) : {result.blocked_by_akamai}")
    if result.block_reason:
        print(f"  Block reason     : {result.block_reason}")
    if result.error:
        print(f"  Error            : {result.error}")
    if result.headers_summary:
        print("  Response headers (safe subset):")
        for k, v in result.headers_summary.items():
            print(f"    {k}: {v}")
    print("-" * W)
    print("  Recommendation:")
    # Wrap long recommendation text
    words = result.recommendation.split()
    line = "    "
    for word in words:
        if len(line) + len(word) + 1 > W - 2:
            print(line)
            line = "    " + word + " "
        else:
            line += word + " "
    if line.strip():
        print(line)
    print("=" * W)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    result = test_connectivity()
    print_report(result)
    sys.exit(0 if result.reachable else 1)
