"""
Environment validation — production readiness check.

Checks all infrastructure dependencies before going live:
  1. Database connection
  2. Redis connection
  3. Storage directory write access
  4. Saudi Exchange connectivity + Akamai block status
  5. Companies endpoint configured (or still default / unverified)
  6. ENABLE_SAMPLE_DATA disabled (required in production)

CLI usage::

    docker compose exec backend python -m app.pipeline.exchange.validate_environment

Exit codes:
  0 — all checks passed (or only warnings, no errors)
  1 — one or more critical checks failed
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.config import settings
from app.pipeline.exchange.connectivity import test_connectivity

log = logging.getLogger(__name__)

# The factory-default path — if SAUDI_EXCHANGE_COMPANIES_PATH is still this,
# the endpoint has not yet been verified on a GCC server.
_DEFAULT_COMPANIES_PATH = (
    "/wps/portal/saudiexchange/newsandreports/market-data/"
    "trading-data/all-shares"
)


@dataclass
class CheckResult:
    name: str
    passed: bool
    is_warning: bool   # True = advisory; False = critical failure
    detail: str


@dataclass
class ValidationReport:
    checks: list[CheckResult] = field(default_factory=list)
    checked_at: str = ""

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def has_critical_failure(self) -> bool:
        return any(not c.passed and not c.is_warning for c in self.checks)

    @property
    def warnings(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed and c.is_warning]

    @property
    def failures(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed and not c.is_warning]


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

async def _check_database() -> CheckResult:
    from app.core.database import check_db_health
    try:
        ok = await check_db_health()
        if ok:
            return CheckResult("database", True, False, "Connected and responsive.")
        return CheckResult("database", False, False,
                           "Database health check returned False. "
                           "Check DATABASE_URL and that PostgreSQL is running.")
    except Exception as exc:
        return CheckResult("database", False, False,
                           f"Database connection failed: {exc}. "
                           "Check DATABASE_URL and PostgreSQL service.")


async def _check_redis() -> CheckResult:
    try:
        import redis as redis_lib
        r = redis_lib.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=5)
        r.ping()
        r.close()
        return CheckResult("redis", True, False, "Connected and responsive.")
    except Exception as exc:
        return CheckResult("redis", False, False,
                           f"Redis connection failed: {exc}. "
                           "Check REDIS_URL and that Redis is running.")


def _check_storage() -> CheckResult:
    path = settings.STORAGE_PATH
    try:
        os.makedirs(path, exist_ok=True)
        test_file = os.path.join(path, ".write_test")
        with open(test_file, "w") as f:
            f.write("ok")
        os.remove(test_file)
        return CheckResult("storage", True, False,
                           f"Storage path {path!r} is writable.")
    except Exception as exc:
        return CheckResult("storage", False, False,
                           f"Storage path {path!r} is not writable: {exc}. "
                           "Check STORAGE_PATH and directory permissions.")


def _check_saudi_exchange() -> tuple[CheckResult, CheckResult]:
    """Returns two checks: connectivity and block status."""
    try:
        result = test_connectivity()

        if not result.dns_ok:
            connectivity = CheckResult(
                "saudi_exchange_dns", False, False,
                f"DNS resolution failed for Saudi Exchange. {result.recommendation}",
            )
            block = CheckResult(
                "saudi_exchange_block", False, True,
                "Cannot determine block status — DNS failed.",
            )
            return connectivity, block

        connectivity = CheckResult(
            "saudi_exchange_reachable",
            result.reachable,
            True,   # not reachable locally is expected; not critical
            (
                f"Reachable: {result.reachable}. "
                f"Status: {result.status_code}. "
                f"Latency: {result.latency_ms} ms. "
                f"{result.recommendation}"
            ),
        )
        block = CheckResult(
            "saudi_exchange_akamai_block",
            not result.blocked_by_akamai,
            True,   # blocked locally is expected; not critical until we go live
            (
                f"Blocked by Akamai: {result.blocked_by_akamai}. "
                + (f"Reason: {result.block_reason}. " if result.block_reason else "")
                + result.recommendation
            ),
        )
        return connectivity, block

    except Exception as exc:
        return (
            CheckResult("saudi_exchange_reachable", False, True,
                        f"Connectivity check raised an error: {exc}."),
            CheckResult("saudi_exchange_akamai_block", False, True,
                        "Cannot determine block status — connectivity check failed."),
        )


def _check_companies_path() -> CheckResult:
    path = settings.SAUDI_EXCHANGE_COMPANIES_PATH
    is_default = (path == _DEFAULT_COMPANIES_PATH)
    if is_default:
        return CheckResult(
            "companies_endpoint",
            False,
            True,  # warning: endpoint not yet confirmed
            (
                "SAUDI_EXCHANGE_COMPANIES_PATH is still the unverified default. "
                "On a GCC server, run: "
                "python -m app.pipeline.exchange.endpoint_probe "
                "then set SAUDI_EXCHANGE_COMPANIES_PATH to the confirmed path."
            ),
        )
    return CheckResult(
        "companies_endpoint",
        True,
        False,
        f"SAUDI_EXCHANGE_COMPANIES_PATH is set to a non-default path: {path!r}. "
        "Run endpoint_probe to confirm it returns company data.",
    )


def _check_sample_data() -> CheckResult:
    if settings.ENABLE_SAMPLE_DATA:
        return CheckResult(
            "sample_data_disabled",
            False,
            settings.APP_ENV != "production",  # critical only in production
            (
                "ENABLE_SAMPLE_DATA=true. "
                + (
                    "CRITICAL: Must be false in production. "
                    if settings.APP_ENV == "production"
                    else "Acceptable in development, but must be false before going live. "
                )
                + "Set ENABLE_SAMPLE_DATA=false in .env."
            ),
        )
    return CheckResult(
        "sample_data_disabled",
        True,
        False,
        "ENABLE_SAMPLE_DATA=false. Official imports will not be contaminated.",
    )


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

async def _run_all() -> ValidationReport:
    report = ValidationReport(
        checked_at=datetime.now(timezone.utc).isoformat()
    )

    # DB and Redis can be checked in parallel
    db_task = asyncio.create_task(_check_database())
    redis_task = asyncio.create_task(_check_redis())

    # Sync checks (run in threads so they don't block the event loop)
    storage_task = asyncio.to_thread(_check_storage)
    se_task = asyncio.to_thread(_check_saudi_exchange)
    path_check = _check_companies_path()
    sample_check = _check_sample_data()

    db_result = await db_task
    redis_result = await redis_task
    storage_result = await storage_task
    se_conn, se_block = await se_task

    report.checks = [
        db_result,
        redis_result,
        storage_result,
        se_conn,
        se_block,
        path_check,
        sample_check,
    ]
    return report


def validate_environment() -> ValidationReport:
    return asyncio.run(_run_all())


def print_report(report: ValidationReport) -> None:
    W = 70
    print("=" * W)
    print("  Mejhr — Environment Validation Report")
    print("=" * W)
    print(f"  Environment : {settings.APP_ENV}")
    print(f"  Checked at  : {report.checked_at}")
    print()

    for check in report.checks:
        icon = "OK " if check.passed else ("WRN" if check.is_warning else "ERR")
        print(f"  [{icon}] {check.name}")
        # Wrap detail
        words = check.detail.split()
        line = "        "
        for word in words:
            if len(line) + len(word) + 1 > W - 2:
                print(line)
                line = "        " + word + " "
            else:
                line += word + " "
        if line.strip():
            print(line)
        print()

    print("-" * W)
    failures = report.failures
    warnings = report.warnings

    if not failures and not warnings:
        print("  ALL CHECKS PASSED. Environment is ready.")
    elif not failures:
        print(f"  PASSED with {len(warnings)} warning(s). Review warnings above.")
    else:
        print(f"  FAILED: {len(failures)} critical issue(s). Fix before going live.")
        for f in failures:
            print(f"    - {f.name}")

    print("=" * W)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    report = validate_environment()
    print_report(report)
    sys.exit(0 if not report.has_critical_failure else 1)
