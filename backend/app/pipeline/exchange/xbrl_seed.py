"""
Manual XBRL filing seed — registers known XBRL file URLs when discovery is unavailable.

The Saudi Exchange announcement search API (ci_anncmnt/annWdgtSearch) was removed
in a portal rebuild (confirmed 2026-06-16).  Use this CLI to register official
XBRL HTML file URLs obtained directly from the Saudi Exchange portal.

Only official Saudi Exchange URLs are accepted (saudiexchange.sa domain).
No financial values are parsed here — metadata only.

Usage::
    docker compose exec backend python -m app.pipeline.exchange.xbrl_seed \\
        --symbol 2010 \\
        --url "https://www.saudiexchange.sa/Resources/XBRL_DOCS/404_2010_2026-03-12_10-30-00_ARB.html" \\
        --year 2025 \\
        --period Annual

    # Dry-run (no DB write):
    docker compose exec backend python -m app.pipeline.exchange.xbrl_seed \\
        --symbol 2010 --url "https://..." --year 2025 --period Annual --dry-run

Hard rules:
  - Only saudiexchange.sa URLs accepted
  - No normalization, no ratios, no inferred values
  - Idempotent: re-seeding the same URL updates metadata, does not duplicate
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

log = logging.getLogger(__name__)

_ALLOWED_DOMAINS = frozenset({"www.saudiexchange.sa", "saudiexchange.sa"})


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http"):
        raise ValueError(f"URL must be https://: {url}")
    if parsed.netloc not in _ALLOWED_DOMAINS:
        raise ValueError(
            f"Only official saudiexchange.sa URLs are accepted. Got: {parsed.netloc}"
        )


async def seed_xbrl_filing(
    symbol: str,
    url: str,
    fiscal_year: int | None,
    period: str | None,
    language: str = "ar",
    dry_run: bool = False,
) -> dict:
    """
    Upsert an XBRLFiling record for the given symbol + URL.

    Returns a dict with keys: status, filing_id, action (inserted|updated|skipped).
    """
    _validate_url(url)

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy.pool import NullPool
    from app.core.config import settings
    from app.models.company import Company
    from app.models.xbrl import XBRLFiling

    _connect_args: dict = {}
    if "pooler.supabase.com" in settings.DATABASE_URL:
        _connect_args["prepared_statement_cache_size"] = 0

    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, connect_args=_connect_args)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with SessionLocal() as db:
        # Find company
        company_result = await db.execute(
            select(Company).where(Company.symbol == symbol)
        )
        company = company_result.scalar_one_or_none()
        if company is None:
            return {"status": "error", "error": f"Company not found: {symbol}"}

        # Check for existing filing with this URL
        existing_result = await db.execute(
            select(XBRLFiling).where(
                XBRLFiling.symbol == symbol,
                XBRLFiling.xbrl_url == url,
            )
        )
        existing = existing_result.scalar_one_or_none()

        if existing is not None:
            if dry_run:
                return {
                    "status": "dry_run",
                    "action": "would_update",
                    "filing_id": str(existing.id),
                    "symbol": symbol,
                    "url": url,
                }
            # Update mutable fields
            existing.fiscal_year = fiscal_year
            existing.period = period
            existing.language = language
            existing.imported_at = datetime.now(timezone.utc)
            await db.commit()
            return {
                "status": "ok",
                "action": "updated",
                "filing_id": str(existing.id),
                "symbol": symbol,
                "url": url,
            }

        if dry_run:
            return {
                "status": "dry_run",
                "action": "would_insert",
                "symbol": symbol,
                "url": url,
                "fiscal_year": fiscal_year,
                "period": period,
            }

        filing = XBRLFiling(
            company_id=company.id,
            symbol=symbol,
            xbrl_url=url,
            fiscal_year=fiscal_year,
            period=period,
            filing_type="html",
            language=language,
            import_status="pending",
            data_status="official",
            imported_at=datetime.now(timezone.utc),
        )
        db.add(filing)
        await db.commit()
        await db.refresh(filing)
        return {
            "status": "ok",
            "action": "inserted",
            "filing_id": str(filing.id),
            "symbol": symbol,
            "url": url,
            "fiscal_year": fiscal_year,
            "period": period,
        }


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Manually seed an XBRL filing URL into the database."
    )
    parser.add_argument("--symbol", required=True, help="Company symbol e.g. 2010")
    parser.add_argument(
        "--url",
        required=True,
        help="Official Saudi Exchange XBRL file URL (saudiexchange.sa only)",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Fiscal year (integer, e.g. 2025)",
    )
    parser.add_argument(
        "--period",
        default=None,
        help="Fiscal period: Annual | Q1 | Q2 | Q3 | Q4 | H1 | H2",
    )
    parser.add_argument(
        "--lang",
        default="ar",
        choices=["ar", "en"],
        help="File language (default: ar)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without writing to DB",
    )
    args = parser.parse_args()

    try:
        result = asyncio.run(
            seed_xbrl_filing(
                symbol=args.symbol,
                url=args.url,
                fiscal_year=args.year,
                period=args.period,
                language=args.lang,
                dry_run=args.dry_run,
            )
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    import json
    print(json.dumps(result, indent=2))
    if result.get("status") == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
