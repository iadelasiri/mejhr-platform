# Phase 2D.2 — Daily Prices & Announcements: Source Discovery Report

**Status:** Discovery only. No pipeline implemented. No DB writes. No migrations applied.
**Generated:** 2026-06-18
**Method:** Live probing of `saudiexchange.sa` via `curl_cffi` (Chrome124 TLS impersonation) from this environment. No third-party sources (no yfinance, no Argaam, no StockAnalysis, no unofficial feeds) were used or considered.
**Environment note:** Plain `httpx` (no TLS impersonation) is blocked with `HTTP 403` + Akamai headers from this environment, confirming the existing finding in [[feedback_saudi_exchange]]. `curl_cffi` with `impersonate="chrome124"` bypasses this for all GET requests tested below.

---

## A. Company Prices

### Endpoints found

| # | Method | URL | Status |
|---|--------|-----|--------|
| 1 | GET | `/tadawul.eportal.theme.helper/TickerServlet` | 200, confirmed JSON |
| 2 | — | Main Market Watch page embeds a JS `tickerData` array | same data as #1, weaker |
| 3 | — | Individual "Company Profile" page (`/wps/portal/saudiexchange/hidden/company-profile-main/...?companySymbol=2222`) | 200, but generic shell — no company-specific OHLCV server-rendered |

### Sample payload — `TickerServlet`

```json
{
  "pk_rf_company": "2222",
  "companyShortNameEn": "SAUDI ARAMCO",
  "companyShortNameAr": "أرامكو السعودية",
  "companyLongNameEn": "Saudi Arabian Oil Co.",
  "companyLongNameAr": "شركة الزيت العربية السعودية",
  "highPrice": null,
  "lowPrice": null,
  "noOfTrades": 15755,
  "previousClosePrice": null,
  "todaysOpen": null,
  "transactionDate": null,
  "turnOver": 604947114.32,
  "volumeTraded": 22849767,
  "aveTradeSize": 1450.32,
  "change": -0.08,
  "changePercent": -0.3,
  "lastTradePrice": 26.52,
  "transactionDateStr": null
}
```

`stockData` contains 399 records (verified to include both large-cap main-market symbols like `2222`, `2380`–`2382` and smaller traded funds like `4700`–`4702`). **`highPrice`, `lowPrice`, `previousClosePrice`, `todaysOpen`, and `transactionDate` were `null` across every sampled record**, including Aramco — this is not a data-availability fluke for illiquid names, it appears to be structurally unpopulated by this servlet.

### Field mapping vs. requirements

| Required field | Source field | Status |
|---|---|---|
| `symbol` | `pk_rf_company` | ✅ available |
| `trade_date` | `transactionDate` | ❌ always null |
| `open` | `todaysOpen` | ❌ always null |
| `high` | `highPrice` | ❌ always null |
| `low` | `lowPrice` | ❌ always null |
| `close` | `lastTradePrice` | ✅ available |
| `previous_close` | `previousClosePrice` | ❌ always null |
| `change` | `change` | ✅ available |
| `change_percent` | `changePercent` | ✅ available |
| `volume` | `volumeTraded` | ✅ available |
| `traded_value` | `turnOver` | ✅ available |
| `trades_count` | `noOfTrades` | ✅ available |

### Gap

No endpoint reachable via `curl_cffi` returns full daily OHLCV (open/high/low/close/previous_close) for individual companies. The "Company Profile" page's quote widget likely loads via a lazy client-side call that never appeared in the static HTML — consistent with an Angular/React component that only fires after full JS execution. **This requires Playwright to confirm** (not yet attempted in this discovery pass — see Implementation Plan).

---

## B. Index Prices

### Endpoints found

