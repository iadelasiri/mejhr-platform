# Phase 2G.6 — Admin Manual Financial Entry Fallback: Design Spec

**Status:** Design only. No code. No migrations. No UI. No ratios. No screener. No valuation.
**Generated:** 2026-06-19
**Supersedes:** The "Phase 2G.1 — Admin Manual Financial Entry Fallback" draft in `ROADMAP.md`. That name now collides with the completed normalization Phase 2G.1 (BS/CF totals). This document is the authoritative, expanded version under the current numbering — `ROADMAP.md` should be updated to point here once this spec is approved.
**Grounded against:** the actual current schema (`NormalizedFinancial`, `NormalizationConflict`, `Company`, `User`) and the actual current normalizer (`xbrl_normalizer.py`, Phase 2G.1–2G.3) — not a hypothetical future schema.

---

## 0. Why this exists

Some companies/periods will never have usable XBRL: the filing predates XBRL adoption, the Saudi Exchange XBRL viewer omits a section, or `xbrl_raw_items` resolves to a `NormalizationConflict` that nobody manually resolves. Today those fields sit `NULL` forever — correct per the platform's "no fabricated values" principle, but it means real gaps in the company page that an admin who has the official PDF in hand could close. This phase designs a controlled, auditable, clearly-labeled path for that — never a silent override of official XBRL data.

---

## 1. When manual entry is allowed

Manual entry is a **fallback of last resort**, not a parallel data path. It is allowed only when one of these is true for a specific `(symbol, fiscal_year, period, field)`:

| Condition | Example |
|---|---|
| **XBRL filing does not exist** for the period at all | Pre-XBRL-era annual report, or Saudi Exchange never published one |
| **XBRL filing exists but the field resolved to `missing`** | e.g. `short_term_debt` not in `missing_fields` because no label matched (2020, 2050) |
| **XBRL field resolved to a `NormalizationConflict`** that has sat `unresolved` past a defined review window | e.g. 2240's `short_term_debt` conflict between two debt-component labels |

Manual entry is **never allowed** when:
- XBRL already produced a clean value for that exact field+period (no "admin thinks the official number is wrong" override path in this phase — that would require a separate, more heavily-controlled "dispute" workflow, out of scope here).
- The field is outside the currently-normalized set (see §7 — this is the guard against using manual entry as a backdoor for forbidden fields).

**Trigger to surface the option to an admin:** the existing `NormalizedFinancial.missing_fields` JSON and `NormalizationConflict` rows are already the source of truth for "what's gap-able." An admin UI (future phase) would read those exact fields to decide what to offer for manual entry — no new "is this fillable" logic needs inventing.

---

## 2. Approval workflow

Four states, matching the original ROADMAP draft, made precise:

```
draft ──submit──▶ submitted ──approve──▶ approved
  │                   │
  │                   └──reject──▶ rejected ──(admin can re-edit)──▶ draft
  └──(admin can delete/edit freely while draft)
```

| State | Meaning | Who can act |
|---|---|---|
| `draft` | Admin is entering/editing a value. Not visible anywhere except the admin's own queue. | Entering admin only |
| `submitted` | Locked for editing. Awaiting review. | Any admin can review (see segregation-of-duties note below) |
| `approved` | Eligible to flow into `normalized_financials` on the next normalization run. Immutable — corrections require a new entry, not editing an approved row (preserves audit integrity). | — |
| `rejected` | Reviewer declined it. Returns to the original submitter as `draft` with the reviewer's reason attached, or can be archived. | — |

**Segregation of duties — flagged as a gap, not solved here:** the current `User.role` model has exactly two values (`admin`, `user`) via `require_admin` (`backend/app/core/security.py`). There is no "reviewer" vs. "data-entry" distinction today. Recommended control for this phase: **enforce `entered_by != reviewed_by` at the application layer** (an admin cannot approve their own submission), using the existing single `admin` role. A proper two-tier role split is a candidate for a future phase if manual entry volume grows — not proposed as a migration now.

---

## 3. Audit trail

Every state transition and every edit must be recorded, append-only. Two complementary mechanisms (design only, no migration yet):

