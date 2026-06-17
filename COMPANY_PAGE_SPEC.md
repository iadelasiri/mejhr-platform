# Company Page Specification

**Status:** Design only. No UI implemented. No new normalization. No schema changes.
**Generated:** 2026-06-17
**Pipeline baseline:** Phase 2G.2 complete (BS + CF totals + limited IS fields normalized for 6 symbols).

---

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ available | DB column populated and pipeline-complete for sample symbols |
| 🟡 partial | Column or data exists but not complete (coverage gaps, some symbols NULL, or single-year only) |
| ❌ not implemented | Data not in DB; pipeline or schema work required |

**Source abbreviations:**

| Code | Meaning |
|------|---------|
| `XBRL` | From `xbrl_raw_items` → `normalized_financials` via normalizer |
| `MARKET` | From `market_data` (Saudi Exchange daily price feed) |
| `CO` | From `companies` / `company_profiles` table |
| `SECTOR` | From `sectors` / `industry_groups` / `industries` tables |
| `CALC` | Derived/calculated from other normalized fields |
| `ANNC` | From `announcements` table |
| `MANUAL` | Admin manual entry (Phase 2G.1 fallback — not yet implemented) |

---

## Section 1 — Header

| Field | DB Location | Source | Status | Phase Dependency | Notes / Risks |
|-------|-------------|--------|--------|-----------------|---------------|
| `company_name_ar` | `companies.arabic_name` | CO | ✅ available | — | Populated from Saudi Exchange official import (Phase 2D) |
| `company_name_en` | `companies.english_name` | CO | 🟡 partial | — | Populated where available; some symbols may be NULL |
| `symbol` | `companies.symbol` | CO | ✅ available | — | — |
| `market` | `companies.market` | CO | ✅ available | — | `tadawul` or `nomu` |
| `sector_ar` | `sectors.arabic_name` via `companies.sector_id` | SECTOR | ✅ available | — | Requires JOIN `companies → sectors`. Sector mapping complete for all imported companies |
| `sector_en` | `sectors.english_name` via `companies.sector_id` | SECTOR | 🟡 partial | — | English name present for most sectors; some may be NULL |
| `last_price` | `market_data.close` WHERE `trade_date = max(trade_date)` | MARKET | 🟡 partial | — | `market_data` table exists and schema is complete. Pipeline to ingest live price feed not yet implemented. Manual/seed data only |
| `price_timestamp` | `market_data.trade_date` | MARKET | 🟡 partial | — | Depends on price feed pipeline being live |

**Section risk:** Last price is not live — `market_data` table has no automated refresh pipeline. Display the trade_date prominently so the user knows the price is not real-time.

---

## Section 2 — Summary / Key Metrics