| # | Method | URL | Status |
|---|--------|-----|--------|
| 1 | GET | `/tadawul.eportal.theme.helper/ThemeTASIUtilityServlet` | 200, confirmed JSON — full OHLCV for TASI + MT30 |
| 2 | GET | `/tadawul.eportal.theme.helper/RefreshTradeDetailsServlet?companySymbol=X` | 200, **identical payload regardless of `companySymbol`** — name is misleading; it's a market-summary servlet, not company-specific |
| 3 | — | Listed-securities page embeds a JS `indicesJson` array | 200 — open/close/change for all 22 sector indices + 7 market-wide indices |

### Sample payload — `ThemeTASIUtilityServlet` (TASI bean)

```json
{
  "tasiBean": {
    "symbol": "TASI",
    "tasiTodaysSummaryBean": {
      "openPrice": 11117.12,
      "indexPrice": 11121.13,
      "netChange": 6.23,
      "percentChange": 0.06,
      "previouseIndexPrice": 11114.9,
      "volumeTraded": 275069403,
      "highPrice": 11136.26,
      "lowPrice": 11099.8,
      "turnOver": 6541910657.19,
      "noOfTrades": 412822,
      "noOfCompaniesTraded": 268,
      "status": 2
    }
  },
  "mt30Bean": { "symbol": "MT30", "tasiTodaysSummaryBean": { "...": "same shape" } }
}
```

### Sample payload — `indicesJson` (listed-securities page, sector/market indices)

```json
{"symbol":"TCPI","name":"Commercial & Professional Svc","price":4011.03,"volume":5223906,"turnover":60598540.31,"netChange":-24.22,"netPercentChange":-0.6,"priceIndicatorCssClass":"priceDown","open":4030.54,"noOfTrades":"7943"}
{"symbol":"TASI","name":"Tadawul All Share Index (TASI)","price":11121.13,"volume":275069403,"turnover":6541910657.19,"netChange":6.23,"netPercentChange":0.06,"priceIndicatorCssClass":"priceUp","open":11117.12,"noOfTrades":"412822"}
```

### Field mapping vs. requirements

| Required field | TASI/MT30 (`ThemeTASIUtilityServlet`) | Sector/market indices (`indicesJson`) |
|---|---|---|
| `index_code` | `tasiBean.symbol` | `symbol` |
| `trade_date` | ❌ no explicit field — must derive from `currentTime` (today, Asia/Riyadh) | ❌ same |
| `open` | `openPrice` ✅ | `open` ✅ |
| `high` | `highPrice` ✅ | ❌ not present |
| `low` | `lowPrice` ✅ | ❌ not present |
| `close` | `indexPrice` ✅ | `price` ✅ |
| `previous_close` | `previouseIndexPrice` ✅ | derivable: `price − netChange` |
| `change` | `netChange` ✅ | `netChange` ✅ |
| `change_percent` | `percentChange` ✅ | `netPercentChange` ✅ |
| `value/volume` | `volumeTraded`, `turnOver` ✅ | `volume`, `turnover` ✅ |
| `trades_count` | `noOfTrades` ✅ | `noOfTrades` ✅ |

**B is in good shape via `curl_cffi` alone.** TASI and MT30 get full OHLCV. The 22 GICS sector indices and the other 5 market-wide indices (`TLCIC`, `TMCIC`, `TSCIC`, `TIPOC`, `TT50CI`) get everything except explicit high/low (close/open/change/volume/turnover/trades are all present). No index source gives an explicit `trade_date` — this must be set to the current Saudi trading day at fetch time, with care taken on weekends (Sat/Sun) and public holidays (Saudi market trades Sun–Thu) by checking `marketStatusCode`/`currentTime` rather than blindly using `date.today()`.

---

## C. Company Announcements

### Endpoint found

`https://www.saudiexchange.sa/wps/portal/saudiexchange/newsandreports/news/company-announcements`

This is a genuine, distinct portal page (confirmed: 572 KB, not a generic 1,016 KB fallback shell). It renders a search form with fields `annoucmentType`, `symbol`, `fromDate`, `toDate`, `datePeriod`, `textSearch`, `pageNumberDb`, `pageSize`, `requestLocale`, and loads results via:

```js
$.ajax({
    url: 'p0/IZ7_5A602H80O0TRC068TFQ7NN00C3=CZ6_5A602H80OOA970QFJBGILA3867=NJgetNewsListData=/',
    type: 'POST',
    data: formJSON,
    success: function(data) {
        var jArr = jQuery.parseJSON(data);
        $.each(jArr.announcementList, function(index, obj) { listingList.push(obj); });
        var totalCount = jArr.totalCount;
        ...
    }
});
```

Expected response shape: `{"announcementList": [...], "totalCount": N}` — **but the exact field names inside each announcement object were not captured**, because:

### Blocker — confirmed

I POSTed directly to the resource URL with `curl_cffi` (both with and without `X-Requested-With: XMLHttpRequest` / `Accept: application/json` headers). **Both attempts returned HTTP 200 with the full page HTML shell (573 KB), not the JSON payload.** This is a WebSphere Portal "resource-serving" URL — the cryptic `IZ7_..._getNewsListData=` segment encodes a portlet window ID that is scoped to an active browser session/render state. A stateless POST cannot replicate this.

This is **not** the same failure mode as the old `ci_anncmnt/annWdgtSearch` endpoint (confirmed `404`, portlet removed in the portal rebuild, per the `_ANNOUNCEMENT_SEARCH_BROKEN = True` flag already in `xbrl_discovery.py`). This is a *different* endpoint that returns `200` but the wrong content — a session/render-state requirement, not a removed-endpoint 404.

**Conclusion: Playwright is required for company announcements.** A real browser must load the page (establishing the portlet session), submit the search form (or intercept the resulting XHR), and the response captured via network interception or DOM scraping after JS execution.

---

## D. Market Announcements

### Endpoint found

`https://www.saudiexchange.sa/wps/portal/saudiexchange/newsandreports/news` — same page family, same `getNewsListData` POST mechanism, with `symbol` left blank to get all-market announcements rather than company-specific ones.

### Blocker

Identical to C — same WebSphere Portal resource-serving URL pattern, same session requirement, same confirmed failure when posted statelessly via `curl_cffi`.

**Conclusion: Playwright is required for market announcements**, using the same mechanism as C (likely the same Playwright script with `symbol` parameter omitted).

---

## curl_cffi vs. Playwright — summary

| Target | curl_cffi sufficient? | Notes |
|---|---|---|
| A. Company prices | **Partial** | Close/change/volume/turnover/trades available via `TickerServlet`; OHLC + trade_date missing. Full OHLCV needs Playwright on the company profile widget (untested) or the historical-reports download mechanism (untested, likely same WPS portlet pattern). |
| B. Index prices | **Yes** | Full OHLCV for TASI/MT30; open/close/change/volume for sector & other market indices. `trade_date` must be derived, not read from the payload. |
| C. Company announcements | **No** | Confirmed: stateless POST returns the page shell, not JSON. Playwright required. |
| D. Market announcements | **No** | Same as C. |

Existing project precedent: Playwright (`playwright==1.49.0`) is **already a dependency**, used for the XBRL HTML viewer rendering in Phase 2E.1 (`xbrl_renderer.py`). Adopting it here is consistent with the established pattern, not a new tool introduction.

---

## Proposed DB tables / migrations

### Reuse existing tables (no new table needed)

