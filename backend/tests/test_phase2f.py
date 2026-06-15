"""
Phase 2F tests — XBRL raw fact parsing.

All tests are offline: file I/O and DB operations are mocked or use temp bytes.

Required scenarios (per Phase 2F spec):
  1. Parse basic XBRL XML facts
  2. Parse inline XBRL (iXBRL) from XHTML
  3. Invalid file records parse error without raising
  4. Idempotent parsing — same fact updates, not duplicated
  5. Preserves source traceability (filing_id, xbrl_file_id, symbol, source_url)
  6. Import job stats (files_scanned, files_parsed, files_failed, facts_found, ...)
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.pipeline.exchange.xbrl_parser import (
    ParsedFact,
    ParseResult,
    parse_xbrl_file_bytes,
    _detect_statement_type,
    _to_decimal,
    _clean_numeric,
)

# ─────────────────────────────────────────────────────────────────────────────
# Sample XBRL fixtures
# ─────────────────────────────────────────────────────────────────────────────

_STANDARD_XBRL = b"""<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl
    xmlns:xbrli="http://www.xbrl.org/2003/instance"
    xmlns:ifrs-full="http://xbrl.ifrs.org/taxonomy/2021-03-24/ifrs-full">
  <xbrli:context id="c_dur">
    <xbrli:entity>
      <xbrli:identifier scheme="http://www.tadawul.com.sa">1010</xbrli:identifier>
    </xbrli:entity>
    <xbrli:period>
      <xbrli:startDate>2024-01-01</xbrli:startDate>
      <xbrli:endDate>2024-03-31</xbrli:endDate>
    </xbrli:period>
  </xbrli:context>
  <xbrli:context id="c_inst">
    <xbrli:entity>
      <xbrli:identifier scheme="http://www.tadawul.com.sa">1010</xbrli:identifier>
    </xbrli:entity>
    <xbrli:period>
      <xbrli:instant>2024-03-31</xbrli:instant>
    </xbrli:period>
  </xbrli:context>
  <xbrli:unit id="u_sar">
    <xbrli:measure>iso4217:SAR</xbrli:measure>
  </xbrli:unit>
  <ifrs-full:Revenue contextRef="c_dur" unitRef="u_sar" decimals="-3">5000000000</ifrs-full:Revenue>
  <ifrs-full:ProfitLoss contextRef="c_dur" unitRef="u_sar" decimals="-3">1200000000</ifrs-full:ProfitLoss>
  <ifrs-full:Assets contextRef="c_inst" unitRef="u_sar" decimals="-3">30000000000</ifrs-full:Assets>
</xbrli:xbrl>"""

_IXBRL_XHTML = b"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"
      xmlns:xbrli="http://www.xbrl.org/2003/instance"
      xmlns:ifrs-full="http://xbrl.ifrs.org/taxonomy/2021-03-24/ifrs-full">
<head>
  <ix:header>
    <ix:resources>
      <xbrli:context id="c1">
        <xbrli:entity>
          <xbrli:identifier scheme="http://www.tadawul.com.sa">1010</xbrli:identifier>
        </xbrli:entity>
        <xbrli:period>
          <xbrli:startDate>2024-01-01</xbrli:startDate>
          <xbrli:endDate>2024-03-31</xbrli:endDate>
        </xbrli:period>
      </xbrli:context>
      <xbrli:unit id="u1">
        <xbrli:measure>iso4217:SAR</xbrli:measure>
      </xbrli:unit>
    </ix:resources>
  </ix:header>
</head>
<body>
  <p>Revenue:
    <ix:nonFraction name="ifrs-full:Revenue" contextRef="c1" unitRef="u1" decimals="-3">
      5,000,000,000
    </ix:nonFraction>
  </p>
  <p>Entity:
    <ix:nonNumeric name="ifrs-full:NameOfReportingEntity" contextRef="c1">SABIC</ix:nonNumeric>
  </p>
</body>
</html>"""

_INVALID_XML = b"Not XML at all <<<"

_EMPTY_CONTENT = b""


# ─────────────────────────────────────────────────────────────────────────────
# Helper: build a DB session mock for _run_xbrl_parse
# ─────────────────────────────────────────────────────────────────────────────

def _make_task_db(*side_effects):
    """Return a session_cm mock whose db.execute runs the given side_effects in order."""
    db = AsyncMock()
    db.execute.side_effect = list(side_effects)
    # session.add() is synchronous in SQLAlchemy async sessions
    db.add = MagicMock()
    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=db)
    session_cm.__aexit__ = AsyncMock(return_value=None)
    return session_cm, db


