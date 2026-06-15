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

    Args:
        content:   Raw file bytes.
        extension: File extension hint (".xbrl", ".xml", ".xhtml", ".html").

    Returns:
        ParseResult with facts list and any error message.
    """
    if not content:
        return ParseResult(error="Empty file content", parse_note="empty", file_format="unknown")

    ns_map = _extract_ns_map(content)

    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        return ParseResult(
            error=f"XML parse error: {exc}",
            parse_note="xml_parse_failed",
            file_format="unknown",
        )

    content_head = content[:4096]

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
