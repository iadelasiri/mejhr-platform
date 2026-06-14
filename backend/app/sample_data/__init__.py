"""
Sample data module — FOR UI TESTING ONLY.

Rules:
  - ENABLE_SAMPLE_DATA must be true to use any function in this module.
  - All sample records have data_status = 'sample_not_official'.
  - Symbols are clearly fake (SMPL1, SMPL2, …) and cannot be confused with real companies.
  - This module must NEVER be called with production data or real company symbols.
  - In production, ENABLE_SAMPLE_DATA must be false (the default).
"""

from app.core.config import settings


def sample_data_guard():
    """Raise if sample data is not enabled."""
    if not settings.ENABLE_SAMPLE_DATA:
        raise RuntimeError(
            "Sample data is disabled. Set ENABLE_SAMPLE_DATA=true only in development."
        )
