from fastapi import APIRouter
from datetime import datetime, timezone

from app.core.config import settings
from app.core.database import check_db_health
from app.core.redis_client import check_redis_health

router = APIRouter()


@router.get("/")
async def health_check():
    db_ok = await check_db_health()
    redis_ok = await check_redis_health()

    status = "healthy" if db_ok and redis_ok else "degraded"

    return {
        "status": status,
        "platform": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": "development" if settings.DEBUG else "production",
        "sample_data_enabled": settings.ENABLE_SAMPLE_DATA,
        "services": {
            "database": "healthy" if db_ok else "unhealthy",
            "redis": "healthy" if redis_ok else "unhealthy",
            "worker": "unknown",
        },
    }