| Field | DB Location | Source | Status | Phase Dependency | Notes / Risks |
|-------|-------------|--------|--------|-----------------|---------------|
| `market_cap` | `market_data.market_cap` | MARKET | 🟡 partial | Price feed pipeline | Populated in `market_data` when price feed is active. Not live. |
| `enterprise_value` | `calculated_ratios.enterprise_value` | CALC | ❌ not implemented | Phase 2G.3 (total_debt, cash) + ratio calculation step | Formula: `market_cap + total_debt − cash_and_equivalents`. `total_debt` and `cash_and_equivalents` not yet normalized. |
| `net_profit` (net_income) | `normalized_financials.net_income` | XBRL | ✅ available | Phase 2G.2 ✅ done | Available for all 6 sample symbols. Continuing-ops preferred; total logged in `source_map["net_income_total"]` when they differ. |
| `EPS` | `normalized_financials.eps` | CALC | ❌ not implemented | `shares_outstanding` ingestion + EPS calculation step | Column exists in schema. Requires `net_income` (available) ÷ `shares_outstanding`. `CompanyProfile.shares_outstanding` column exists but not populated for all symbols. |
| `P/E` | `calculated_ratios.pe` | CALC | ❌ not implemented | EPS + live price | `calculated_ratios` table schema exists, NOT populated. No ratio calculation pipeline built. |
| `ROE` | `calculated_ratios.roe` | CALC | ❌ not implemented | Ratio calculation step | Formula: `net_income / equity`. Both columns available in `normalized_financials`; ratio calculation pipeline not built. |
| `ROIC` | `calculated_ratios.roic` | CALC | ❌ not implemented | Ratio calculation step | Formula: `NOPAT / invested_capital`. Complex multi-step derivation. NOPAT requires tax rate; invested_capital requires total_debt (not yet normalized). |
| `dividend_yield` | No dedicated table | ANNC | ❌ not implemented | Dividend history pipeline | `announcements` table captures raw SA announcements. No structured dividend table (amount, ex-date, yield). Parsing dividend announcements is a separate pipeline phase not yet planned. |
| `net_margin` | `calculated_ratios.net_margin` | CALC | ❌ not implemented | Revenue normalization (Phase 2G.3) | Formula: `net_income / revenue`. `revenue` column in schema but NOT normalized yet (deferred for nature-of-expense companies). |
| `data_quality_flags` | `normalized_financials.normalization_status` + `missing_fields` + `normalization_conflicts` | XBRL | ✅ available | — | `normalization_status` is one of: `pending / normalized / partial / conflict / failed`. `missing_fields` JSONB logs which fields were NULL and why. `NormalizationConflict` rows track unresolved conflicts. All three are populated by the normalizer. |

**Section risk:** Most summary metrics require either the ratio calculation pipeline (not built) or revenue normalization (not yet done). The page can show `market_cap`, `net_income`, and `data_quality_flags` immediately; the rest will display as NULL.

---

## Section 3 — Revenue & Profit Trend

| Field | DB Location | Source | Status | Phase Dependency | Notes / Risks |
|-------|-------------|--------|--------|-----------------|---------------|
| `revenue` (annual series) | `normalized_financials.revenue` | XBRL | ❌ not implemented | Phase 2G.3 | Column exists. For function-of-expense companies (2240, 4263, 2050): label `الإيرادات` — HIGH confidence. For nature-of-expense (2222, 2020): label conflict risk (see NORMALIZATION_SPEC §5). For banks (1120): maps to `gross_special_commission_income` — approximate only. |
| `net_profit` (annual series) | `normalized_financials.net_income` | XBRL | ✅ available | Phase 2G.2 ✅ done | Available for all 6 symbols for the single annual filing period ingested. |
| `net_margin` (annual series) | CALC | CALC | ❌ not implemented | Revenue (Phase 2G.3) + ratio step | Derived from `revenue` and `net_income`. |
| Annual history (multi-year) | Multiple rows in `normalized_financials` by `fiscal_year` | XBRL | 🟡 partial | Additional XBRL filings ingested | Currently only one annual period per symbol is normalized. Multi-year trend requires ingesting and normalizing prior-year filings individually. |
| Quarterly data | Quarterly rows in `normalized_financials` | XBRL | ❌ not implemented | Quarterly XBRL ingestion | No quarterly filings in the current pipeline. All sample filings are annual (`period_type = annual`). Quarterly normalization is deferred (NORMALIZATION_SPEC §16). |

---

## Section 4 — Financial Overview Cards

| Field | DB Location | Source | Status | Phase Dependency | Notes / Risks |
|-------|-------------|--------|--------|-----------------|---------------|
| `revenue` | `normalized_financials.revenue` | XBRL | ❌ not implemented | Phase 2G.3 | See Section 3. |
| `net_profit` | `normalized_financials.net_income` | XBRL | ✅ available | Phase 2G.2 ✅ done | — |
| `total_debt` | `normalized_financials.total_debt` (or SUM of `short_term_debt + long_term_debt`) | XBRL | ❌ not implemented | Phase 2G.3 (medium-confidence debt fields) | No single label covers total debt. Must derive from `short_term_debt + long_term_debt`. Both are medium-confidence and require conflict resolution per NORMALIZATION_SPEC §3B. |
| `total_assets` | `normalized_financials.total_assets` | XBRL | ✅ available | Phase 2G.1 ✅ done | — |
| `free_cash_flow` | `calculated_ratios.fcf` | CALC | ❌ not implemented | Ratio calculation step | Formula: `operating_cash_flow + capex`. Both columns are available and populated. FCF itself is not calculated because no ratio pipeline exists yet. Can be derived on the fly from `normalized_financials` as `operating_cash_flow + capex` (capex is stored as negative outflow). |
| `price_vs_EPS` (EPS chart) | `normalized_financials.eps` + `market_data.close` | CALC + MARKET | ❌ not implemented | EPS calculation + price feed | See Section 2 EPS row. |

