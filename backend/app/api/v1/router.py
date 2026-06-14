from fastapi import APIRouter

from app.api.v1 import (
    health, auth, companies, screener, sectors,
    announcements, data_quality, jobs, system,
)

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["Health"])
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(companies.router, prefix="/companies", tags=["Companies"])
api_router.include_router(screener.router, prefix="/screener", tags=["Screener"])
api_router.include_router(sectors.router, prefix="/sectors", tags=["Sectors"])
api_router.include_router(announcements.router, prefix="/announcements", tags=["Announcements"])
api_router.include_router(data_quality.router, prefix="/data-quality", tags=["Data Quality"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])
api_router.include_router(system.router, prefix="/system", tags=["System"])
