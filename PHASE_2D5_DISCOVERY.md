# Phase 2D.5 — Company OHLCV Playwright Discovery Spike

**Status:** Closed — blocked by environment. Discovery spike only. No DB writes. No model/migration changes. No production pipeline. No modifications to `company_prices.py`.
**Generated:** 2026-06-20
**Objective:** Discover the real data source behind the Saudi Exchange company-profile price widget (open/high/low/previous_close/close/volume/turnover/trades_count/trade_date) by observing live XHR/fetch network traffic via Playwright.

**The objective was NOT technically completed.** The spike set out to discover and map the company-profile widget's OHLCV data source by capturing live XHR/fetch traffic. It could not do so: every navigation attempt — for every symbol, and even for the bare homepage — received an HTTP `403` from Akamai before the browser ever rendered page content or executed page JavaScript. No XHR/fetch request was ever fired, captured, or observed. **Full OHLCV availability for individual companies on saudiexchange.sa therefore remains unknown** — this spike did not establish that such data exists, nor that it doesn't; it simply could not reach far enough to check. **No conclusion of any kind was reached about the underlying widget API** (its existence, shape, authentication requirements, or field set) — there is nothing to report on that front beyond "unreachable by this method."

This is the same Akamai control documented throughout this project (`[[feedback_saudi_exchange]]`), now confirmed to also apply to Playwright's browser engine, not just plain `httpx`. **No security-control bypass of any kind was attempted** — no stealth plugins, no fingerprint patching, no CDP-flag manipulation, no alternate browser binary — consistent with the hard stop ("do not bypass CAPTCHA or security controls").

**TickerServlet (Phase 2D.4) remains the only confirmed, working source for company prices**, and only for its partial field set (`close`, `change`, `change_pct`, `volume`, `turnover`, `trades_count` — `open`/`high`/`low`/`previous_close`/`trade_date` are structurally null there, per Phase 2D.2/2D.4 findings, unchanged by this spike).

---

## 0. Environment (versions, recorded for reproducibility)

| Component | Version |
|---|---|
| `playwright` (pip package) | 1.49.0 |
| Bundled Chromium (launched by Playwright) | 131.0.6778.33 |
| Python | 3.11.15 |
| Container OS | Debian GNU/Linux 13 (trixie) |
| Browser context `User-Agent` sent | `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36` |
| Viewport | 1366×900 |
| Locale | `en-US` |
| Launch mode | `headless=True` (no `playwright-stealth` or other fingerprint-modification packages installed or used) |

---

## 1. Pages tested

| # | URL | Method |
|---|-----|--------|
| 1 | `https://www.saudiexchange.sa/` (bare homepage) | `page.goto()`, `wait_until="domcontentloaded"` |
| 2 | `https://www.saudiexchange.sa/wps/portal/tadawul/markets/equities/equities-securities/listed-securities` (public page, confirmed reachable via `curl_cffi` in Phase 2D.2) | same |
| 3 | `https://www.saudiexchange.sa/wps/portal/saudiexchange/hidden/company-profile-main/!ut/p/z1/...&companySymbol={SYMBOL}` (the "hidden" company-profile deep link discovered in Phase 2D.2 — confirmed `200` via `curl_cffi` but returning a generic shell with no company-specific OHLCV server-rendered) | same, once per required symbol |

**Symbols tested against page #3:** 2240, 2222, 2020, 4263, 2050, 1120 — all 6 required symbols.

## 2. Captured requests

