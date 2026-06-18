"""
Phase 2G.3 tests — Revenue, cash, debt, and free_cash_flow normalization.

All tests are offline: no DB connection, no network.  Facts are built as simple
namespace objects.  Covers: revenue (multi-label + conflict), cash_and_equivalents,
short_term_debt, long_term_debt (multi-label), total_debt derivation, free_cash_flow
derivation, and source_map traceability for calculated fields.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.pipeline.exchange.xbrl_normalizer import (
    _BANK_REVENUE_LABEL,
    _CASH_LABEL,
    _CURRENT_DEBT_LABELS,
    _NONCURRENT_DEBT_LABELS,
    _REVENUE_LABEL_SET,
    _REVENUE_LABELS,
    _derive_free_cash_flow,
    _derive_total_debt,
    _resolve_debt,
    _resolve_revenue,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_fact(
    label_ar: str,
    value_numeric: float | None,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
    context_ref: str | None = None,
    fact_id: str | None = None,
) -> SimpleNamespace:
    ps = period_start or date(2025, 1, 1)
    pe = period_end or date(2025, 12, 31)
    return SimpleNamespace(
        id=uuid.UUID(fact_id) if fact_id else uuid.uuid4(),
        label_ar=label_ar,
        value_numeric=Decimal(str(value_numeric)) if value_numeric is not None else None,
        statement_type="income_statement",
        period_start=ps,
        period_end=pe,
        context_ref=context_ref or f"PERIOD__{ps}__{pe}",
    )


def _bs_fact(
    label_ar: str,
    value_numeric: float | None,
    *,
    instant_date: date | None = None,
    context_ref: str | None = None,
    fact_id: str | None = None,
) -> SimpleNamespace:
    d = instant_date or date(2025, 12, 31)
    return SimpleNamespace(
        id=uuid.UUID(fact_id) if fact_id else uuid.uuid4(),
        label_ar=label_ar,
        value_numeric=Decimal(str(value_numeric)) if value_numeric is not None else None,
        statement_type="balance_sheet",
        instant_date=d,
        context_ref=context_ref or f"INSTANT__{d}",
    )


_START = date(2025, 1, 1)
_END = date(2025, 12, 31)
_PRIOR_START = date(2024, 1, 1)
_PRIOR_END = date(2024, 12, 31)
_DATE = date(2025, 12, 31)
_PRIOR_DATE = date(2024, 12, 31)


# ── Revenue: function-of-expense ──────────────────────────────────────────────

def test_maps_revenue_function_company():
    """Primary function label 'الإيرادات' resolves cleanly."""
    fid = str(uuid.uuid4())
    facts = [_is_fact("الإيرادات", 1_500_000, period_start=_START, period_end=_END, fact_id=fid)]
    result = _resolve_revenue(facts, _START, _END)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("1500000")
    assert result.raw_item_id == fid
    assert result.label_ar == "الإيرادات"


def test_operating_income_label_not_in_revenue_set():
    """
    'إجمالي دخل العمليات' must NOT be in the revenue label set.

    For function-of-expense companies (2240, 4263, 2050) this label appears in
    the IS alongside الإيرادات but represents operating income (~18-56 % of
    revenues), not top-line revenues.  Including it would produce spurious
    revenue conflicts for those companies.
    """
    assert "إجمالي دخل العمليات" not in _REVENUE_LABEL_SET


def test_revenue_2020_conflict():
    """
    2020 scenario: إجمالي الإيرادات and مبيعات بضاعة exist with different values.
    Revenue must be NULL — Conflict is returned, not a silent pick.
    """
    facts = [
        _is_fact("إجمالي الإيرادات", 5_000_000, period_start=_START, period_end=_END),
        _is_fact("مبيعات بضاعة", 4_800_000, period_start=_START, period_end=_END),
    ]
    result = _resolve_revenue(facts, _START, _END)
    from app.pipeline.exchange.xbrl_normalizer import _Conflict
    assert isinstance(result, _Conflict)
    assert result.field_name == "revenue"
    assert len(result.candidates) == 2
    values = {c["value"] for c in result.candidates}
    assert values == {5_000_000.0, 4_800_000.0}


def test_revenue_same_value_two_labels_no_conflict():
    """Two labels with the same value → deduplicated Match, not a conflict."""
    fid = str(uuid.uuid4())
    facts = [
        _is_fact("الإيرادات", 1_200_000, period_start=_START, period_end=_END, fact_id=fid),
        _is_fact("إجمالي دخل العمليات", 1_200_000, period_start=_START, period_end=_END),
    ]
    result = _resolve_revenue(facts, _START, _END)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("1200000")
    # Must pick the highest-priority label
    assert result.label_ar == "الإيرادات"


def test_revenue_comparative_period_ignored():
    """Prior-year IS facts must not match; only current period."""
    current_id = str(uuid.uuid4())
    facts = [
        _is_fact("الإيرادات", 1_500_000, period_start=_START, period_end=_END, fact_id=current_id),
        _is_fact("الإيرادات", 1_200_000, period_start=_PRIOR_START, period_end=_PRIOR_END),
    ]
    result = _resolve_revenue(facts, _START, _END)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("1500000")
    assert result.raw_item_id == current_id


def test_revenue_absent_returns_none():
    """No matching revenue labels → None."""
    facts = [_is_fact("تكلفة المبيعات", 500_000, period_start=_START, period_end=_END)]
    result = _resolve_revenue(facts, _START, _END)
    assert result is None


def test_revenue_bank_label_resolves():
    """Bank total operating income label resolves as revenue (approximate proxy)."""
    facts = [_is_fact("إجمالي الدخل التشغيلي", 80_000_000, period_start=_START, period_end=_END)]
    result = _resolve_revenue(facts, _START, _END)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("80000000")
    assert result.label_ar == _BANK_REVENUE_LABEL


# ── Cash & equivalents ────────────────────────────────────────────────────────

def test_maps_cash_and_equivalents():
    """BS label maps with correct instant_date."""
    from app.pipeline.exchange.xbrl_normalizer import _resolve_bs
    label_ar, negate = _CASH_LABEL
    fid = str(uuid.uuid4())
    facts = [_bs_fact(label_ar, 350_000, instant_date=_DATE, fact_id=fid)]
    result = _resolve_bs("cash_and_equivalents", label_ar, negate, facts, _DATE)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("350000")
    assert result.raw_item_id == fid


def test_cash_prior_instant_date_ignored():
    """Prior-year balance sheet instant_date must not match."""
    from app.pipeline.exchange.xbrl_normalizer import _resolve_bs
    label_ar, negate = _CASH_LABEL
    current_id = str(uuid.uuid4())
    facts = [
        _bs_fact(label_ar, 350_000, instant_date=_DATE, fact_id=current_id),
        _bs_fact(label_ar, 290_000, instant_date=_PRIOR_DATE),
    ]
    result = _resolve_bs("cash_and_equivalents", label_ar, negate, facts, _DATE)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("350000")
    assert result.raw_item_id == current_id


# ── Short-term debt ───────────────────────────────────────────────────────────

def test_maps_current_debt_primary_label():
    """'قروض قصيرة الأجل' → short_term_debt Match."""
    fid = str(uuid.uuid4())
    facts = [_bs_fact("قروض قصيرة الأجل", 200_000, instant_date=_DATE, fact_id=fid)]
    result = _resolve_debt("short_term_debt", _CURRENT_DEBT_LABELS, facts, _DATE)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("200000")
    assert result.raw_item_id == fid
    assert result.label_ar == "قروض قصيرة الأجل"


def test_maps_current_debt_secondary_label():
    """'قروض - متداولة' (2222) resolves when primary label absent."""
    facts = [_bs_fact("قروض - متداولة", 500_000, instant_date=_DATE)]
    result = _resolve_debt("short_term_debt", _CURRENT_DEBT_LABELS, facts, _DATE)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("500000")
    assert result.label_ar == "قروض - متداولة"


def test_current_debt_absent_returns_none():
    """No matching debt labels → None."""
    facts = [_bs_fact("إجمالي الموجودات", 10_000_000, instant_date=_DATE)]
    result = _resolve_debt("short_term_debt", _CURRENT_DEBT_LABELS, facts, _DATE)
    assert result is None


# ── Long-term debt ────────────────────────────────────────────────────────────

def test_maps_noncurrent_debt_primary_label():
    """'قروض - غير متداولة' (2222) → long_term_debt Match."""
    fid = str(uuid.uuid4())
    facts = [_bs_fact("قروض - غير متداولة", 3_000_000, instant_date=_DATE, fact_id=fid)]
    result = _resolve_debt("long_term_debt", _NONCURRENT_DEBT_LABELS, facts, _DATE)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("3000000")
    assert result.raw_item_id == fid


def test_maps_noncurrent_debt_secondary_label():
    """'سندات دين وقروض لأجل وقروض وصكوك مصدرة' resolves when primary absent."""
    label = "سندات دين وقروض لأجل وقروض وصكوك مصدرة"
    facts = [_bs_fact(label, 1_500_000, instant_date=_DATE)]
    result = _resolve_debt("long_term_debt", _NONCURRENT_DEBT_LABELS, facts, _DATE)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("1500000")
    assert result.label_ar == label


# ── Debt conflict detection ───────────────────────────────────────────────────

def test_debt_conflict_multiple_labels_different_values():
    """Two debt labels with different values → Conflict; do not auto-pick."""
    facts = [
        _bs_fact("قروض قصيرة الأجل", 200_000, instant_date=_DATE),
        _bs_fact("قسط متداول من قروض طويلة الأجل", 80_000, instant_date=_DATE),
    ]
    result = _resolve_debt("short_term_debt", _CURRENT_DEBT_LABELS, facts, _DATE)
    from app.pipeline.exchange.xbrl_normalizer import _Conflict
    assert isinstance(result, _Conflict)
    assert result.field_name == "short_term_debt"
    assert len(result.candidates) == 2


def test_debt_two_labels_same_value_no_conflict():
    """Two labels with the same value → Match (deduped, first label wins)."""
    facts = [
        _bs_fact("قروض قصيرة الأجل", 200_000, instant_date=_DATE),
        _bs_fact("قروض - متداولة", 200_000, instant_date=_DATE),
    ]
    result = _resolve_debt("short_term_debt", _CURRENT_DEBT_LABELS, facts, _DATE)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("200000")
    assert result.label_ar == "قروض قصيرة الأجل"


# ── Derivation: total_debt ────────────────────────────────────────────────────

def test_derives_total_debt_from_components():
    """total_debt = short_term_debt + long_term_debt."""
    result = _derive_total_debt(Decimal("200000000"), Decimal("1500000000"))
    assert result == Decimal("1700000000")


def test_derive_total_debt_zero_current():
    """Works when short_term_debt is zero."""
    assert _derive_total_debt(Decimal("0"), Decimal("500000000")) == Decimal("500000000")


# ── Derivation: free_cash_flow ────────────────────────────────────────────────

def test_derives_free_cash_flow_positive_result():
    """FCF = operating_cash_flow + capex; capex is negative outflow."""
    ocf = Decimal("1000000000")
    capex = Decimal("-200000000")
    result = _derive_free_cash_flow(ocf, capex)
    assert result == Decimal("800000000")


def test_derives_free_cash_flow_negative_when_capex_exceeds_ocf():
    """FCF can be negative — capex larger than OCF."""
    ocf = Decimal("100000000")
    capex = Decimal("-500000000")
    result = _derive_free_cash_flow(ocf, capex)
    assert result == Decimal("-400000000")


def test_free_cash_flow_sign_convention():
    """Capex must be negative for FCF formula to be correct."""
    ocf = Decimal("800000000")
    capex = Decimal("-116346000")
    fcf = _derive_free_cash_flow(ocf, capex)
    assert fcf < ocf, "FCF must be less than OCF when capex is a non-zero outflow"
    assert fcf == ocf + capex


# ── Label map integrity ───────────────────────────────────────────────────────

def test_revenue_label_map_covers_all_company_types():
    """All required revenue labels are present in the map."""
    labels = {label for label, _ in _REVENUE_LABELS}
    assert "الإيرادات" in labels, "function-of-expense primary"
    assert "إجمالي الإيرادات" in labels, "nature-of-expense primary"
    assert "مبيعات بضاعة" in labels, "2020 conflict label"
    assert _BANK_REVENUE_LABEL in labels, "bank approximate proxy"
    assert "إجمالي دخل العمليات" not in labels, "operating income must not be treated as revenue"


def test_current_debt_label_map_priority():
    """Primary short-term label must come before secondary labels."""
    labels = [label for label, _ in _CURRENT_DEBT_LABELS]
    assert labels[0] == "قروض قصيرة الأجل"
    assert "قروض - متداولة" in labels
    assert "قسط متداول من قروض طويلة الأجل" in labels


def test_noncurrent_debt_label_map_has_three_entries():
    """All three long-term debt label variants are present."""
    labels = [label for label, _ in _NONCURRENT_DEBT_LABELS]
    assert len(labels) == 3
    assert "قروض - غير متداولة" in labels
    assert "سندات دين وقروض لأجل وقروض وصكوك مصدرة" in labels
    assert "قروض وسلف" in labels


def test_revenue_label_set_matches_list():
    """_REVENUE_LABEL_SET must be the exact frozenset of _REVENUE_LABELS."""
    expected = frozenset(label for label, _ in _REVENUE_LABELS)
    assert _REVENUE_LABEL_SET == expected
