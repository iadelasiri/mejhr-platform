"""
Phase 2A tests — Saudi Exchange connectivity and companies fetcher.

All tests are offline: httpx and socket calls are mocked so the test suite
runs without a real network connection to Saudi Exchange.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


# ---------------------------------------------------------------------------
# Helpers — build fake httpx.Response objects
# ---------------------------------------------------------------------------

def _make_httpx_response(
    status_code: int,
    body: bytes = b"",
    headers: dict | None = None,
) -> httpx.Response:
    h = httpx.Headers(headers or {})
    # httpx.Response requires a stream; we use ByteStream directly.
    return httpx.Response(
        status_code=status_code,
        headers=h,
        content=body,
    )


# ---------------------------------------------------------------------------
# 1. SaudiExchangeClient — HTTP 200 (reachable)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_client_200_ok():
    """Client returns ok=True and no block when the server responds 200."""
    from app.pipeline.exchange.client import SaudiExchangeClient

    fake_response = _make_httpx_response(200, b"<html>OK</html>",
                                         {"content-type": "text/html"})

    with patch("httpx.Client.get", return_value=fake_response):
        client = SaudiExchangeClient()
        result = client.get("/")
        client.close()

    assert result.ok is True
    assert result.status_code == 200
    assert result.blocked_by_akamai is False
    assert result.error is None


# ---------------------------------------------------------------------------
# 2. SaudiExchangeClient — HTTP 403 reported as blocked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_client_403_reported_as_blocked():
    """Client treats HTTP 403 as blocked_by_akamai=True, ok=False."""
    from app.pipeline.exchange.client import SaudiExchangeClient

    body = b"<html>Access Denied - Reference #123</html>"
    fake_response = _make_httpx_response(
        403, body,
        {"content-type": "text/html", "server": "AkamaiGHost"},
    )

    with patch("httpx.Client.get", return_value=fake_response):
        client = SaudiExchangeClient()
        result = client.get("/")
        client.close()

    assert result.ok is False
    assert result.status_code == 403
    assert result.blocked_by_akamai is True
    assert result.block_reason is not None


# ---------------------------------------------------------------------------
# 3. SaudiExchangeClient — Akamai header without 403 still flagged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_client_akamai_header_flagged():
    """Akamai-specific response header triggers blocked_by_akamai=True."""
    from app.pipeline.exchange.client import SaudiExchangeClient

    fake_response = _make_httpx_response(
        200, b"content",
        {"content-type": "text/html", "x-check-cacheable": "YES"},
    )

    with patch("httpx.Client.get", return_value=fake_response):
        client = SaudiExchangeClient()
        result = client.get("/")
        client.close()

    assert result.blocked_by_akamai is True


# ---------------------------------------------------------------------------
# 4. SaudiExchangeClient — network timeout returns ok=False with error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_client_timeout_returns_error():
    """Timeout exception is caught and returned as ok=False."""
    from app.pipeline.exchange.client import SaudiExchangeClient

    with patch("httpx.Client.get", side_effect=httpx.TimeoutException("timeout")):
        with patch("time.sleep"):  # don't actually sleep in tests
            client = SaudiExchangeClient()
            result = client.get("/")
            client.close()

    assert result.ok is False
    assert result.status_code is None
    assert "Timeout" in (result.error or "")


# ---------------------------------------------------------------------------
# 5. ConnectivityResult shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_connectivity_result_shape_when_reachable():
    """test_connectivity() returns a result with all expected fields."""
    from app.pipeline.exchange.connectivity import test_connectivity, ConnectivityResult

    fake_response = _make_httpx_response(200, b"<html/>",
                                         {"content-type": "text/html"})

    with patch("app.pipeline.exchange.connectivity._resolve_dns", return_value=True):
        with patch("httpx.Client.get", return_value=fake_response):
            result = test_connectivity()

    assert isinstance(result, ConnectivityResult)
    assert result.dns_ok is True
    assert result.reachable is True
    assert result.blocked_by_akamai is False
    assert isinstance(result.headers_summary, dict)
    assert isinstance(result.recommendation, str)
    assert len(result.recommendation) > 10
    assert result.checked_at  # non-empty ISO timestamp


@pytest.mark.asyncio
async def test_connectivity_result_shape_when_blocked():
    """Blocked result still has all fields; reachable=False, blocked=True."""
    from app.pipeline.exchange.connectivity import test_connectivity, ConnectivityResult

    fake_response = _make_httpx_response(
        403, b"Access Denied",
        {"server": "AkamaiGHost", "content-type": "text/html"},
    )

    with patch("app.pipeline.exchange.connectivity._resolve_dns", return_value=True):
        with patch("httpx.Client.get", return_value=fake_response):
            result = test_connectivity()

    assert isinstance(result, ConnectivityResult)
    assert result.dns_ok is True
    assert result.reachable is False
    assert result.blocked_by_akamai is True
    assert "block" in result.recommendation.lower() or "saudi" in result.recommendation.lower()


@pytest.mark.asyncio
async def test_connectivity_result_shape_when_dns_fails():
    """DNS failure yields a valid result with dns_ok=False, reachable=False."""
    from app.pipeline.exchange.connectivity import test_connectivity

    with patch("app.pipeline.exchange.connectivity._resolve_dns", return_value=False):
        result = test_connectivity()

    assert result.dns_ok is False
    assert result.reachable is False
    assert result.status_code is None


# ---------------------------------------------------------------------------
# 6. Companies fetcher — honest empty result when blocked
# ---------------------------------------------------------------------------

class _MockCurlResp:
    """Minimal curl_cffi response stand-in for companies fetcher tests."""
    def __init__(self, status_code: int, content_type: str, body: bytes):
        self.status_code = status_code
        self.headers = {"content-type": content_type}
        self._body = body

    def json(self):
        import json as _json
        return _json.loads(self._body)


@pytest.mark.asyncio
async def test_companies_fetcher_blocked_returns_empty():
    """HTTP 403 from ThemeSearchUtilityServlet is treated as Akamai block."""
    from app.pipeline.exchange.companies import fetch_companies

    mock_resp = _MockCurlResp(403, "text/html", b"Access Denied")

    with patch("app.pipeline.exchange.companies._http_get", return_value=mock_resp):
        result = fetch_companies()

    assert result.companies == []
    assert result.blocked is True
    assert result.reachable is False
    assert result.status_code == 403
    assert result.parse_note
    assert "block" in result.parse_note.lower()


@pytest.mark.asyncio
async def test_companies_fetcher_html_response_returns_empty():
    """HTML response (servlet URL changed) returns empty with diagnostic."""
    from app.pipeline.exchange.companies import fetch_companies

    mock_resp = _MockCurlResp(200, "text/html; charset=utf-8", b"<html><body>Portal</body></html>")

    with patch("app.pipeline.exchange.companies._http_get", return_value=mock_resp):
        result = fetch_companies()

    assert result.companies == []
    assert result.blocked is False
    assert result.reachable is True
    assert result.raw_format == "html"
    assert "json" in result.parse_note.lower() or "HTML" in result.parse_note


@pytest.mark.asyncio
async def test_companies_fetcher_json_response_parsed():
    """Valid ThemeSearchUtilityServlet JSON is parsed into CompanyRecords."""
    from app.pipeline.exchange.companies import fetch_companies

    payload = json.dumps([
        {
            "symbol": "1010", "companyNameAR": "شركة الراجحي",
            "companyNameEN": "Al Rajhi Bank", "market_type": "M",
            "tradingNameEn": "AL RAJHI BANK", "tradingNameAr": "الراجحي",
            "isin": "SA0007879097",
        },
        {
            "symbol": "2222", "companyNameAR": "أرامكو السعودية",
            "companyNameEN": "Saudi Aramco", "market_type": "M",
            "tradingNameEn": "SAUDI ARAMCO", "tradingNameAr": "أرامكو",
            "isin": "SA12I810E153",
        },
    ]).encode()

    mock_resp = _MockCurlResp(200, "application/json", payload)

    with patch("app.pipeline.exchange.companies._http_get", return_value=mock_resp):
        result = fetch_companies()

    assert result.reachable is True
    assert result.blocked is False
    assert len(result.companies) == 2
    symbols = {c.symbol for c in result.companies}
    assert "1010" in symbols
    assert "2222" in symbols
    for c in result.companies:
        assert c.data_status == "official"
        assert c.mapping_status == "pending_official_mapping"


@pytest.mark.asyncio
async def test_companies_fetcher_network_error_returns_empty():
    """Network exception from _http_get returns empty list with error, never raises."""
    from app.pipeline.exchange.companies import fetch_companies

    with patch("app.pipeline.exchange.companies._http_get",
               side_effect=Exception("Connection refused")):
        result = fetch_companies()

    assert result.companies == []
    assert result.reachable is False
    assert result.error is not None


# ---------------------------------------------------------------------------
# 7. /api/v1/system/saudi-exchange-health — valid JSON shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_saudi_exchange_health_endpoint_shape():
    """
    GET /api/v1/system/saudi-exchange-health returns 200 with all expected fields.
    The connectivity probe itself is mocked so no real network call is made.
    """
    from app.pipeline.exchange.connectivity import ConnectivityResult

    mock_result = ConnectivityResult(
        dns_ok=True,
        reachable=False,
        status_code=403,
        latency_ms=120.5,
        blocked_by_akamai=True,
        block_reason="HTTP 403 — geo/bot/IP block",
        headers_summary={"server": "AkamaiGHost"},
        error=None,
        recommendation="Deploy on a Saudi/GCC server.",
        checked_at="2026-06-14T12:00:00+00:00",
    )

    with patch(
        "app.api.v1.system.test_connectivity",
        return_value=mock_result,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/system/saudi-exchange-health")

    assert response.status_code == 200
    data = response.json()

    required_keys = {
        "reachable", "status_code", "blocked_by_akamai", "block_reason",
        "dns_ok", "latency_ms", "headers_summary", "recommendation",
        "error", "checked_at",
    }
    assert required_keys.issubset(data.keys()), (
        f"Missing keys: {required_keys - data.keys()}"
    )
    assert data["reachable"] is False
    assert data["blocked_by_akamai"] is True
    assert data["dns_ok"] is True
    assert data["status_code"] == 403
    assert data["latency_ms"] == 120.5
    assert isinstance(data["headers_summary"], dict)
    assert isinstance(data["recommendation"], str)


# ---------------------------------------------------------------------------
# 8. /api/v1/companies/ — returns empty list without sample data
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_companies_api_empty_without_data():
    """
    GET /api/v1/companies/ returns a valid paginated response with empty data
    when no companies are in the database.

    Uses FastAPI dependency_overrides to inject a mock DB session so the
    test never touches a real database.
    """
    from app.core.database import get_db

    count_result = MagicMock()
    count_result.scalar.return_value = 0

    data_result = MagicMock()
    data_result.scalars.return_value.all.return_value = []

    # Third execute: latest fetch_companies import job (none exists yet)
    no_job_result = MagicMock()
    no_job_result.scalar_one_or_none.return_value = None

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=[count_result, data_result, no_job_result])
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/companies/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)
    assert "meta" in data
    assert "pipeline_status" in data["meta"]
