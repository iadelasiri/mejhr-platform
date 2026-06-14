"""
Phase 2B tests — deployment readiness, endpoint probe, production guards.

All tests are offline: HTTP and socket calls are mocked.
No real network requests are made.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_httpx_response(
    status_code: int,
    body: bytes = b"",
    headers: dict | None = None,
) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        headers=httpx.Headers(headers or {}),
        content=body,
    )


# ---------------------------------------------------------------------------
# 1. Production sample data guard — APP_ENV=production + ENABLE_SAMPLE_DATA=true
#    must raise ValidationError at settings construction.
# ---------------------------------------------------------------------------

def test_production_sample_data_guard_raises():
    """
    Settings raises ValueError if APP_ENV=production and ENABLE_SAMPLE_DATA=true.
    This prevents the app from starting with sample data in production.
    """
    from pydantic import ValidationError
    from app.core.config import Settings

    with pytest.raises((ValidationError, ValueError)):
        Settings(
            APP_ENV="production",
            ENABLE_SAMPLE_DATA=True,
            DATABASE_URL="postgresql+asyncpg://u:p@db:5432/mejhr",
            DATABASE_URL_SYNC="postgresql://u:p@db:5432/mejhr",
            SECRET_KEY="a" * 32,
        )


def test_production_sample_data_guard_passes_when_disabled():
    """
    Settings succeeds when APP_ENV=production and ENABLE_SAMPLE_DATA=false.
    """
    from app.core.config import Settings

    s = Settings(
        APP_ENV="production",
        ENABLE_SAMPLE_DATA=False,
        DATABASE_URL="postgresql+asyncpg://u:p@db:5432/mejhr",
        DATABASE_URL_SYNC="postgresql://u:p@db:5432/mejhr",
        SECRET_KEY="a" * 32,
    )
    assert s.APP_ENV == "production"
    assert s.ENABLE_SAMPLE_DATA is False


def test_development_sample_data_allowed():
    """
    ENABLE_SAMPLE_DATA=true is allowed in APP_ENV=development (the default).
    """
    from app.core.config import Settings

    s = Settings(
        APP_ENV="development",
        ENABLE_SAMPLE_DATA=True,
        DATABASE_URL="postgresql+asyncpg://u:p@db:5432/mejhr",
        DATABASE_URL_SYNC="postgresql://u:p@db:5432/mejhr",
        SECRET_KEY="a" * 32,
    )
    assert s.ENABLE_SAMPLE_DATA is True


# ---------------------------------------------------------------------------
# 2. Endpoint probe — response shapes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_endpoint_probe_blocked_returns_result():
    """Probe returns a valid ProbeResult when Saudi Exchange is blocked."""
    from app.pipeline.exchange.endpoint_probe import probe_endpoint, ProbeResult

    fake_response = _make_httpx_response(
        403, b"Access Denied",
        {"server": "AkamaiGHost", "content-type": "text/html"},
    )

    with patch("httpx.Client.get", return_value=fake_response):
        result = probe_endpoint("/some/path")

    assert isinstance(result, ProbeResult)
    assert result.blocked_by_akamai is True
    assert result.json_parseable is False
    assert result.record_count == 0
    assert result.appears_to_have_companies is False
    assert "block" in result.recommendation.lower() or "Block" in result.recommendation


@pytest.mark.asyncio
async def test_endpoint_probe_html_returns_result():
    """Probe returns honest result when the endpoint returns HTML (portal page)."""
    from app.pipeline.exchange.endpoint_probe import probe_endpoint

    fake_response = _make_httpx_response(
        200, b"<html><body>Portal page</body></html>",
        {"content-type": "text/html; charset=utf-8"},
    )

    with patch("httpx.Client.get", return_value=fake_response):
        result = probe_endpoint("/some/path")

    assert result.status_code == 200
    assert result.blocked_by_akamai is False
    assert result.json_parseable is False
    assert "html" in result.recommendation.lower() or "HTML" in result.recommendation


@pytest.mark.asyncio
async def test_endpoint_probe_json_no_companies():
    """Probe returns result when JSON has no recognisable company fields."""
    from app.pipeline.exchange.endpoint_probe import probe_endpoint

    payload = json.dumps({"status": "ok", "count": 0, "records": []}).encode()
    fake_response = _make_httpx_response(
        200, payload,
        {"content-type": "application/json"},
    )

    with patch("httpx.Client.get", return_value=fake_response):
        result = probe_endpoint("/some/path")

    assert result.json_parseable is True
    assert result.record_count == 0
    assert result.appears_to_have_companies is False


@pytest.mark.asyncio
async def test_endpoint_probe_json_with_companies():
    """Probe detects company records when response contains known field names."""
    from app.pipeline.exchange.endpoint_probe import probe_endpoint

    payload = json.dumps({
        "data": [
            {"symbol": "1010", "nameAr": "الراجحي", "nameEn": "Al Rajhi", "market": "A"},
            {"symbol": "2222", "nameAr": "أرامكو", "nameEn": "Saudi Aramco", "market": "A"},
        ]
    }).encode()
    fake_response = _make_httpx_response(
        200, payload,
        {"content-type": "application/json"},
    )

    with patch("httpx.Client.get", return_value=fake_response):
        result = probe_endpoint("/api/companies")

    assert result.json_parseable is True
    assert result.record_count == 2
    assert result.appears_to_have_companies is True
    assert "CONFIRMED" in result.recommendation or "confirmed" in result.recommendation.lower()


@pytest.mark.asyncio
async def test_endpoint_probe_network_error():
    """Probe handles network error gracefully — returns result, does not raise."""
    from app.pipeline.exchange.endpoint_probe import probe_endpoint

    with patch("httpx.Client.get", side_effect=httpx.ConnectError("refused")):
        with patch("time.sleep"):
            result = probe_endpoint("/some/path")

    assert result.status_code is None
    assert result.error is not None
    assert result.appears_to_have_companies is False


# ---------------------------------------------------------------------------
# 3. Endpoint probe — build_candidate_list
# ---------------------------------------------------------------------------

def test_build_candidate_list_includes_configured_path():
    """build_candidate_list always starts with the configured companies path."""
    from app.pipeline.exchange.endpoint_probe import build_candidate_list
    from app.core.config import settings

    candidates = build_candidate_list()
    assert len(candidates) >= 1
    assert candidates[0] == settings.SAUDI_EXCHANGE_COMPANIES_PATH


def test_build_candidate_list_deduplicates():
    """build_candidate_list returns no duplicates even if configured path repeated."""
    from app.pipeline.exchange.endpoint_probe import build_candidate_list
    from app.core.config import settings

    with patch.object(settings, "SAUDI_EXCHANGE_ENDPOINT_CANDIDATES",
                      [settings.SAUDI_EXCHANGE_COMPANIES_PATH, "/extra"]):
        candidates = build_candidate_list()

    assert len(candidates) == len(set(candidates))


# ---------------------------------------------------------------------------
# 4. Extended health endpoint — new fields present
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_endpoint_includes_new_fields():
    """
    GET /api/v1/system/saudi-exchange-health includes the Phase 2B fields:
    base_url, companies_path_configured, companies_path_is_default,
    companies_path_status.
    """
    from app.pipeline.exchange.connectivity import ConnectivityResult

    mock_result = ConnectivityResult(
        dns_ok=True,
        reachable=False,
        status_code=403,
        latency_ms=200.0,
        blocked_by_akamai=True,
        block_reason="Akamai header present",
        headers_summary={"server": "AkamaiGHost"},
        error="HTTP 403",
        recommendation="Deploy on a Saudi/GCC server.",
        checked_at="2026-06-14T12:00:00+00:00",
    )

    with patch("app.api.v1.system.test_connectivity", return_value=mock_result):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/system/saudi-exchange-health")

    assert response.status_code == 200
    data = response.json()

    # Phase 2A fields still present
    required_phase2a = {
        "reachable", "status_code", "blocked_by_akamai", "block_reason",
        "dns_ok", "latency_ms", "headers_summary", "recommendation",
        "error", "checked_at",
    }
    assert required_phase2a.issubset(data.keys())

    # Phase 2B fields
    assert "base_url" in data
    assert "companies_path_configured" in data
    assert "companies_path_is_default" in data
    assert "companies_path_status" in data

    assert data["base_url"].startswith("https://")
    assert isinstance(data["companies_path_configured"], str)
    assert isinstance(data["companies_path_is_default"], bool)
    assert data["companies_path_status"] is None  # not probed without ?probe_companies=true


@pytest.mark.asyncio
async def test_health_endpoint_probe_companies_param():
    """
    GET /api/v1/system/saudi-exchange-health?probe_companies=true
    includes companies_path_status as a dict.
    """
    from app.pipeline.exchange.connectivity import ConnectivityResult
    from app.pipeline.exchange.endpoint_probe import ProbeResult

    mock_conn = ConnectivityResult(
        dns_ok=True,
        reachable=False,
        status_code=403,
        latency_ms=200.0,
        blocked_by_akamai=True,
        block_reason="Akamai header",
        headers_summary={},
        error="HTTP 403",
        recommendation="Deploy on GCC.",
        checked_at="2026-06-14T12:00:00+00:00",
    )

    mock_probe = ProbeResult(
        path="/some/path",
        full_url="https://www.saudiexchange.sa/some/path",
        status_code=403,
        content_type="text/html",
        response_size_bytes=1200,
        latency_ms=180.0,
        blocked_by_akamai=True,
        block_reason="Akamai header",
        json_parseable=False,
        record_count=0,
        appears_to_have_companies=False,
        top_level_keys=[],
        sample_fields=[],
        recommendation="Blocked.",
        error="HTTP 403",
        probed_at="2026-06-14T12:00:01+00:00",
    )

    with patch("app.api.v1.system.test_connectivity", return_value=mock_conn):
        with patch("app.pipeline.exchange.endpoint_probe.probe_endpoint",
                   return_value=mock_probe):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/api/v1/system/saudi-exchange-health?probe_companies=true"
                )

    assert response.status_code == 200
    data = response.json()

    assert data["companies_path_status"] is not None
    cps = data["companies_path_status"]
    for key in ("path", "status_code", "content_type", "json_parseable",
                "record_count", "appears_to_have_companies", "recommendation"):
        assert key in cps, f"Missing key in companies_path_status: {key}"


# ---------------------------------------------------------------------------
# 5. Validate environment — report shape
# ---------------------------------------------------------------------------

def test_validate_environment_report_shape():
    """
    validate_environment() returns a ValidationReport with all expected checks.
    All infrastructure is mocked so this runs offline.
    """
    from app.pipeline.exchange.validate_environment import (
        validate_environment, ValidationReport,
    )
    from app.pipeline.exchange.connectivity import ConnectivityResult

    mock_conn = ConnectivityResult(
        dns_ok=True,
        reachable=False,
        status_code=403,
        latency_ms=200.0,
        blocked_by_akamai=True,
        block_reason="Akamai",
        headers_summary={},
        error="HTTP 403",
        recommendation="Deploy on GCC.",
        checked_at="2026-06-14T12:00:00+00:00",
    )

    with (
        patch("app.pipeline.exchange.validate_environment._check_database",
              return_value=MagicMock(
                  name="database", passed=True, is_warning=False,
                  detail="Connected."
              )),
        patch("app.pipeline.exchange.validate_environment._check_redis",
              return_value=MagicMock(
                  name="redis", passed=True, is_warning=False,
                  detail="Connected."
              )),
        patch("app.pipeline.exchange.validate_environment._check_storage",
              return_value=MagicMock(
                  name="storage", passed=True, is_warning=False,
                  detail="Writable."
              )),
        patch("app.pipeline.exchange.validate_environment.test_connectivity",
              return_value=mock_conn),
    ):
        report = validate_environment()

    assert isinstance(report, ValidationReport)
    assert len(report.checks) >= 5
    assert report.checked_at != ""
    # sample_data_disabled should appear
    check_names = [c.name for c in report.checks]
    assert "sample_data_disabled" in check_names
    assert "companies_endpoint" in check_names
