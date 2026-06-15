"""
XBRL raw fact parser for Saudi Exchange official filings.

Supports:
  - Standard XBRL XML instance documents (.xbrl, .xml)
  - Inline XBRL (iXBRL) embedded in XHTML (.xhtml, .html)

Returns raw ParsedFact records only.  Nothing is normalised or mapped.
Phase 2G normalization reads from xbrl_raw_items; it does not live here.

CLI usage::
    docker compose exec backend python -m app.pipeline.exchange.xbrl_parser /path/to/file.xbrl
"""

from __future__ import annotations

import io
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import xml.etree.ElementTree as ET

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Saudi Exchange HTML viewer constants
# ─────────────────────────────────────────────────────────────────────────────

# Marker bytes that identify a Saudi Exchange XBRL HTML viewer file
_SA_VIEWER_MARKER = b"templateCheck-div"
_SA_VIEWER_MARKER2 = b"templateIdClass"

# Section class → statement_type mapping (also used by xbrl_renderer.py)
_SA_SECTION_STMT_TYPE: dict[str, str] = {
    "FilingInformation": "filing_info",
    "IndependentAuditorsReport": "auditors_report",
    "StatementOfFinancialPositionCurrentNonCurrent": "balance_sheet",
    "StatementOfIncomeFunctionOfExpense": "income_statement",
    "StatementOfOtherComprehensiveIncomeBeforeTax": "income_statement",
    "StatementOfChangesInEquity": "changes_in_equity",
    "StatementOfCashFlowsIndirectMethod": "cash_flow",
    "NotesFormingPartOfAccounts": "notes",
}

# Balance sheet sections where the date is an instant (end-of-period snapshot)
_SA_BS_SECTIONS = frozenset({
    "StatementOfFinancialPositionCurrentNonCurrent",
})

# Sections whose table structure is narrative/notes — skip numeric extraction
_SA_SKIP_PARSE_SECTIONS = frozenset({
    "IndependentAuditorsReport",
    "NotesFormingPartOfAccounts",
})

# Pre-compiled regexes for the SA viewer HTML parser.
# Attribute quotes matched as ['""] to handle original single-quote HTML
# and double-quote output from Playwright DOM serialisation.
_Q = r"""['"]"""

_SA_SECTION_DIV_RE = re.compile(
    r"<div\s+class=" + _Q + r"(" + "|".join(_SA_SECTION_STMT_TYPE.keys()) + r")" + _Q + r"[\s>]",
    re.DOTALL,
)
_SA_GRIDTABLE_RE = re.compile(
    r"<table\s+class=" + _Q + r"gridtable" + _Q + r"[^>]*>(.*?)</table>",
    re.DOTALL,
)
_SA_TBODY_RE = re.compile(r"<tbody[^>]*>(.*?)</tbody>", re.DOTALL)
_SA_TR_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL)
_SA_TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)
_SA_DATE_RE = re.compile(r">(\d{4}-\d{2}-\d{2})<")
_SA_ARB_SPAN_RE = re.compile(
    r"<span\s+class=" + _Q + r"arb" + _Q + r">(.*?)</span>", re.DOTALL
)
_SA_TAG_RE = re.compile(r"<[^>]+>")
_SA_ENTITY_RE = re.compile(r"&(?:#\d+|[a-zA-Z]+);")
_SA_WHITESPACE_RE = re.compile(r"\s+")
_SA_INDENT_RE = re.compile(r"^[\s ]+")  # strip leading &nbsp; / spaces used for indent


def _sa_strip_html(fragment: str) -> str:
    """Remove HTML tags, decode common entities, collapse whitespace."""
    frag = fragment.replace("&nbsp;", " ").replace("&#160;", " ").replace("\u00a0", " ")
    frag = _SA_ENTITY_RE.sub("", frag)
    frag = _SA_TAG_RE.sub("", frag)
    return _SA_WHITESPACE_RE.sub(" ", frag).strip()


def _sa_label_from_td(td_inner: str) -> str:
    """Extract Arabic label text from a label <td> (first column of a data row)."""
    # Prefer text inside <span class='arb'>
    m = _SA_ARB_SPAN_RE.search(td_inner)
    raw = m.group(1) if m else td_inner
    label = _sa_strip_html(raw)
    # Strip leading non-breaking space indentation (used for tree indentation)
    label = _SA_INDENT_RE.sub("", label).strip()
    return label


