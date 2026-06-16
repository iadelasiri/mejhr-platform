"""
Phase 2F.1 — Batch validation: XBRL render + raw fact extraction.

Runs discovery → download → render → parse for each target symbol and
prints a per-symbol report.  Idempotent: already-downloaded files are
skipped; already-rendered files are skipped.

Usage (from repo root):
    docker compose exec backend python scripts/batch_validate_xbrl.py

Hard rules:
  - No normalization
  - No ratios
  - No inferred values
  - Official Saudi Exchange files only
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("batch_validate")

TARGET_SYMBOLS = ["2222", "2020", "4263", "2050", "1120"]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers that re-use task internals
# ─────────────────────────────────────────────────────────────────────────────

async def _create_job(job_type: str) -> str:
    from app.workers.tasks_xbrl import _create_job as _cj
    return await _cj(job_type, triggered_by="batch_validate")


async def run_discovery(symbol: str) -> dict:
    from app.workers.tasks_xbrl import _run_xbrl_discovery
    job_id = await _create_job("xbrl_discovery")
    return await _run_xbrl_discovery(job_id, target_symbol=symbol)


async def run_download(symbol: str) -> dict:
    from app.workers.tasks_xbrl import _run_xbrl_download
    job_id = await _create_job("xbrl_download")
    return await _run_xbrl_download(job_id, target_symbol=symbol)


async def run_render(symbol: str) -> dict:
    from app.workers.tasks_xbrl import _run_xbrl_render
    job_id = await _create_job("xbrl_render")
    return await _run_xbrl_render(job_id, target_symbol=symbol)


async def run_parse(symbol: str) -> dict:
    from app.workers.tasks_xbrl import _run_xbrl_parse
    job_id = await _create_job("xbrl_parse")
    return await _run_xbrl_parse(job_id, target_symbol=symbol)


# ─────────────────────────────────────────────────────────────────────────────
# Per-symbol state query
# ─────────────────────────────────────────────────────────────────────────────

async def query_symbol_state(symbol: str) -> dict:
    """Return current DB state for this symbol."""
    from app.core.database import engine
    from sqlalchemy import text

    async with engine.connect() as conn:
        # Filings
        filings_rows = await conn.execute(text(
            "SELECT f.id, f.xbrl_url, f.fiscal_year, f.period, f.import_status "
            "FROM xbrl_filings f "
            "WHERE f.symbol = :sym "
            "ORDER BY f.fiscal_year DESC NULLS LAST"
        ), {"sym": symbol})
        filings = [dict(r._mapping) for r in filings_rows]

        # XBRL files
        files_rows = await conn.execute(text(
            "SELECT xf.id, xf.local_path, xf.rendered_path, xf.render_status, "
            "       xf.selected_sections, xf.rendered_at, xf.download_status "
            "FROM xbrl_files xf "
            "JOIN xbrl_filings f ON f.id = xf.filing_id "
            "WHERE f.symbol = :sym "
            "ORDER BY f.fiscal_year DESC NULLS LAST"
        ), {"sym": symbol})
        files = [dict(r._mapping) for r in files_rows]

        # Fact counts by statement type
        facts_rows = await conn.execute(text(
            "SELECT ri.statement_type, COUNT(*) as cnt "
            "FROM xbrl_raw_items ri "
            "WHERE ri.symbol = :sym "
            "GROUP BY ri.statement_type "
            "ORDER BY ri.statement_type"
        ), {"sym": symbol})
        facts_by_type = {r.statement_type: r.cnt for r in facts_rows}

    return {
        "symbol": symbol,
        "filings": filings,
        "files": files,
        "facts_by_type": facts_by_type,
        "total_facts": sum(facts_by_type.values()),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main batch loop
# ─────────────────────────────────────────────────────────────────────────────

async def process_symbol(symbol: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "symbol": symbol,
        "discovery": None,
        "download": None,
        "render": None,
        "parse": None,
        "state": None,
        "error": None,
    }

    print(f"\n{'='*60}")
    print(f"  {symbol}")
    print(f"{'='*60}")

    # 1. Discovery
    print(f"  [1/4] Discovery ...", flush=True)
    try:
        d = await run_discovery(symbol)
        result["discovery"] = d
        blocked = d.get("endpoint_blocked", False)
        found = d.get("filings_found", 0)
        inserted = d.get("filings_inserted", 0)
        print(f"        filings_found={found}  inserted={inserted}  blocked={blocked}"
              + (f"  error={d.get('error')}" if d.get("error") else ""))
    except Exception as exc:
        result["error"] = f"discovery: {exc}"
        print(f"        FAILED: {exc}")
        return result

    # 2. Download
    print(f"  [2/4] Download ...", flush=True)
    try:
        dl = await run_download(symbol)
        result["download"] = dl
        downloaded = dl.get("files_downloaded", 0)
        skipped = dl.get("files_skipped", 0)
        failed = dl.get("files_failed", 0)
        print(f"        downloaded={downloaded}  skipped={skipped}  failed={failed}"
              + (f"  error={dl.get('error')}" if dl.get("error") else ""))
    except Exception as exc:
        result["error"] = f"download: {exc}"
        print(f"        FAILED: {exc}")
        return result

    # 3. Render
    print(f"  [3/4] Render ...", flush=True)
    try:
        rn = await run_render(symbol)
        result["render"] = rn
        rendered = rn.get("files_rendered", 0)
        r_skipped = rn.get("files_skipped", 0)
        r_failed = rn.get("files_failed", 0)
        sections_found = rn.get("sections_found", 0)
        sections_missing = rn.get("sections_missing", 0)
        print(f"        rendered={rendered}  skipped={r_skipped}  failed={r_failed}"
              f"  sections_found={sections_found}  sections_missing={sections_missing}"
              + (f"  warnings={rn.get('warnings')}" if rn.get("warnings") else ""))
    except Exception as exc:
        result["error"] = f"render: {exc}"
        print(f"        FAILED: {exc}")
        return result

    # 4. Parse
    print(f"  [4/4] Parse ...", flush=True)
    try:
        ps = await run_parse(symbol)
        result["parse"] = ps
        facts_found = ps.get("facts_found", 0)
        facts_inserted = ps.get("facts_inserted", 0)
        files_parsed = ps.get("files_parsed", 0)
        files_failed = ps.get("files_failed", 0)
        print(f"        files_parsed={files_parsed}  files_failed={files_failed}"
              f"  facts_found={facts_found}  facts_inserted={facts_inserted}"
              + (f"  error={ps.get('error')}" if ps.get("error") else ""))
    except Exception as exc:
        result["error"] = f"parse: {exc}"
        print(f"        FAILED: {exc}")
        return result

    # 5. State query
    try:
        state = await query_symbol_state(symbol)
        result["state"] = state
        if state["facts_by_type"]:
            print(f"        facts by statement_type:")
            for stype, cnt in sorted(state["facts_by_type"].items()):
                print(f"          {stype}: {cnt}")
    except Exception as exc:
        print(f"        state query failed: {exc}")

    return result


async def main():
    print("Phase 2F.1 — Batch XBRL Validation")
    print(f"Symbols: {TARGET_SYMBOLS}")
    print(f"Started: {datetime.now(timezone.utc).isoformat()}")

    results = []
    for symbol in TARGET_SYMBOLS:
        r = await process_symbol(symbol)
        results.append(r)

    # ─── Final Report ───
    print(f"\n\n{'='*60}")
    print("  FINAL REPORT — Phase 2F.1")
    print(f"{'='*60}")

    successful = []
    failed = []
    total_facts = 0

    for r in results:
        symbol = r["symbol"]
        state = r.get("state") or {}
        sym_facts = state.get("total_facts", 0)
        parse = r.get("parse") or {}
        has_error = bool(r.get("error"))
        has_parse_error = bool(parse.get("error"))

        if has_error or has_parse_error:
            failed.append(symbol)
        elif parse.get("files_parsed", 0) > 0 and sym_facts > 0:
            successful.append(symbol)
        elif r.get("discovery", {}).get("filings_found", 0) == 0:
            # No filing found — not a failure, but not success
            failed.append(symbol)
        else:
            failed.append(symbol)

        total_facts += sym_facts

    print(f"\nSymbols tested:     {len(TARGET_SYMBOLS)}")
    print(f"Successful:         {len(successful)}  {successful}")
    print(f"Failed/no-filing:   {len(failed)}  {failed}")
    print(f"Total facts in DB:  {total_facts}")

    print(f"\nPer-symbol breakdown:")
    print(f"{'Symbol':<8} {'Filings':>8} {'Downloaded':>10} {'Rendered':>9} {'Facts':>7} {'Error'}")
    print("-" * 65)
    for r in results:
        symbol = r["symbol"]
        disc = r.get("discovery") or {}
        dl = r.get("download") or {}
        rn = r.get("render") or {}
        state = r.get("state") or {}
        err = r.get("error") or (r.get("parse") or {}).get("error") or ""
        print(
            f"{symbol:<8}"
            f"{disc.get('filings_found', 0):>8}"
            f"{dl.get('files_downloaded', 0) + dl.get('files_skipped', 0):>10}"
            f"{rn.get('files_rendered', 0) + rn.get('files_skipped', 0):>9}"
            f"{state.get('total_facts', 0):>7}"
            f"  {err[:40] if err else 'OK'}"
        )

    print(f"\nCompleted: {datetime.now(timezone.utc).isoformat()}")
    print("\nHard stop: Phase 2G (normalization) NOT started.")

    # Return non-zero exit if any symbol failed
    if failed:
        print(f"\nWARNING: {len(failed)} symbol(s) did not produce facts: {failed}")
        # Don't fail the script — missing filings are expected for some symbols


if __name__ == "__main__":
    asyncio.run(main())
