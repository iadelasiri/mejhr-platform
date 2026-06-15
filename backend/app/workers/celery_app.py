from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

app = Celery(
    "mejhr",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.tasks_companies",        # Phase 2A — Saudi Exchange companies
        # "app.workers.tasks_prices",         # Phase 2B
        # "app.workers.tasks_announcements",  # Phase 2B
        # "app.workers.tasks_xbrl",           # Phase 2C
        # "app.workers.tasks_normalize",      # Phase 2D
        # "app.workers.tasks_ratios",         # Phase 2D
        # "app.workers.tasks_screener",       # Phase 2D
        # "app.workers.tasks_quality",        # Phase 2D
    ],
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Riyadh",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",  # match worker -Q default,pipeline,xbrl
    task_routes={
        "tasks.pipeline.*": {"queue": "pipeline"},
        "tasks.xbrl.*": {"queue": "xbrl"},
    },
)

# -------------------------------------------------------
# Phase 1: Schedule definitions (no actual tasks yet).
# Phase 2: Uncomment each entry when the task module exists.
# -------------------------------------------------------
app.conf.beat_schedule = {
    # Phase 2A — Saudi Exchange companies (daily, 06:00 Riyadh time)
    "daily-fetch-companies": {
        "task": "tasks.fetch_companies",
        "schedule": crontab(hour=6, minute=0),
    },
    # "daily-fetch-sectors": {
    #     "task": "tasks.fetch_sectors",
    #     "schedule": crontab(hour=6, minute=10),
    # },
    # "daily-fetch-prices": {
    #     "task": "tasks.fetch_prices",
    #     "schedule": crontab(hour=16, minute=30),  # After market close
    # },
    # "daily-fetch-announcements": {
    #     "task": "tasks.fetch_announcements",
    #     "schedule": crontab(hour="*/4", minute=0),
    # },
    # Nightly jobs
    # "nightly-xbrl-discovery": {
    #     "task": "tasks.xbrl_discovery",
    #     "schedule": crontab(hour=0, minute=0),
    # },
    # "nightly-normalize": {
    #     "task": "tasks.normalize",
    #     "schedule": crontab(hour=2, minute=0),
    # },
    # "nightly-calculate-ratios": {
    #     "task": "tasks.calculate_ratios",
    #     "schedule": crontab(hour=3, minute=0),
    # },
    # "nightly-build-screener": {
    #     "task": "tasks.build_screener",
    #     "schedule": crontab(hour=4, minute=0),
    # },
    # "nightly-build-quality-report": {
    #     "task": "tasks.build_quality_report",
    #     "schedule": crontab(hour=4, minute=30),
    # },
}
