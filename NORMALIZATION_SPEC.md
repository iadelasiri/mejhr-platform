# Phase 2G.0 — Normalization Design & Mapping Spec

**Status:** Design only. No values written to DB. Hard stop before Phase 2G implementation.
**Source data:** 6 symbols × raw xbrl_raw_items (Arabic labels from SA viewer HTML)
**Generated:** 2026-06-17

---

## 1. Source Data Summary

| Symbol | Company | Sector | IS Method | BS Format | Scale |
|--------|---------|--------|-----------|-----------|-------|
| 2240 | صناعات البناء المتقدمة | Basic Materials / Metals | Function of Expense | Current/Non-Current | بالآلاف (×1,000) |
| 2222 | أرامكو السعودية | Energy / Oil & Gas | **Nature of Expense** | Current/Non-Current | بالملايين (×1,000,000) |
| 2020 | سابك للمغذيات الزراعية | Basic Materials / Chemicals | **Nature of Expense** | Current/Non-Current | بالآلاف (×1,000) |
| 4263 | سال السعودية للخدمات اللوجستية | Industrials / Logistics | Function of Expense | Current/Non-Current | بالآلاف (×1,000) |
| 2050 | مجموعة صافولا | Consumer Staples / Food | Function of Expense | Current/Non-Current | بالآلاف (×1,000) |
| 1120 | مصرف الراجحي | Finance / Banks | **Bank** | **Order of Liquidity** | بالآلاف (×1,000) |

All filings in this sample are consolidated (موحدة) and annual (سنوي).

---

## 2. Company Classification

```
company_type = "non_financial"  →  all non-bank companies
company_type = "bank"           →  1120 (Rajhi) and any symbol in sector "المالية | البنوك"
company_type = "insurance"      →  deferred (no sample)
```

Classification source: `filing_info` fact with label `القطاع | المجموعة الصناعية` — if it contains `البنوك` → bank.

Income statement method source: `filing_info` fact with label `طريقة عرض قائمة الدخل`:
- `وظيفة المصاريف` → `is_method = "function"`
- `طبيعة المصاريف` → `is_method = "nature"`

---

## 3. Normalization Mapping — Balance Sheet (Non-Financial)

### 3A. High-Confidence Mappings (exact label, all 5 non-bank symbols)

| Field | Primary Arabic Label | Confidence | Notes |
|-------|---------------------|-----------|-------|
| `total_assets` | `إجمالي الموجودات` | HIGH | Identical across all 5 companies |
| `current_assets` | `إجمالي الموجودات المتداولة` | HIGH | All non-banks |
| `non_current_assets` | `إجمالي الموجودات غير المتداولة` | HIGH | All non-banks |
| `cash_and_equivalents` | `أرصدة لدى البنوك ونقد في الصندوق` | HIGH | All 5 non-banks use this label |
| `total_liabilities` | `إجمالي المطلوبات` | HIGH | All companies |
| `current_liabilities` | `إجمالي المطلوبات المتداولة` | HIGH | All non-banks |
| `non_current_liabilities` | `إجمالي المطلوبات غير المتداولة` | HIGH | All non-banks |
| `total_equity` | `إجمالي حقوق الملكية` | HIGH | All companies |

**Validation check:** `total_assets ≈ total_liabilities + total_equity` (balance sheet equation).

### 3B. Medium-Confidence Mappings (debt — multiple components, no single label)

**`short_term_debt`** — try labels in priority order, take first match:

| Priority | Arabic Label | Observed In |
|----------|-------------|-------------|
| 1 | `قروض قصيرة الأجل` | 2240 |
| 2 | `قروض - متداولة` | 2222 |
| 3 | `قسط متداول من قروض طويلة الأجل` | 2240, 4263 |

**`long_term_debt`** — try in priority order:

| Priority | Arabic Label | Observed In |
|----------|-------------|-------------|
| 1 | `قروض - غير متداولة` | 2222 |
| 2 | `سندات دين وقروض لأجل وقروض وصكوك مصدرة` | 2240, 4263, 2050 |
| 3 | `قروض وسلف` | 2050 |

**`total_debt`** — NOT a single label in any company. Derive as `short_term_debt + long_term_debt`.
- Do NOT include lease liabilities (`عقود إيجار تمويلية`) in `total_debt` unless explicitly requested.
- Lease lines go to `missing_fields` with note `lease_excluded`.