---

## Section 5 — Quarterly Results Table

> **Note:** No quarterly filings are currently in the pipeline. All data below applies to annual filings only until quarterly XBRL ingestion is implemented.

| Column | DB Location | Source | Status | Phase Dependency | Notes / Risks |
|--------|-------------|--------|--------|-----------------|---------------|
| `revenue` | `normalized_financials.revenue` | XBRL | ❌ not implemented | Phase 2G.3 | — |
| `expenses` (total operating expenses) | No schema column | — | ❌ not implemented | Not planned | `expenses` is not a standard output in the XBRL normalizer. Would need to be derived or a new column added to schema. |
| `operating_profit` | `normalized_financials.operating_profit` | XBRL | ❌ not implemented | Phase 2G.3 | Column in schema. Only resolvable for function-of-expense companies. Nature-of-expense (2222, 2020) and banks (1120) cannot produce this field without additional label mapping. |
| `operating_margin` | CALC | CALC | ❌ not implemented | `operating_profit` + `revenue` | Both required. |
| `finance_cost` | `normalized_financials.finance_cost` | XBRL | ✅ available | Phase 2G.2 ✅ done | NULL for banks (1120) by design — label `تكلفة تمويل` not present in bank IS. |
| `depreciation` | No schema column | — | ❌ not implemented | Not in current plan | `depreciation` and `amortization` are not in the XBRL normalizer label maps. No schema column. Would require new Phase 2G.x work. Risk: label varies significantly across IS methods and companies. |
| `profit_before_tax` | `normalized_financials.profit_before_tax` | XBRL | ✅ available | Phase 2G.2 ✅ done | — |
| `zakat_tax` | `normalized_financials.zakat_tax` | XBRL | ✅ available | Phase 2G.2 ✅ done | May be negative (credit/reversal) — e.g. 2050 2025. Stored as-is. |
| `net_income` | `normalized_financials.net_income` | XBRL | ✅ available | Phase 2G.2 ✅ done | Continuing-ops preferred. |
| `EPS` | `normalized_financials.eps` | CALC | ❌ not implemented | Shares outstanding + calc step | — |
| `YoY growth` (all columns) | CALC | CALC | ❌ not implemented | Multi-year history | Requires at least 2 normalized periods per symbol. Currently single period only. |
| Quarterly granularity | — | — | ❌ not implemented | Quarterly XBRL ingestion | All current data is annual. |

---

## Section 6 — Profit & Loss Table

