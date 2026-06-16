# Mejhr Platform — Roadmap

## Completed

### Phase 2D — Company & Sector Import
- Official Saudi Exchange company list imported
- Company → sector/index mapping pipeline

### Phase 2E — XBRL Discovery & Download
- Saudi Exchange XBRL file discovery (now marked broken — `_ANNOUNCEMENT_SEARCH_BROKEN = True`)
- Official XBRL HTML file download and local storage
- Manual seed CLI (`xbrl_seed.py`) as fallback when discovery API is unavailable

### Phase 2E.1 — XBRL HTML Render
- Render required XBRL HTML sections (balance sheet, income statement, cash flow, changes in equity, filing info)

### Phase 2F — Raw XBRL Fact Extraction
- Parse raw facts from rendered XBRL HTML
- Atomic delete-then-insert to prevent duplicate facts from concurrent runs
- `xbrl_raw_items` table: official data only, no normalization

### Phase 2F.1 — Batch XBRL Validation
- Batch pipeline validation across target symbols
- Per-symbol coverage and failure reporting

---

## Planned

### Phase 2E.2 — Admin XBRL URL Ingestion

**Objective:** Allow an admin to submit an official Saudi Exchange XBRL URL from the admin dashboard. The system automatically runs the full import pipeline and reports status.

#### Admin Form Fields

| Field | Required | Notes |
|---|---|---|
| `company` / `symbol` | yes | Selected from known companies |
| `xbrl_url` | yes | Must be under `https://www.saudiexchange.sa/Resources/XBRL_DOCS/` |
| `fiscal_year` | yes | Integer |
| `fiscal_period` | yes | Annual / Q1 / Q2 / Q3 / Q4 / H1 / H2 |
| `language` | yes | ar / en |
| `filing_type` | yes | e.g. html |
| `notes` | no | Optional admin notes |

#### Validation Rules

1. URL must start with `https://www.saudiexchange.sa/Resources/XBRL_DOCS/`.
2. Symbol embedded in the URL should match the selected company where detectable.
3. `fiscal_year` and `fiscal_period` are required.
4. Duplicate URL → upsert the existing filing record, do not create a duplicate.
5. Non-Saudi-Exchange URLs are rejected.
6. Admin must explicitly confirm the source is official before submission.

#### Automatic Pipeline After Submit

1. Upsert `xbrl_filings` record.
2. Download the XBRL file.
3. Render the following required sections:
   - `100010`
   - `200100`
   - `300200`
   - `300400`
   - `300500`
   - `300600`
   - `300700`
   - `400100`
4. Save rendered file path.
5. Parse raw facts into `xbrl_raw_items`.

#### Import Status Shown to Admin

| Status | Meaning |
|---|---|
| `pending` | Queued, not yet started |
| `running` | Pipeline in progress |
| `completed` | All steps succeeded |
| `failed` | Pipeline stopped with error |

#### Import Stats Shown to Admin

- File downloaded (yes/no)
- Sections rendered (list)
- Missing sections (list)
- Raw facts inserted (count)
- Warnings / errors (list)

#### Audit Fields

| Field | Notes |
|---|---|
| `admin_user_id` | Who submitted |
| `submitted_at` | Submission timestamp |
| `import_job_id` | Background task / Celery job ID |
| `source_url` | The submitted XBRL URL |
| `selected_sections` | List of section codes rendered |
| `rendered_path` | Local path of rendered HTML |
| `status` | Final pipeline status |
| `error_message` | Populated if status = failed |

#### Hard Rules

- Do not normalize automatically in this feature.
- Do not calculate ratios automatically in this feature.
- Only import / render / parse raw facts.
- Normalization happens in a later reviewed step.

---

### Phase 2G.1 — Admin Manual Financial Entry Fallback

**Trigger:** XBRL is missing or unavailable for a company/period.

#### Data-Source Policy

| Priority | Source | Condition |
|---|---|---|
| 1 (primary) | Official Saudi Exchange XBRL | Always preferred |
| 2 (fallback) | Admin manual input | Only when XBRL is missing or unavailable |

**PDF policy:**
- PDF attachments are for human review reference only.
- Financial values must NOT be automatically extracted from PDFs.
- OCR/AI extraction of financial values is prohibited unless explicitly approved in a future phase.

#### Manual Entry Fields

| Field | Type | Notes |
|---|---|---|
| `company_id` | FK | |
| `symbol` | text | |
| `fiscal_year` | int | |
| `fiscal_period` | text | Annual / Q1 / Q2 / Q3 / Q4 / H1 / H2 |
| `statement_type` | text | balance_sheet / income_statement / cash_flow / changes_in_equity |
| `line_item_code` | text | |
| `line_item_name_ar` | text | |
| `line_item_name_en` | text | |
| `value` | numeric | |
| `currency` | text | |
| `unit` | text | |
| `period_start` | date | |
| `period_end` | date | |
| `instant_date` | date | nullable — if applicable |
| `source_reference` | text | Citation / description of the source |
| `source_pdf_url` | text | optional |
| `page_number` | int | optional |
| `entered_by` | FK/text | Admin user who entered the value |
| `entered_at` | timestamptz | |
| `reviewed_by` | FK/text | nullable until reviewed |
| `reviewed_at` | timestamptz | nullable until reviewed |
| `review_status` | enum | `draft` / `submitted` / `approved` / `rejected` |
| `data_status` | enum | `manual_pending` / `manual_approved` |
| `notes` | text | nullable |

#### Controls

1. Manual values must not appear in official calculations until `review_status = 'approved'`.
2. Manual values must be clearly labeled as manual in all outputs.
3. Manual values must never silently overwrite XBRL values.
4. If both XBRL and a manual value exist for the same line item, XBRL takes priority by default.
5. Conflicts between XBRL and manual values must be logged in `normalization_conflicts`.
6. Every manual edit must produce an audit log entry.
7. Admin can attach a PDF or source link as evidence (`source_pdf_url`, `page_number`).
8. Only `manual_approved` values (`review_status = 'approved'`) can flow into `normalized_financials`.
