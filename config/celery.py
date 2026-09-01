import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("siparis")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    # TCMB publishes at 15:30; fetch a few minutes later on weekdays.
    "fetch-daily-exchange-rate": {
        "task": "payments.fetch_daily_exchange_rate",
        "schedule": crontab(hour=15, minute=35, day_of_week="mon-fri"),
    },
    # Safety net: fill in anything the daily job missed.
    "backfill-exchange-rates": {
        "task": "payments.backfill_exchange_rates",
        "schedule": crontab(hour=6, minute=0),
    },
}