| Line Item | DB Location | Source | Status | Phase Dependency | Notes / Risks |
|-----------|-------------|--------|--------|-----------------|---------------|
| `revenue` | `normalized_financials.revenue` | XBRL | ❌ not implemented | Phase 2G.3 | — |
| `cost_of_revenue` | `normalized_financials.cost_of_revenue` | XBRL | ❌ not implemented | Phase 2G.3 | Column in schema. NULL by design for nature-of-expense companies (2222, 2020) — costs are disaggregated in those filings and cannot be auto-normalized. |
| `gross_profit` | `normalized_financials.gross_profit` | XBRL | ❌ not implemented | Phase 2G.3 | NULL for nature-of-expense and banks. Validation: should equal `revenue − cost_of_revenue` (±0.1%). |
| `operating_profit` | `normalized_financials.operating_profit` | XBRL | ❌ not implemented | Phase 2G.3 | NULL for nature-of-expense and banks (different structure). |
| `finance_cost` | `normalized_financials.finance_cost` | XBRL | ✅ available | Phase 2G.2 ✅ done | — |
| `depreciation` | No schema column | — | ❌ not implemented | Not planned | See Section 5. |
| `profit_before_tax` | `normalized_financials.profit_before_tax` | XBRL | ✅ available | Phase 2G.2 ✅ done | — |
| `zakat_tax` | `normalized_financials.zakat_tax` | XBRL | ✅ available | Phase 2G.2 ✅ done | — |
| `income_tax` | `normalized_financials.source_map["income_tax_detail"]` | XBRL | 🟡 partial | Schema column required | Identifiable for 2240 and 2050 only. Currently stored in `source_map` JSONB only (no dedicated column). Requires schema migration to surface on the company page. |
| `discontinued_operations` | `normalized_financials.source_map["net_income_total"]` | XBRL | 🟡 partial | Schema column required | Difference between `net_income` (continuing ops) and total period profit logged in `source_map` for 2020 and 2050 only. No dedicated column in schema. |
| `net_income` | `normalized_financials.net_income` | XBRL | ✅ available | Phase 2G.2 ✅ done | — |
| `EPS` | `normalized_financials.eps` | CALC | ❌ not implemented | Shares + calc step | — |
| Year columns (multi-period) | Multiple `fiscal_year` rows | XBRL | 🟡 partial | Additional filings ingested | Single year only until prior-year filings are ingested. |

---

## Section 7 — Balance Sheet Table

| Line Item | DB Location | Source | Status | Phase Dependency | Notes / Risks |
|-----------|-------------|--------|--------|-----------------|---------------|
| `cash_and_equivalents` | `normalized_financials.cash_and_equivalents` | XBRL | ❌ not implemented | Phase 2G.3 | Column in schema. Label `أرصدة لدى البنوك ونقد في الصندوق` — high confidence for non-banks. Banks: no single label (SAMA deposits + due from banks) → NULL for banks. |
| `current_assets` | `normalized_financials.current_assets` | XBRL | ❌ not implemented | Phase 2G.3 | NULL for banks (order-of-liquidity format). |
| `non_current_assets` | `normalized_financials.non_current_assets` | XBRL | ❌ not implemented | Phase 2G.3 | NULL for banks. |
| `total_assets` | `normalized_financials.total_assets` | XBRL | ✅ available | Phase 2G.1 ✅ done | — |
| `total_equity` | `normalized_financials.equity` | XBRL | ✅ available | Phase 2G.1 ✅ done | DB column is `equity` (not `total_equity`). |
| `current_liabilities` | `normalized_financials.current_liabilities` | XBRL | ❌ not implemented | Phase 2G.3 | NULL for banks. |
| `non_current_liabilities` | `normalized_financials.non_current_liabilities` | XBRL | ❌ not implemented | Phase 2G.3 | NULL for banks. |
| `total_liabilities` | `normalized_financials.total_liabilities` | XBRL | ✅ available | Phase 2G.1 ✅ done | — |
| `short_term_debt` | `normalized_financials.short_term_debt` | XBRL | ❌ not implemented | Phase 2G.3 (medium confidence) | Multiple competing labels — conflict-prone. See NORMALIZATION_SPEC §3B. Must not auto-pick when labels conflict; requires manual conflict resolution. |
| `long_term_debt` | `normalized_financials.long_term_debt` | XBRL | ❌ not implemented | Phase 2G.3 (medium confidence) | Same conflict risk. Note: lease liabilities (`عقود إيجار تمويلية`) must NOT be included in total_debt. |
| `total_debt` | `normalized_financials.total_debt` | CALC | ❌ not implemented | Phase 2G.3 | Derived as `short_term_debt + long_term_debt`. No single XBRL label covers total debt. |
| `debt_to_equity` | `calculated_ratios.debt_equity` | CALC | ❌ not implemented | Ratio calculation step | Requires `total_debt` and `equity`. |
| Year columns | Multiple `fiscal_year` rows | XBRL | 🟡 partial | Additional filings | Single year only currently. |