def _parse_sa_html_viewer(html_text: str) -> list[ParsedFact]:
    """
    Parse a Saudi Exchange XBRL HTML viewer file.

    The viewer embeds all financial statement data in hidden <div> sections.
    Each section contains a <table class='gridtable'> with:
      - Two header rows: period start dates and period end dates
      - A <tbody> with rows of (Arabic label, value_col1, value_col2, ...)

    One ParsedFact is emitted per (section, label_row, period_column) where
    the cell value is non-empty.  No normalization is performed.
    """
    facts: list[ParsedFact] = []

    # Find all section div start positions
    section_matches = list(_SA_SECTION_DIV_RE.finditer(html_text))
    if not section_matches:
        return facts

    for idx, match in enumerate(section_matches):
        section_class = match.group(1)
        stmt_type = _SA_SECTION_STMT_TYPE.get(section_class, "unknown")
        is_bs = section_class in _SA_BS_SECTIONS

        if section_class in _SA_SKIP_PARSE_SECTIONS:
            continue

        # Section content: from end of opening div tag to next section start
        sec_start = match.end()
        sec_end = (
            section_matches[idx + 1].start()
            if idx + 1 < len(section_matches)
            else len(html_text)
        )
        sec_html = html_text[sec_start:sec_end]

        # Find the gridtable inside this section
        gt_match = _SA_GRIDTABLE_RE.search(sec_html)
        if not gt_match:
            continue
        grid_html = gt_match.group(1)

        # Partition all <tr> rows into header rows (contain <th>) and data rows
        # (contain <td>).  This handles two layouts:
        #   - Original HTML: header <tr>s are before <tbody>, data <tr>s inside
        #   - Playwright rendered HTML: ALL rows are wrapped in <tbody> elements;
        #     header rows still use <th>, data rows use <td>.
        all_rows = _SA_TR_RE.findall(grid_html)
        th_rows = [r for r in all_rows if "<th" in r and "<td" not in r]
        data_rows = [r for r in all_rows if "<td" in r]

        # Date header rows: th_rows that contain date patterns
        date_th_rows = [r for r in th_rows if _SA_DATE_RE.search(r)]

        start_dates: list[date | None] = []
        end_dates: list[date | None] = []

        if len(date_th_rows) >= 1:
            start_dates = [
                _to_date(s) for s in _SA_DATE_RE.findall(date_th_rows[0])
            ]
        if len(date_th_rows) >= 2:
            end_dates = [
                _to_date(s) for s in _SA_DATE_RE.findall(date_th_rows[1])
            ]

        # Normalise to equal-length lists
        n_periods = max(len(start_dates), len(end_dates))
        if n_periods == 0:
            continue

        while len(start_dates) < n_periods:
            start_dates.append(None)
        while len(end_dates) < n_periods:
            end_dates.append(None)

        # Pre-compute context refs and period tuples
        periods: list[tuple[date | None, date | None, date | None, str | None]] = []
        for i in range(n_periods):
            sd = start_dates[i]
            ed = end_dates[i]
            if is_bs:
                # Balance sheet: instant snapshot at end date
                instant = ed
                ctx = f"INSTANT__{ed.isoformat()}" if ed else None
            else:
                instant = None
                ctx = (
                    f"PERIOD__{sd.isoformat() if sd else 'None'}"
                    f"__{ed.isoformat() if ed else 'None'}"
                )
            periods.append((sd, ed, instant, ctx))

        # Parse data rows

        for row_html in data_rows:
            tds = _SA_TD_RE.findall(row_html)
            if not tds:
                continue

            # First td = label
            label = _sa_label_from_td(tds[0])
            if not label:
                continue

            value_tds = tds[1:]

            for period_idx, (p_start, p_end, instant, ctx_ref) in enumerate(periods):
                if period_idx >= len(value_tds):
                    break

                val_raw = _sa_strip_html(value_tds[period_idx])
                if not val_raw:
                    continue

                facts.append(ParsedFact(
                    concept_name=label[:500],
                    concept_namespace="sa_xbrl_viewer",
                    label_ar=label[:1000],
                    label_en=None,
                    value_raw=val_raw[:2000],
                    value_numeric=_to_decimal(val_raw),
                    unit_ref=None,
                    decimals=None,
                    context_ref=ctx_ref,
                    period_start=p_start if not is_bs else None,
                    period_end=p_end,
                    instant_date=instant,
                    statement_type=stmt_type,
                ))

    return facts


