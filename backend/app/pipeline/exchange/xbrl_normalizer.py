"""
XBRL financial normalizer — Phase 2G.1 (BS + CF), 2G.2 (IS high-confidence),
                             Phase 2G.3 (revenue, cash, debt, free_cash_flow).

Phase 2G.1 scope — Balance Sheet:  total_assets, total_liabilities, equity
                  — Cash Flow:      operating_cash_flow, investing_cash_flow,
                                    financing_cash_flow, capex

Phase 2G.2 scope — Income Statement (high-confidence only):
                    finance_cost, profit_before_tax, zakat_tax, net_income
                  — income_tax is logged in source_map["income_tax_detail"] when
                    separately identifiable but has no schema column yet.

Phase 2G.3 scope — Revenue (multi-label; conflict detection for 2020;
                              'إجمالي دخل العمليات' excluded — it is operating
                              income not revenues for function companies)
                  — cash_and_equivalents (BS instant-date field)
                  — short_term_debt, long_term_debt (multi-label BS with conflict)
                  — total_debt (derived: short_term_debt + long_term_debt)
                  — free_cash_flow (derived: operating_cash_flow + capex)

Hard stops: no cost_of_revenue / gross_profit / operating_profit / EBIT / EBITDA /
            EPS, no ratios, no screener writes.
Values are stored in absolute SAR (value_numeric × scale).
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

# ── Balance Sheet label map ───────────────────────────────────────────────────
# field_name → (label_ar, negate)
_BS_LABELS: dict[str, tuple[str, bool]] = {
    "total_assets":      ("إجمالي الموجودات", False),
    "total_liabilities": ("إجمالي المطلوبات", False),
    "equity":            ("إجمالي حقوق الملكية", False),
}

# ── Cash Flow label map ───────────────────────────────────────────────────────
# field_name → ordered list of (label_ar, negate); first label match wins.
# capex primary label is stored positive in SA viewer → negate to outflow convention.
# 2222 fallback label 'نفقات رأسمالية' is already negative → keep as-is.
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

# ── Income Statement label map ────────────────────────────────────────────────
# field_name → ordered list of (label_ar, negate); first match wins.
#
# finance_cost: stored positive (expense magnitude); not present in bank IS.
# profit_before_tax: bank (1120) uses a different label order.
# zakat_tax: 2222 uses combined ضرائب الدخل والزكاة; others use the zakat-only label.
#            2050-2025 has a negative zakat value (credit) — stored as-is.
# net_income: prefer continuing-operations label; fall back to period total.
#             When continuing-ops ≠ total, both are preserved in source_map.
_IS_LABELS: dict[str, list[tuple[str, bool]]] = {
    "finance_cost": [
        ("تكلفة تمويل", False),
    ],
    "profit_before_tax": [
        ("الربح (الخسارة) قبل الزكاة وضريبة الدخل من العمليات المستمرة", False),
        ("الربح (الخسارة) من العمليات المستمرة قبل الزكاة وضريبة الدخل", False),
    ],
    "zakat_tax": [
        ("مصاريف الزكاة على العمليات المستمرة للفترة", False),
        ("ضرائب الدخل والزكاة", False),
    ],
    "net_income": [
        ("ربح (خسارة) الفترة من العمليات المستمرة", False),
        ("ربح (خسارة) الفترة", False),
    ],
}

# Income-tax-only label — no schema column; logged in source_map detail only.
_INCOME_TAX_LABEL = "ضريبة الدخل على العمليات المستمرة للفترة"
# Used to detect when continuing-ops was used so we can also log the total.
_NET_INCOME_CONTINUING_LABEL = "ربح (خسارة) الفترة من العمليات المستمرة"
_NET_INCOME_TOTAL_LABEL = "ربح (خسارة) الفترة"

_SCALE_LABEL = "مستوى التقريب المستخدم في القوائم المالية"

# ── Phase 2G.3 label maps ─────────────────────────────────────────────────────

# Revenue — all candidates checked together; any two labels with different values
# produce a Conflict rather than silently picking one.
#
# Function-of-expense (2240, 4263, 2050): الإيرادات
# Nature-of-expense (2222, 2020):         إجمالي الإيرادات / مبيعات / مبيعات بضاعة
#   2020 conflict: إجمالي الإيرادات and مبيعات بضاعة have DIFFERENT values → Conflict
# Bank (1120):                            إجمالي الدخل التشغيلي (approximate proxy)
#
# NOTE: 'إجمالي دخل العمليات' is intentionally excluded.  It appears in the IS
# for function companies (2240, 4263, 2050) but represents operating income
# (~18–56 % of revenues), not top-line revenues.  Including it would produce
# spurious revenue conflicts for these companies.
_REVENUE_LABELS: list[tuple[str, bool]] = [
    ("الإيرادات", False),
    ("إجمالي الإيرادات", False),
    ("مبيعات", False),
    ("مبيعات بضاعة", False),
    ("إجمالي الدخل التشغيلي", False),
]
_REVENUE_LABEL_SET: frozenset[str] = frozenset(label for label, _ in _REVENUE_LABELS)
# When this label is the revenue source, mark source_map as approximate bank proxy.
_BANK_REVENUE_LABEL = "إجمالي الدخل التشغيلي"

# Cash & equivalents — single BS label; NULL for banks (no single label).
_CASH_LABEL: tuple[str, bool] = ("أرصدة لدى البنوك ونقد في الصندوق", False)

# Short-term debt labels in priority order.
# If multiple match with DIFFERENT values → Conflict (do not auto-pick).
_CURRENT_DEBT_LABELS: list[tuple[str, bool]] = [
    ("قروض قصيرة الأجل", False),                    # 2240
    ("قروض - متداولة", False),                       # 2222
    ("قسط متداول من قروض طويلة الأجل", False),        # 2240, 4263 (current portion of LTD)
]

# Long-term debt labels in priority order.
_NONCURRENT_DEBT_LABELS: list[tuple[str, bool]] = [
    ("قروض - غير متداولة", False),                              # 2222
    ("سندات دين وقروض لأجل وقروض وصكوك مصدرة", False),          # 2240, 4263, 2050
    ("قروض وسلف", False),                                        # 2050 fallback
]

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


# ── Field resolvers ───────────────────────────────────────────────────────────

def _resolve_bs(
    field_name: str,
    label_ar: str,
    negate: bool,
    facts: list,
    period_end: date,
) -> _Match | _Conflict | None:
    """Resolve a balance-sheet field: instant_date == period_end."""
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
    return _Match(
        field_name=field_name,
        value=-c.value_numeric if negate else c.value_numeric,
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
    """Resolve a cash-flow field: statement_type='cash_flow', period filter."""
    return _resolve_duration(field_name, label_specs, facts, period_start, period_end, "cash_flow")


def _resolve_is(
    field_name: str,
    label_specs: list[tuple[str, bool]],
    facts: list,
    period_start: date,
    period_end: date,
) -> _Match | _Conflict | None:
    """Resolve an income-statement field: statement_type='income_statement', period filter."""
    return _resolve_duration(field_name, label_specs, facts, period_start, period_end, "income_statement")


def _resolve_duration(
    field_name: str,
    label_specs: list[tuple[str, bool]],
    facts: list,
    period_start: date,
    period_end: date,
    statement_type: str,
) -> _Match | _Conflict | None:
    """
    Try each (label_ar, negate) in order; return first match.
    Deduplicates by value — multiple rows with identical value count as one.
    Multiple rows with different values → Conflict.
    """
    for label_ar, negate in label_specs:
        candidates = [
            f for f in facts
            if f.label_ar == label_ar
            and f.statement_type == statement_type
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
        return _Match(
            field_name=field_name,
            value=-c.value_numeric if negate else c.value_numeric,
            raw_item_id=str(c.id),
            label_ar=c.label_ar,
            context_ref=c.context_ref,
        )
    return None


def _resolve_revenue(
    facts: list,
    period_start: date,
    period_end: date,
) -> _Match | _Conflict | None:
    """
    Revenue resolver: all label candidates checked simultaneously.

    Gathers every IS fact whose label_ar is in _REVENUE_LABEL_SET for the
    current period. If all matching facts share a single unique numeric value,
    returns the highest-priority label match. If any two labels produce
    different values, returns Conflict — revenue is not silently resolved.

    This handles the 2020 case where إجمالي الإيرادات and مبيعات بضاعة appear
    with different values in the same filing.
    """
    candidates = [
        f for f in facts
        if f.label_ar in _REVENUE_LABEL_SET
        and f.statement_type == "income_statement"
        and f.period_start == period_start
        and f.period_end == period_end
        and f.value_numeric is not None
    ]
    if not candidates:
        return None

    unique_vals = {f.value_numeric for f in candidates}
    if len(unique_vals) > 1:
        return _Conflict(
            field_name="revenue",
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

    # All candidates agree — pick the highest-priority label for source traceability.
    label_priority = {label: i for i, (label, _) in enumerate(_REVENUE_LABELS)}
    best = min(candidates, key=lambda f: label_priority.get(f.label_ar, 999))
    return _Match(
        field_name="revenue",
        value=best.value_numeric,
        raw_item_id=str(best.id),
        label_ar=best.label_ar,
        context_ref=best.context_ref,
    )


def _resolve_debt(
    field_name: str,
    label_specs: list[tuple[str, bool]],
    facts: list,
    period_end: date,
) -> _Match | _Conflict | None:
    """
    Multi-label balance-sheet debt resolver.

    Each label spec is tried independently. Clean matches (one unique value
    per label) are collected. If multiple clean matches have different scaled
    values → Conflict (do not auto-pick). If all agree or only one matches →
    Match on the first clean candidate.

    This handles the 2240 case where قروض قصيرة الأجل and
    قسط متداول من قروض طويلة الأجل are two distinct debt components that must
    not be conflated.
    """
    clean: list[tuple[Any, bool]] = []  # (fact, negate)

    for label_ar, negate in label_specs:
        candidates = [
            f for f in facts
            if f.label_ar == label_ar
            and f.statement_type == "balance_sheet"
            and f.instant_date == period_end
            and f.value_numeric is not None
        ]
        if not candidates:
            continue
        unique_vals = {f.value_numeric for f in candidates}
        if len(unique_vals) > 1:
            # Within-label ambiguity — include all as conflict candidates
            for c in candidates:
                clean.append((c, negate))
            continue
        clean.append((candidates[0], negate))

    if not clean:
        return None

    unique_scaled = {(-f.value_numeric if n else f.value_numeric) for f, n in clean}
    if len(unique_scaled) > 1:
        return _Conflict(
            field_name=field_name,
            candidates=[
                {
                    "raw_item_id": str(f.id),
                    "label_ar": f.label_ar,
                    "value": float(f.value_numeric),
                    "context_ref": f.context_ref,
                }
                for f, _ in clean
            ],
        )

    f, negate = clean[0]
    return _Match(
        field_name=field_name,
        value=-f.value_numeric if negate else f.value_numeric,
        raw_item_id=str(f.id),
        label_ar=f.label_ar,
        context_ref=f.context_ref,
    )


# ── Pure derivation helpers (also used in tests) ──────────────────────────────

def _derive_total_debt(current: Decimal, noncurrent: Decimal) -> Decimal:
    """total_debt = short_term_debt + long_term_debt."""
    return current + noncurrent


def _derive_free_cash_flow(operating_cf: Decimal, capex: Decimal) -> Decimal:
    """free_cash_flow = operating_cash_flow + capex (capex is stored as negative outflow)."""
    return operating_cf + capex


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

    # ── Balance Sheet ────────────────────────────────────────────────────────
    for field_name, (label_ar, negate) in _BS_LABELS.items():
        r = _resolve_bs(field_name, label_ar, negate, all_facts, p_end)
        if isinstance(r, _Match):
            matches[field_name] = r
        elif isinstance(r, _Conflict):
            conflict_list.append(r)
        else:
            missing.append(field_name)

    # ── Cash Flow ────────────────────────────────────────────────────────────
    for field_name, label_specs in _CF_LABELS.items():
        r = _resolve_cf(field_name, label_specs, all_facts, p_start, p_end)
        if isinstance(r, _Match):
            matches[field_name] = r
        elif isinstance(r, _Conflict):
            conflict_list.append(r)
        else:
            missing.append(field_name)

    # ── Income Statement ─────────────────────────────────────────────────────
    for field_name, label_specs in _IS_LABELS.items():
        r = _resolve_is(field_name, label_specs, all_facts, p_start, p_end)
        if isinstance(r, _Match):
            matches[field_name] = r
        elif isinstance(r, _Conflict):
            conflict_list.append(r)
        else:
            missing.append(field_name)

    # ── Phase 2G.3 — Revenue ─────────────────────────────────────────────────
    r = _resolve_revenue(all_facts, p_start, p_end)
    if isinstance(r, _Match):
        matches["revenue"] = r
    elif isinstance(r, _Conflict):
        conflict_list.append(r)
    else:
        missing.append("revenue")

    # ── Phase 2G.3 — Cash & Equivalents ─────────────────────────────────────
    cash_label_ar, cash_negate = _CASH_LABEL
    r = _resolve_bs("cash_and_equivalents", cash_label_ar, cash_negate, all_facts, p_end)
    if isinstance(r, _Match):
        matches["cash_and_equivalents"] = r
    elif isinstance(r, _Conflict):
        conflict_list.append(r)
    else:
        missing.append("cash_and_equivalents")

    # ── Phase 2G.3 — Short-term Debt ─────────────────────────────────────────
    r = _resolve_debt("short_term_debt", _CURRENT_DEBT_LABELS, all_facts, p_end)
    if isinstance(r, _Match):
        matches["short_term_debt"] = r
    elif isinstance(r, _Conflict):
        conflict_list.append(r)
    else:
        missing.append("short_term_debt")

    # ── Phase 2G.3 — Long-term Debt ──────────────────────────────────────────
    r = _resolve_debt("long_term_debt", _NONCURRENT_DEBT_LABELS, all_facts, p_end)
    if isinstance(r, _Match):
        matches["long_term_debt"] = r
    elif isinstance(r, _Conflict):
        conflict_list.append(r)
    else:
        missing.append("long_term_debt")

    # ── Scale XBRL-sourced fields ─────────────────────────────────────────────
    field_values: dict[str, Decimal] = {
        fn: m.value * scale for fn, m in matches.items()
    }

    # ── Phase 2G.3 — Derive total_debt ───────────────────────────────────────
    # Both components must be resolved without conflict. If either is missing,
    # total_debt is ambiguous — leave NULL and record in missing_fields.
    if "short_term_debt" in field_values and "long_term_debt" in field_values:
        field_values["total_debt"] = _derive_total_debt(
            field_values["short_term_debt"], field_values["long_term_debt"]
        )
    else:
        missing.append("total_debt")

    # ── Phase 2G.3 — Derive free_cash_flow ───────────────────────────────────
    # operating_cash_flow and capex are Phase 2G.1 high-confidence fields.
    # capex is already stored as a negative outflow value, so FCF = OCF + capex.
    if "operating_cash_flow" in field_values and "capex" in field_values:
        field_values["free_cash_flow"] = _derive_free_cash_flow(
            field_values["operating_cash_flow"], field_values["capex"]
        )
    else:
        missing.append("free_cash_flow")

    # ── Source map (XBRL-sourced fields) ─────────────────────────────────────
    source_map: dict[str, dict] = {
        fn: {
            "raw_item_id": m.raw_item_id,
            "label_ar": m.label_ar,
            "context_ref": m.context_ref,
        }
        for fn, m in matches.items()
    }

    # Bank revenue: mark as approximate proxy when total_operating_income label used.
    if "revenue" in source_map and matches["revenue"].label_ar == _BANK_REVENUE_LABEL:
        source_map["revenue"]["bank_approximate"] = True

    # Derived total_debt: record calculation provenance.
    if "total_debt" in field_values:
        source_map["total_debt"] = {
            "calculated": True,
            "formula": "short_term_debt + long_term_debt",
            "components": {
                "short_term_debt": float(field_values["short_term_debt"]),
                "long_term_debt": float(field_values["long_term_debt"]),
            },
        }

    # Derived free_cash_flow: record calculation provenance.
    if "free_cash_flow" in field_values:
        source_map["free_cash_flow"] = {
            "calculated": True,
            "formula": "operating_cash_flow + capex",
            "components": {
                "operating_cash_flow": float(field_values["operating_cash_flow"]),
                "capex": float(field_values["capex"]),
            },
        }

    # ── Supplemental: log total net_income when continuing-ops label was used ─
    ni_match = matches.get("net_income")
    if ni_match and ni_match.label_ar == _NET_INCOME_CONTINUING_LABEL:
        total_facts = [
            f for f in all_facts
            if f.label_ar == _NET_INCOME_TOTAL_LABEL
            and f.statement_type == "income_statement"
            and f.period_start == p_start
            and f.period_end == p_end
            and f.value_numeric is not None
        ]
        if total_facts:
            total_unique = {f.value_numeric for f in total_facts}
            if len(total_unique) == 1:
                total_scaled = list(total_unique)[0] * scale
                if total_scaled != field_values["net_income"]:
                    source_map["net_income_total"] = {
                        "raw_item_id": str(total_facts[0].id),
                        "label_ar": _NET_INCOME_TOTAL_LABEL,
                        "context_ref": total_facts[0].context_ref,
                        "value_scaled": float(total_scaled),
                    }

    # ── Supplemental: log income_tax detail when separately available ─────────
    it_facts = [
        f for f in all_facts
        if f.label_ar == _INCOME_TAX_LABEL
        and f.statement_type == "income_statement"
        and f.period_start == p_start
        and f.period_end == p_end
        and f.value_numeric is not None
    ]
    if it_facts:
        it_unique = {f.value_numeric for f in it_facts}
        if len(it_unique) == 1:
            source_map["income_tax_detail"] = {
                "raw_item_id": str(it_facts[0].id),
                "label_ar": _INCOME_TAX_LABEL,
                "context_ref": it_facts[0].context_ref,
                "value_scaled": float(list(it_unique)[0] * scale),
            }

    # ── Status ───────────────────────────────────────────────────────────────
    if conflict_list:
        status = "conflict"
    elif missing:
        status = "partial"
    else:
        status = "normalized"

    # ── BS validation ─────────────────────────────────────────────────────────
    bs_valid: bool | None = None
    if all(k in field_values for k in ("total_assets", "total_liabilities", "equity")):
        ta = field_values["total_assets"]
        if ta:
            diff_ratio = abs(ta - (field_values["total_liabilities"] + field_values["equity"])) / ta
            bs_valid = diff_ratio < Decimal("0.001")

    # ── Upsert ────────────────────────────────────────────────────────────────
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

    # ── Conflicts ─────────────────────────────────────────────────────────────
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