---

## Section 8 — Cash Flow Table

| Line Item | DB Location | Source | Status | Phase Dependency | Notes / Risks |
|-----------|-------------|--------|--------|-----------------|---------------|
| `operating_cash_flow` | `normalized_financials.operating_cash_flow` | XBRL | ✅ available | Phase 2G.1 ✅ done | — |
| `investing_cash_flow` | `normalized_financials.investing_cash_flow` | XBRL | ✅ available | Phase 2G.1 ✅ done | — |
| `financing_cash_flow` | `normalized_financials.financing_cash_flow` | XBRL | ✅ available | Phase 2G.1 ✅ done | — |
| `capex` | `normalized_financials.capex` | XBRL | ✅ available | Phase 2G.1 ✅ done | Stored as negative outflow. Primary label (`شراء ممتلكات وآلات ومعدات`) is negated; fallback label (`نفقات رأسمالية`, 2222 only) stored as-is. |
| `dividends_paid` | `normalized_financials.dividends_paid` | XBRL | ❌ not implemented | Phase 2G.3 | Column in schema. Label varies by company (see NORMALIZATION_SPEC §7). Medium confidence — label not present in all companies. |
| `free_cash_flow` | `calculated_ratios.fcf` | CALC | ❌ not implemented | Ratio calculation step | `operating_cash_flow + capex` (both available). Can compute on read if ratio pipeline not yet built. |
| Year columns | Multiple `fiscal_year` rows | XBRL | 🟡 partial | Additional filings | Single year currently. |

---

## Section 9 — Ratios

All ratios live in `calculated_ratios` table. Schema is fully defined. **No ratio calculation pipeline exists yet.** The `calculated_ratios` table is empty.

| Ratio | Formula | Components Available? | Status | Notes / Risks |
|-------|---------|----------------------|--------|---------------|
| `ROE` | `net_income / equity` | Both ✅ available | ❌ not implemented | Simplest ratio — all inputs ready. First candidate to enable once calc pipeline exists. |
| `ROIC` | `NOPAT / invested_capital` | Partial | ❌ not implemented | `NOPAT = operating_profit × (1 − tax_rate)`. Requires `operating_profit` (Phase 2G.3) and a tax rate assumption. `invested_capital = equity + total_debt`. `total_debt` not yet normalized. Complex — deferred. |
| `gross_margin` | `gross_profit / revenue` | Neither available | ❌ not implemented | Requires Phase 2G.3. NULL for nature-of-expense companies by design. |
| `operating_margin` | `operating_profit / revenue` | Neither available | ❌ not implemented | Same as gross_margin. NULL for nature-of-expense and banks. |
| `net_margin` | `net_income / revenue` | `net_income` ✅; `revenue` ❌ | ❌ not implemented | Closest to available — blocked only by revenue normalization. |
| `debt_to_equity` | `total_debt / equity` | `equity` ✅; `total_debt` ❌ | ❌ not implemented | Blocked by total_debt normalization. |

---

## Section 10 — Dividends

No dedicated dividend history table exists in the current schema. The `announcements` table captures raw Saudi Exchange announcements, but dividend-specific structured data (amount, ex-date, payment date, yield) is not extracted.