**Conflict rule for debt:** If multiple labels match, record all in `normalization_conflicts` with `field_name = "short_term_debt"` or `"long_term_debt"`. Do not pick one automatically — flag for manual review.

---

## 4. Normalization Mapping — Income Statement (Function of Expense)

Applies to: 2240, 4263, 2050. Condition: `is_method = "function"`.

| Field | Primary Arabic Label | Fallback Label | Confidence | Notes |
|-------|---------------------|---------------|-----------|-------|
| `revenue` | `الإيرادات` | `إجمالي دخل العمليات` | HIGH | 2240, 4263, 2050 |
| `cost_of_revenue` | `تكلفة المبيعات` | — | HIGH | Function method only |
| `gross_profit` | `إجمالي الربح (الخسارة)` | — | HIGH | Verify = revenue − COGS |
| `operating_profit` | `ربح (خسارة) العمليات` | — | HIGH | After all opex |
| `finance_cost` | `تكلفة تمويل` | — | HIGH | IS section only (not CF) |
| `profit_before_tax` | `الربح (الخسارة) قبل الزكاة وضريبة الدخل من العمليات المستمرة` | `ربح (خسارة) الفترة قبل الزكاة وضريبة الدخل` | HIGH | Prefer "المستمرة" variant |
| `zakat` | `مصاريف الزكاة على العمليات المستمرة للفترة` | `ضرائب الدخل والزكاة` | HIGH | See §4a |
| `income_tax` | `ضريبة الدخل على العمليات المستمرة للفترة` | — | MEDIUM | May be NULL for pure KSA cos |
| `net_income` | `ربح (خسارة) الفترة من العمليات المستمرة` | `ربح (خسارة) الفترة` | HIGH | See §4b |

### §4a — Zakat/Tax conflict

If `ضرائب الدخل والزكاة` (combined) is the only label (as in 2222), map to `zakat` and leave `income_tax = NULL`. If both zakat and income_tax labels exist (as in 2050), map each separately.

### §4b — Net income context conflict

`ربح (خسارة) الفترة` appears in 4 rows per symbol:
- Current year income statement
- Prior year income statement (comparative column)
- Current year statement of comprehensive income
- Prior year comprehensive income

**Resolution rule:** Filter by `statement_type = 'income_statement'` AND `period_end = filing_end_date`. If still multiple, prefer `ربح (خسارة) الفترة من العمليات المستمرة` over total (excludes discontinued ops).

---

## 5. Normalization Mapping — Income Statement (Nature of Expense)

Applies to: 2222, 2020. Condition: `is_method = "nature"`.

| Field | Mapping | Confidence |
|-------|---------|-----------|
| `revenue` | `إجمالي الإيرادات` OR `مبيعات` | MEDIUM — labels vary by company |
| `cost_of_revenue` | **UNRESOLVABLE** — costs are disaggregated | — → NULL |
| `gross_profit` | **UNRESOLVABLE** — no gross profit line | — → NULL |
| `operating_profit` | **UNRESOLVABLE** — no single line | — → NULL |
| `finance_cost` | `تكلفة تمويل` | HIGH — consistent with function method |
| `profit_before_tax` | `الربح (الخسارة) قبل الزكاة وضريبة الدخل من العمليات المستمرة` | HIGH |
| `zakat` | `مصاريف الزكاة على العمليات المستمرة للفترة` | HIGH |
| `net_income` | `ربح (خسارة) الفترة من العمليات المستمرة` | HIGH |

**Revenue conflict (2020):** `إجمالي الإيرادات` and `مبيعات بضاعة` appear with different values. Flag as conflict — do not auto-resolve. Manual review required.

**Revenue priority:** `إجمالي الإيرادات` → `مبيعات` (in that order). If both exist with different values → conflict.

---

## 6. Normalization Mapping — Bank (1120 / مصرف الراجحي)

Bank financials use a fundamentally different structure. Most non-bank fields are irrelevant or inapplicable.

### 6A. Balance Sheet — Bank

