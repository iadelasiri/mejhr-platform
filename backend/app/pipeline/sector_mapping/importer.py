"""
Sector mapping importer — CSV-based company→sector assignment.

Source: backend/data/sector_mapping.csv
        Each row maps one company symbol to an official TASI sector code.

Rules:
  - sector_code must exist in the sectors table (validated before import).
  - symbol must exist in the companies table (unknown symbols are reported).
  - source_url is required.
  - Only confidence='verified' or 'approximate' rows are imported.
    Rows with confidence='needs_review' are skipped and reported.
  - Import is idempotent: re-running updates existing mappings.
  - Companies not in the CSV keep mapping_status='unmapped_sector'.
  - Successfully mapped companies get mapping_status='mapped'.

CSV format (header required):
  symbol,company_name,sector_code,sector_name,source_url,
  mapping_source,reviewed_at,confidence

  symbol         — TASI trading symbol (e.g. "1010")
  company_name   — display name, for human readability only
  sector_code    — official TASI sector index code (e.g. "TBNI")
  sector_name    — sector English name, for human readability only
  source_url     — URL where this assignment was confirmed
  mapping_source — "manual_review" | "official_api" | ...
  reviewed_at    — ISO date (e.g. "2026-06-15")
  confidence     — "verified" | "approximate" | "needs_review"

CLI usage::
    docker compose exec backend python -m app.pipeline.sector_mapping.importer

Exit codes:
  0 — completed (even if 0 mappings applied)
  1 — unexpected error
"""

from __future__ import annotations

import csv
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

_ACCEPTED_CONFIDENCE: frozenset[str] = frozenset({"verified", "approximate"})
_REQUIRED_FIELDS: tuple[str, ...] = (
    "symbol", "company_name", "sector_code", "sector_name",
    "source_url", "mapping_source", "reviewed_at", "confidence",
)

DEFAULT_CSV_PATH = Path(__file__).parent.parent.parent.parent / "data" / "sector_mapping.csv"


@dataclass
class MappingRow:
    """One validated row from the sector mapping CSV."""
    symbol: str
    company_name: str
    sector_code: str
    sector_name: str
    source_url: str
    mapping_source: str
    reviewed_at: str
    confidence: str


@dataclass
class ImportResult:
    rows_read: int
    rows_accepted: int
    rows_skipped_confidence: int
    companies_mapped: int
    companies_updated: int
    companies_not_found: int
    invalid_sector_codes: list[str]
    unknown_symbols: list[str]
    error: str | None
    completed_at: str


def load_csv(path: Path) -> tuple[list[MappingRow], list[str]]:
    """
    Read and validate the CSV.  Returns (accepted_rows, error_messages).
    Rows with missing required fields or missing source_url are rejected.
    """
    rows: list[MappingRow] = []
    errors: list[str] = []

    if not path.exists():
        errors.append(f"CSV file not found: {path}")
        return rows, errors

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            errors.append("CSV has no header row")
            return rows, errors

        missing = set(_REQUIRED_FIELDS) - set(reader.fieldnames)
        if missing:
            errors.append(f"CSV missing required columns: {sorted(missing)}")
            return rows, errors

        for i, raw in enumerate(reader, start=2):  # row 1 = header
            symbol = raw.get("symbol", "").strip()
            sector_code = raw.get("sector_code", "").strip()
            source_url = raw.get("source_url", "").strip()
            confidence = raw.get("confidence", "").strip().lower()

            if not symbol:
                errors.append(f"Row {i}: empty symbol — skipped")
                continue
            if not sector_code:
                errors.append(f"Row {i} ({symbol}): empty sector_code — skipped")
                continue
            if not source_url:
                errors.append(f"Row {i} ({symbol}): source_url required — skipped")
                continue

            rows.append(MappingRow(
                symbol=symbol,
                company_name=raw.get("company_name", "").strip(),
                sector_code=sector_code,
                sector_name=raw.get("sector_name", "").strip(),
                source_url=source_url,
                mapping_source=raw.get("mapping_source", "manual_review").strip(),
                reviewed_at=raw.get("reviewed_at", "").strip(),
                confidence=confidence,
            ))

    return rows, errors