**None.** Zero XHR/fetch requests were captured for any symbol or page. The browser never received page content to execute JavaScript against — every navigation was rejected at the HTTP response level before `domcontentloaded` fired with real content (the "content" received was Akamai's own block page, not the site).

| Symbol | HTTP status | Akamai header present | XHR/fetch events captured |
|---|---|---|---|
| 2240 | 403 | yes | 0 |
| 2222 | 403 | yes | 0 |
| 2020 | 403 | yes | 0 |
| 4263 | 403 | yes | 0 |
| 2050 | 403 | yes | 0 |
| 1120 | 403 | yes | 0 |

Homepage and the public listed-securities page (tested without a symbol, as a control) also returned `403` with the identical Akamai signature — confirming this is a sitewide block on the browser's fingerprint, not specific to the company-profile deep link or to any symbol.

## 3. Session requirements

**Undetermined — never reached the point where session/cookie requirements could be observed.** No cookies were set by the server (the 403 response carries no `Set-Cookie`), so there is no session bootstrap to describe. This spike cannot answer "what cookies/session state does the widget need" because the widget's page was never served.

## 4. Relevant headers / block signature

Captured from the `listed-securities` control test (representative of all 403s observed):

```
HTTP/1.1 403
content-type: text/html
akamai-cache-status: Error from child
```

Response body (475 bytes, generic Akamai error page — not sensitive, included here for evidence, not as a discovery fixture since it carries no Saudi Exchange business data):

```html
<HTML><HEAD>
<TITLE>Access Denied</TITLE>
</HEAD><BODY>
<H1>Access Denied</H1>
You don't have permission to access "http://www.saudiexchange.sa/wps/portal/tadawul/markets/equities/equities-securities/listed-securities" on this server.<P>
Reference #18.d89d7d4.1781909935.e8ba0e0
<P>https://errors.edgesuite.net/18.d89d7d4.1781909935.e8ba0e0</P>
</BODY>
</HTML>
```

This is the identical block signature already documented in `feedback_saudi_exchange` memory and in `PHASE_2D2_DISCOVERY.md` for plain `httpx` — now confirmed to also apply to Playwright's bundled Chromium, despite a realistic Chrome 124 `User-Agent`, standard `en-US` locale, and a normal `1366x900` viewport.

**One diagnostic data point (informational, not used to attempt evasion):** `navigator.webdriver` evaluated to `True` inside the one page that did return enough content to run `page.evaluate()` against (the listed-securities 403 page's own minimal DOM). Whether Akamai's block decision is driven by this flag specifically, by TLS/JA3 fingerprint differences between Playwright's bundled Chromium and a genuine Chrome installation, or by some other automation signal could not be isolated further without deliberately patching browser fingerprinting — which would constitute bypassing the bot-detection control and was not attempted, per the hard stop.

## 5. Sample payload and exact field mapping

**Not available.** No company-profile page content was ever served, so no quote widget, no XHR/fetch call, and no payload of any kind was observed. There is nothing to map.

## 6. Availability of full OHLCV

**Undetermined by this method.** This spike cannot confirm or deny whether the company-profile widget exposes full OHLCV (open/high/low/previous_close) — the blocker occurred before the page (and therefore the widget) could load at all. This is different from the Phase 2D.2 finding for `TickerServlet` (which positively confirmed `open`/`high`/`low`/`previousClosePrice` are structurally null) — this spike simply could not reach the relevant page to make any determination either way.

## 7. Historical coverage

**Undetermined**, for the same reason as §6.

## 8. curl_cffi replay result

Not applicable in the originally-planned direction (there is no discovered request to replay, since none was discovered). The useful comparison is the reverse: the exact same URLs were already confirmed reachable via `curl_cffi` with Chrome124 TLS impersonation in Phase 2D.2 (`200` status, full HTML body, e.g. 1,084,620 bytes for the hidden company-profile shell). Playwright, using a real browser engine with a matching User-Agent string, was blocked (`403`) on those same URLs. This indicates Akamai's bot-detection signal here is **not** simply User-Agent string matching — `curl_cffi`'s TLS-fingerprint impersonation passes where Playwright's actual (but automation-flagged) browser engine does not.

Practical implication: `curl_cffi` remains the only confirmed-working access method for this site within this project's toolset. Playwright — despite being a real browser, which is normally a *stronger* signal of legitimacy than a TLS-impersonation library — is paradoxically the one that gets blocked here.

## 9. Discrepancies versus TickerServlet

Not applicable — no data was retrieved from the company-profile widget to compare against `TickerServlet`. `TickerServlet`'s own findings (close/change/change_pct/volume/turnover/trades available; open/high/low/previous_close/transactionDate always null) stand unchanged from Phase 2D.2/2D.4 and were not re-tested here (out of scope for this spike, and re-confirming them was not necessary since Phase 2D.4's live validation already did so independently).

## 10. Risks / blockers

1. **Primary blocker (this spike): Akamai blocks Playwright's browser engine at the network layer, before page load.** This is not a CAPTCHA or a JS-challenge that could be "solved" — it's an immediate `403` with no challenge page offered, consistent with a fingerprint-based (TLS/JA3 or CDP-detection) rejection rather than an interactive bot challenge. Per the hard stop, no attempt was made to alter the browser's fingerprint (e.g., `playwright-stealth`, patching `navigator.webdriver`, custom CDP flags, or installing/using a real non-bundled Chrome binary instead of Playwright's Chromium build) to get past this, since doing so would constitute deliberately bypassing a bot-detection security control.
2. **This blocks the stated objective entirely.** The company-profile widget's real OHLCV data source (if one exists) remains unknown. Phase 2D.4's partial pipeline (close/change/volume/turnover/trades only, via `TickerServlet`) remains the only confirmed, working, official data path for company prices.
3. **No alternative non-evasive method was identified** within this spike's scope. Possible future directions that would NOT constitute evasion (not attempted here, would need separate approval): (a) requesting official API access from Saudi Exchange directly, (b) deploying from a Saudi/GCC IP range (the existing `connectivity.py` already notes this as a possible mitigation for the `httpx` case — untested for Playwright specifically, and outside this spike's environment), (c) checking whether Saudi Exchange or Tadawul Group publishes an official downloadable historical-data file/bulletin through a different, non-bot-gated channel (the "Historical Reports" page was noted as unexplored in `PHASE_2D2_DISCOVERY.md` and remains unexplored).
4. **No discovery fixtures were saved** beyond the block-page evidence quoted in §4 — there was no company-specific or session-specific data to sanitize and store, since none was ever retrieved.

## 11. Files changed

None in the repository. All diagnostic scripts were written to and executed from `/tmp` inside the backend container (ephemeral, not part of the codebase) and have not been committed. This report (`PHASE_2D5_DISCOVERY.md`) is the only new file, and it is not yet committed or pushed per the hard stop.

---

## Hard stop confirmation

No database writes. No model or migration changes. No production pipeline code. No modifications to `company_prices.py`. No announcements work. No Celery scheduling. No UI, ratios, screener, or valuation. No CAPTCHA or security-control bypass was attempted — the spike stopped at the first legitimate blocker and reported it honestly rather than fabricating a workaround. Not committed or pushed.
