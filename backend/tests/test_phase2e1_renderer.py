"""
Tests for Phase 2E.1: Saudi Exchange XBRL HTML viewer rendering and parsing.

Coverage:
  Parser tests (no browser required):
    1. _is_sa_html_viewer: True for SA viewer content
    2. _is_sa_html_viewer: False for standard XBRL XML
    3. _parse_sa_html_viewer: balance sheet facts extracted with instant_date
    4. _parse_sa_html_viewer: income statement facts with period_start/period_end
    5. _parse_sa_html_viewer: empty / &nbsp; cells produce no facts
    6. _parse_sa_html_viewer: unknown/skipped section (auditors) emits no facts
    7. parse_xbrl_file_bytes: dispatches to SA viewer parser automatically
    8. parse_xbrl_file_bytes: original file unchanged (bytes comparison)
    9. RenderResult: missing section warning recorded correctly

  Playwright render tests (skipped if Playwright not installed):
    10. render_xbrl_html: required sections selected and rendered HTML saved
    11. render_xbrl_html: original file unchanged after rendering
    12. render_xbrl_html: missing section recorded in sections_missing + warnings
    13. render_xbrl_html: rendered_path is different from source_path
"""

from __future__ import annotations

import json
import textwrap
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.pipeline.exchange.xbrl_parser import (
    _is_sa_html_viewer,
    _parse_sa_html_viewer,
    parse_xbrl_file_bytes,
)
from app.pipeline.exchange.xbrl_renderer import (
    RenderResult,
    REQUIRED_SECTIONS,
    SECTION_MAP,
    _PLAYWRIGHT_AVAILABLE,
    render_xbrl_html,
    rendered_output_path,
    sections_to_json,
)

# ─────────────────────────────────────────────────────────────────────────────
# Sample HTML fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_sa_viewer_html(
    *,
    include_bs: bool = True,
    include_is: bool = True,
    include_auditors: bool = True,
    extra_sections: str = "",
) -> str:
    """Build a minimal but realistic SA XBRL viewer HTML for testing."""
    bs_section = ""
    if include_bs:
        bs_section = """
<div class='StatementOfFinancialPositionCurrentNonCurrent' style='display:none; clear:both;'>
  <table><tr class=' template-title '><td><span class='arb'>[300200] قاائمة المركز المالي</span></td></tr></table>
  <div class='template-div' style='float: right;'>
    <table class='gridtable' style='direction:rtl;'>
      <tr>
        <th align="center"><span class='arb'>بداية الفترة</span></th>
        <th align="center">2025-01-01</th>
        <th align="center">2024-01-01</th>
      </tr>
      <tr>
        <th align="center"><span class='arb'>نهاية الفترة</span></th>
        <th align="center">2025-12-31</th>
        <th align="center">2024-12-31</th>
      </tr>
      <tbody>
        <tr>
          <td width='500px;'><span class='arb'>أرصدة لدى البنوك ونقد في الصندوق</span></td>
          <td align='center'>299,300</td>
          <td align='center'>551,735</td>
        </tr>
        <tr>
          <td width='500px;'><span class='arb'>إجمالي الموجودات</span></td>
          <td align='center'>1,200,000</td>
          <td align='center'>&nbsp;</td>
        </tr>
        <tr>
          <td width='500px;'><span class='arb'>رأس المال</span></td>
          <td align='center'>&nbsp;</td>
          <td align='center'>&nbsp;</td>
        </tr>
      </tbody>
    </table>
  </div>
</div>
"""

    is_section = ""
    if include_is:
        is_section = """
<div class='StatementOfIncomeFunctionOfExpense' style='display:none; clear:both;'>
  <table><tr class=' template-title '><td><span class='arb'>[300400] قائمة الدخل</span></td></tr></table>
  <div class='template-div' style='float: right;'>
    <table class='gridtable' style='direction:rtl;'>
      <tr>
        <th align="center"><span class='arb'>بداية الفترة</span></th>
        <th align="center">2025-01-01</th>
        <th align="center">2024-01-01</th>
      </tr>
      <tr>
        <th align="center"><span class='arb'>نهاية الفترة</span></th>
        <th align="center">2025-12-31</th>
        <th align="center">2024-12-31</th>
      </tr>
      <tbody>
        <tr>
          <td width='500px;'><span class='arb'>الإيرادات</span></td>
          <td align='center'>500,000</td>
          <td align='center'>(450,000)</td>
        </tr>
      </tbody>
    </table>
  </div>
</div>
"""

    auditors_section = ""
    if include_auditors:
        auditors_section = """
<div class='IndependentAuditorsReport' style='display:none; clear:both;'>
  <div class='template-div'>
    <p>Auditors report text — no gridtable here.</p>
  </div>
</div>
"""

    return textwrap.dedent(f"""
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
<head><title>XBRL Viewer</title></head>
<body style='direction:rtl;'>
<div class='templateCheck-div'>
  <table><tr>
    <td><input type='checkbox' name='templateId' value='StatementOfFinancialPositionCurrentNonCurrent' class='templateIdClass'></td>
    <td>[300200] قاائمة المركز المالي</td>
    <td><input type='checkbox' name='templateId' value='StatementOfIncomeFunctionOfExpense' class='templateIdClass'></td>
    <td>[300400] قائمة الدخل</td>
    <td><input type='checkbox' name='templateId' value='IndependentAuditorsReport' class='templateIdClass'></td>
    <td>[200100] تقرير مراجعي الحسابات</td>
  </tr></table>
</div>
<div class='templateSelect-div'>
  <table><tr><td><input type='button' value='submit' class='displayResult'></td></tr></table>
</div>
{bs_section}
{is_section}
{auditors_section}
{extra_sections}
</body>
</html>
""")


