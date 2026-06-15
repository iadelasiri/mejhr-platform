"""
XBRL file downloader — Saudi Exchange official filings only.

Downloads XBRL/iXBRL files from Saudi Exchange attachment URLs, computes
a SHA-256 hash of the content, and stores the file under:
  {STORAGE_PATH}/xbrl/{symbol}/{fiscal_year}/{fiscal_period}/{filename}

Hash-based deduplication:
  - If a file with the same SHA-256 already exists in xbrl_files, the
    download is skipped and the result is marked download_status='skipped_duplicate'.
  - If the content is unchanged (same URL, same hash), no new row is created.

Does NOT parse XBRL content.  That is Phase 2F.

Usage::
    docker compose exec backend python -m app.pipeline.exchange.xbrl_downloader \
        https://www.saudiexchange.sa/.../file.xhtml 1010 2024 Q3
"""

from __future__ import annotations

import hashlib
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# Maximum file size we'll accept (50 MB). Real XBRL files are typically <5 MB.
_MAX_FILE_BYTES = 50 * 1024 * 1024


@dataclass
class DownloadResult:
    """Result of one file download attempt."""
    url: str
    # SHA-256 hex digest of downloaded content (None if download failed)
    file_hash: str | None
    file_size_bytes: int | None
    local_path: str | None
    # downloaded | skipped_duplicate | failed
    download_status: str
    error: str | None
    downloaded_at: str


def _http_get_binary(url: str):
    """GET via curl_cffi Chrome124 TLS impersonation. Returns raw response."""
    from curl_cffi import requests as cffi_requests
    return cffi_requests.get(url, impersonate="chrome124", timeout=60, stream=False)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_filename(url: str) -> str:
    """Extract a filesystem-safe filename from a URL."""
    name = url.split("?")[0].rstrip("/").split("/")[-1]
    # Remove any characters unsafe for filenames
    safe = "".join(c for c in name if c.isalnum() or c in (".", "-", "_"))
    return safe or "filing.xhtml"


def _storage_path(
    base: Path,
    symbol: str,
    fiscal_year: int | None,
    fiscal_period: str | None,
    filename: str,
) -> Path:
    year_dir = str(fiscal_year) if fiscal_year else "unknown_year"
    period_dir = (fiscal_period or "unknown_period").upper()
    dest = base / "xbrl" / symbol / year_dir / period_dir / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    return dest


def download_file(
    url: str,
    symbol: str,
    fiscal_year: int | None,
    fiscal_period: str | None,
    storage_base: Path,
    existing_hashes: frozenset[str] | None = None,
) -> DownloadResult:
    """
    Download one XBRL file.

    - existing_hashes: set of SHA-256 hashes already in xbrl_files for this filing.
      If the downloaded content's hash is in existing_hashes, the file is not
      written to disk and download_status='skipped_duplicate' is returned.

    Always returns DownloadResult — never raises.
    """
    now = datetime.now(timezone.utc).isoformat()

    try:
        resp = _http_get_binary(url)
    except Exception as exc:
        return DownloadResult(
            url=url, file_hash=None, file_size_bytes=None,
            local_path=None, download_status="failed",
            error=f"Network error: {exc}",
            downloaded_at=now,
        )

    if resp.status_code == 403:
        return DownloadResult(
            url=url, file_hash=None, file_size_bytes=None,
            local_path=None, download_status="failed",
            error=f"HTTP 403 — Saudi Exchange blocked download",
            downloaded_at=now,
        )

    if resp.status_code != 200:
        return DownloadResult(
            url=url, file_hash=None, file_size_bytes=None,
            local_path=None, download_status="failed",
            error=f"HTTP {resp.status_code}",
            downloaded_at=now,
        )

    content: bytes = resp.content

    if len(content) > _MAX_FILE_BYTES:
        return DownloadResult(
            url=url, file_hash=None, file_size_bytes=len(content),
            local_path=None, download_status="failed",
            error=f"File too large: {len(content):,} bytes (max {_MAX_FILE_BYTES:,})",
            downloaded_at=now,
        )

    if not content:
        return DownloadResult(
            url=url, file_hash=None, file_size_bytes=0,
            local_path=None, download_status="failed",
            error="Empty response body",
            downloaded_at=now,
        )

    digest = _sha256(content)

    # Hash-based dedup: skip if this exact content already downloaded
    if existing_hashes and digest in existing_hashes:
        log.info("Skipping duplicate: %s (hash %s already stored)", url, digest[:12])
        return DownloadResult(
            url=url, file_hash=digest, file_size_bytes=len(content),
            local_path=None, download_status="skipped_duplicate",
            error=None,
            downloaded_at=now,
        )

    filename = _safe_filename(url)
    dest = _storage_path(storage_base, symbol, fiscal_year, fiscal_period, filename)

    try:
        dest.write_bytes(content)
    except Exception as exc:
        return DownloadResult(
            url=url, file_hash=digest, file_size_bytes=len(content),
            local_path=None, download_status="failed",
            error=f"Write error: {exc}",
            downloaded_at=now,
        )

    log.info(
        "Downloaded %s → %s (%d bytes, hash %s)",
        url[:60], dest, len(content), digest[:12],
    )
    return DownloadResult(
        url=url, file_hash=digest, file_size_bytes=len(content),
        local_path=str(dest), download_status="downloaded",
        error=None,
        downloaded_at=now,
    )


if __name__ == "__main__":
    from app.core.config import settings

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if len(sys.argv) < 2:
        print("Usage: xbrl_downloader.py <url> [symbol] [year] [period]")
        sys.exit(1)

    url = sys.argv[1]
    symbol = sys.argv[2] if len(sys.argv) > 2 else "UNKNOWN"
    year = int(sys.argv[3]) if len(sys.argv) > 3 else None
    period = sys.argv[4] if len(sys.argv) > 4 else None
    base = Path(settings.STORAGE_PATH)

    result = download_file(url, symbol, year, period, base)
    print(f"Status      : {result.download_status}")
    print(f"Hash        : {result.file_hash}")
    print(f"Size        : {result.file_size_bytes}")
    print(f"Local path  : {result.local_path}")
    if result.error:
        print(f"Error       : {result.error}")
    sys.exit(0 if result.download_status in ("downloaded", "skipped_duplicate") else 1)