| Field | DB Location | Source | Status | Phase Dependency | Notes / Risks |
|-------|-------------|--------|--------|-----------------|---------------|
| `announcement_date` | `announcements.announced_at` | ANNC | 🟡 partial | Dividend announcement parser | Raw announcement timestamps available. No filter or classifier for dividend vs. non-dividend announcements in the pipeline. |
| `amount` (dividend per share) | No schema column | ANNC | ❌ not implemented | Dividend parser pipeline | Must be parsed from announcement title/body or XBRL dividend disclosure. Announcements are Arabic-language text — requires parsing logic or manual entry. |
| `price_at_announcement` | CALC from `market_data` | MARKET + CALC | ❌ not implemented | Price feed + dividend parser | Requires joining announcement date to `market_data.close` on matching `trade_date`. |
| `dividend_yield` | CALC | CALC | ❌ not implemented | Amount + price | `dividend_per_share / price_at_announcement` |
| `annual_yield` | CALC | CALC | ❌ not implemented | Historical dividend series | Sum of all dividends in a year / year-end price. |
| `payment_date` | No schema column | ANNC | ❌ not implemented | Dividend parser | Must be parsed from announcement text. |
| `consistency_years` | CALC | CALC | ❌ not implemented | Multi-year dividend series | Count of consecutive years with dividends. Requires historical series. |

**Section risk:** This section is entirely blocked. It requires a new pipeline phase to:
1. Classify `announcements` by type (filter for dividend announcements).
2. Parse dividend amount and dates from announcement text or attachments.
3. Create a dedicated `dividend_history` table.

---

## Section 11 — Peer Comparison

| Field | DB Location | Source | Status | Phase Dependency | Notes / Risks |
|-------|-------------|--------|--------|-----------------|---------------|
| `company` (peer list) | `companies` WHERE `sector_id = target.sector_id` | CO + SECTOR | ✅ available | — | Sector grouping is complete. Peer set = companies in the same sector. |
| `market_cap` | `market_data.market_cap` | MARKET | 🟡 partial | Price feed | Available where price feed is active. |
| `revenue` | `normalized_financials.revenue` | XBRL | ❌ not implemented | Phase 2G.3 | — |
| `net_profit` | `normalized_financials.net_income` | XBRL | ✅ available | Phase 2G.2 ✅ done | Available for 6 normalized symbols only. Other symbols in the same sector will be NULL until their filings are ingested. |
| `total_debt` | `normalized_financials.total_debt` | XBRL | ❌ not implemented | Phase 2G.3 | — |
| `gross_margin` | `calculated_ratios.gross_margin` | CALC | ❌ not implemented | Ratio step + revenue | — |
| `net_margin` | `calculated_ratios.net_margin` | CALC | ❌ not implemented | Revenue | — |
| `ROIC` | `calculated_ratios.roic` | CALC | ❌ not implemented | Ratio step | — |
| `ROE` | `calculated_ratios.roe` | CALC | ❌ not implemented | Ratio step | — |
| `P/E` | `calculated_ratios.pe` | CALC | ❌ not implemented | EPS + price | — |

**Section risk:** Peer comparison requires the same normalized fields for multiple symbols. Only 6 symbols are fully normalized now. Peer comparison is only meaningful once all or most symbols in a sector are normalized. Coverage completeness should be shown as a data quality flag.

---

## Section 12 — Insights / Valuation

| Insight | Components Needed | Status | Notes / Risks |
|---------|------------------|--------|---------------|
| `revenue_growth` (YoY) | `revenue` current + prior year | ❌ not implemented | Revenue not normalized; only one year of data available. Requires Phase 2G.3 + multi-year ingestion. |
| `profit_growth` (YoY) | `net_income` current + prior year | 🟡 partial | `net_income` available for current year. Prior-year comparison requires ingesting and normalizing prior filings. |
| `earnings_quality` (accruals ratio) | `net_income`, `operating_cash_flow`, `total_assets` | 🟡 partial | `net_income` and `operating_cash_flow` available. `total_assets` available. Could compute `(net_income − operating_cash_flow) / total_assets` as a proxy for earnings quality now. |
| `capital_efficiency` (ROIC) | `operating_profit`, `total_debt`, `equity` | ❌ not implemented | `operating_profit` and `total_debt` not yet normalized. |
| `cash_generation` (FCF yield) | `operating_cash_flow`, `capex`, `market_cap` | 🟡 partial | `operating_cash_flow` and `capex` available. `market_cap` partially available. FCF calc pipeline not built. |
| `fair_value_estimate` | Multiple inputs + model | ❌ not in scope | Requires valuation model, growth assumptions, discount rate. Out of scope for current phases. |
| `upside_downside` | `fair_value_estimate` + `last_price` | ❌ not in scope | Depends on fair_value_estimate above. |
| `warnings / data_quality_flags` | `normalization_status`, `missing_fields`, `normalization_conflicts` | ✅ available | All three are populated by the normalizer. Can surface: `partial` status, NULL field list, unresolved conflicts, BS equation failures. |

