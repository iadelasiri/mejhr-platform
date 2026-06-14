from pydantic_settings import BaseSettings
from pydantic import field_validator, model_validator
from typing import List
import json


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Mejhr"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    # "production" | "development" | "test"
    APP_ENV: str = "development"

    # Database
    DATABASE_URL: str
    DATABASE_URL_SYNC: str

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Celery
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    # Security
    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    # Data
    # IMPORTANT: Must be false in production. Sample data is for UI testing only.
    ENABLE_SAMPLE_DATA: bool = False

    # Storage
    STORAGE_PATH: str = "/storage"

    # Saudi Exchange connectivity
    SAUDI_EXCHANGE_BASE_URL: str = "https://www.saudiexchange.sa"
    SAUDI_EXCHANGE_TIMEOUT: int = 30
    SAUDI_EXCHANGE_RETRY_ATTEMPTS: int = 3
    SAUDI_EXCHANGE_RETRY_SLEEP: float = 2.0
    SAUDI_EXCHANGE_PROXY: str | None = None
    SAUDI_EXCHANGE_API_KEY: str | None = None
    SAUDI_EXCHANGE_USER_AGENT: str = (
        "Mozilla/5.0 (compatible; MejhrDataBot/1.0; official-data-collection)"
    )
    # Path to the listed-companies JSON endpoint.
    # Defaults to the public All Shares page; override once the exact
    # JSON API path is confirmed via browser network inspection.
    SAUDI_EXCHANGE_COMPANIES_PATH: str = (
        "/wps/portal/saudiexchange/newsandreports/market-data/"
        "trading-data/all-shares"
    )
    # Additional candidate endpoint paths for the probe tool.
    # Set as a JSON array in the env var, e.g.:
    #   SAUDI_EXCHANGE_ENDPOINT_CANDIDATES=["/api/v1/companies","/market/listed"]
    # Leave empty to probe only SAUDI_EXCHANGE_COMPANIES_PATH.
    SAUDI_EXCHANGE_ENDPOINT_CANDIDATES: List[str] = []

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [origin.strip() for origin in v.split(",")]
        return v

    @field_validator("SAUDI_EXCHANGE_ENDPOINT_CANDIDATES", mode="before")
    @classmethod
    def parse_endpoint_candidates(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [p.strip() for p in v.split(",") if p.strip()]
        return v

    @model_validator(mode="after")
    def production_guard(self) -> "Settings":
        """Refuse to start if sample data is enabled in production."""
        if self.APP_ENV == "production" and self.ENABLE_SAMPLE_DATA:
            raise ValueError(
                "ENABLE_SAMPLE_DATA must be false in production "
                "(APP_ENV=production). Set ENABLE_SAMPLE_DATA=false in .env."
            )
        return self

    model_config = {"env_file": ".env", "case_sensitive": True, "extra": "ignore"}


settings = Settings()