| Field | Arabic Label | Confidence | Notes |
|-------|-------------|-----------|-------|
| `total_assets` | `إجمالي الموجودات` | HIGH | Same label as non-banks |
| `total_liabilities` | `إجمالي المطلوبات` | HIGH | Same |
| `total_equity` | `إجمالي حقوق الملكية` | HIGH | Same |
| `current_assets` | **NULL** | — | Order-of-liquidity format — no current/non-current split |
| `non_current_assets` | **NULL** | — | Same |
| `current_liabilities` | **NULL** | — | Same |
| `non_current_liabilities` | **NULL** | — | Same |
| `cash_and_equivalents` | **NULL (see note)** | — | Bank cash = SAMA deposits + due from banks — not a single label |
| `net_loans_and_financing` *(new)* | `قروض وتمويل وسلف، صافي` | HIGH | Major bank asset |
| `customer_deposits` *(new)* | `ودائع العملاء` | HIGH | Major bank liability |

### 6B. Income Statement — Bank

| Field | Arabic Label | Confidence | Notes |
|-------|-------------|-----------|-------|
| `gross_special_commission_income` *(new)* | `دخل العمولات الخاصة / إجمالي دخل التمويل والاستثمارات` | HIGH | = total financing income before cost of funds |
| `cost_of_funds` *(new)* | `مصاريف / عائدات العمولات الخاصة على ودائع` | HIGH | = cost of customer deposits |
| `net_special_commission_income` *(new)* | `دخل (مصروف) العمولات الخاصة / دخل (مصاريف) التمويل والاستثمارات،صافي` | HIGH | = gross − cost of funds |
| `total_operating_income_bank` *(new)* | `إجمالي الدخل التشغيلي` | HIGH | = bank's equivalent of gross profit |
| `provision_for_credit_losses` *(new)* | `مخصص انخفاض (عكس قيد انخفاض) خسائر ائتمان / قروض وتمويل وسلف` | HIGH | Major bank expense |
| `revenue` | **Map to `gross_special_commission_income`** | MEDIUM | Approximate — reviewers should see both |
| `operating_profit` | `الربح (الخسارة) من النشاطات التشغيلية` | HIGH | = bank's operating earnings |
| `profit_before_tax` | `الربح (الخسارة) من العمليات المستمرة قبل الزكاة وضريبة الدخل` | HIGH |  |
| `zakat` | `مصاريف الزكاة على العمليات المستمرة للفترة` | HIGH | Same label as non-banks |
| `net_income` | `ربح (خسارة) الفترة من العمليات المستمرة` | HIGH | Same pattern |

### 6C. Cash Flow — Bank

| Field | Arabic Label | Notes |
|-------|-------------|-------|
| `operating_cash_flow` | `صافي التدفقات النقدية من (المستخدمة في) النشاطات التشغيلية` | Typically large negative for growing bank |
| `investing_cash_flow` | `صافي التدفقات النقدية من (المستخدمة في) النشاطات الاستثمارية` | |
| `financing_cash_flow` | `صافي التدفقات النقدية من (المستخدمة في) النشاطات التمويلية` | |
| `capex` | `شراء ممتلكات وآلات ومعدات` | Apply sign negation |
| `dividends_paid` | `توزيعات أرباح مدفوعة` | Bank uses shorter label |

---

## 7. Cash Flow Mappings (All Companies)

| Field | Primary Label | Notes |
|-------|--------------|-------|
| `operating_cash_flow` | `صافي التدفقات النقدية من (المستخدمة في) النشاطات التشغيلية` | Do NOT use `من العمليات` (pre-adjustment subtotal) |
| `investing_cash_flow` | `صافي التدفقات النقدية من (المستخدمة في) النشاطات الاستثمارية` | |
| `financing_cash_flow` | `صافي التدفقات النقدية من (المستخدمة في) النشاطات التمويلية` | |
| `capex` | `شراء ممتلكات وآلات ومعدات` → **negate** | Primary for all except 2222 |
| `capex` fallback | `نفقات رأسمالية` → use as-is | 2222 only; already negative |
| `dividends_paid` | `توزيعات أرباح مدفوعة إلى المساهمين في الشركة` | 2222 |
| `dividends_paid` fallback | `توزيعات أرباح مدفوعة (عدا لحقوق الملكية غير مسيطرة)، مصنفة كنشاطات تمويلية` | 4263, 2050 |
| `dividends_paid` fallback 2 | `توزيعات أرباح مدفوعة` | 1120 |

**Capex note:** The SA viewer presents outflows as positive numbers in the investing section. `شراء ممتلكات وآلات ومعدات` = 116,346 means SAR 116M paid. Store as -116,346 in normalized_financials. Exception: `نفقات رأسمالية` for 2222 is already stored as -188,890 (negative in source) — use as-is.

---

## 8. Period Selection Rules

