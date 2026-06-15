"""
Phase 2E tests — XBRL filing discovery and download pipeline.

All tests are offline: HTTP calls and DB operations are mocked.

Required scenarios (per Phase 2E spec):
  1. XBRL discovery success — filings found and inserted
  2. No filings found — honest empty result, no DB writes
  3. Duplicate filing skipped — idempotent on (symbol, xbrl_url)
  4. File download success — file written, hash recorded
  5. Hash prevents duplicate download — skipped_duplicate on re-download
  6. Blocked / 403 — recorded honestly, endpoint_blocked=True
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Helpers shared across tests
# ─────────────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _AsyncCtx:
    def __init__(self, obj):
        self._obj = obj

    async def __aenter__(self):
        return self._obj

    async def __aexit__(self, *_):
        pass


def _session_factory(db_mock):
    return lambda: _AsyncCtx(db_mock)


def _make_db_no_existing() -> AsyncMock:
    """DB that finds no existing XBRLFiling rows and no existing file hashes."""
    db = AsyncMock()
    db.add = MagicMock()
    no_row = MagicMock()
    no_row.scalar_one_or_none.return_value = None
    no_row.scalars.return_value.all.return_value = []
    db.execute.return_value = no_row
    return db


def _make_db_existing_filing(xbrl_url: str) -> AsyncMock:
    """DB that finds an existing XBRLFiling row (for idempotency tests)."""
    db = AsyncMock()
    db.add = MagicMock()

    existing_filing = MagicMock()
    existing_filing.xbrl_url = xbrl_url

    row_with_existing = MagicMock()
    row_with_existing.scalar_one_or_none.return_value = existing_filing

    empty_row = MagicMock()
    empty_row.scalars.return_value.all.return_value = []

    db.execute.return_value = row_with_existing
    return db


def _make_discovery_response(
    symbol: str = "1010",
    num_filings: int = 2,
    blocked: bool = False,
) -> MagicMock:
    """Build a mock curl_cffi response for the announcements API."""
    resp = MagicMock()

    if blocked:
        resp.status_code = 403
        resp.text = "Access Denied"
        return resp

    resp.status_code = 200
    resp.text = ""

    attachments = [
        {
            "attachmentName": f"FS_Q{i}_2024.xhtml",
            "attachmentUrl": f"https://www.saudiexchange.sa/wps/wcm/connect/uuid{i}/{symbol}_Q{i}_2024.xhtml",
            "mimeType": "application/xhtml+xml",
        }
        for i in range(1, num_filings + 1)
    ]

    resp.json.return_value = {
        "totalRecord": num_filings,
        "announcements": [
            {
                "announcementId": f"ann-{i}",
                "companyShortName": symbol,
                "announcementDate": "2024-11-12",
                "categoryName": "Financial Statements",
                "title": f"Financial Statements Q{i} 2024",
                "attachments": [attachments[i - 1]],
            }
            for i in range(1, num_filings + 1)
        ],
    }
    return resp


def _make_company_mock(symbol: str = "1010") -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.symbol = symbol
    c.market = "tadawul"
    return c


# ─────────────────────────────────────────────────────────────────────────────
# 1. XBRL discovery success
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_xbrl_discovery_success():
    """
    discover_filings parses announcements API response and returns
    DiscoveredFiling records for all XBRL attachments in Financial Statement
    announcements.
    """
    from app.pipeline.exchange.xbrl_discovery import discover_filings

    resp = _make_discovery_response(symbol="1010", num_filings=3)

    with patch("app.pipeline.exchange.xbrl_discovery._http_get", return_value=resp):
        result = discover_filings("1010")

    assert result.reachable is True
    assert result.blocked is False
    assert result.status_code == 200
    assert len(result.filings) == 3

    f = result.filings[0]
    assert f.symbol == "1010"
    assert "saudiexchange.sa" in f.filing_url
    assert f.filing_type == "xhtml"
    assert f.language == "en"
    assert f.fiscal_year == 2024


# ─────────────────────────────────────────────────────────────────────────────
# 2. No filings found
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_xbrl_discovery_no_filings():
    """
    When the API returns announcements with no XBRL attachments,
    discover_filings returns an empty filings list without error.
    """
    from app.pipeline.exchange.xbrl_discovery import discover_filings

    resp = MagicMock()
    resp.status_code = 200
    resp.text = ""
    resp.json.return_value = {
        "totalRecord": 1,
        "announcements": [
            {
                "announcementId": "ann-1",
                "companyShortName": "9999",
                "announcementDate": "2024-01-01",
                "categoryName": "General Announcement",  # NOT financial statements
                "title": "Board Meeting Notice",
                "attachments": [],
            }
        ],
    }

    with patch("app.pipeline.exchange.xbrl_discovery._http_get", return_value=resp):
        result = discover_filings("9999")

    assert result.reachable is True
    assert result.blocked is False
    assert len(result.filings) == 0
    assert result.error is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Duplicate filing skipped (idempotency)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_xbrl_discovery_duplicate_filing_skipped():
    """
    Running discovery twice for the same company does not create duplicate
    XBRLFiling rows. The second run updates the existing record (filings_updated)
    instead of inserting (filings_inserted stays 0).
    """
    from app.pipeline.exchange.xbrl_discovery import discover_filings
    from app.workers.tasks_xbrl import _run_xbrl_discovery

    discovery_resp = _make_discovery_response(symbol="1010", num_filings=1)
    company = _make_company_mock("1010")

    # DB: companies query returns one company; filing query returns an EXISTING row
    company_result = MagicMock()
    company_result.scalars.return_value.all.return_value = [company]

    existing_filing = MagicMock()
    existing_filing.xbrl_url = discovery_resp.json()["announcements"][0]["attachments"][0]["attachmentUrl"]

    existing_result = MagicMock()
    existing_result.scalar_one_or_none.return_value = existing_filing

    job_update_result = MagicMock()

    db = AsyncMock()
    db.add = MagicMock()
    db.execute.side_effect = [
        job_update_result, # update(ImportJob) → running  (from _update_job at task start)
        company_result,    # select(Company)
        existing_result,   # select(XBRLFiling) — existing row found
        job_update_result, # update(ImportJob) → completed (from _update_job at task end)
    ]

    job_id = str(uuid.uuid4())

    with (
        patch("app.pipeline.exchange.xbrl_discovery._http_get", return_value=discovery_resp),
        patch("app.workers.tasks_xbrl.AsyncSessionLocal", _session_factory(db)),
    ):
        stats = await _run_xbrl_discovery(job_id)

    assert stats["filings_found"] == 1
    assert stats["filings_inserted"] == 0   # not a new insertion
    assert stats["filings_updated"] == 1    # existing row updated
    db.add.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 4. File download success
# ─────────────────────────────────────────────────────────────────────────────

def test_xbrl_file_download_success(tmp_path: Path):
    """
    download_file writes content to disk, returns file_hash and local_path.
    """
    from app.pipeline.exchange.xbrl_downloader import download_file

    content = b"<html xmlns:xbrli='...'><body>XBRL content</body></html>"
    expected_hash = hashlib.sha256(content).hexdigest()

    resp = MagicMock()
    resp.status_code = 200
    resp.content = content

    with patch("app.pipeline.exchange.xbrl_downloader._http_get_binary", return_value=resp):
        result = download_file(
            url="https://www.saudiexchange.sa/wps/wcm/connect/uuid1/1010_Q1_2024.xhtml",
            symbol="1010",
            fiscal_year=2024,
            fiscal_period="Q1",
            storage_base=tmp_path,
            existing_hashes=None,
        )

    assert result.download_status == "downloaded"
    assert result.file_hash == expected_hash
    assert result.file_size_bytes == len(content)
    assert result.local_path is not None
    assert result.error is None

    # File actually exists on disk
    assert Path(result.local_path).exists()
    assert Path(result.local_path).read_bytes() == content


# ─────────────────────────────────────────────────────────────────────────────
# 5. Hash prevents duplicate download
# ─────────────────────────────────────────────────────────────────────────────

def test_xbrl_hash_prevents_duplicate_download(tmp_path: Path):
    """
    When existing_hashes contains the SHA-256 of the content being downloaded,
    download_file returns download_status='skipped_duplicate' and writes nothing.
    """
    from app.pipeline.exchange.xbrl_downloader import download_file

    content = b"<html xmlns:xbrli='...'><body>XBRL content</body></html>"
    content_hash = hashlib.sha256(content).hexdigest()

    resp = MagicMock()
    resp.status_code = 200
    resp.content = content

    with patch("app.pipeline.exchange.xbrl_downloader._http_get_binary", return_value=resp):
        result = download_file(
            url="https://www.saudiexchange.sa/wps/wcm/connect/uuid1/1010_Q1_2024.xhtml",
            symbol="1010",
            fiscal_year=2024,
            fiscal_period="Q1",
            storage_base=tmp_path,
            existing_hashes=frozenset({content_hash}),  # hash already in DB
        )

    assert result.download_status == "skipped_duplicate"
    assert result.file_hash == content_hash
    assert result.local_path is None   # nothing written to disk
    assert result.error is None

    # Storage directory may exist but no file was written for this hash
    xbrl_dir = tmp_path / "xbrl" / "1010" / "2024" / "Q1"
    if xbrl_dir.exists():
        files = list(xbrl_dir.iterdir())
        assert len(files) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 6. Blocked / 403 recorded honestly
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_xbrl_discovery_blocked_403():
    """
    When Saudi Exchange returns 403, discovery records endpoint_blocked=True,
    filings_found=0, and reports the error without crashing.
    """
    from app.pipeline.exchange.xbrl_discovery import discover_filings

    blocked_resp = _make_discovery_response(symbol="1010", blocked=True)

    with patch("app.pipeline.exchange.xbrl_discovery._http_get", return_value=blocked_resp):
        result = discover_filings("1010")

    assert result.reachable is False
    assert result.blocked is True
    assert result.status_code == 403
    assert len(result.filings) == 0
    assert result.error is not None
    assert "403" in result.error or "block" in result.error.lower()


@pytest.mark.asyncio
async def test_xbrl_discovery_task_blocked_sets_endpoint_blocked():
    """
    When discover_filings returns blocked=True for the first company,
    _run_xbrl_discovery sets endpoint_blocked=True in stats and stops scanning.
    """
    from app.workers.tasks_xbrl import _run_xbrl_discovery
    from app.pipeline.exchange.xbrl_discovery import DiscoveryResult

    company = _make_company_mock("1010")

    company_result = MagicMock()
    company_result.scalars.return_value.all.return_value = [company]

    job_update = MagicMock()

    db = AsyncMock()
    db.execute.side_effect = [
        job_update,      # update(ImportJob) → running  (from _update_job at task start)
        company_result,  # select(Company)
        # discover_filings is mocked → returns blocked_result immediately
        job_update,      # update(ImportJob) → completed (from _update_job at task end)
    ]

    blocked_result = DiscoveryResult(
        symbol="1010", filings=[],
        reachable=False, blocked=True, status_code=403,
        parse_note="Blocked",
        error="HTTP 403 — blocked",
        fetched_at=_now(),
    )

    job_id = str(uuid.uuid4())

    with (
        patch("app.workers.tasks_xbrl.discover_filings", return_value=blocked_result),
        patch("app.workers.tasks_xbrl.AsyncSessionLocal", _session_factory(db)),
    ):
        stats = await _run_xbrl_discovery(job_id)

    assert stats["endpoint_blocked"] is True
    assert stats["filings_found"] == 0
    assert stats["companies_scanned"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# Additional: download 403 is recorded honestly
# ─────────────────────────────────────────────────────────────────────────────

def test_xbrl_download_blocked_403(tmp_path: Path):
    """
    When the download URL returns 403, download_file records download_status='failed'
    and an appropriate error message. It does not crash.
    """
    from app.pipeline.exchange.xbrl_downloader import download_file

    resp = MagicMock()
    resp.status_code = 403
    resp.content = b"Access Denied"

    with patch("app.pipeline.exchange.xbrl_downloader._http_get_binary", return_value=resp):
        result = download_file(
            url="https://www.saudiexchange.sa/wps/wcm/connect/blocked.xhtml",
            symbol="1010",
            fiscal_year=2024,
            fiscal_period="Q1",
            storage_base=tmp_path,
        )

    assert result.download_status == "failed"
    assert result.file_hash is None
    assert result.local_path is None
    assert result.error is not None
    assert "403" in result.error or "blocked" in result.error.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Additional: _extract_filings_from_response shape handling
# ─────────────────────────────────────────────────────────────────────────────

def test_extract_filings_shape1():
    """_extract_filings_from_response handles shape 1 {totalRecord, announcements}."""
    from app.pipeline.exchange.xbrl_discovery import _extract_filings_from_response

    data = {
        "totalRecord": 1,
        "announcements": [
            {
                "announcementId": "abc",
                "companyShortName": "2222",
                "announcementDate": "2024-03-31",
                "categoryName": "Financial Statements",
                "title": "Annual Financial Statements 2023",
                "attachments": [
                    {
                        "attachmentName": "Annual_2023.xhtml",
                        "attachmentUrl": "https://www.saudiexchange.sa/wps/wcm/connect/x/Annual_2023.xhtml",
                        "mimeType": "application/xhtml+xml",
                    }
                ],
            }
        ],
    }

    filings = _extract_filings_from_response("2222", data, "https://www.saudiexchange.sa")

    assert len(filings) == 1
    f = filings[0]
    assert f.symbol == "2222"
    assert f.filing_url.endswith("Annual_2023.xhtml")
    assert f.filing_type == "xhtml"
    assert f.fiscal_year == 2023
    assert f.fiscal_period is not None and "ANNUAL" in f.fiscal_period.upper()


def test_extract_filings_non_financial_announcement_skipped():
    """Non-financial announcements (board meetings, etc.) are not returned as filings."""
    from app.pipeline.exchange.xbrl_discovery import _extract_filings_from_response

    data = {
        "totalRecord": 1,
        "announcements": [
            {
                "announcementId": "xyz",
                "companyShortName": "1010",
                "announcementDate": "2024-02-10",
                "categoryName": "Board Meeting",
                "title": "Board of Directors Meeting",
                "attachments": [
                    {
                        "attachmentName": "agenda.pdf",
                        "attachmentUrl": "https://www.saudiexchange.sa/wps/wcm/connect/x/agenda.pdf",
                        "mimeType": "application/pdf",
                    }
                ],
            }
        ],
    }

    filings = _extract_filings_from_response("1010", data, "https://www.saudiexchange.sa")

    assert len(filings) == 0  # PDF agenda in a non-financial announcement is not a filing


def test_sha256_dedup_uses_content_hash():
    """SHA-256 dedup is content-based, not URL-based."""
    from app.pipeline.exchange.xbrl_downloader import _sha256

    content_a = b"<xbrl>data A</xbrl>"
    content_b = b"<xbrl>data B</xbrl>"

    hash_a = _sha256(content_a)
    hash_b = _sha256(content_b)

    assert hash_a != hash_b
    assert len(hash_a) == 64   # SHA-256 is 256 bits = 64 hex chars
    assert _sha256(content_a) == hash_a  # deterministic
