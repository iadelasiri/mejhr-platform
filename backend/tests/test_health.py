import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.config import settings

# Patch at the import site, not the definition site
DB_PATCH = "app.api.v1.health.check_db_health"
REDIS_PATCH = "app.api.v1.health.check_redis_health"


@pytest.mark.asyncio
async def test_health_healthy():
    with (
        patch(DB_PATCH, new_callable=AsyncMock, return_value=True),
        patch(REDIS_PATCH, new_callable=AsyncMock, return_value=True),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/health/")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["platform"] == settings.APP_NAME
    assert data["services"]["database"] == "healthy"
    assert data["services"]["redis"] == "healthy"


@pytest.mark.asyncio
async def test_health_degraded_db():
    with (
        patch(DB_PATCH, new_callable=AsyncMock, return_value=False),
        patch(REDIS_PATCH, new_callable=AsyncMock, return_value=True),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/health/")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["services"]["database"] == "unhealthy"
    assert data["services"]["redis"] == "healthy"


@pytest.mark.asyncio
async def test_health_response_structure():
    with (
        patch(DB_PATCH, new_callable=AsyncMock, return_value=True),
        patch(REDIS_PATCH, new_callable=AsyncMock, return_value=True),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/health/")

    data = response.json()
    assert "status" in data
    assert "platform" in data
    assert "version" in data
    assert "timestamp" in data
    assert "environment" in data
    assert "services" in data
    assert "sample_data_enabled" in data
    # Phase 1: sample data must be disabled by default
    assert data["sample_data_enabled"] is False