---

## Data Availability Summary

### Available now (Phase 2G.2 baseline)

| Category | Fields Available |
|----------|----------------|
| Company identity | `arabic_name`, `english_name`, `symbol`, `market`, `sector_ar/en` |
| Balance sheet totals | `total_assets`, `total_liabilities`, `equity` |
| Cash flow totals | `operating_cash_flow`, `investing_cash_flow`, `financing_cash_flow`, `capex` |
| IS (limited) | `finance_cost`, `profit_before_tax`, `zakat_tax`, `net_income` |
| Market data | `last_price` (close), `market_cap`, `change_pct`, `trade_date` (price feed not live) |
| Data quality | `normalization_status`, `missing_fields`, `source_map`, `NormalizationConflict` rows |

### Blocked on Phase 2G.3 (next normalization phase)

- `revenue`, `cost_of_revenue`, `gross_profit`, `operating_profit` (function-of-expense only)
- `cash_and_equivalents`, `current_assets`, `non_current_assets`
- `current_liabilities`, `non_current_liabilities`
- `short_term_debt`, `long_term_debt`, `total_debt` (conflict-prone)
- `dividends_paid`

### Blocked on ratio calculation pipeline

- All rows in `calculated_ratios`
- `EPS`, `P/E`, `P/B`, `P/S`
- `ROE`, `ROIC`, `gross_margin`, `operating_margin`, `net_margin`
- `free_cash_flow` (could be derived inline as `operating_cash_flow + capex`)
- `enterprise_value`, `net_debt`

### Blocked on dedicated pipeline phases (not yet planned)

- Dividends (amount, yield, payment date, consistency) — requires dividend parser
- Quarterly data — requires quarterly XBRL ingestion
- Multi-year trend — requires additional annual filings ingested and normalized
- `income_tax` as a first-class column — requires schema migration (currently in `source_map` only)
- `discontinued_operations` as a first-class column — same
- Bank-specific fields (`net_special_commission_income`, `provision_for_credit_losses`, etc.)

### Fields not in schema and not in current plan

- `depreciation` / `amortization`
- `expenses` (total operating expenses aggregate)
- `EV/EBIT`, `EV/EBITDA` (requires EBITDA — no schema column and deferred per hard stop)
- `fair_value_estimate`, `upside_downside`
- `dividend_yield`, `annual_yield`, `consistency_years`

---

## Existing Schema Gaps Relevant to This Page

These columns are referenced in this spec but require schema work before they can be populated:

| Column | Table | Gap |
|--------|-------|-----|
| `income_tax` | `normalized_financials` | No column — stored in `source_map["income_tax_detail"]` only. Requires new Alembic migration. |
| `discontinued_operations` | `normalized_financials` | No column — stored in `source_map["net_income_total"]` only. Requires new Alembic migration. |
| `is_method` | `normalized_financials` | No column. Required to distinguish function/nature/bank IS structure. See NORMALIZATION_SPEC §12A. |
| `is_consolidated` | `normalized_financials` | No column. Required to flag consolidated vs. standalone. See NORMALIZATION_SPEC §12A. |
| Bank-specific IS/BS columns | `normalized_financials` | 7 columns listed in NORMALIZATION_SPEC §12B — none in current schema. |
| Dividend history | — | No table. `announcements` has raw SA announcements but no structured dividend fields. |

---

*Hard stop: no UI implemented, no new normalization, no schema changes in this document.*
*This spec is a planning artifact only. Implementation phases must be explicitly approved before execution.*