_STANDARD_XBRL = b"""<?xml version="1.0" encoding="UTF-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:ifrs-full="http://xbrl.ifrs.org/taxonomy/2021-03-24/ifrs-full">
  <context id="ctx1">
    <entity><identifier scheme="http://standards.iso.org/iso/17442">SA-001</identifier></entity>
    <period><startDate>2024-01-01</startDate><endDate>2024-12-31</endDate></period>
  </context>
  <unit id="u1"><measure>iso4217:SAR</measure></unit>
  <ifrs-full:Revenue contextRef="ctx1" unitRef="u1" decimals="0">5000000</ifrs-full:Revenue>
</xbrl>"""


# ─────────────────────────────────────────────────────────────────────────────
# 1. Detection tests
# ─────────────────────────────────────────────────────────────────────────────

def test_is_sa_html_viewer_true():
    html = _make_sa_viewer_html()
    content = html.encode("utf-8")
    assert _is_sa_html_viewer(content[:8192]) is True


def test_is_sa_html_viewer_false_standard_xbrl():
    assert _is_sa_html_viewer(_STANDARD_XBRL[:8192]) is False


def test_is_sa_html_viewer_false_empty():
    assert _is_sa_html_viewer(b"") is False


# ─────────────────────────────────────────────────────────────────────────────
# 2. Balance sheet parsing
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_sa_html_viewer_balance_sheet_facts():
    html = _make_sa_viewer_html(include_is=False, include_auditors=False)
    facts = _parse_sa_html_viewer(html)

    # Should get 3 facts: 2 from first row (2 periods), 1 from second row (col1 only)
    # Third row is all &nbsp; → no facts
    assert len(facts) == 3

    bs_facts = [f for f in facts if f.statement_type == "balance_sheet"]
    assert len(bs_facts) == 3

    # First fact: cash, period 2025-12-31
    cash_facts = [f for f in bs_facts if "بنوك" in f.concept_name]
    assert len(cash_facts) == 2  # current year + prior year

    current = next(f for f in cash_facts if f.period_end == date(2025, 12, 31))
    assert current.value_raw == "299,300"
    from decimal import Decimal
    assert current.value_numeric == Decimal("299300")
    assert current.instant_date == date(2025, 12, 31)
    assert current.period_start is None  # balance sheet = instant, no period_start
    assert current.context_ref == "INSTANT__2025-12-31"
    assert current.label_ar == current.concept_name
    assert current.concept_namespace == "sa_xbrl_viewer"