Each raw fact has `period_start`, `period_end` (income statement / cash flow) or `instant_date` (balance sheet).

The filing's reporting period comes from `filing_info` facts:
- `تاريخ بداية الفترة للتقرير` → `filing_period_start`
- `تاريخ نهاية الفترة للتقرير` → `filing_period_end`

**Rule 1 — Current period only:** For income statement and cash flow, match facts where:
```
period_start = filing_period_start  AND  period_end = filing_period_end
```
Discard comparative (prior year) facts.

**Rule 2 — Balance sheet date:** Match `instant_date = filing_period_end`.

**Rule 3 — Continuing operations first:** When both `ربح (خسارة) الفترة` and `ربح (خسارة) الفترة من العمليات المستمرة` match, prefer the continuing-operations label. Record the discontinued-ops difference in `missing_fields` if material.

**Rule 4 — Context ambiguity:** If after Rules 1–3 multiple rows match the same label, record all as a conflict in `normalization_conflicts`. Do NOT auto-pick.

---

## 9. Scale Factor Rules

Each filing's reporting scale is in `filing_info`:

| Label value | Multiplier | Symbols using |
|------------|-----------|--------------|
| `بالآلاف` | 1,000 | 2240, 2020, 4263, 2050, 1120 |
| `بالملايين` | 1,000,000 | 2222 (Aramco) |
| `بالريالات` | 1 | Not seen in sample |

**Rule:** `normalized_value = value_numeric × scale_factor`

Normalized financials store values in **absolute SAR** (no division). All comparisons and ratios use absolute SAR.

Add `reporting_scale` (integer: 1 / 1000 / 1000000) column to `normalized_financials` for traceability.

---

## 10. Sign Conventions

| Field | Convention | Why |
|-------|-----------|-----|
| Revenue, gross_profit, operating_profit, net_income | POSITIVE = income | Standard |
| Cost of revenue | POSITIVE = cost | Store as positive |
| Finance cost | POSITIVE = expense | Source: `تكلفة تمويل` is already positive |
| Zakat / income tax | POSITIVE = expense | Source labels are positive in IS |
| Operating CF | POSITIVE = inflow | Already signed correctly in source |
| Investing CF | NEGATIVE = outflow | Already signed correctly in source |
| Financing CF | POSITIVE/NEGATIVE per source | Already signed correctly |
| Capex | NEGATIVE = outflow | Source has positive → negate; `نفقات رأسمالية` already negative |
| Dividends paid | NEGATIVE = outflow | 2222 source already negative; others positive → negate |
| Short/long-term debt | POSITIVE = balance | Balance sheet values are positive |
| Total equity | POSITIVE = balance | |

---

## 11. Conflict Resolution Rules

### 11A. Multiple label matches for the same field

If two Arabic labels both qualify for `revenue` (e.g., `الإيرادات` and `إجمالي الإيرادات`):
1. Check if values are equal → pick the first match, no conflict logged
2. Values differ → log `NormalizationConflict` with both raw_item_ids and values
3. Do NOT write any value to `normalized_financials.revenue` — leave NULL until resolved

### 11B. Current vs comparative period collision

After period filtering (Rule 1), if two facts remain with same label:
- They are from different column slots in the same SA viewer HTML
- Re-examine context_ref: `PERIOD__2024-01-01__2024-12-31` vs `PERIOD__2023-01-01__2023-12-31`
- Discard the prior year

### 11C. IS section vs CF section collision

`تكلفة تمويل` appears in both income_statement and cash_flow sections (different statement_type).
- Filter: only use `statement_type = 'income_statement'` for IS fields
- Filter: only use `statement_type = 'cash_flow'` for CF fields

### 11D. Continued + discontinued operations

If both `ربح (خسارة) الفترة` and `ربح (خسارة) الفترة من العمليات المستمرة` exist with different values:
- Use continuing operations for `net_income`
- Log the discontinued component in `missing_fields.discontinued_net_income`

### 11E. Conflict auto-resolution threshold

Future rule (Phase 2G.1 may define): if two candidates differ by <0.1% of the larger value, auto-pick the larger one and log `auto_resolved = true`. Do NOT apply now — all conflicts require manual review.

---

## 12. Proposed Schema Changes to `normalized_financials`

The existing schema is mostly adequate. The following changes are required before implementation:

### 12A. New columns — all companies