def _mock_filing(symbol="1010"):
    f = MagicMock()
    f.id = uuid.uuid4()
    f.symbol = symbol
    f.company_id = uuid.uuid4()
    f.xbrl_url = f"https://www.saudiexchange.sa/wps/wcm/connect/abc/{symbol}_Q1_2024.xbrl"
    f.fiscal_year = 2024
    f.period = "Q1"
    return f


def _mock_file(filing, local_path="/fake/storage/xbrl/1010/2024/Q1/filing.xbrl"):
    fi = MagicMock()
    fi.id = uuid.uuid4()
    fi.filing_id = filing.id
    fi.local_path = local_path
    fi.download_status = "downloaded"
    return fi


# ─────────────────────────────────────────────────────────────────────────────
# 1. Parse basic XBRL XML facts
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_standard_xbrl_xml_facts():
    """Parser extracts all three facts from standard XBRL XML."""
    result = parse_xbrl_file_bytes(_STANDARD_XBRL, ".xbrl")

    assert result.error is None
    assert result.file_format == "xbrl_xml"
    assert len(result.facts) == 3

    revenue = next(f for f in result.facts if f.concept_name == "Revenue")
    assert revenue.value_numeric == Decimal("5000000000")
    assert revenue.unit_ref == "iso4217:SAR"
    assert revenue.decimals == -3
    assert revenue.period_start == date(2024, 1, 1)
    assert revenue.period_end == date(2024, 3, 31)
    assert revenue.instant_date is None
    assert revenue.context_ref == "c_dur"
    assert "ifrs" in (revenue.concept_namespace or "")


def test_parse_standard_xbrl_instant_context():
    """Instant contexts populate instant_date, not period_start/period_end."""
    result = parse_xbrl_file_bytes(_STANDARD_XBRL, ".xbrl")

    assets = next(f for f in result.facts if f.concept_name == "Assets")
    assert assets.instant_date == date(2024, 3, 31)
    assert assets.period_start is None
    assert assets.period_end is None


def test_parse_standard_xbrl_statement_type_detection():
    """Parser detects statement type from IFRS concept names."""
    result = parse_xbrl_file_bytes(_STANDARD_XBRL, ".xbrl")

    revenue = next(f for f in result.facts if f.concept_name == "Revenue")
    assert revenue.statement_type == "income_statement"

    assets = next(f for f in result.facts if f.concept_name == "Assets")
    assert assets.statement_type == "balance_sheet"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Parse inline XBRL (iXBRL) from XHTML
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_inline_xbrl_from_xhtml():
    """Parser extracts nonFraction and nonNumeric facts from iXBRL XHTML."""
    result = parse_xbrl_file_bytes(_IXBRL_XHTML, ".xhtml")

    assert result.error is None
    assert result.file_format == "ixbrl"
    assert len(result.facts) == 2

    revenue = next(f for f in result.facts if f.concept_name == "Revenue")
    assert revenue.value_numeric == Decimal("5000000000")
    assert revenue.unit_ref == "iso4217:SAR"
    assert revenue.period_start == date(2024, 1, 1)
    assert revenue.period_end == date(2024, 3, 31)
    assert "ifrs" in (revenue.concept_namespace or "")

    entity = next(f for f in result.facts if f.concept_name == "NameOfReportingEntity")
    assert entity.value_raw == "SABIC"
    assert entity.value_numeric is None


def test_parse_ixbrl_formatted_number_cleaned():
    """iXBRL formatted number '5,000,000,000' is parsed to Decimal correctly."""
    result = parse_xbrl_file_bytes(_IXBRL_XHTML, ".xhtml")
    revenue = next(f for f in result.facts if f.concept_name == "Revenue")
    assert revenue.value_numeric == Decimal("5000000000")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Invalid file records parse error without raising
# ─────────────────────────────────────────────────────────────────────────────

def test_invalid_xml_returns_error_not_raises():
    """Malformed XML returns ParseResult with error; never raises."""
    result = parse_xbrl_file_bytes(_INVALID_XML, ".xbrl")

    assert result.facts == []
    assert result.error is not None
    assert "parse" in result.error.lower() or "xml" in result.error.lower()
    assert result.file_format == "unknown"