def test_parse_sa_html_viewer_balance_sheet_prior_year():
    html = _make_sa_viewer_html(include_is=False, include_auditors=False)
    facts = _parse_sa_html_viewer(html)

    prior = next(
        f for f in facts
        if "بنوك" in f.concept_name and f.period_end == date(2024, 12, 31)
    )
    assert prior.value_raw == "551,735"
    assert prior.instant_date == date(2024, 12, 31)
    assert prior.context_ref == "INSTANT__2024-12-31"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Income statement parsing
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_sa_html_viewer_income_statement_period_dates():
    html = _make_sa_viewer_html(include_bs=False, include_auditors=False)
    facts = _parse_sa_html_viewer(html)

    is_facts = [f for f in facts if f.statement_type == "income_statement"]
    assert len(is_facts) == 2  # current + prior year revenue

    current = next(f for f in is_facts if f.period_end == date(2025, 12, 31))
    assert current.period_start == date(2025, 1, 1)
    assert current.period_end == date(2025, 12, 31)
    assert current.instant_date is None
    assert current.context_ref == "PERIOD__2025-01-01__2025-12-31"
    assert current.value_raw == "500,000"


def test_parse_sa_html_viewer_income_statement_negative_paren():
    html = _make_sa_viewer_html(include_bs=False, include_auditors=False)
    facts = _parse_sa_html_viewer(html)

    from decimal import Decimal
    prior = next(f for f in facts if f.period_end == date(2024, 12, 31))
    assert prior.value_raw == "(450,000)"
    assert prior.value_numeric == Decimal("-450000")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Empty / &nbsp; cells produce no facts
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_sa_html_viewer_skips_empty_cells():
    html = _make_sa_viewer_html(include_is=False, include_auditors=False)
    facts = _parse_sa_html_viewer(html)

    # رأس المال row has both cells as &nbsp; → 0 facts
    capital_facts = [f for f in facts if "رأس المال" in f.concept_name]
    assert len(capital_facts) == 0

    # إجمالي الموجودات row: col1 = 1,200,000 / col2 = &nbsp; → 1 fact only
    total_facts = [f for f in facts if "إجمالي" in f.concept_name]
    assert len(total_facts) == 1
    assert total_facts[0].value_raw == "1,200,000"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Skipped sections (auditors, notes) produce no facts
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_sa_html_viewer_skips_auditors_section():
    html = _make_sa_viewer_html(include_bs=False, include_is=False)
    facts = _parse_sa_html_viewer(html)
    auditors_facts = [f for f in facts if f.statement_type == "auditors_report"]
    assert len(auditors_facts) == 0


def test_parse_sa_html_viewer_no_facts_from_notes_section():
    notes_html = """
<div class='NotesFormingPartOfAccounts' style='display:none; clear:both;'>
  <div class='template-div'>
    <table>
      <tbody>
        <tr><td style="width:200pt;"><p>Some note text</p></td><td>2,227</td></tr>
      </tbody>
    </table>
  </div>
</div>
"""
    extra = notes_html
    html = _make_sa_viewer_html(include_bs=False, include_is=False, extra_sections=extra)
    facts = _parse_sa_html_viewer(html)
    notes_facts = [f for f in facts if f.statement_type == "notes"]
    assert len(notes_facts) == 0  # notes section is in _SA_SKIP_PARSE_SECTIONS


# ─────────────────────────────────────────────────────────────────────────────
# 6. parse_xbrl_file_bytes dispatches to SA viewer parser
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_xbrl_file_bytes_detects_sa_viewer():
    html = _make_sa_viewer_html()
    result = parse_xbrl_file_bytes(html.encode("utf-8"), extension=".html")

    assert result.file_format == "sa_html_viewer"
    assert result.error is None
    assert len(result.facts) > 0


def test_parse_xbrl_file_bytes_sa_viewer_facts_correct():
    html = _make_sa_viewer_html(include_is=False, include_auditors=False)
    result = parse_xbrl_file_bytes(html.encode("utf-8"), extension=".html")

    bs_facts = [f for f in result.facts if f.statement_type == "balance_sheet"]
    assert len(bs_facts) == 3
    assert all(f.concept_namespace == "sa_xbrl_viewer" for f in bs_facts)


def test_parse_xbrl_file_bytes_standard_xbrl_not_sa_viewer():
    result = parse_xbrl_file_bytes(_STANDARD_XBRL, extension=".xbrl")
    assert result.file_format == "xbrl_xml"
    assert len(result.facts) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 7. Original file unchanged after parsing
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_sa_viewer_original_bytes_unchanged(tmp_path):
    html = _make_sa_viewer_html()
    original_bytes = html.encode("utf-8")

    # Simulate writing + reading back (as parse_xbrl_file does)
    file = tmp_path / "test.html"
    file.write_bytes(original_bytes)

    from app.pipeline.exchange.xbrl_parser import parse_xbrl_file
    parse_xbrl_file(file)

    assert file.read_bytes() == original_bytes


