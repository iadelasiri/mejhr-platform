"""
Phase 2G.1 tests — XBRL normalization (BS totals + CF totals).

All tests are offline: no DB connection, no network.  Facts are built as simple
namespace objects so we avoid SQLAlchemy model machinery.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.pipeline.exchange.xbrl_normalizer import (
    NormalizeResult,
    _BS_LABELS,
    _CF_LABELS,
    _resolve_bs,
    _resolve_cf,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fact(
    label_ar: str,
    value_numeric: float | None,
    statement_type: str,
    *,
    instant_date: date | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
    context_ref: str | None = None,
    fact_id: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.UUID(fact_id) if fact_id else uuid.uuid4(),
        label_ar=label_ar,
        value_numeric=Decimal(str(value_numeric)) if value_numeric is not None else None,
        statement_type=statement_type,
        instant_date=instant_date,
        period_start=period_start,
        period_end=period_end,
        context_ref=context_ref or (
            f"INSTANT__{instant_date}" if instant_date
            else f"PERIOD__{period_start}__{period_end}"
        ),
    )


_BS_DATE = date(2025, 12, 31)
_CF_START = date(2025, 1, 1)
_CF_END = date(2025, 12, 31)
_PRIOR_BS = date(2024, 12, 31)
_PRIOR_START = date(2024, 1, 1)
_PRIOR_END = date(2024, 12, 31)


# ── Tests: Balance Sheet label maps ──────────────────────────────────────────

def test_maps_total_assets():
    fid = str(uuid.uuid4())
    facts = [
        _fact("إجمالي الموجودات", 5_000_000, "balance_sheet",
              instant_date=_BS_DATE, fact_id=fid),
        _fact("إجمالي الموجودات", 4_500_000, "balance_sheet",
              instant_date=_PRIOR_BS),
    ]
    result = _resolve_bs("total_assets", "إجمالي الموجودات", False, facts, _BS_DATE)
    assert result is not None
    assert not isinstance(result, type(None))
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("5000000")
    assert result.raw_item_id == fid
    assert result.label_ar == "إجمالي الموجودات"


def test_maps_total_liabilities():
    fid = str(uuid.uuid4())
    facts = [
        _fact("إجمالي المطلوبات", 2_000_000, "balance_sheet",
              instant_date=_BS_DATE, fact_id=fid),
    ]
    result = _resolve_bs("total_liabilities", "إجمالي المطلوبات", False, facts, _BS_DATE)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("2000000")


def test_maps_total_equity():
    fid = str(uuid.uuid4())
    facts = [
        _fact("إجمالي حقوق الملكية", 3_000_000, "balance_sheet",
              instant_date=_BS_DATE, fact_id=fid),
    ]
    # DB column is 'equity', label maps to 'إجمالي حقوق الملكية'
    result = _resolve_bs("equity", "إجمالي حقوق الملكية", False, facts, _BS_DATE)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("3000000")
    assert result.field_name == "equity"


# ── Tests: Cash Flow label maps ───────────────────────────────────────────────

def test_maps_operating_cash_flow():
    label = "صافي التدفقات النقدية من (المستخدمة في) النشاطات التشغيلية"
    facts = [
        _fact(label, 1_200_000, "cash_flow",
              period_start=_CF_START, period_end=_CF_END),
    ]
    result = _resolve_cf("operating_cash_flow", [(label, False)], facts, _CF_START, _CF_END)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("1200000")


def test_maps_investing_cash_flow():
    label = "صافي التدفقات النقدية من (المستخدمة في) النشاطات الاستثمارية"
    facts = [
        _fact(label, -300_000, "cash_flow",
              period_start=_CF_START, period_end=_CF_END),
    ]
    result = _resolve_cf("investing_cash_flow", [(label, False)], facts, _CF_START, _CF_END)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("-300000")


def test_maps_financing_cash_flow():
    label = "صافي التدفقات النقدية من (المستخدمة في) النشاطات التمويلية"
    facts = [
        _fact(label, -500_000, "cash_flow",
              period_start=_CF_START, period_end=_CF_END),
    ]
    result = _resolve_cf("financing_cash_flow", [(label, False)], facts, _CF_START, _CF_END)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("-500000")


# ── Tests: Capex sign convention ──────────────────────────────────────────────

def test_capex_sign_flip_primary_label():
    """Primary capex label (شراء ممتلكات...) is stored positive → must be negated."""
    label = "شراء ممتلكات وآلات ومعدات"
    facts = [
        _fact(label, 116_346, "cash_flow",
              period_start=_CF_START, period_end=_CF_END),
    ]
    specs = _CF_LABELS["capex"]
    result = _resolve_cf("capex", specs, facts, _CF_START, _CF_END)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("-116346"), "capex must be stored as negative outflow"


def test_capex_fallback_label_not_negated():
    """Fallback capex label (نفقات رأسمالية, 2222-only) is already negative → keep as-is."""
    primary = "شراء ممتلكات وآلات ومعدات"
    fallback = "نفقات رأسمالية"
    facts = [
        _fact(fallback, -188_890, "cash_flow",
              period_start=_CF_START, period_end=_CF_END),
    ]
    specs = _CF_LABELS["capex"]
    result = _resolve_cf("capex", specs, facts, _CF_START, _CF_END)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("-188890"), "fallback capex label must NOT be negated"


# ── Tests: Period filtering ───────────────────────────────────────────────────

def test_comparative_period_ignored_bs():
    """Only the current-period instant_date matches; prior-year row must be discarded."""
    label = "إجمالي الموجودات"
    current_id = str(uuid.uuid4())
    facts = [
        _fact(label, 5_000_000, "balance_sheet",
              instant_date=_BS_DATE, fact_id=current_id),
        _fact(label, 4_500_000, "balance_sheet",
              instant_date=_PRIOR_BS),
    ]
    result = _resolve_bs("total_assets", label, False, facts, _BS_DATE)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("5000000")
    assert result.raw_item_id == current_id


def test_comparative_period_ignored_cf():
    """Only the current period_start/period_end pair matches."""
    label = "صافي التدفقات النقدية من (المستخدمة في) النشاطات التشغيلية"
    current_id = str(uuid.uuid4())
    facts = [
        _fact(label, 1_200_000, "cash_flow",
              period_start=_CF_START, period_end=_CF_END, fact_id=current_id),
        _fact(label, 900_000, "cash_flow",
              period_start=_PRIOR_START, period_end=_PRIOR_END),
    ]
    result = _resolve_cf("operating_cash_flow", [(label, False)], facts, _CF_START, _CF_END)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.value == Decimal("1200000")
    assert result.raw_item_id == current_id


# ── Tests: Conflict detection ─────────────────────────────────────────────────

def test_conflict_when_same_label_different_values():
    """Two facts with the same label, same period, different values → Conflict."""
    label = "إجمالي الموجودات"
    facts = [
        _fact(label, 5_000_000, "balance_sheet", instant_date=_BS_DATE),
        _fact(label, 5_500_000, "balance_sheet", instant_date=_BS_DATE),
    ]
    result = _resolve_bs("total_assets", label, False, facts, _BS_DATE)
    from app.pipeline.exchange.xbrl_normalizer import _Conflict
    assert isinstance(result, _Conflict)
    assert result.field_name == "total_assets"
    assert len(result.candidates) == 2


# ── Tests: Source traceability ────────────────────────────────────────────────

def test_source_traceability_preserved():
    """Match result must carry raw_item_id, label_ar, and context_ref."""
    fid = str(uuid.uuid4())
    ctx = "INSTANT__2025-12-31"
    facts = [
        _fact("إجمالي الموجودات", 5_000_000, "balance_sheet",
              instant_date=_BS_DATE, context_ref=ctx, fact_id=fid),
    ]
    result = _resolve_bs("total_assets", "إجمالي الموجودات", False, facts, _BS_DATE)
    from app.pipeline.exchange.xbrl_normalizer import _Match
    assert isinstance(result, _Match)
    assert result.raw_item_id == fid
    assert result.label_ar == "إجمالي الموجودات"
    assert result.context_ref == ctx


# ── Tests: Label map integrity ────────────────────────────────────────────────

def test_bs_label_map_has_required_fields():
    assert set(_BS_LABELS.keys()) == {"total_assets", "total_liabilities", "equity"}


def test_cf_label_map_has_required_fields():
    assert set(_CF_LABELS.keys()) == {
        "operating_cash_flow", "investing_cash_flow", "financing_cash_flow", "capex"
    }


def test_cf_capex_has_two_labels():
    assert len(_CF_LABELS["capex"]) == 2
    labels = [l for l, _ in _CF_LABELS["capex"]]
    assert "شراء ممتلكات وآلات ومعدات" in labels
    assert "نفقات رأسمالية" in labels
