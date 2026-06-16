"""
Phase 2G.2 tests — Income Statement normalization (high-confidence fields only).

All tests are offline: no DB connection, no network.  Facts are built as simple
namespace objects.  Covers: finance_cost, profit_before_tax, zakat_tax, net_income.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.pipeline.exchange.xbrl_normalizer import (
    _IS_LABELS,
    _NET_INCOME_CONTINUING_LABEL,
    _NET_INCOME_TOTAL_LABEL,
    _resolve_is,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fact(
    label_ar: str,
    value_numeric: float | None,
    statement_type: str = "income_statement",
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
        statement_type=statement_type,
        period_start=ps,
        period_end=pe,
        context_ref=context_ref or f"PERIOD__{ps}__{pe}",
    )


_START = date(2025, 1, 1)
_END = date(2025, 12, 31)
_PRIOR_START = date(2024, 1, 1)
_PRIOR_END = date(2024, 12, 31)


# ── finance_cost ──────────────────────────────────────────────────────────────

def test_maps_finance_cost():
    fid = str(uuid.uuid4())
    facts = [
        _fact("تكلفة تمويل", 166_184, period_start=_START, period_end=_END, fact_id=fid),
    ]
    result = _resolve_is("finance_cost", _IS_LABELS["finance_cost"], facts, _START, _END)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("166184")
    assert result.raw_item_id == fid
    assert result.label_ar == "تكلفة تمويل"


def test_finance_cost_stored_positive():
    """Finance cost is an expense — stored positive, not negated."""
    facts = [_fact("تكلفة تمويل", 57_811, period_start=_START, period_end=_END)]
    result = _resolve_is("finance_cost", _IS_LABELS["finance_cost"], facts, _START, _END)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value > 0


def test_finance_cost_absent_for_bank_returns_none():
    """Bank IS does not use تكلفة تمويل — resolver returns None."""
    # No finance_cost fact in facts list
    facts = [_fact("دخل التمويل والاستثمارات", 999, period_start=_START, period_end=_END)]
    result = _resolve_is("finance_cost", _IS_LABELS["finance_cost"], facts, _START, _END)
    assert result is None


# ── profit_before_tax ─────────────────────────────────────────────────────────

def test_maps_profit_before_tax_primary_label():
    label = "الربح (الخسارة) قبل الزكاة وضريبة الدخل من العمليات المستمرة"
    fid = str(uuid.uuid4())
    facts = [_fact(label, 186_752, period_start=_START, period_end=_END, fact_id=fid)]
    result = _resolve_is("profit_before_tax", _IS_LABELS["profit_before_tax"], facts, _START, _END)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("186752")
    assert result.raw_item_id == fid


def test_maps_profit_before_tax_bank_label():
    """Bank (1120) uses a different label; should match the second spec entry."""
    bank_label = "الربح (الخسارة) من العمليات المستمرة قبل الزكاة وضريبة الدخل"
    facts = [_fact(bank_label, 27_646_496, period_start=_START, period_end=_END)]
    result = _resolve_is("profit_before_tax", _IS_LABELS["profit_before_tax"], facts, _START, _END)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("27646496")
    assert result.label_ar == bank_label


def test_profit_before_tax_in_cash_flow_ignored():
    """profit_before_tax appears in CF reconciliation; IS filter must exclude it."""
    label = "الربح (الخسارة) قبل الزكاة وضريبة الدخل من العمليات المستمرة"
    facts = [
        _fact(label, 186_752, statement_type="income_statement",
              period_start=_START, period_end=_END),
        _fact(label, 186_752, statement_type="cash_flow",
              period_start=_START, period_end=_END),
    ]
    result = _resolve_is("profit_before_tax", _IS_LABELS["profit_before_tax"], facts, _START, _END)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("186752")


# ── zakat_tax ─────────────────────────────────────────────────────────────────

def test_maps_zakat_primary_label():
    label = "مصاريف الزكاة على العمليات المستمرة للفترة"
    facts = [_fact(label, 4_888, period_start=_START, period_end=_END)]
    result = _resolve_is("zakat_tax", _IS_LABELS["zakat_tax"], facts, _START, _END)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("4888")


def test_maps_zakat_combined_label_for_aramco():
    """2222 uses ضرائب الدخل والزكاة (combined); should match fallback."""
    facts = [_fact("ضرائب الدخل والزكاة", 352_650, period_start=_START, period_end=_END)]
    result = _resolve_is("zakat_tax", _IS_LABELS["zakat_tax"], facts, _START, _END)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("352650")
    assert result.label_ar == "ضرائب الدخل والزكاة"


def test_zakat_negative_value_stored_as_is():
    """2050-2025 has a zakat credit (−217,425); must not be negated or flagged."""
    label = "مصاريف الزكاة على العمليات المستمرة للفترة"
    facts = [_fact(label, -217_425, period_start=_START, period_end=_END)]
    result = _resolve_is("zakat_tax", _IS_LABELS["zakat_tax"], facts, _START, _END)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("-217425"), "zakat credit must be stored negative, not flipped"


# ── net_income ────────────────────────────────────────────────────────────────

def test_maps_net_income_continuing_operations_preferred():
    """Prefer ربح (خسارة) الفترة من العمليات المستمرة over the total."""
    cont_label = "ربح (خسارة) الفترة من العمليات المستمرة"
    total_label = "ربح (خسارة) الفترة"
    cont_id = str(uuid.uuid4())
    facts = [
        _fact(cont_label, 5_746_948, period_start=_START, period_end=_END, fact_id=cont_id),
        _fact(total_label, 5_639_566, period_start=_START, period_end=_END),
        _fact(total_label, 5_639_566, period_start=_START, period_end=_END),
    ]
    result = _resolve_is("net_income", _IS_LABELS["net_income"], facts, _START, _END)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.label_ar == _NET_INCOME_CONTINUING_LABEL
    assert result.value == Decimal("5746948")
    assert result.raw_item_id == cont_id


def test_maps_net_income_fallback_to_total_when_no_continuing_ops():
    """When only ربح (خسارة) الفترة exists (e.g., 1120), use it."""
    total_label = "ربح (خسارة) الفترة"
    facts = [
        _fact(total_label, 24_824_510, period_start=_START, period_end=_END),
        _fact(total_label, 24_824_510, period_start=_START, period_end=_END),
    ]
    result = _resolve_is("net_income", _IS_LABELS["net_income"], facts, _START, _END)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.label_ar == _NET_INCOME_TOTAL_LABEL
    assert result.value == Decimal("24824510")


def test_net_income_duplicate_identical_rows_not_conflict():
    """Two IS rows with the same label and same value per period are deduped — not a conflict."""
    label = "ربح (خسارة) الفترة"
    facts = [
        _fact(label, 697_890, period_start=_START, period_end=_END),
        _fact(label, 697_890, period_start=_START, period_end=_END),
    ]
    result = _resolve_is("net_income", _IS_LABELS["net_income"], facts, _START, _END)
    from app.pipeline.exchange.xbrl_normalizer import _Match, _Conflict
    assert isinstance(result, _Match), "identical duplicate rows must not produce a conflict"
    assert result.value == Decimal("697890")


# ── Period filtering ──────────────────────────────────────────────────────────

def test_comparative_period_ignored_for_is_fields():
    """Facts from the prior year must not be matched; only current period."""
    label = "تكلفة تمويل"
    current_id = str(uuid.uuid4())
    facts = [
        _fact(label, 166_184, period_start=_START, period_end=_END, fact_id=current_id),
        _fact(label, 173_067, period_start=_PRIOR_START, period_end=_PRIOR_END),
    ]
    result = _resolve_is("finance_cost", _IS_LABELS["finance_cost"], facts, _START, _END)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("166184")
    assert result.raw_item_id == current_id


# ── Conflict detection ────────────────────────────────────────────────────────

def test_conflict_creates_normalization_conflict_for_is():
    """Two IS facts with same label, same period, different values → Conflict."""
    label = "الربح (الخسارة) قبل الزكاة وضريبة الدخل من العمليات المستمرة"
    facts = [
        _fact(label, 186_752, period_start=_START, period_end=_END),
        _fact(label, 190_000, period_start=_START, period_end=_END),
    ]
    result = _resolve_is("profit_before_tax", _IS_LABELS["profit_before_tax"], facts, _START, _END)
    from app.pipeline.exchange.xbrl_normalizer import _Conflict
    assert isinstance(result, _Conflict)
    assert result.field_name == "profit_before_tax"
    assert len(result.candidates) == 2


# ── Source traceability ───────────────────────────────────────────────────────

def test_source_map_preserved_for_is_fields():
    """Match result carries raw_item_id, label_ar, context_ref."""
    fid = str(uuid.uuid4())
    ctx = "PERIOD__2025-01-01__2025-12-31"
    facts = [
        _fact("تكلفة تمويل", 57_811, period_start=_START, period_end=_END,
              context_ref=ctx, fact_id=fid),
    ]
    result = _resolve_is("finance_cost", _IS_LABELS["finance_cost"], facts, _START, _END)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.raw_item_id == fid
    assert result.label_ar == "تكلفة تمويل"
    assert result.context_ref == ctx


# ── 2050 discontinued operations safety check ─────────────────────────────────

def test_2050_discontinued_ops_does_not_distort_net_income():
    """
    2050-2025: continuing ops (948,084) != total net income (940,499).
    The resolver must return continuing ops — the caller (normalize_symbol) then
    logs the total separately in source_map.  The resolver itself must not merge
    or average the two values.
    """
    cont_label = "ربح (خسارة) الفترة من العمليات المستمرة"
    total_label = "ربح (خسارة) الفترة"
    cont_id = str(uuid.uuid4())
    facts = [
        _fact(cont_label, 948_084, period_start=_START, period_end=_END, fact_id=cont_id),
        _fact(total_label, 940_499, period_start=_START, period_end=_END),
        _fact(total_label, 940_499, period_start=_START, period_end=_END),
    ]
    result = _resolve_is("net_income", _IS_LABELS["net_income"], facts, _START, _END)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("948084"), \
        "continuing-ops net income must win; total must not silently replace it"
    assert result.label_ar == _NET_INCOME_CONTINUING_LABEL


# ── Label map integrity ───────────────────────────────────────────────────────

def test_is_label_map_has_required_fields():
    assert set(_IS_LABELS.keys()) == {"finance_cost", "profit_before_tax", "zakat_tax", "net_income"}


def test_net_income_label_priority_order():
    """Continuing-ops label must come before total-period label in the spec list."""
    labels = [l for l, _ in _IS_LABELS["net_income"]]
    assert labels[0] == _NET_INCOME_CONTINUING_LABEL
    assert labels[1] == _NET_INCOME_TOTAL_LABEL


def test_profit_before_tax_bank_label_is_second_priority():
    """Bank label is a fallback — standard label must come first."""
    primary = "الربح (الخسارة) قبل الزكاة وضريبة الدخل من العمليات المستمرة"
    bank = "الربح (الخسارة) من العمليات المستمرة قبل الزكاة وضريبة الدخل"
    labels = [l for l, _ in _IS_LABELS["profit_before_tax"]]
    assert labels[0] == primary
    assert labels[1] == bank
