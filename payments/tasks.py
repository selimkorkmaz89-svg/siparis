from celery import shared_task

from payments import services


@shared_task(name="payments.fetch_daily_exchange_rate")
def fetch_daily_exchange_rate():
    """Runs shortly after 15:30, when TCMB has published the day's rate."""
    rate = services.fetch_tcmb_rate()
    return str(rate.usd_try_rate) if rate else None


@shared_task(name="payments.backfill_exchange_rates")
def backfill_exchange_rates(days: int = 10):
    return services.backfill_rates(days)