| Column | Type | Default | Reason |
|--------|------|---------|--------|
| `profit_before_tax` | Numeric(28,4) | NULL | Missing from current schema |
| `income_tax` | Numeric(28,4) | NULL | Currently merged with zakat — needs separation |
| `reporting_scale` | Integer | 1000 | For absolute SAR reconstruction |
| `is_consolidated` | Boolean | True | From `وصف طبيعة القوائم المالية` |
| `is_method` | Varchar(20) | NULL | `function` / `nature` / `bank` |
| `source_map` | JSONB | NULL | Per-field audit trail: `{field: {raw_item_id, label_ar, value_raw, context_ref}}` |

### 12B. New columns — bank-specific

| Column | Type | Reason |
|--------|------|--------|
| `gross_special_commission_income` | Numeric(28,4) | Bank total financing income |
| `cost_of_funds` | Numeric(28,4) | Bank cost of customer deposits |
| `net_special_commission_income` | Numeric(28,4) | Bank net financing spread |
| `total_operating_income_bank` | Numeric(28,4) | Bank equivalent of revenue (after fees, FX, etc.) |
| `provision_for_credit_losses` | Numeric(28,4) | Major bank expense |
| `net_loans_and_financing` | Numeric(28,4) | Bank loan book (asset) |
| `customer_deposits` | Numeric(28,4) | Bank funding base (liability) |

### 12C. Rename

| Old | New | Reason |
|-----|-----|--------|
| `equity` | `total_equity` | Consistency with other `total_*` names |
| `finance_cost` | `finance_cost` | No change — already correct |
| `zakat_tax` | `zakat` | Separate income_tax now added |

### 12D. Normalization conflict — add `field_source` column

Add `field_source` varchar(100) to `normalization_conflicts` to distinguish which mapping rule triggered the conflict (e.g., `"multi_label_revenue"`, `"context_ambiguity"`, `"period_filter_failed"`).

---

## 13. Validation Rules (post-normalization checks)

### 13A. Balance sheet equation

```
ABS(total_assets - (total_liabilities + total_equity)) / total_assets < 0.001
```
Tolerance: 0.1%. Failure → set `normalization_status = "conflict"`, log to `missing_fields.bs_equation_error`.

### 13B. Cash flow rollforward

```
operating_cash_flow + investing_cash_flow + financing_cash_flow ≈ net_change_in_cash
```
Where `net_change_in_cash` = `النقدية وشبه النقدية في نهاية الفترة` − `النقدية وشبه النقدية في بداية الفترة`.
Tolerance: 2% (FX effects can cause small residuals).

### 13C. Sign checks

| Assertion | Severity |
|-----------|---------|
| `revenue > 0` | WARNING if zero or negative |
| `total_assets > 0` | ERROR |
| `capex <= 0` | ERROR (capex must be outflow) |
| `total_equity > 0` | WARNING if negative (technically possible) |
| `finance_cost >= 0` | WARNING if negative (unusual) |

### 13D. Gross profit derivation check (function method only)

```
ABS(gross_profit - (revenue - cost_of_revenue)) / revenue < 0.001
```
If check fails → log conflict on `gross_profit`.

### 13E. Net income derivation check

```
ABS(net_income - (profit_before_tax - zakat - income_tax)) / ABS(profit_before_tax) < 0.01
```
Tolerance 1% (minority interest rounding). Failure → WARNING only (not a blocking error).

---

## 14. What Can Be Normalized Safely Now

These fields can be auto-populated from raw facts with high confidence and minimal risk of error:

**Balance sheet (non-bank):**
- `total_assets`, `current_assets`, `non_current_assets`
- `cash_and_equivalents`
- `total_liabilities`, `current_liabilities`, `non_current_liabilities`
- `total_equity`

**Income statement (function-of-expense companies: 2240, 4263, 2050):**
- `revenue`, `cost_of_revenue`, `gross_profit`, `operating_profit`
- `finance_cost`, `profit_before_tax`, `zakat`, `net_income`

**Income statement (nature-of-expense companies: 2222, 2020):**
- `revenue` (medium confidence — needs conflict check)
- `finance_cost`, `profit_before_tax`, `zakat`, `net_income`
- `cost_of_revenue`, `gross_profit`, `operating_profit` → **NULL** (cannot auto-resolve)

**Cash flow (all):**
- `operating_cash_flow`, `investing_cash_flow`, `financing_cash_flow`
- `capex` (with sign negation)
- `dividends_paid` (medium confidence — label varies)