# ─────────────────────────────────────────────────────────────────────────────
# 8. RenderResult helpers
# ─────────────────────────────────────────────────────────────────────────────

def test_sections_to_json_serializes_correctly():
    codes = ["300200", "300400"]
    result = sections_to_json(codes)
    assert json.loads(result) == codes


def test_rendered_output_path_naming(tmp_path):
    original = tmp_path / "404_2240_2026-04-13_18-25-37_ARB.html"
    expected = tmp_path / "404_2240_2026-04-13_18-25-37_ARB_rendered.html"
    assert rendered_output_path(original) == expected


# ─────────────────────────────────────────────────────────────────────────────
# 9. Playwright render tests (mocked — no browser required)
# ─────────────────────────────────────────────────────────────────────────────

def _build_mock_playwright(rendered_html: str, section_counts: dict[str, int]):
    """
    Build a minimal Playwright mock that simulates:
    - locator().count() returning section_counts[template_id] (1=found, 0=missing)
    - page.content() returning rendered_html
    """
    mock_page = AsyncMock()
    mock_page.content = AsyncMock(return_value=rendered_html)
    mock_page.wait_for_timeout = AsyncMock()

    def make_locator(selector: str):
        loc = AsyncMock()
        # Parse template value from selector
        # e.g. "input[name='templateId'][value='FilingInformation']"
        import re
        m = re.search(r"value='([^']+)'", selector)
        template_id = m.group(1) if m else selector
        loc.count = AsyncMock(return_value=section_counts.get(template_id, 1))
        loc.check = AsyncMock()
        loc.click = AsyncMock()
        return loc

    mock_page.locator = MagicMock(side_effect=make_locator)

    mock_browser = AsyncMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_browser.close = AsyncMock()

    mock_chromium = AsyncMock()
    mock_chromium.launch = AsyncMock(return_value=mock_browser)

    mock_pw_instance = AsyncMock()
    mock_pw_instance.chromium = mock_chromium

    mock_pw_cm = AsyncMock()
    mock_pw_cm.__aenter__ = AsyncMock(return_value=mock_pw_instance)
    mock_pw_cm.__aexit__ = AsyncMock(return_value=None)

    return mock_pw_cm, mock_page


@pytest.mark.asyncio
async def test_render_saves_rendered_html(tmp_path):
    """Rendered HTML is written to output_path."""
    html = _make_sa_viewer_html()
    source = tmp_path / "viewer.html"
    source.write_text(html, encoding="utf-8")
    output = tmp_path / "viewer_rendered.html"

    expected_rendered = "<html>rendered content</html>"
    mock_pw_cm, _ = _build_mock_playwright(expected_rendered, {})

    with patch("app.pipeline.exchange.xbrl_renderer.async_playwright", return_value=mock_pw_cm), \
         patch("app.pipeline.exchange.xbrl_renderer._PLAYWRIGHT_AVAILABLE", True):
        result = await render_xbrl_html(source, output)

    assert result.error is None
    assert result.rendered_path == output
    assert output.exists()
    assert output.read_text(encoding="utf-8") == expected_rendered


@pytest.mark.asyncio
async def test_render_original_file_unchanged(tmp_path):
    """Source file must not be modified by the render step."""
    html = _make_sa_viewer_html()
    source = tmp_path / "viewer.html"
    source.write_text(html, encoding="utf-8")
    original_bytes = source.read_bytes()
    output = tmp_path / "viewer_rendered.html"

    mock_pw_cm, _ = _build_mock_playwright("<html>rendered</html>", {})

    with patch("app.pipeline.exchange.xbrl_renderer.async_playwright", return_value=mock_pw_cm), \
         patch("app.pipeline.exchange.xbrl_renderer._PLAYWRIGHT_AVAILABLE", True):
        await render_xbrl_html(source, output)

    assert source.read_bytes() == original_bytes


