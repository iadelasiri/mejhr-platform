"""
SaudiExchangeClient — httpx wrapper for all Saudi Exchange requests.

Features:
  - Configurable timeout, retries, proxy, and User-Agent (all via Settings).
  - Structured ClientResponse — never raises; callers inspect .ok / .error.
  - Akamai / geo-block detection via response headers and body keywords.
  - Safe logging: no secrets, no full response bodies, no CAPTCHA bypass.

This client does NOT bypass login, CAPTCHA, paywall, or access controls.
If the server returns 403 or a block page, that is reported honestly.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)

# Headers / body patterns that indicate Akamai or other CDN blocking.
_AKAMAI_HEADER_NAMES = frozenset(
    ["x-check-cacheable", "akamai-cache-status", "x-akamai-transformed",
     "x-akamai-request-id", "akamai-origin-hop"]
)
_AKAMAI_SERVER_TOKENS = ("akamaighost", "akamai")
_BLOCK_BODY_KEYWORDS = ("access denied", "reference #", "you have been blocked",
                        "enable javascript and cookies", "ray id")


@dataclass
class ClientResponse:
    """Structured result from a single HTTP request attempt."""
    ok: bool
    status_code: int | None
    body: bytes | None
    headers: dict[str, str]
    latency_ms: float | None
    error: str | None
    blocked_by_akamai: bool = False
    block_reason: str | None = None

    @property
    def json(self) -> dict | list | None:
        """Attempt to decode body as JSON; return None on failure."""
        if not self.body:
            return None
        try:
            import json
            return json.loads(self.body)
        except Exception:
            return None

    @property
    def is_html(self) -> bool:
        ct = self.headers.get("content-type", "")
        return "text/html" in ct


class SaudiExchangeClient:
    """
    Sync httpx client scoped to SAUDI_EXCHANGE_BASE_URL.

    Usage::

        with SaudiExchangeClient() as client:
            result = client.get("/")
            if result.blocked_by_akamai:
                ...
    """

    def __init__(self) -> None:
        self._client = self._build()

    def _build(self) -> httpx.Client:
        headers: dict[str, str] = {
            "User-Agent": settings.SAUDI_EXCHANGE_USER_AGENT,
            "Accept": (
                "application/json, text/html, application/xhtml+xml, "
                "application/xml;q=0.9, */*;q=0.8"
            ),
            "Accept-Language": "ar-SA,ar;q=0.9,en;q=0.8",
        }
        if settings.SAUDI_EXCHANGE_API_KEY:
            headers["X-API-Key"] = settings.SAUDI_EXCHANGE_API_KEY

        # httpx 0.28+: proxy= accepts a URL string or None.
        # Treat empty string the same as None (no proxy configured).
        proxy = settings.SAUDI_EXCHANGE_PROXY or None

        return httpx.Client(
            base_url=settings.SAUDI_EXCHANGE_BASE_URL,
            headers=headers,
            timeout=settings.SAUDI_EXCHANGE_TIMEOUT,
            proxy=proxy,
            follow_redirects=True,
        )

    def get(self, path: str, **kwargs) -> ClientResponse:
        """
        GET *path* with automatic retry on network errors.

        HTTP 4xx/5xx are NOT retried — they are returned as-is so callers
        can distinguish a block (403) from a server error (500).
        """
        last_error: str | None = None

        for attempt in range(1, settings.SAUDI_EXCHANGE_RETRY_ATTEMPTS + 1):
            try:
                t0 = time.monotonic()
                resp = self._client.get(path, **kwargs)
                latency_ms = round((time.monotonic() - t0) * 1000, 1)

                headers_dict = {k.lower(): v for k, v in resp.headers.items()}
                blocked, reason = self._detect_block(resp, headers_dict)

                log.info(
                    "SE GET %s → %d (%.0f ms) blocked=%s",
                    path, resp.status_code, latency_ms, blocked,
                )

                body = resp.content if len(resp.content) <= 2 * 1024 * 1024 else None

                return ClientResponse(
                    ok=resp.is_success and not blocked,
                    status_code=resp.status_code,
                    body=body,
                    headers=headers_dict,
                    latency_ms=latency_ms,
                    error=None if resp.is_success else f"HTTP {resp.status_code}",
                    blocked_by_akamai=blocked,
                    block_reason=reason,
                )

            except httpx.TimeoutException:
                last_error = f"Timeout after {settings.SAUDI_EXCHANGE_TIMEOUT}s"
                log.warning("SE attempt %d/%d timed out", attempt,
                            settings.SAUDI_EXCHANGE_RETRY_ATTEMPTS)
            except httpx.ConnectError as exc:
                last_error = f"Connection error: {exc}"
                log.warning("SE attempt %d/%d connect error: %s", attempt,
                            settings.SAUDI_EXCHANGE_RETRY_ATTEMPTS, exc)
            except Exception as exc:
                last_error = f"Unexpected error: {exc}"
                log.error("SE attempt %d/%d unexpected: %s", attempt,
                          settings.SAUDI_EXCHANGE_RETRY_ATTEMPTS, exc)

            if attempt < settings.SAUDI_EXCHANGE_RETRY_ATTEMPTS:
                time.sleep(settings.SAUDI_EXCHANGE_RETRY_SLEEP)

        return ClientResponse(
            ok=False,
            status_code=None,
            body=None,
            headers={},
            latency_ms=None,
            error=last_error,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_block(
        response: httpx.Response,
        headers_lower: dict[str, str],
    ) -> tuple[bool, str | None]:
        """Return (blocked, reason) by inspecting headers and body."""

        # Akamai-specific response headers
        for h in _AKAMAI_HEADER_NAMES:
            if h in headers_lower:
                return True, f"Akamai header present: {h}"

        # Server header contains Akamai token
        server = headers_lower.get("server", "")
        for token in _AKAMAI_SERVER_TOKENS:
            if token in server:
                return True, f"Akamai server token in Server header: {server!r}"

        # 403 — always treat as a block
        if response.status_code == 403:
            try:
                body_text = response.content.decode("utf-8", errors="replace").lower()
                for kw in _BLOCK_BODY_KEYWORDS:
                    if kw in body_text:
                        return True, f"Block-page keyword detected: {kw!r}"
            except Exception:
                pass
            return True, "HTTP 403 — geo/bot/IP block (no specific CDN identified)"

        return False, None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SaudiExchangeClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()