# ─────────────────────────────────────────────────────────────────────────────
# Namespace constants
# ─────────────────────────────────────────────────────────────────────────────
_XBRLI_NS = "http://www.xbrl.org/2003/instance"
_IX_NS = "http://www.xbrl.org/2013/inlineXBRL"
_IX_NS_2011 = "http://www.xbrl.org/2011/inlineXBRL"
_LINK_NS = "http://www.xbrl.org/2003/linkbase"
_XLINK_NS = "http://www.w3.org/1999/xlink"

# Namespaces whose top-level elements are never XBRL facts
_SKIP_NS = frozenset({
    _XBRLI_NS, _LINK_NS, _XLINK_NS,
    "http://www.w3.org/1999/xlink",
    "http://www.w3.org/2001/XMLSchema-instance",
    "http://www.w3.org/2001/XMLSchema",
    "http://www.xbrl.org/2003/linkbase",
})

# Statement-type heuristics (minimal detection, not normalisation)
_CF_RE = re.compile(r"cashflow|cash_flow|operatingactivit|investingactivit|financingactivit", re.I)
_IS_RE = re.compile(r"revenue|profit|loss|income|expense|costofsale|earn|gross|ebit", re.I)
_BS_RE = re.compile(r"asset|liabilit|equity|capital|inventor|receivable|payable|propertyplant", re.I)
_EQ_RE = re.compile(r"changesinequity|changesofequity|componentofequity", re.I)

# Parentheses notation for negative numbers: (1,234) → -1234
_PAREN_NEG_RE = re.compile(r"^\(([0-9,.\s]+)\)$")


# ─────────────────────────────────────────────────────────────────────────────
# Public data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ParsedFact:
    concept_name: str
    concept_namespace: str | None
    label_ar: str | None
    label_en: str | None
    value_raw: str | None
    value_numeric: Decimal | None
    unit_ref: str | None
    decimals: int | None
    context_ref: str | None
    period_start: date | None
    period_end: date | None
    instant_date: date | None
    statement_type: str


@dataclass
class ParseResult:
    facts: list[ParsedFact] = field(default_factory=list)
    error: str | None = None
    parse_note: str = ""
    file_format: str = "unknown"  # "xbrl_xml" | "ixbrl" | "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _clark(ns: str, local: str) -> str:
    return f"{{{ns}}}{local}"


_CLARK_RE = re.compile(r"\{([^}]*)\}(.*)")


def _split_clark(tag: str) -> tuple[str | None, str]:
    m = _CLARK_RE.match(tag)
    return (m.group(1), m.group(2)) if m else (None, tag)


def _clean_numeric(s: str) -> str | None:
    s = s.strip().replace("\xa0", "").replace(" ", "").replace(" ", "")
    m = _PAREN_NEG_RE.match(s)
    if m:
        s = "-" + m.group(1)
    s = s.replace(",", "")
    return s if s else None