@pytest.mark.asyncio
async def test_render_required_sections_selected(tmp_path):
    """All required section checkboxes are checked."""
    html = _make_sa_viewer_html()
    source = tmp_path / "viewer.html"
    source.write_text(html, encoding="utf-8")
    output = tmp_path / "viewer_rendered.html"

    # All sections present (count=1)
    mock_pw_cm, mock_page = _build_mock_playwright("<html/>", {})

    with patch("app.pipeline.exchange.xbrl_renderer.async_playwright", return_value=mock_pw_cm), \
         patch("app.pipeline.exchange.xbrl_renderer._PLAYWRIGHT_AVAILABLE", True):
        result = await render_xbrl_html(source, output, section_codes=REQUIRED_SECTIONS)

    assert result.error is None
    assert len(result.sections_found) == len(REQUIRED_SECTIONS)
    assert result.sections_missing == []


@pytest.mark.asyncio
async def test_render_missing_section_recorded_in_warnings(tmp_path):
    """If a section checkbox is absent, it appears in sections_missing and warnings."""
    html = _make_sa_viewer_html()
    source = tmp_path / "viewer.html"
    source.write_text(html, encoding="utf-8")
    output = tmp_path / "viewer_rendered.html"

    # "FilingInformation" absent (count=0), all others present
    counts = {"FilingInformation": 0}
    mock_pw_cm, _ = _build_mock_playwright("<html/>", counts)

    with patch("app.pipeline.exchange.xbrl_renderer.async_playwright", return_value=mock_pw_cm), \
         patch("app.pipeline.exchange.xbrl_renderer._PLAYWRIGHT_AVAILABLE", True):
        result = await render_xbrl_html(source, output, section_codes=REQUIRED_SECTIONS)

    assert "100010" in result.sections_missing
    assert any("100010" in w or "FilingInformation" in w for w in result.warnings)
    assert "100010" not in result.sections_found


@pytest.mark.asyncio
async def test_render_rendered_path_differs_from_source(tmp_path):
    """rendered_path must be a different file than source_path."""
    html = _make_sa_viewer_html()
    source = tmp_path / "viewer.html"
    source.write_text(html, encoding="utf-8")
    output = rendered_output_path(source)

    mock_pw_cm, _ = _build_mock_playwright("<html/>", {})

    with patch("app.pipeline.exchange.xbrl_renderer.async_playwright", return_value=mock_pw_cm), \
         patch("app.pipeline.exchange.xbrl_renderer._PLAYWRIGHT_AVAILABLE", True):
        result = await render_xbrl_html(source, output)

    assert result.rendered_path != source
    assert result.rendered_path == output


@pytest.mark.asyncio
async def test_render_no_playwright_returns_error(tmp_path):
    """RenderResult.error is set when Playwright is not installed."""
    html = _make_sa_viewer_html()
    source = tmp_path / "viewer.html"
    source.write_text(html, encoding="utf-8")
    output = tmp_path / "viewer_rendered.html"

    with patch("app.pipeline.exchange.xbrl_renderer._PLAYWRIGHT_AVAILABLE", False):
        result = await render_xbrl_html(source, output)

    assert result.error is not None
    assert "playwright" in result.error.lower()
    assert result.rendered_path is None
    assert not output.exists()


@pytest.mark.asyncio
async def test_render_source_not_found_returns_error(tmp_path):
    """RenderResult.error is set when source file does not exist."""
    source = tmp_path / "nonexistent.html"
    output = tmp_path / "out.html"

    with patch("app.pipeline.exchange.xbrl_renderer._PLAYWRIGHT_AVAILABLE", True):
        result = await render_xbrl_html(source, output)

    assert result.error is not None
    assert "not found" in result.error.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 10. Live Playwright test (only when Playwright + Chromium are installed)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not _PLAYWRIGHT_AVAILABLE, reason="Playwright not installed")
@pytest.mark.asyncio
async def test_render_live_with_real_playwright(tmp_path):
    """
    Open a real local SA viewer HTML file with Playwright.
    Verifies that the rendered HTML snapshot is written and non-empty.
    """
    html = _make_sa_viewer_html()
    source = tmp_path / "live_test.html"
    source.write_text(html, encoding="utf-8")
    output = tmp_path / "live_test_rendered.html"

    result = await render_xbrl_html(source, output, section_codes=list(SECTION_MAP.keys())[:3])

    assert result.error is None, f"Live render failed: {result.error}"
    assert output.exists()
    rendered = output.read_text(encoding="utf-8")
    assert len(rendered) > 100
    # Original unchanged
    assert source.read_text(encoding="utf-8") == html