def test_empty_content_returns_error():
    """Empty bytes returns ParseResult with error."""
    result = parse_xbrl_file_bytes(_EMPTY_CONTENT, ".xbrl")

    assert result.facts == []
    assert result.error is not None
    assert result.file_format == "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Idempotent parsing — same fact updates, not duplicated
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_xbrl_parse_task_idempotent():
    """
    When a fact (concept_name, context_ref, unit_ref) already exists in DB,
    the task updates it instead of inserting — facts_updated incremented.
    """
    filing = _mock_filing()
    xbrl_file = _mock_file(filing)

    job_result = MagicMock()
    job_result.rowcount = 1

    # Files + filings query result
    files_result = MagicMock()
    files_result.all.return_value = [(xbrl_file, filing)]

    # Existing raw items result: one existing fact with the same dedup key
    existing_row = MagicMock()
    existing_row.concept_name = "Revenue"
    existing_row.context_ref = "c_dur"
    existing_row.unit_ref = "iso4217:SAR"
    existing_row.id = uuid.uuid4()
    existing_result = MagicMock()
    existing_result.__iter__ = MagicMock(return_value=iter([existing_row]))

    update_result = MagicMock()

    session_cm, db = _make_task_db(
        job_result,       # _update_job("running")
        files_result,     # select(XBRLFile, XBRLFiling)
        existing_result,  # select(XBRLRawItem) — returns existing row
        update_result,    # update(XBRLRawItem) — the update call
        job_result,       # _update_job("completed")
    )

    # Parse result will have one fact matching the existing dedup key
    fake_parse_result = ParseResult(
        facts=[ParsedFact(
            concept_name="Revenue",
            concept_namespace="http://xbrl.ifrs.org/taxonomy/2021-03-24/ifrs-full",
            label_ar=None, label_en=None,
            value_raw="5000000000",
            value_numeric=Decimal("5000000000"),
            unit_ref="iso4217:SAR",
            decimals=-3,
            context_ref="c_dur",
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            instant_date=None,
            statement_type="income_statement",
        )],
        error=None,
        parse_note="ok",
        file_format="xbrl_xml",
    )

    with patch("app.workers.tasks_xbrl.AsyncSessionLocal", return_value=session_cm), \
         patch("app.workers.tasks_xbrl.parse_xbrl_file", return_value=fake_parse_result):
        from app.workers.tasks_xbrl import _run_xbrl_parse
        stats = await _run_xbrl_parse("test-job-id")

    assert stats["files_scanned"] == 1
    assert stats["files_parsed"] == 1
    assert stats["files_failed"] == 0
    assert stats["facts_found"] == 1
    assert stats["facts_updated"] == 1
    assert stats["facts_inserted"] == 0
    # db.add should NOT have been called (no inserts)
    db.add.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 5. Preserves source traceability
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_xbrl_parse_task_preserves_traceability():
    """
    Inserted XBRLRawItem rows carry filing_id, xbrl_file_id, company_id,
    symbol, source_url, local_file_path, data_status=official.
    """
    filing = _mock_filing(symbol="2222")
    xbrl_file = _mock_file(filing, local_path="/storage/xbrl/2222/2024/Q1/q1.xbrl")

    job_result = MagicMock()
    files_result = MagicMock()
    files_result.all.return_value = [(xbrl_file, filing)]
    existing_result = MagicMock()
    existing_result.__iter__ = MagicMock(return_value=iter([]))

    session_cm, db = _make_task_db(
        job_result,       # _update_job("running")
        files_result,     # query files+filings
        existing_result,  # query existing raw items (empty)
        job_result,       # _update_job("completed")
    )

    fake_fact = ParsedFact(
        concept_name="Revenue", concept_namespace="http://xbrl.ifrs.org/taxonomy/",
        label_ar=None, label_en=None,
        value_raw="1000000", value_numeric=Decimal("1000000"),
        unit_ref="iso4217:SAR", decimals=-3,
        context_ref="c1",
        period_start=date(2024, 1, 1), period_end=date(2024, 3, 31),
        instant_date=None, statement_type="income_statement",
    )
    fake_parse_result = ParseResult(facts=[fake_fact], error=None, parse_note="ok", file_format="xbrl_xml")

    with patch("app.workers.tasks_xbrl.AsyncSessionLocal", return_value=session_cm), \
         patch("app.workers.tasks_xbrl.parse_xbrl_file", return_value=fake_parse_result):
        from app.workers.tasks_xbrl import _run_xbrl_parse
        await _run_xbrl_parse("test-job-id")

    # Inspect the XBRLRawItem that was added
    assert db.add.call_count == 1
    added_item = db.add.call_args[0][0]
    from app.models.xbrl import XBRLRawItem
    assert isinstance(added_item, XBRLRawItem)
    assert added_item.filing_id == filing.id
    assert added_item.xbrl_file_id == xbrl_file.id
    assert added_item.company_id == filing.company_id
    assert added_item.symbol == "2222"
    assert added_item.source_url == filing.xbrl_url
    assert added_item.local_file_path == "/storage/xbrl/2222/2024/Q1/q1.xbrl"
    assert added_item.data_status == "official"
    assert added_item.fiscal_year == 2024
    assert added_item.fiscal_period == "Q1"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Import job stats
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_xbrl_parse_task_stats_success():
    """Task returns correct stats for one file parsed with two new facts."""
    filing = _mock_filing()
    xbrl_file = _mock_file(filing)

    job_result = MagicMock()
    files_result = MagicMock()
    files_result.all.return_value = [(xbrl_file, filing)]
    existing_result = MagicMock()
    existing_result.__iter__ = MagicMock(return_value=iter([]))

    session_cm, db = _make_task_db(
        job_result, files_result, existing_result, job_result
    )

    facts = [
        ParsedFact("Revenue", None, None, None, "1000", Decimal("1000"), "iso4217:SAR", -3, "c1",
                   date(2024, 1, 1), date(2024, 3, 31), None, "income_statement"),
        ParsedFact("Assets", None, None, None, "5000", Decimal("5000"), "iso4217:SAR", -3, "c2",
                   None, None, date(2024, 3, 31), "balance_sheet"),
    ]
    fake_result = ParseResult(facts=facts, error=None, parse_note="ok", file_format="xbrl_xml")

    with patch("app.workers.tasks_xbrl.AsyncSessionLocal", return_value=session_cm), \
         patch("app.workers.tasks_xbrl.parse_xbrl_file", return_value=fake_result):
        from app.workers.tasks_xbrl import _run_xbrl_parse
        stats = await _run_xbrl_parse("test-job-id")

    assert stats["files_scanned"] == 1
    assert stats["files_parsed"] == 1
    assert stats["files_failed"] == 0
    assert stats["facts_found"] == 2
    assert stats["facts_inserted"] == 2
    assert stats["facts_updated"] == 0
    assert stats["error"] is None