1. **State timestamps on the entry itself** (cheap, sufficient for "what's the current state"): `entered_by`, `entered_at`, `reviewed_by`, `reviewed_at`, `review_status`. This is what the original ROADMAP draft already specified.
2. **A separate append-only log table** for full history (needed because an admin may edit a `draft` multiple times before submitting, get rejected and resubmit, etc. — the single-row timestamp fields above only capture the *latest* transition, not the full sequence):

   Proposed `manual_entry_audit_log` (design only):

   | Column | Type | Notes |
   |---|---|---|
   | `id` | UUID PK | |
   | `manual_entry_id` | UUID FK | |
   | `action` | string | `created` / `edited` / `submitted` / `approved` / `rejected` / `superseded` |
   | `actor_id` | UUID FK → users | |
   | `actor_role` | string | snapshot of role at time of action (role could change later) |
   | `before_value` | JSONB nullable | full row snapshot before the action, for edits |
   | `after_value` | JSONB | full row snapshot after the action |
   | `notes` | text nullable | reviewer's rejection reason, or submitter's note |
   | `created_at` | timestamptz | |

   This table is **INSERT-only at the application layer** — no UPDATE, no DELETE, enforced in code (not a DB-level immutability trigger, to keep this phase simple; a DB-level `REVOKE UPDATE, DELETE` could be added later if this becomes a compliance requirement).

---

## 4. How manual values interact with XBRL values

This is the most important section — it must not weaken the "no fabricated values, no silent overrides" principle that every prior phase (2G.1–2G.5) has held to.

**Rule: XBRL is always tried first, unconditionally.** The existing `normalize_symbol()` resolution flow (BS/CF/IS/revenue/debt resolvers in `xbrl_normalizer.py`) runs exactly as it does today, completely unaware that manual entries exist. Only *after* that pass completes does a new, separate step run:

```
for each field_name in result.missing_fields:
    look up an `approved` manual_entry for (symbol, fiscal_year, period, field_name)
    if exactly one unambiguous approved value exists:
        field_values[field_name] = manual_value
        source_map[field_name] = {
            "source": "manual",
            "manual_entry_id": ...,
            "entered_by": ...,
            "approved_by": ...,
            "source_reference": ...,
        }
        # field_name is removed from missing_fields, normalization_status
        # may upgrade from "partial" to a new status (see below)
    if multiple conflicting approved values exist (shouldn't happen if §5
    conflict rules are enforced at approval time, but checked defensively):
        leave the field NULL, log a NormalizationConflict with
        field_source="manual_vs_manual"
```

**Fields where XBRL already has a value are never touched by this step.** There is no comparison, no "admin override," no replacement logic for those — manual entry literally cannot run for a field that isn't in `missing_fields`. This directly satisfies ROADMAP's pre-existing rule #4 ("XBRL takes priority by default") by construction rather than by a runtime if/else that could be gotten wrong.

**New `normalization_status` value needed:** today's enum is `pending | normalized | partial | conflict | failed`. A manually-completed field changes the picture — it's no longer purely XBRL-derived. Recommend adding `"partial_manual"` (some fields manual, rest XBRL-derived, no conflicts) and reusing `"conflict"` when a manual value disagrees with something. **This is a schema enum-value change, not a structural migration** — flagged in §10 risks for explicit approval before implementation, per the hard stop on migrations.

---

## 5. Conflict rules

Three distinct conflict shapes, each handled differently:

| Conflict | Resolution | Logged as |
|---|---|---|
| **Manual vs. Manual** — two approved manual entries claim the same `(symbol, fiscal_year, period, field_name)` with different values | Should be prevented at approval time (a reviewer should never approve a second entry for an already-`approved` line item — see §7 uniqueness constraint). If it happens anyway (race condition, or an old entry approved before a newer conflicting submission), defensive check at normalization time leaves the field NULL. | `NormalizationConflict(field_source="manual_vs_manual")` |
| **Manual vs. XBRL discovered later** — a manual value was approved and flowed into `normalized_financials`, then a later XBRL re-run finds the field is no longer missing (new filing ingested, or a prior conflict got manually resolved upstream) | XBRL wins automatically on the next normalization run, by construction (§4) — the manual value is simply not consulted anymore because the field is no longer in `missing_fields`. The manual entry record itself is **not deleted** — it stays in its `approved` state for audit history, just no longer referenced by `source_map`. | Not a conflict — this is the designed behavior. Optionally log an informational note (not a `NormalizationConflict`) that a manual value was superseded. |
| **Manual value disagrees with a value an admin can see in a different document** (e.g., admin enters a number from the annual report PDF that doesn't match a number elsewhere) | Out of scope for this phase — there is no automated way to detect this since the "other document" isn't structured data. This relies entirely on the human reviewer step (§2) catching it before approval. | Reviewer's job, not the system's |

**Conflict auto-resolution is explicitly NOT introduced here**, consistent with NORMALIZATION_SPEC §11E ("Future rule... Do NOT apply now — all conflicts require manual review").

---

## 6. Source/reference attachment policy

Carries forward the existing, already-approved policy from ROADMAP.md unchanged:

- **PDF attachments are reference-only.** An admin may attach a `source_pdf_url` and `page_number` so a reviewer can verify the entered value against the original document.
- **No OCR. No AI extraction of financial values from PDFs.** This is a hard prohibition, not a "not yet implemented" — it must stay a human-read-and-type workflow unless a separate future phase explicitly proposes and gets approval for automated extraction (with its own accuracy/audit requirements).
- **`source_reference` (free text) is mandatory**, not optional — every manual entry must say *where* the number came from in human-readable form (e.g., "Annual Report 2025, page 42, Note 18 — Short-term borrowings"), independent of whether a PDF link is also attached (the link may rot; the citation should still be readable).
- If the source is a Saudi Exchange announcement already in the `announcements` table, the entry should reference it by `announcement_id`/`source_url` rather than re-uploading a duplicate PDF link — avoids redundant storage and keeps one canonical source pointer.

---

## 7. Required fields

Reconciled against the actual field names already in use by the normalizer (not the original ROADMAP draft's generic placeholders), and **deliberately restricted to the same allowed-field set as XBRL normalization** — this is the guard against manual entry becoming a backdoor for forbidden fields (EPS, EBITDA, gross_profit, operating_profit, ratios):

| Field | Type | Notes |
|---|---|---|
| `company_id` | FK → companies | |
| `symbol` | string | denormalized for query convenience, matches `NormalizedFinancial.symbol` |
| `fiscal_year` | int | |
| `period` | string | `"Annual"` / `"Q1"` / `"Q2"` / `"Q3"` / `"Q4"` / `"H1"` / `"H2"` — matches `NormalizedFinancial.period` exactly |
| `period_type` | string | `annual` / `quarterly` / `semi_annual` — matches `NormalizedFinancial.period_type` |
| `field_name` | enum, **restricted** | Must be one of the 17 fields currently normalized: `revenue`, `finance_cost`, `profit_before_tax`, `zakat_tax`, `net_income`, `total_assets`, `total_liabilities`, `equity`, `cash_and_equivalents`, `short_term_debt`, `long_term_debt`, `total_debt`, `operating_cash_flow`, `investing_cash_flow`, `financing_cash_flow`, `capex`, `free_cash_flow`. **Not** `eps`, `gross_profit`, `operating_profit`, `ebit`, or any ratio — expanding this list requires its own approved phase, exactly like XBRL normalization itself was phased. |
| `value` | numeric | In absolute SAR (same convention as `normalized_financials` — no separate scale factor for manual entries, to avoid a second scale-conversion bug surface) |
| `currency` | string | default `SAR` |
| `period_start` / `period_end` | date, nullable | for duration fields (IS/CF) — same semantics as `xbrl_raw_items` |
| `instant_date` | date, nullable | for balance-sheet fields |
| `source_reference` | text, **mandatory** | see §6 |
| `source_pdf_url` | text, optional | see §6 |
| `source_announcement_id` | FK, optional | see §6 |
| `page_number` | int, optional | |
| `entered_by` | FK → users | |
| `entered_at` | timestamptz | |
| `reviewed_by` | FK → users, nullable | |
| `reviewed_at` | timestamptz, nullable | |
| `review_status` | enum | `draft` / `submitted` / `approved` / `rejected` |
| `rejection_reason` | text, nullable | required when `review_status = 'rejected'` |
| `notes` | text, nullable | |

**Recommended uniqueness constraint** (design-level, not yet a migration): only one row may be `approved` at a time for a given `(symbol, fiscal_year, period, field_name)`. Multiple `draft`/`rejected` rows for the same line item are fine (re-attempts), but the system should refuse to approve a second `approved` row without first superseding the first one.

---

## 8. Admin permissions

Using the existing infrastructure, no new role machinery required for this phase:

- All manual-entry endpoints (create/edit draft, submit, approve, reject) require `role = "admin"` via the existing `require_admin` dependency (`backend/app/core/security.py`, already used by `jobs.py`).
- **Application-level rule** (not a DB constraint): `reviewed_by` must not equal `entered_by` — enforced in the endpoint handler, returning `403` if an admin attempts to approve/reject their own submission. This is the lightweight segregation-of-duties control discussed in §2, achievable with zero schema changes.
- Read access to manual entries (e.g., for the future admin review queue) is also `admin`-only — manual entries in `draft`/`submitted` state must never be visible through any public-facing endpoint, including the Phase 2G.5 `GET /companies/{symbol}/financials` endpoint, which only ever reflects `approved` values that have already flowed into `normalized_financials`.

---

## 9. API impact

### New admin-only endpoints (design only, not implemented)

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/admin/manual-financials` | Create a `draft` entry |
| `PUT /api/v1/admin/manual-financials/{id}` | Edit a `draft` entry (rejected entries become editable drafts again) |
| `POST /api/v1/admin/manual-financials/{id}/submit` | `draft` → `submitted` |
| `POST /api/v1/admin/manual-financials/{id}/approve` | `submitted` → `approved` (blocked if `reviewed_by == entered_by`) |
| `POST /api/v1/admin/manual-financials/{id}/reject` | `submitted` → `rejected`, requires `rejection_reason` |
| `GET /api/v1/admin/manual-financials` | List/filter queue by `symbol`, `fiscal_year`, `review_status` |
| `GET /api/v1/admin/manual-financials/{id}/audit-log` | Full history from §3's audit log table |

### Impact on the existing Phase 2G.5 endpoint

`GET /api/v1/companies/{symbol}/financials` already has two fields that this phase directly activates rather than introduces:

- **`metadata.manual_override`** — currently hardcoded `false` in the Phase 2G.5 schema (`ResponseMetadata.manual_override: bool = False`, see `backend/app/schemas/financial.py`). Once this phase ships, it would flip to `true` whenever *any* field in the response came from an approved manual entry rather than XBRL.
- **`data_quality.source_map`** — already designed to carry a per-field provenance dict (`{label_ar, raw_item_id, context_ref}` for XBRL fields, `{calculated: true, formula, ...}` for derived fields). This phase adds a third shape: `{source: "manual", manual_entry_id, entered_by, approved_by, source_reference}` for manually-filled fields. No structural change to the `source_map` field itself — it's already an untyped JSONB dict for exactly this kind of extensibility.

No other response-shape change is needed — this phase's data lands inside structures Phase 2G.5 already built.

---

## 10. Risks and controls

| Risk | Control |
|---|---|
| Admin enters an incorrect value | Mandatory `source_reference` (§6) + mandatory human review before `approved` (§2) + full audit trail (§3) |
| Self-approval (no real second pair of eyes) | Application-level `reviewed_by != entered_by` check (§2, §8) — acknowledged as weaker than a true second role, flagged as a future improvement candidate |
| Manual entry used as a backdoor for forbidden fields (EPS, ratios, EBITDA) | `field_name` restricted by enum to the exact 17 currently-normalized fields (§7) — expanding requires its own approved phase, same discipline as XBRL normalization |
| Manual data quietly treated as equally authoritative as official XBRL | `source_map[field].source = "manual"` and `metadata.manual_override = true` are always present and machine-readable wherever the field surfaces (§4, §9) — no endpoint may omit this label |
| Manual value becomes permanently stuck even after XBRL is later able to fill the gap | By construction, manual values are only consulted for fields still in `missing_fields` *at normalization time* — every re-run automatically prefers fresh XBRL data (§4, §5) |
| Audit trail tampering or silent edits | Append-only log table, INSERT-only at the application layer (§3); `approved` rows are immutable — corrections require a new entry, not an edit |
| Duplicate/competing approved entries for the same line item | Recommended uniqueness constraint: at most one `approved` row per `(symbol, fiscal_year, period, field_name)` (§7) |
| PDF/OCR scope creep (automated extraction introduced later without the same rigor) | Explicit prohibition restated (§6), not merely "deferred" |
| Admin queue exposing unapproved figures publicly | `draft`/`submitted` entries are never readable outside `admin`-only endpoints; public endpoints only ever see post-approval, normalized values (§8) |
| Schema/enum changes implied by this design (new `normalization_status` value, new tables) | **Not implemented in this phase.** Explicitly called out in §4 and here for separate approval before any migration is written, per this phase's hard stop |

---

## Hard stop

No code written. No migrations applied. No UI implemented. No ratios, screener, or valuation logic touched. This document is a design artifact only, pending your review and explicit approval before any implementation phase begins.