**Bank (1120):**
- `total_assets`, `total_liabilities`, `total_equity`
- `gross_special_commission_income`, `net_special_commission_income`
- `total_operating_income_bank`, `provision_for_credit_losses`
- `profit_before_tax`, `zakat`, `net_income`
- `net_loans_and_financing`, `customer_deposits`
- `operating_cash_flow`, `investing_cash_flow`, `financing_cash_flow`, `capex`, `dividends_paid`

---

## 15. What Needs Manual Review

| Item | Reason | Symbols |
|------|--------|---------|
| `revenue` (nature-of-expense) | `إجمالي الإيرادات` vs `مبيعات` with different values | 2020 |
| `short_term_debt` / `long_term_debt` | Multiple component labels, no single total | All |
| `total_debt` | Derived from sum of ST + LT debt; conflicts expected | All |
| `gross_profit` / `operating_profit` | Not in source for nature-of-expense | 2222, 2020 |
| Discontinued operations | `2050` has large discontinued component | 2050 |
| `net_income` vs continuing net_income | `ربح (خسارة) الفترة` appears in 4 contexts | All |
| Revenue labeling (bank) | `revenue` field maps to bank concept that has no IS equivalent | 1120 |

---

## 16. What Should Be Deferred

| Item | Reason |
|------|--------|
| `cost_of_revenue` for 2222, 2020 | Nature-of-expense disaggregation requires judgment — not a safe auto-mapping |
| `operating_profit` for 2222, 2020 | Same; no single label |
| Insurance company mappings | No sample in Phase 2F; deferred to when insurance symbols are added |
| IFRS concept-based normalization | All current data uses Arabic labels, not IFRS taxonomy codes; switching requires re-download of XBRL XML source |
| Quarterly normalization | Current sample has only annual filings |
| LTM (trailing twelve months) | Requires at least 5 quarters of data — deferred |

---

## 17. Recommended Implementation Plan — Phase 2G.1

### Step 1: Schema migration
Add all new columns from §12 via Alembic migration. No data written yet.

### Step 2: Mapping engine
Implement `normalize_symbol(symbol, filing_id)` function in `backend/app/pipeline/exchange/xbrl_normalizer.py`:
1. Load `filing_info` facts → extract `filing_period_start`, `filing_period_end`, `reporting_scale`, `is_method`, `is_consolidated`, `company_type`
2. For each field in the mapping table: query `xbrl_raw_items` filtered by `symbol`, `statement_type`, `period_start/period_end or instant_date`
3. Apply label priority (first match wins unless conflict)
4. Apply scale factor
5. Apply sign convention
6. Run validation checks (§13)
7. Write to `normalized_financials`; write conflicts to `normalization_conflicts`

### Step 3: High-confidence fields first
Run normalizer for all 6 symbols, writing only the 20+ high-confidence fields (balance sheet totals, IS subtotals, cash flow totals). Validate against manual spot-checks.

### Step 4: Conflict review
Inspect all `normalization_conflicts` rows for `resolution_status = "unresolved"`. Resolve manually via admin interface (Phase 2E.2 or direct DB update).

### Step 5: Medium-confidence fields
After §3 conflicts are resolved, extend normalizer to debt fields and revenue variants.

### Step 6: Bank validation
Validate bank normalization separately — assert `total_assets ≈ total_liabilities + total_equity` and that `net_special_commission_income = gross − cost_of_funds`.

---

## 18. Remaining Blockers for Phase 2G.1

| Blocker | Resolution |
|---------|-----------|
| `normalized_financials` schema missing 12 columns | Alembic migration required before any writes |
| Scale factor not stored per raw fact | Must derive from `filing_info` at normalization time |
| Period filtering logic not implemented | Must implement context_ref parser |
| `company_type` not on companies table | Must add or derive from sector at normalization time |
| Bank fields `current_assets` / `non_current_assets` must be NULL for banks | Mapping engine must branch on company_type |
| Nature-of-expense missing `gross_profit` / `operating_profit` | Accept NULL; document in `missing_fields` |
| Conflict resolution UI not built | Phase 2E.2 form covers XBRL URL ingestion but not conflict resolution; separate UI needed or admin DB update |

---

*Hard stop: No normalization implemented in Phase 2G.0. No values written to DB. No ratios calculated.*
*Next step pending approval: Phase 2G.1 — implement normalization engine per §17.*