async def apply_mappings(
    rows: list[MappingRow],
    db,  # AsyncSession
) -> dict:
    """
    Validate sector codes, look up companies, apply sector_id updates.
    Returns stats dict.
    """
    from sqlalchemy import select
    from app.models.sector import Sector
    from app.models.company import Company

    # Load all known sector codes
    sector_result = await db.execute(select(Sector))
    sector_map: dict[str, Sector] = {
        s.code: s for s in sector_result.scalars().all() if s.code
    }

    stats = {
        "rows_read": len(rows),
        "rows_accepted": 0,
        "rows_skipped_confidence": 0,
        "companies_mapped": 0,
        "companies_updated": 0,
        "companies_not_found": 0,
        "invalid_sector_codes": [],
        "unknown_symbols": [],
    }

    for row in rows:
        # Filter by confidence
        if row.confidence not in _ACCEPTED_CONFIDENCE:
            stats["rows_skipped_confidence"] += 1
            continue

        stats["rows_accepted"] += 1

        # Validate sector code
        sector = sector_map.get(row.sector_code)
        if sector is None:
            if row.sector_code not in stats["invalid_sector_codes"]:
                stats["invalid_sector_codes"].append(row.sector_code)
            log.warning("Invalid sector_code '%s' for symbol %s — skipped", row.sector_code, row.symbol)
            continue

        # Look up company
        result = await db.execute(select(Company).where(Company.symbol == row.symbol))
        company = result.scalar_one_or_none()

        if company is None:
            if row.symbol not in stats["unknown_symbols"]:
                stats["unknown_symbols"].append(row.symbol)
            stats["companies_not_found"] += 1
            log.warning("Symbol '%s' not found in companies table — skipped", row.symbol)
            continue

        mapping_info = {
            "source_url": row.source_url,
            "mapping_source": row.mapping_source,
            "reviewed_at": row.reviewed_at,
            "confidence": row.confidence,
            "sector_name": row.sector_name,
            "imported_at": datetime.now(timezone.utc).isoformat(),
        }

        previously_mapped = company.sector_id is not None
        company.sector_id = sector.id
        company.mapping_status = "mapped"
        company.sector_mapping_info = mapping_info

        if previously_mapped:
            stats["companies_updated"] += 1
        else:
            stats["companies_mapped"] += 1

    return stats


async def run_import(path: Path | None = None) -> ImportResult:
    """Full pipeline: load CSV → validate → apply → return result."""
    from app.core.database import AsyncSessionLocal

    csv_path = path or DEFAULT_CSV_PATH
    completed_at = datetime.now(timezone.utc).isoformat()

    rows, load_errors = load_csv(csv_path)

    if load_errors:
        for err in load_errors:
            log.error("CSV load error: %s", err)
        if not rows:
            return ImportResult(
                rows_read=0, rows_accepted=0, rows_skipped_confidence=0,
                companies_mapped=0, companies_updated=0, companies_not_found=0,
                invalid_sector_codes=[], unknown_symbols=[],
                error="; ".join(load_errors),
                completed_at=completed_at,
            )

    async with AsyncSessionLocal() as db:
        stats = await apply_mappings(rows, db)
        await db.commit()

    return ImportResult(
        rows_read=stats["rows_read"],
        rows_accepted=stats["rows_accepted"],
        rows_skipped_confidence=stats["rows_skipped_confidence"],
        companies_mapped=stats["companies_mapped"],
        companies_updated=stats["companies_updated"],
        companies_not_found=stats["companies_not_found"],
        invalid_sector_codes=stats["invalid_sector_codes"],
        unknown_symbols=stats["unknown_symbols"],
        error="; ".join(load_errors) if load_errors else None,
        completed_at=completed_at,
    )


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    async def main():
        result = await run_import()
        print(f"Rows read       : {result.rows_read}")
        print(f"Rows accepted   : {result.rows_accepted}")
        print(f"Skipped (conf.) : {result.rows_skipped_confidence}")
        print(f"Companies mapped: {result.companies_mapped}")
        print(f"Updated mappings: {result.companies_updated}")
        print(f"Not found       : {result.companies_not_found}")
        if result.invalid_sector_codes:
            print(f"Invalid sectors : {result.invalid_sector_codes}")
        if result.unknown_symbols:
            print(f"Not found syms  : {result.unknown_symbols[:20]}")
        if result.error:
            print(f"Error           : {result.error}")

    asyncio.run(main())
    sys.exit(0)