def _to_decimal(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    cleaned = _clean_numeric(raw)
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _to_date(s: str | None) -> date | None:
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _to_int(s: str | None) -> int | None:
    if not s:
        return None
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def _detect_statement_type(concept_name: str) -> str:
    if _CF_RE.search(concept_name):
        return "cash_flow"
    if _EQ_RE.search(concept_name):
        return "changes_in_equity"
    if _IS_RE.search(concept_name):
        return "income_statement"
    if _BS_RE.search(concept_name):
        return "balance_sheet"
    return "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# Context and unit parsing (shared by both XBRL and iXBRL)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _XBRLContext:
    id: str
    period_start: date | None
    period_end: date | None
    instant_date: date | None


def _parse_contexts(root: ET.Element) -> dict[str, _XBRLContext]:
    contexts: dict[str, _XBRLContext] = {}
    for ctx in root.iter(_clark(_XBRLI_NS, "context")):
        ctx_id = ctx.get("id", "")
        period = ctx.find(_clark(_XBRLI_NS, "period"))
        start = end = instant = None
        if period is not None:
            el_start = period.find(_clark(_XBRLI_NS, "startDate"))
            el_end = period.find(_clark(_XBRLI_NS, "endDate"))
            el_inst = period.find(_clark(_XBRLI_NS, "instant"))
            start = _to_date(el_start.text if el_start is not None else None)
            end = _to_date(el_end.text if el_end is not None else None)
            instant = _to_date(el_inst.text if el_inst is not None else None)
        contexts[ctx_id] = _XBRLContext(ctx_id, start, end, instant)
    return contexts


def _parse_units(root: ET.Element) -> dict[str, str]:
    units: dict[str, str] = {}
    for unit in root.iter(_clark(_XBRLI_NS, "unit")):
        unit_id = unit.get("id", "")
        measure = unit.find(_clark(_XBRLI_NS, "measure"))
        if measure is not None and measure.text:
            units[unit_id] = measure.text.strip()
    return units


# ─────────────────────────────────────────────────────────────────────────────
# Standard XBRL XML parser
# ─────────────────────────────────────────────────────────────────────────────

def _parse_standard_xbrl(root: ET.Element) -> list[ParsedFact]:
    """
    Parse a standard XBRL instance document.
    Facts are direct children of the root whose contextRef attribute is present.
    """
    contexts = _parse_contexts(root)
    units = _parse_units(root)
    facts: list[ParsedFact] = []

    for elem in root:
        ns, local = _split_clark(elem.tag)
        if not ns or ns in _SKIP_NS:
            continue
        ctx_ref = elem.get("contextRef")
        if not ctx_ref:
            continue

        ctx = contexts.get(ctx_ref, _XBRLContext(ctx_ref, None, None, None))
        unit_id = elem.get("unitRef")
        unit_str = units.get(unit_id, unit_id) if unit_id else None

        raw = (elem.text or "").strip()

        facts.append(ParsedFact(
            concept_name=local,
            concept_namespace=ns,
            label_ar=None,
            label_en=None,
            value_raw=raw or None,
            value_numeric=_to_decimal(raw),
            unit_ref=unit_str,
            decimals=_to_int(elem.get("decimals")),
            context_ref=ctx_ref,
            period_start=ctx.period_start,
            period_end=ctx.period_end,
            instant_date=ctx.instant_date,
            statement_type=_detect_statement_type(local),
        ))

    return facts


# ─────────────────────────────────────────────────────────────────────────────
# Inline XBRL (iXBRL) parser
# ─────────────────────────────────────────────────────────────────────────────

def _parse_ixbrl(root: ET.Element, ns_map: dict[str, str]) -> list[ParsedFact]:
    """
    Parse an inline XBRL document (XHTML with ix: namespace).
    Facts are ix:nonFraction (numeric) and ix:nonNumeric (text) elements.
    """
    contexts = _parse_contexts(root)
    units = _parse_units(root)
    facts: list[ParsedFact] = []

    for ix_ns in (_IX_NS, _IX_NS_2011):
        for tag in ("nonFraction", "nonNumeric"):
            for elem in root.iter(_clark(ix_ns, tag)):
                name_attr = elem.get("name", "")
                if not name_attr:
                    continue

                # Resolve "prefix:LocalName" to (namespace_uri, local_name)
                if ":" in name_attr:
                    prefix, local = name_attr.split(":", 1)
                    resolved_ns = ns_map.get(prefix)
                else:
                    local = name_attr
                    resolved_ns = None

                if not local:
                    continue

                ctx_ref = elem.get("contextRef")
                unit_id = elem.get("unitRef")

                ctx = contexts.get(ctx_ref or "", _XBRLContext(ctx_ref or "", None, None, None))
                unit_str = units.get(unit_id, unit_id) if unit_id else None

                # Gather all text content (the value may span nested elements)
                raw = "".join(elem.itertext()).strip()

                value_num = _to_decimal(raw) if tag == "nonFraction" else None

                facts.append(ParsedFact(
                    concept_name=local,
                    concept_namespace=resolved_ns,
                    label_ar=None,
                    label_en=None,
                    value_raw=raw[:2000] if raw else None,
                    value_numeric=value_num,
                    unit_ref=unit_str,
                    decimals=_to_int(elem.get("decimals")),
                    context_ref=ctx_ref,
                    period_start=ctx.period_start,
                    period_end=ctx.period_end,
                    instant_date=ctx.instant_date,
                    statement_type=_detect_statement_type(local),
                ))

    return facts


# ─────────────────────────────────────────────────────────────────────────────
# Format detection
# ─────────────────────────────────────────────────────────────────────────────

def _extract_ns_map(content: bytes) -> dict[str, str]:
    """Two-pass: extract prefix→URI namespace map without building a full tree."""
    ns_map: dict[str, str] = {}
    try:
        for event, data in ET.iterparse(io.BytesIO(content), events=["start-ns"]):
            prefix, uri = data
            ns_map[prefix] = uri
    except ET.ParseError:
        pass
    return ns_map


def _is_sa_html_viewer(content_head: bytes) -> bool:
    """Return True if content looks like a Saudi Exchange XBRL HTML viewer file."""
    return _SA_VIEWER_MARKER in content_head and _SA_VIEWER_MARKER2 in content_head


def _is_ixbrl(root: ET.Element, content_head: bytes) -> bool:
    _, local = _split_clark(root.tag)
    if local.lower() in ("html", "xhtml"):
        return True
    return (
        b"http://www.xbrl.org/2013/inlineXBRL" in content_head
        or b"ix:nonFraction" in content_head
        or b"ix:nonNumeric" in content_head
        or b"ix:header" in content_head
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def parse_xbrl_file_bytes(content: bytes, extension: str = ".xbrl") -> ParseResult:
    """
    Parse XBRL file from raw bytes.  Never raises — errors are returned in ParseResult.

    Supported formats (detected automatically):
      - Saudi Exchange XBRL HTML viewer (sa_html_viewer)
      - Inline XBRL / iXBRL in XHTML (ixbrl)
      - Standard XBRL XML instance document (xbrl_xml)

    Args:
        content:   Raw file bytes.
        extension: File extension hint (".xbrl", ".xml", ".xhtml", ".html").

    Returns:
        ParseResult with facts list and any error message.
    """
    if not content:
        return ParseResult(error="Empty file content", parse_note="empty", file_format="unknown")

    content_head = content[:8192]

    # ── 1. Saudi Exchange XBRL HTML viewer (must be checked before XML parsing)
    if _is_sa_html_viewer(content_head):
        try:
            html_text = content.decode("utf-8", errors="replace")
        except Exception as exc:
            return ParseResult(
                error=f"UTF-8 decode error: {exc}",
                parse_note="decode_failed",
                file_format="unknown",
            )
        facts = _parse_sa_html_viewer(html_text)
        return ParseResult(
            facts=facts,
            error=None,
            parse_note=f"Parsed {len(facts)} fact(s) as sa_html_viewer",
            file_format="sa_html_viewer",
        )

    # ── 2. Standard XBRL XML or iXBRL (requires valid XML)
    ns_map = _extract_ns_map(content)

    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        return ParseResult(
            error=f"XML parse error: {exc}",
            parse_note="xml_parse_failed",
            file_format="unknown",
        )

    if _is_ixbrl(root, content_head):
        file_format = "ixbrl"
        facts = _parse_ixbrl(root, ns_map)
    else:
        file_format = "xbrl_xml"
        facts = _parse_standard_xbrl(root)

    return ParseResult(
        facts=facts,
        error=None,
        parse_note=f"Parsed {len(facts)} fact(s) as {file_format}",
        file_format=file_format,
    )


def parse_xbrl_file(path: Path) -> ParseResult:
    """
    Parse XBRL file from disk.  Never raises.

    Suitable for use with asyncio.to_thread() from an async Celery task.
    """
    try:
        content = path.read_bytes()
    except OSError as exc:
        return ParseResult(
            error=f"File read error: {exc}",
            parse_note="read_failed",
            file_format="unknown",
        )
    return parse_xbrl_file_bytes(content, path.suffix)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if len(sys.argv) < 2:
        print("Usage: xbrl_parser.py <file_path>")
        sys.exit(1)

    path = Path(sys.argv[1])
    result = parse_xbrl_file(path)

    print(f"Format  : {result.file_format}")
    print(f"Facts   : {len(result.facts)}")
    print(f"Note    : {result.parse_note}")
    if result.error:
        print(f"Error   : {result.error}")
        sys.exit(1)

    for f in result.facts[:10]:
        print(
            f"  {f.concept_name:<50} "
            f"{str(f.value_raw or '')[:20]:<20} "
            f"[{f.statement_type}]"
        )

    sys.exit(0)
