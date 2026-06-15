"""
Phase 2C tests — Official Saudi Exchange companies import pipeline.

All tests are offline: HTTP calls and DB operations are mocked so the
suite runs without a real Saudi Exchange connection or database.

Six core scenarios:
  1. Successful companies JSON import  — records inserted, status=completed
  2. Akamai/403 blocked import        — status=failed, endpoint_blocked=True
  3. HTML/non-JSON response           — status=completed, records_found=0 (honest empty)
  4. Network failure                  — status=failed, endpoint_blocked=False
  5. Idempotent upsert behavior       — second import updates, not inserts
  6. ImportJob status tracking        — stats dict has all required keys and values

Plus two API-level scenarios:
  7. GET /api/v1/companies/ with no jobs → pipeline_status=not_configured
  8. GET /api/v1/companies/ after blocked import → pipeline_status=import_failed
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import get_db


# ---------------------------------------------------------------------------
# Helpers shared across all scenarios
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _AsyncCtx:
    """Minimal async context manager that yields a given object."""
    def __init__(self, obj):
        self._obj = obj

    async def __aenter__(self):
        return self._obj

    async def __aexit__(self, *_):
        pass


def _session_factory(db_mock):
    """
    Return a zero-argument callable that mimics AsyncSessionLocal.
    Each call returns an async context manager that yields db_mock.
    """
    return lambda: _AsyncCtx(db_mock)


def _make_db_all_inserts() -> AsyncMock:
    """
    DB mock where every company SELECT returns no existing row → insert path.
    Row-result objects must be MagicMock (not AsyncMock) so that sync methods
    like scalar_one_or_none() return values directly, not coroutines.
    """
    db = AsyncMock()
    db.add = MagicMock()

    no_row = MagicMock()  # sync result object
    no_row.scalar_one_or_none.return_value = None

    db.execute.return_value = no_row
    return db


def _make_db_all_updates(existing_data_status: str = "official") -> AsyncMock:
    """
    DB mock where every company SELECT returns an existing Company row → update path.
    """
    db = AsyncMock()
    db.add = MagicMock()

    existing_co = MagicMock()
    existing_co.data_status = existing_data_status

    row_result = MagicMock()  # sync result object
    row_result.scalar_one_or_none.return_value = existing_co

    db.execute.return_value = row_result
    return db


def _make_company_records(count: int = 2):
    from app.pipeline.exchange.companies import CompanyRecord
    return [
        CompanyRecord(
            symbol=str(1010 + i * 10),
            arabic_name=f"شركة {i + 1}",
            english_name=f"Company {i + 1}",
            market="tadawul",
            source="saudi_exchange_official",
            source_url="https://www.saudiexchange.sa/wps/portal/tadawul/markets/equities",
            imported_at=datetime.now(timezone.utc),
            data_status="official",
            mapping_status="pending_official_mapping",
        )
        for i in range(count)
    ]


def _make_fetch_result(
    *,
    companies=None,
    reachable: bool = True,
    blocked: bool = False,
    status_code: int | None = 200,
    raw_format: str = "json",
    parse_note: str = "",
    error: str | None = None,
):
    from app.pipeline.exchange.companies import FetchResult
    return FetchResult(
        companies=companies or [],
        reachable=reachable,
        blocked=blocked,
        status_code=status_code,
        raw_format=raw_format,
        parse_note=parse_note,
        error=error,
        fetched_at=_now(),
    )


# ---------------------------------------------------------------------------
# Scenario 1: Successful companies JSON import
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_successful_json_import():
    """fetch_companies returns 2 official companies → 2 inserted, status=completed."""
    companies = _make_company_records(2)
    fetch_result = _make_fetch_result(
        companies=companies,
        parse_note="Successfully parsed 2 company records from 2 raw entries.",
    )
    db = _make_db_all_inserts()
    job_id = str(uuid.uuid4())

    with (
        patch("app.workers.tasks_companies.fetch_companies", return_value=fetch_result),
        patch("app.workers.tasks_companies.AsyncSessionLocal", _session_factory(db)),
    ):
        from app.workers.tasks_companies import _run_import
        stats = await _run_import(job_id)

    assert stats["companies_found"] == 2
    assert stats["companies_inserted"] == 2
    assert stats["companies_updated"] == 0
    assert stats["companies_failed"] == 0
    assert stats["endpoint_blocked"] is False
    assert stats["endpoint_reachable"] is True
    assert stats["error"] is None
    assert db.add.call_count == 2


# ---------------------------------------------------------------------------
# Scenario 2: Akamai/403 blocked import
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_akamai_blocked_import():
    """Akamai geo-block → status=failed, endpoint_blocked=True, 0 rows inserted."""
    fetch_result = _make_fetch_result(
        blocked=True,
        reachable=False,
        status_code=403,
        raw_format="error",
        parse_note=(
            "Saudi Exchange is blocking this environment. "
            "Reason: HTTP 403 with Akamai server header. "
            "No official company records imported. "
            "Deploy on a Saudi/GCC server or configure SAUDI_EXCHANGE_PROXY."
        ),
        error="HTTP 403 with Akamai server header",
    )
    db = _make_db_all_inserts()
    job_id = str(uuid.uuid4())

    with (
        patch("app.workers.tasks_companies.fetch_companies", return_value=fetch_result),
        patch("app.workers.tasks_companies.AsyncSessionLocal", _session_factory(db)),
    ):
        from app.workers.tasks_companies import _run_import
        stats = await _run_import(job_id)

    assert stats["endpoint_blocked"] is True
    assert stats["endpoint_reachable"] is False
    assert stats["companies_found"] == 0
    assert stats["companies_inserted"] == 0
    assert stats["error"] is not None
    # execute called at least twice: mark running + mark failed
    assert db.execute.call_count >= 2
    db.add.assert_not_called()


# ---------------------------------------------------------------------------
# Scenario 3: HTML/non-JSON response (honest empty)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_html_non_json_response():
    """
    HTML response → status=completed with records_found=0.
    The endpoint was reachable and not blocked, so this is an honest empty result,
    not a failure. The parse_note explains the path needs updating.
    """
    html_note = (
        "Response is an HTML page, not a JSON API. "
        "SAUDI_EXCHANGE_COMPANIES_PATH points to a portal page. "
        "Inspect the browser's Network tab on the Saudi Exchange website "
        "to find the JSON endpoint that backs the companies list, "
        "then set SAUDI_EXCHANGE_COMPANIES_PATH accordingly."
    )
    fetch_result = _make_fetch_result(
        companies=[],
        reachable=True,
        blocked=False,
        status_code=200,
        raw_format="html",
        parse_note=html_note,
        error=None,
    )
    db = _make_db_all_inserts()
    job_id = str(uuid.uuid4())

    with (
        patch("app.workers.tasks_companies.fetch_companies", return_value=fetch_result),
        patch("app.workers.tasks_companies.AsyncSessionLocal", _session_factory(db)),
    ):
        from app.workers.tasks_companies import _run_import
        stats = await _run_import(job_id)

    # HTML response is "completed" — endpoint reachable, no block, just wrong format
    assert stats["endpoint_blocked"] is False
    assert stats["endpoint_reachable"] is True
    assert stats["companies_found"] == 0
    assert stats["companies_inserted"] == 0
    assert stats["error"] is None
    assert "HTML page" in stats["parse_note"]
    db.add.assert_not_called()


# ---------------------------------------------------------------------------
# Scenario 4: Network failure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_network_failure():
    """Connection error → status=failed, endpoint_blocked=False, error set."""
    fetch_result = _make_fetch_result(
        companies=[],
        reachable=False,
        blocked=False,
        status_code=None,
        raw_format="error",
        parse_note="Network error: [Errno 111] Connection refused",
        error="[Errno 111] Connection refused",
    )
    db = _make_db_all_inserts()
    job_id = str(uuid.uuid4())

    with (
        patch("app.workers.tasks_companies.fetch_companies", return_value=fetch_result),
        patch("app.workers.tasks_companies.AsyncSessionLocal", _session_factory(db)),
    ):
        from app.workers.tasks_companies import _run_import
        stats = await _run_import(job_id)

    assert stats["endpoint_blocked"] is False
    assert stats["endpoint_reachable"] is False
    assert stats["companies_found"] == 0
    assert stats["companies_inserted"] == 0
    assert stats["error"] == "[Errno 111] Connection refused"
    assert db.execute.call_count >= 2
    db.add.assert_not_called()


# ---------------------------------------------------------------------------
# Scenario 5: Idempotent upsert behavior
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_idempotent_upsert_first_run_inserts():
    """First import with 2 companies → 2 inserted, 0 updated."""
    companies = _make_company_records(2)
    fetch_result = _make_fetch_result(companies=companies)
    db = _make_db_all_inserts()
    job_id = str(uuid.uuid4())

    with (
        patch("app.workers.tasks_companies.fetch_companies", return_value=fetch_result),
        patch("app.workers.tasks_companies.AsyncSessionLocal", _session_factory(db)),
    ):
        from app.workers.tasks_companies import _run_import
        stats = await _run_import(job_id)

    assert stats["companies_inserted"] == 2
    assert stats["companies_updated"] == 0
    assert stats["companies_failed"] == 0


@pytest.mark.asyncio
async def test_idempotent_upsert_second_run_updates():
    """Second import with same symbols and data_status='official' → 0 inserted, 2 updated."""
    companies = _make_company_records(2)
    fetch_result = _make_fetch_result(companies=companies)
    db = _make_db_all_updates(existing_data_status="official")
    job_id = str(uuid.uuid4())

    with (
        patch("app.workers.tasks_companies.fetch_companies", return_value=fetch_result),
        patch("app.workers.tasks_companies.AsyncSessionLocal", _session_factory(db)),
    ):
        from app.workers.tasks_companies import _run_import
        stats = await _run_import(job_id)

    assert stats["companies_inserted"] == 0
    assert stats["companies_updated"] == 2
    assert stats["companies_failed"] == 0
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_sample_company_not_overwritten():
    """Company with data_status='sample_not_official' is skipped — never overwritten."""
    companies = _make_company_records(1)
    fetch_result = _make_fetch_result(companies=companies)
    db = _make_db_all_updates(existing_data_status="sample_not_official")
    job_id = str(uuid.uuid4())

    with (
        patch("app.workers.tasks_companies.fetch_companies", return_value=fetch_result),
        patch("app.workers.tasks_companies.AsyncSessionLocal", _session_factory(db)),
    ):
        from app.workers.tasks_companies import _run_import
        stats = await _run_import(job_id)

    assert stats["companies_inserted"] == 0
    assert stats["companies_updated"] == 0
    assert stats["companies_failed"] == 0
    db.add.assert_not_called()


# ---------------------------------------------------------------------------
# Scenario 6: ImportJob status tracking
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_import_job_stats_keys_present():
    """_run_import always returns a stats dict with every required key."""
    companies = _make_company_records(1)
    fetch_result = _make_fetch_result(companies=companies)
    db = _make_db_all_inserts()
    job_id = str(uuid.uuid4())

    with (
        patch("app.workers.tasks_companies.fetch_companies", return_value=fetch_result),
        patch("app.workers.tasks_companies.AsyncSessionLocal", _session_factory(db)),
    ):
        from app.workers.tasks_companies import _run_import
        stats = await _run_import(job_id)

    required_keys = {
        "companies_found",
        "companies_inserted",
        "companies_updated",
        "companies_failed",
        "unmapped_sector_count",
        "excluded_nomu_count",
        "excluded_etfs",
        "excluded_funds",
        "excluded_sukuk_bonds",
        "excluded_other_securities",
        "endpoint_reachable",
        "endpoint_blocked",
        "parse_note",
        "error",
    }
    assert required_keys == set(stats.keys()), (
        f"Missing keys: {required_keys - set(stats.keys())}; "
        f"Extra keys: {set(stats.keys()) - required_keys}"
    )


@pytest.mark.asyncio
async def test_import_job_db_transitions():
    """DB is updated to 'running' and then to final status (execute called ≥3 times)."""
    companies = _make_company_records(1)
    fetch_result = _make_fetch_result(companies=companies)
    db = _make_db_all_inserts()
    job_id = str(uuid.uuid4())

    with (
        patch("app.workers.tasks_companies.fetch_companies", return_value=fetch_result),
        patch("app.workers.tasks_companies.AsyncSessionLocal", _session_factory(db)),
    ):
        from app.workers.tasks_companies import _run_import
        await _run_import(job_id)

    # 1 = update running, 1 = select company, 1 = update final  → at least 3 executes
    assert db.execute.call_count >= 3
    # commit called 3 times: after running, after upserts, after final
    assert db.commit.call_count >= 3


@pytest.mark.asyncio
async def test_import_job_failed_on_block_sets_error():
    """Blocked import → stats['error'] is set and can be stored in error_message."""
    fetch_result = _make_fetch_result(
        blocked=True,
        reachable=False,
        status_code=403,
        raw_format="error",
        parse_note="Saudi Exchange is blocking this environment.",
        error="HTTP 403 with Akamai server header",
    )
    db = _make_db_all_inserts()
    job_id = str(uuid.uuid4())

    with (
        patch("app.workers.tasks_companies.fetch_companies", return_value=fetch_result),
        patch("app.workers.tasks_companies.AsyncSessionLocal", _session_factory(db)),
    ):
        from app.workers.tasks_companies import _run_import
        stats = await _run_import(job_id)

    # error key must be non-None so it can be stored in ImportJob.error_message
    assert stats["error"] is not None
    assert stats["endpoint_blocked"] is True


# ---------------------------------------------------------------------------
# Scenario 7: NOMU exclusion and second-import idempotency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_nomu_count_reported_in_stats():
    """excluded_nomu is reflected in import stats from fetch result."""
    from app.pipeline.exchange.companies import FetchResult as _FR

    fetch_result = _FR(
        companies=[],
        reachable=True,
        blocked=False,
        status_code=200,
        raw_format="json",
        parse_note="0 companies. Excluded: 146 NOMU.",
        error=None,
        fetched_at=_now(),
        excluded_nomu=146,
    )
    db = _make_db_all_inserts()
    job_id = str(uuid.uuid4())

    with (
        patch("app.workers.tasks_companies.fetch_companies", return_value=fetch_result),
        patch("app.workers.tasks_companies.AsyncSessionLocal", _session_factory(db)),
    ):
        from app.workers.tasks_companies import _run_import
        stats = await _run_import(job_id)

    assert stats["excluded_nomu_count"] == 146
    assert stats["companies_inserted"] == 0


@pytest.mark.asyncio
async def test_second_import_is_idempotent_for_main_market_companies():
    """
    Second import with same Main Market companies → updates only, no inserts.
    excluded_nomu is carried through stats.
    """
    companies = _make_company_records(2)
    fetch_result = _make_fetch_result(companies=companies)
    db = _make_db_all_updates(existing_data_status="official")
    job_id = str(uuid.uuid4())

    with (
        patch("app.workers.tasks_companies.fetch_companies", return_value=fetch_result),
        patch("app.workers.tasks_companies.AsyncSessionLocal", _session_factory(db)),
    ):
        from app.workers.tasks_companies import _run_import
        stats = await _run_import(job_id)

    assert stats["companies_inserted"] == 0
    assert stats["companies_updated"] == 2
    assert stats["companies_failed"] == 0
    assert stats["excluded_nomu_count"] == 0


# ---------------------------------------------------------------------------
# API scenarios: GET /api/v1/companies/ pipeline_status reporting
# ---------------------------------------------------------------------------

def _make_api_db(*, total: int = 0, last_job=None) -> AsyncMock:
    """
    Mock DB for GET /api/v1/companies/ which runs 3 sequential execute calls:
      1. SELECT COUNT(*)            → count_result.scalar()
      2. SELECT Company (paginated) → companies_result.scalars().all()
      3. SELECT ImportJob (latest)  → job_result.scalar_one_or_none()

    All three are MagicMock (sync) — execute() is async, but the objects
    it returns are plain sync result proxies.
    """
    count_result = MagicMock()
    count_result.scalar.return_value = total

    companies_result = MagicMock()
    companies_result.scalars.return_value.all.return_value = []

    job_result = MagicMock()
    job_result.scalar_one_or_none.return_value = last_job

    db = AsyncMock()
    db.execute.side_effect = [count_result, companies_result, job_result]
    return db


def _api_db_override(db_mock):
    async def _override():
        yield db_mock
    return _override


@pytest.mark.asyncio
async def test_companies_api_not_configured():
    """GET /api/v1/companies/ with no data and no import jobs → not_configured."""
    db = _make_api_db(total=0, last_job=None)
    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        with (
            patch("app.core.database.check_db_health", new_callable=AsyncMock, return_value=True),
            patch("app.core.redis_client.check_redis_health", new_callable=AsyncMock, return_value=True),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get("/api/v1/companies/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["meta"]["pipeline_status"] == "not_configured"
        assert body["meta"]["last_import_job"] is None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_companies_api_import_failed_akamai():
    """GET /api/v1/companies/ after Akamai-blocked import → import_failed with block message."""
    failed_job = MagicMock()
    failed_job.id = uuid.uuid4()
    failed_job.status = "failed"
    failed_job.stats = {
        "endpoint_blocked": True,
        "companies_found": 0,
        "companies_inserted": 0,
        "companies_updated": 0,
    }
    failed_job.error_message = "HTTP 403 with Akamai server header"
    failed_job.started_at = datetime.now(timezone.utc)
    failed_job.completed_at = datetime.now(timezone.utc)
    failed_job.duration_seconds = 3

    db = _make_api_db(total=0, last_job=failed_job)
    app.dependency_overrides[get_db] = _api_db_override(db)
    try:
        with (
            patch("app.core.database.check_db_health", new_callable=AsyncMock, return_value=True),
            patch("app.core.redis_client.check_redis_health", new_callable=AsyncMock, return_value=True),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get("/api/v1/companies/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["pipeline_status"] == "import_failed"
        last = body["meta"]["last_import_job"]
        assert last is not None
        assert last["status"] == "failed"
        assert last["endpoint_blocked"] is True
        assert "Saudi Exchange blocked" in body["meta"]["message"]
    finally:
        app.dependency_overrides.clear()