@pytest.mark.asyncio
async def test_xbrl_parse_task_file_parse_error_counted():
    """
    When a file fails to parse, files_failed is incremented, task continues
    to completion, and the error is recorded on the XBRLFile row.
    """
    filing = _mock_filing()
    xbrl_file = _mock_file(filing)

    job_result = MagicMock()
    files_result = MagicMock()
    files_result.all.return_value = [(xbrl_file, filing)]
    update_file_result = MagicMock()

    session_cm, db = _make_task_db(
        job_result,         # _update_job("running")
        files_result,       # query files+filings
        update_file_result, # update(XBRLFile) with error_message
        job_result,         # _update_job("completed")
    )

    failed_result = ParseResult(facts=[], error="XML parse error: junk", parse_note="failed", file_format="unknown")

    with patch("app.workers.tasks_xbrl.AsyncSessionLocal", return_value=session_cm), \
         patch("app.workers.tasks_xbrl.parse_xbrl_file", return_value=failed_result):
        from app.workers.tasks_xbrl import _run_xbrl_parse
        stats = await _run_xbrl_parse("test-job-id")

    assert stats["files_scanned"] == 1
    assert stats["files_failed"] == 1
    assert stats["files_parsed"] == 0
    assert stats["facts_found"] == 0
    assert stats["facts_inserted"] == 0
    # No fact rows inserted
    db.add.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Additional parser unit tests
# ─────────────────────────────────────────────────────────────────────────────

def test_numeric_cleaning_parentheses_negative():
    """Parentheses notation '(1,234,567)' is parsed as negative Decimal."""
    assert _to_decimal("(1,234,567)") == Decimal("-1234567")


def test_numeric_cleaning_comma_separator():
    """Comma thousand separators are stripped before parsing."""
    assert _to_decimal("1,234,567") == Decimal("1234567")


def test_numeric_cleaning_empty_returns_none():
    assert _to_decimal("") is None
    assert _to_decimal(None) is None


def test_statement_type_detection_cashflow():
    assert _detect_statement_type("CashFlowsFromOperatingActivities") == "cash_flow"


def test_statement_type_detection_unknown():
    assert _detect_statement_type("DisclosureOfSignificantAccountingPolicies") == "unknown"


def test_parse_xbrl_file_missing_path():
    """parse_xbrl_file returns error for non-existent file without raising."""
    from app.pipeline.exchange.xbrl_parser import parse_xbrl_file
    result = parse_xbrl_file(Path("/nonexistent/path/filing.xbrl"))
    assert result.error is not None
    assert "read" in result.error.lower() or "no such file" in result.error.lower()
    assert result.facts == []
