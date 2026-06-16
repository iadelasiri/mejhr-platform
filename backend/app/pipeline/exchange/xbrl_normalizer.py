"""
Phase 2G.1 — Limited normalization for Balance Sheet totals and Cash Flow totals.

Scope (Phase 2G.1 only):
  Balance Sheet:  total_assets, total_liabilities, equity
  Cash Flow:      operating_cash_flow, investing_cash_flow, financing_cash_flow, capex

Hard stops: no Income Statement normalization, no bank-specific fields, no ratios,
no screener writes.  Values are stored in absolute SAR (value_numeric × scale).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

# ── Label maps ────────────────────────────────────────────────────────────────

# Balance Sheet — field_name → (label_ar, negate)
_BS_LABELS: dict[str, tuple[str, bool]] = {
    "total_assets":      ("إجمالي الموجودات", False),
    "total_liabilities": ("إجمالي المطلوبات", False),
    "equity":            ("إجمالي حقوق الملكية", False),
}

# Cash Flow — field_name → ordered list of (label_ar, negate); first match wins
# capex: primary label is stored positive in source → negate to outflow convention.
#        2222 fallback label 'نفقات رأسمالية' is already negative → keep as-is.
_CF_LABELS: dict[str, list[tuple[str, bool]]] = {
    "operating_cash_flow": [
        ("صافي التدفقات النقدية من (المستخدمة في) النشاطات التشغيلية", False),
    ],
    "investing_cash_flow": [
        ("صافي التدفقات النقدية من (المستخدمة في) النشاطات الاستثمارية", False),
    ],
    "financing_cash_flow": [
        ("صافي التدفقات النقدية من (المستخدمة في) النشاطات التمويلية", False),
    ],
    "capex": [
        ("شراء ممتلكات وآلات ومعدات", True),
        ("نفقات رأسمالية", False),
    ],
}

_SCALE_LABEL = "مستوى التقريب المستخدم في القوائم المالية"

# ── Internal result types ─────────────────────────────────────────────────────

@dataclass
class _Match:
    field_name: str
    value: Decimal
    raw_item_id: str
    label_ar: str
    context_ref: str | None

@dataclass
class _Conflict:
    field_name: str
    candidates: list[dict[str, Any]]


# ── Public result ─────────────────────────────────────────────────────────────

@dataclass
class NormalizeResult:
    symbol: str
    fiscal_year: int | None
    normalized_id: str | None
    fields_set: list[str]
    fields_missing: list[str]
    conflicts: list[str]
    bs_valid: bool | None
    scale: int | None
    error: str | None


# ── Filing metadata ───────────────────────────────────────────────────────────

async def _get_filing_metadata(db: AsyncSession, symbol: str) -> dict | None:
    from app.models.xbrl import XBRLFiling, XBRLRawItem

    row = await db.execute(
        select(XBRLFiling)
        .where(XBRLFiling.symbol == symbol)
        .order_by(XBRLFiling.fiscal_year.desc().nulls_last())
        .limit(1)
    )
    filing = row.scalar_one_or_none()
    if not filing:
        return None

    info_rows = await db.execute(
        select(XBRLRawItem)
        .where(XBRLRawItem.filing_id == filing.id)
        .where(XBRLRawItem.statement_type == "filing_info")
    )
    info_facts = info_rows.scalars().all()
    if not info_facts:
        return None

    period_ends = [f.period_end for f in info_facts if f.period_end]
    period_starts = [f.period_start for f in info_facts if f.period_start]
    if not period_ends:
        return None

    primary_end: date = max(period_ends)
    primary_start: date = max(period_starts)

    scale = 1_000
    for f in info_facts:
        if f.label_ar == _SCALE_LABEL and f.value_raw:
            if "بالملايين" in f.value_raw:
                scale = 1_000_000
            elif "بالريالات" in f.value_raw:
                scale = 1
            break

    return {
        "filing_id": filing.id,
        "fiscal_year": filing.fiscal_year,
        "period": filing.period,
        "period_type": filing.period_type,
        "period_start": primary_start,
        "period_end": primary_end,
        "scale": scale,
    }


# ── Field resolution ──────────────────────────────────────────────────────────

def _resolve_bs(
    field_name: str,
    label_ar: str,
    negate: bool,
    facts: list,
    period_end: date,
) -> _Match | _Conflict | None:
    candidates = [
        f for f in facts
        if f.label_ar == label_ar
        and f.statement_type == "balance_sheet"
        and f.instant_date == period_end
        and f.value_numeric is not None
    ]
    if not candidates:
        return None
    unique_vals = {f.value_numeric for f in candidates}
    if len(unique_vals) > 1:
        return _Conflict(
            field_name=field_name,
            candidates=[
                {
                    "raw_item_id": str(c.id),
                    "label_ar": c.label_ar,
                    "value": float(c.value_numeric),
                    "context_ref": c.context_ref,
                }
                for c in candidates
            ],
        )
    c = candidates[0]
    val = -c.value_numeric if negate else c.value_numeric
    return _Match(
        field_name=field_name,
        value=val,
        raw_item_id=str(c.id),
        label_ar=c.label_ar,
        context_ref=c.context_ref,
    )


def _resolve_cf(
    field_name: str,
    label_specs: list[tuple[str, bool]],
    facts: list,
    period_start: date,
    period_end: date,
) -> _Match | _Conflict | None:
    for label_ar, negate in label_specs:
        candidates = [
            f for f in facts
            if f.label_ar == label_ar
            and f.statement_type == "cash_flow"
            and f.period_start == period_start
            and f.period_end == period_end
            and f.value_numeric is not None
        ]
        if not candidates:
            continue
        unique_vals = {f.value_numeric for f in candidates}
        if len(unique_vals) > 1:
            return _Conflict(
                field_name=field_name,
                candidates=[
                    {
                        "raw_item_id": str(c.id),
                        "label_ar": c.label_ar,
                        "value": float(c.value_numeric),
                        "context_ref": c.context_ref,
                    }
                    for c in candidates
                ],
            )
        c = candidates[0]
        val = -c.value_numeric if negate else c.value_numeric
        return _Match(
            field_name=field_name,
            value=val,
            raw_item_id=str(c.id),
            label_ar=c.label_ar,
            context_ref=c.context_ref,
        )
    return None


# ── Main entry point ──────────────────────────────────────────────────────────

async def normalize_symbol(symbol: str, db: AsyncSession) -> NormalizeResult:
    from app.models.financial import NormalizationConflict, NormalizedFinancial
    from app.models.xbrl import XBRLRawItem

    meta = await _get_filing_metadata(db, symbol)
    if not meta:
        return NormalizeResult(
            symbol=symbol, fiscal_year=None, normalized_id=None,
            fields_set=[], fields_missing=[], conflicts=[],
            bs_valid=None, scale=None, error="no_filing",
        )

    all_rows = await db.execute(
        select(XBRLRawItem).where(XBRLRawItem.filing_id == meta["filing_id"])
    )
    all_facts = all_rows.scalars().all()

    scale = meta["scale"]
    p_start: date = meta["period_start"]
    p_end: date = meta["period_end"]

    matches: dict[str, _Match] = {}
    conflict_list: list[_Conflict] = []
    missing: list[str] = []

    for field_name, (label_ar, negate) in _BS_LABELS.items():
        r = _resolve_bs(field_name, label_ar, negate, all_facts, p_end)
        if isinstance(r, _Match):
            matches[field_name] = r
        elif isinstance(r, _Conflict):
            conflict_list.append(r)
        else:
            missing.append(field_name)

    for field_name, label_specs in _CF_LABELS.items():
        r = _resolve_cf(field_name, label_specs, all_facts, p_start, p_end)
        if isinstance(r, _Match):
            matches[field_name] = r
        elif isinstance(r, _Conflict):
            conflict_list.append(r)
        else:
            missing.append(field_name)

    field_values: dict[str, Decimal] = {
        fn: m.value * scale for fn, m in matches.items()
    }
    source_map: dict[str, dict] = {
        fn: {
            "raw_item_id": m.raw_item_id,
            "label_ar": m.label_ar,
            "context_ref": m.context_ref,
        }
        for fn, m in matches.items()
    }

    if conflict_list:
        status = "conflict"
    elif missing:
        status = "partial"
    else:
        status = "normalized"

    bs_valid: bool | None = None
    if all(k in field_values for k in ("total_assets", "total_liabilities", "equity")):
        ta = field_values["total_assets"]
        diff_ratio = abs(ta - (field_values["total_liabilities"] + field_values["equity"])) / ta if ta else None
        if diff_ratio is not None:
            bs_valid = diff_ratio < Decimal("0.001")

    # Upsert — SELECT then INSERT-or-UPDATE (avoids NULL unique-constraint edge cases)
    existing_row = await db.execute(
        select(NormalizedFinancial.id)
        .where(NormalizedFinancial.symbol == symbol)
        .where(NormalizedFinancial.fiscal_year == meta["fiscal_year"])
        .where(NormalizedFinancial.period == meta["period"])
    )
    existing_id = existing_row.scalar_one_or_none()

    update_vals: dict[str, Any] = {
        "filing_id": meta["filing_id"],
        "period_type": meta["period_type"],
        "reporting_scale": scale,
        "source_map": source_map or None,
        "normalization_status": status,
        "missing_fields": {"fields": missing} if missing else None,
        **field_values,
    }

    if existing_id:
        await db.execute(
            update(NormalizedFinancial)
            .where(NormalizedFinancial.id == existing_id)
            .values(**update_vals)
        )
        nf_id = existing_id
    else:
        result = await db.execute(
            insert(NormalizedFinancial)
            .values(
                symbol=symbol,
                fiscal_year=meta["fiscal_year"],
                period=meta["period"],
                **update_vals,
            )
            .returning(NormalizedFinancial.id)
        )
        nf_id = result.scalar_one()

    await db.commit()

    # Replace conflicts for this record
    await db.execute(
        delete(NormalizationConflict).where(
            NormalizationConflict.normalized_financial_id == nf_id
        )
    )
    for c in conflict_list:
        await db.execute(
            insert(NormalizationConflict).values(
                normalized_financial_id=nf_id,
                field_name=c.field_name,
                raw_item_ids=[item["raw_item_id"] for item in c.candidates],
                conflicting_values=c.candidates,
            )
        )
    if conflict_list:
        await db.commit()

    log.info(
        "normalize_symbol %s: fields_set=%s missing=%s conflicts=%s bs_valid=%s scale=%s",
        symbol, list(field_values.keys()), missing,
        [c.field_name for c in conflict_list], bs_valid, scale,
    )

    return NormalizeResult(
        symbol=symbol,
        fiscal_year=meta["fiscal_year"],
        normalized_id=str(nf_id),
        fields_set=list(field_values.keys()),
        fields_missing=missing,
        conflicts=[c.field_name for c in conflict_list],
        bs_valid=bs_valid,
        scale=scale,
        error=None,
    )
