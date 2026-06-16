"""
Playwright-based renderer for Saudi Exchange XBRL HTML viewer files.

Saudi Exchange XBRL filings are served as interactive HTML viewer pages.
The viewer embeds all financial data in hidden <div> sections (display:none).
A checkbox UI lets users select which financial statement sections to show,
then clicking submit reveals those sections via JavaScript.

This module:
  1. Opens the local HTML file with a headless Chromium browser
  2. Selects the required section checkboxes
  3. Clicks the submit button
  4. Waits for JS to make sections visible
  5. Captures the full rendered HTML
  6. Saves it alongside the original file as <stem>_rendered.html

The rendered snapshot preserves full traceability:
  - original_url (the source xbrl_url on XBRLFiling)
  - original_file_path (local_path on XBRLFile)
  - rendered_file_path (rendered_path on XBRLFile)
  - selected_sections (JSON list of section codes)
  - rendered_at (timestamp)

No facts are parsed here. Parsing is done by xbrl_parser.parse_xbrl_file_bytes()
on either the original or rendered HTML — both contain the same data.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Playwright availability guard
# ---------------------------------------------------------------------------
try:
    from playwright.async_api import async_playwright
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    async_playwright = None  # type: ignore[assignment]
    _PLAYWRIGHT_AVAILABLE = False


# ---------------------------------------------------------------------------
# Section code → HTML template class name
# ---------------------------------------------------------------------------
SECTION_MAP: dict[str, str] = {
    "100010": "FilingInformation",
    "200100": "IndependentAuditorsReport",
    "300200": "StatementOfFinancialPositionCurrentNonCurrent",
    "300250": "StatementOfFinancialPositionOrderOfLiquidity",   # bank / unclassified BS
    "300400": "StatementOfIncomeFunctionOfExpense",
    "300450": "StatementOfIncomeNatureOfExpense",               # nature-of-expense IS variant
    "300500": "StatementOfOtherComprehensiveIncomeBeforeTax",
    "300600": "StatementOfChangesInEquity",
    "300700": "StatementOfCashFlowsIndirectMethod",
    "400100": "NotesFormingPartOfAccounts",
}

REQUIRED_SECTIONS: list[str] = list(SECTION_MAP.keys())

# CSS selector for the submit / display button
_SUBMIT_SELECTOR = ".displayResult"

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class RenderResult:
    rendered_path: Path | None = None
    sections_found: list[str] = field(default_factory=list)
    sections_missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


# ---------------------------------------------------------------------------
# Public render function
# ---------------------------------------------------------------------------

async def render_xbrl_html(
    source_path: Path,
    output_path: Path,
    section_codes: list[str] | None = None,
) -> RenderResult:
    """
    Open the SA XBRL HTML viewer, select required sections, capture rendered HTML.

    Args:
        source_path:   Path to the downloaded SA XBRL HTML viewer file.
        output_path:   Where to write the rendered HTML snapshot.
        section_codes: Section codes to select (default: REQUIRED_SECTIONS).
                       Codes not present in SECTION_MAP are ignored.

    Returns:
        RenderResult with rendered_path, sections found/missing, and any warnings.
        On error, rendered_path is None and error is set.
    """
    if section_codes is None:
        section_codes = REQUIRED_SECTIONS

    result = RenderResult()

    if not _PLAYWRIGHT_AVAILABLE:
        result.error = (
            "playwright is not installed. "
            "Run: pip install playwright && playwright install chromium"
        )
        return result

    if not source_path.exists():
        result.error = f"Source file not found: {source_path}"
        return result

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                page = await browser.new_page()

                # Load the local file via file:// URL
                file_url = f"file://{source_path.resolve()}"
                await page.goto(file_url, wait_until="domcontentloaded")

                # Select each required section checkbox
                sections_found: list[str] = []
                sections_missing: list[str] = []

                for code in section_codes:
                    template_id = SECTION_MAP.get(code)
                    if not template_id:
                        result.warnings.append(f"Unknown section code: {code}")
                        continue

                    cb = page.locator(
                        f"input[name='templateId'][value='{template_id}']"
                    )
                    count = await cb.count()
                    if count > 0:
                        await cb.check()
                        sections_found.append(code)
                        log.debug("Checked section %s (%s)", code, template_id)
                    else:
                        sections_missing.append(code)
                        result.warnings.append(
                            f"Section {code} ({template_id}) not found in HTML"
                        )
                        log.warning(
                            "Section %s (%s) not found in %s",
                            code, template_id, source_path.name,
                        )

                result.sections_found = sections_found
                result.sections_missing = sections_missing

                if not sections_found:
                    result.error = "No sections found in HTML — not a valid SA XBRL viewer"
                    return result

                # Click the submit / display button
                submit_btn = page.locator(_SUBMIT_SELECTOR)
                if await submit_btn.count() > 0:
                    await submit_btn.click()
                    await page.wait_for_timeout(800)
                else:
                    result.warnings.append(
                        f"Submit button ({_SUBMIT_SELECTOR}) not found — HTML may render without it"
                    )

                # Capture full rendered HTML
                rendered_html = await page.content()

                # Write to output_path
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(rendered_html, encoding="utf-8")
                result.rendered_path = output_path
                log.info(
                    "Rendered %d sections → %s (%d bytes)",
                    len(sections_found),
                    output_path.name,
                    len(rendered_html.encode()),
                )

            finally:
                await browser.close()

    except Exception as exc:
        log.exception("Playwright render failed for %s", source_path)
        result.error = f"Render error: {exc}"

    return result


# ---------------------------------------------------------------------------
# Traceability helpers
# ---------------------------------------------------------------------------

def sections_to_json(codes: list[str]) -> str:
    """Serialize selected section codes list to JSON string for DB storage."""
    return json.dumps(codes)


def rendered_output_path(original_path: Path) -> Path:
    """Return the conventional rendered file path alongside the original."""
    return original_path.with_name(original_path.stem + "_rendered.html")
