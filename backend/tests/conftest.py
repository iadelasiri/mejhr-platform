import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """HTTP test client with mocked DB and Redis health checks."""
    with (
        patch("app.core.database.check_db_health", new_callable=AsyncMock, return_value=True),
        patch("app.core.redis_client.check_redis_health", new_callable=AsyncMock, return_value=True),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c