| Target | Existing model | Gap |
|---|---|---|
| Company daily prices | `MarketData` (`backend/app/models/market_data.py`) | **Already has the exact schema needed**: `symbol`, `trade_date`, `open`, `high`, `low`, `close`, `previous_close`, `change_amount`, `change_pct`, `volume`, `turnover`, `trades`, `market_cap`, `source`, `source_url`, `imported_at`. Unique constraint on `(symbol, trade_date)` already exists. **No migration needed** — only a pipeline to populate it. |
| Company + market announcements | `Announcement` (`backend/app/models/announcement.py`) | **Already has**: `symbol` (nullable — market-wide when null), `market`, `title_ar`, `title_en`, `announced_at` (datetime, covers date+time), `announcement_type` (category), `source_url`, `attachment_url`, `xbrl_url`, `has_xbrl`. **Missing one column**: a `source_id` (Saudi Exchange's own announcement ID) for idempotent upserts — without it, re-running the pipeline risks duplicate rows since there's no natural dedup key other than `(symbol, announced_at, title_ar)`, which is fragile. **One small migration recommended**: add `source_id: String | None, unique=True nullable=True` (or a composite unique constraint) before C/D are implemented. |

### New table required

| Target | New model | Reason |
|---|---|---|
| Index daily prices | `IndexPrice` (new) | `MarketIndex` is a catalogue table (code/name/type) with no price history columns. Proposed schema: `id`, `index_code` (FK to `market_indices.code` or plain string), `trade_date`, `open`, `high` (nullable), `low` (nullable), `close`, `previous_close`, `change_amount`, `change_pct`, `volume`, `turnover`, `trades_count`, `source`, `source_url`, `imported_at`, `created_at`. `UniqueConstraint(index_code, trade_date)`. |

---

## Proposed Celery tasks (not implemented yet)

Following the existing pattern in `backend/app/workers/` (`tasks_companies.py`, `tasks_sectors.py`, `tasks_xbrl.py`):

| Task module | Purpose | Trigger |
|---|---|---|
| `tasks_prices.py::fetch_daily_prices` | Pull `TickerServlet` snapshot, upsert into `MarketData` (close/change/volume/turnover/trades only until OHLC source is confirmed) | Scheduled, end-of-trading-day (after ~16:00 Riyadh time, Sun–Thu) |
| `tasks_prices.py::fetch_index_prices` | Pull `ThemeTASIUtilityServlet` (TASI/MT30 full OHLCV) + `indicesJson` blob (sector/market indices), upsert into new `IndexPrice` table | Same schedule |
| `tasks_announcements.py::fetch_company_announcements` | Playwright: load company-announcements page per symbol (or in batches), submit search form, capture `getNewsListData` response, upsert into `Announcement` | Scheduled, e.g. every few hours |
| `tasks_announcements.py::fetch_market_announcements` | Playwright: same page family with no `symbol` filter | Same schedule |

---

## Implementation risks

1. **No confirmed full-OHLCV source for individual companies.** This is the biggest open gap. Before implementing A, Playwright must be used to inspect what the company-profile page's quote widget actually calls (not attempted in this discovery pass — static HTML showed only a generic shell).
2. **`trade_date` is never returned explicitly** by any confirmed endpoint (A or B). The pipeline must derive it from server time at fetch time, respecting the Saudi trading week (Sun–Thu) and public holidays — a naive `date.today()` will silently mislabel data fetched after-hours or on a holiday.
3. **WebSphere Portal session/portlet-ID fragility (C & D).** The resource-serving URL segment (`IZ7_..._getNewsListData=`) is likely tied to the specific page render and may rotate between requests or portal redeployments. A Playwright script built against today's URL could break silently after a portal update — the existing `ci_anncmnt` breakage (404 after a 2026 rebuild) is precedent for this exact failure mode. Build for graceful detection (HTML shell returned instead of JSON → flag as broken, like `_ANNOUNCEMENT_SEARCH_BROKEN`), not silent failure.
4. **`RefreshTradeDetailsServlet`'s `companySymbol` parameter appears unused** — it returned an identical payload regardless of the value passed. Do not build pipeline logic that assumes this parameter does anything until proven otherwise via Playwright/network inspection.
5. **Akamai/session sensitivity.** All endpoints above were reachable via `curl_cffi` Chrome124 impersonation from this environment at the time of testing. This can change — Saudi Exchange's bot detection has already broken one pipeline (`ci_anncmnt`) mid-project. Any new pipeline should fail loudly and honestly (as the existing `connectivity.py`/`endpoint_probe.py` pattern does), never silently fabricate or skip.
6. **`TickerServlet`'s 399-record list may not cover the full ~270 main-market company set plus all NOMU/funds/ETFs/REITs.** Coverage was spot-checked (Aramco, Petro Rabigh, Arabian Drilling, ADES, plus Alkhabeer funds) but not exhaustively cross-referenced against the full company catalogue from `ThemeSearchUtilityServlet` (1,915 records). This must be verified before relying on it as the sole price source.

---

## Recommended Phase 2D.2 implementation plan (pending approval — not started)

1. **Step 1 — Index prices (B), curl_cffi only.** Lowest risk, most complete data. Add `IndexPrice` model + migration. Implement `fetch_index_prices()` reusing the established `curl_cffi` pattern from `sectors.py`. Write offline tests against captured sample payloads.
2. **Step 2 — Company prices (A), partial fields only.** Add a pipeline populating `MarketData` from `TickerServlet` for `close`, `change`, `change_pct`, `volume`, `turnover`, `trades` — explicitly leave `open`/`high`/`low`/`previous_close` NULL with a `missing_fields` note, consistent with the platform's "no fabricated values" principle. Defer full OHLCV until the company-profile widget's data source is confirmed via Playwright.
3. **Step 3 — Playwright investigation spike (A full OHLCV).** Use Playwright to load a company-profile page, inspect Network tab / intercept XHR, and confirm what (if anything) returns full daily OHLCV per company. Report back before writing pipeline code.
4. **Step 4 — Announcements (C & D), Playwright.** Build a single Playwright-based fetcher parameterized by `symbol` (None = market-wide). Add the `source_id` column to `Announcement` first. Start with company announcements for the existing 6 sample symbols, verify the response shape matches `{"announcementList": [...], "totalCount": N}`, then extend to market-wide.
5. **Step 5 — Celery scheduling.** Wire `tasks_prices.py` and `tasks_announcements.py` into `celery_app.py` beat schedule once Steps 1–4 are validated against live data.

Each step should be proposed, approved, and reported on individually — consistent with how Phase 2G was executed.

---

## Hard stop

No pipeline implemented. No DB writes. No migrations applied. No Celery tasks registered. This document is discovery/planning only, pending your review and explicit approval of the implementation plan above.

---

## Review addendum (2026-06-20)

Two corrections found on review, evidenced directly from this document's own captured sample payloads — neither changes the overall conclusions, both are implementation risks worth flagging before any pipeline is built:

1. **`noOfTrades` has an inconsistent JSON type across sources.** `ThemeTASIUtilityServlet` returns it unquoted (`"noOfTrades": 412822`, an integer — see the TASI sample payload above). The `indicesJson` blob returns it quoted (`"noOfTrades":"7943"`, a string — see the sector-index sample payload above). Both field-mapping tables (sections A and B) marked this `✅ available` without noting the type mismatch. **Correction:** any pipeline writing both sources into the same `trades_count`/`trades` column must explicitly coerce to int; do not assume a consistent type across Saudi Exchange's own endpoints.
2. **The "(today, Asia/Riyadh)" trade-date derivation assumption was never actually verified.** The only time-of-day evidence captured in this discovery pass is the bare string `"currentTime": "09:01 PM"` — no date, no UTC offset, no timezone marker of any kind. Asia/Riyadh is a reasonable assumption (the server operator is the Saudi Exchange), but this report stated it as settled fact rather than an unverified inference. **Correction:** before relying on `currentTime` for trade-date logic, the implementation step should cross-check it against a known-correct Riyadh wall-clock reading at fetch time, not trust the field blindly.

No other corrections found. Endpoint evidence, field mappings, null-field behavior, Playwright requirements, proposed schema (re-verified against the current `MarketData`, `Announcement`, and `MarketIndex` models on review — all claims still accurate, no drift), and implementation risks/sequencing all check out as written.
