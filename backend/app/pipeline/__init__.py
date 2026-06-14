"""
Mejhr Data Pipeline — Phase 2

This package contains the official data ingestion pipeline.
Modules are stubbed here and will be implemented in Phase 2.

Pipeline order:
  1. exchange/companies.py    — Fetch listed companies from Saudi Exchange
  2. exchange/sectors.py     — Fetch official sectors and industry groups
  3. exchange/prices.py      — Fetch daily market data
  4. exchange/announcements.py — Fetch announcements
  5. xbrl/discovery.py       — Discover XBRL filings from announcements
  6. xbrl/downloader.py      — Download static XBRL files
  7. xbrl/renderer.py        — Playwright rendering for XBRL_DOCS HTML pages
  8. xbrl/parser.py          — Parse XBRL sections (section codes 100010–400100)
  9. normalize/normalizer.py  — Map raw items to standard financial fields
 10. ratios/engine.py        — Calculate all 20 financial ratios
 11. screener builder        — Rebuild screener_snapshot table
 12. quality reporter        — Generate data quality metrics

Data rules (enforced throughout):
  - No yfinance
  - No unofficial sector classification
  - No fabricated values
  - Every value includes source, source_url, imported_at
  - Missing values are stored as NULL
  - Sample data is separated by data_status = 'sample_not_official'
"""
