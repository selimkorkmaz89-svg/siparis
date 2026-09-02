"""Fetch the TCMB USD/TRY rate without needing Celery.

Celery Beat drives this in production, but a local checkout or a VPS without a
worker still needs a way to pull the rate:

    python manage.py fetch_rates            # today plus any missing recent days
    python manage.py fetch_rates --days 30  # wider backfill
    python manage.py fetch_rates --date 2026-09-01
"""
import datetime as dt

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from payments import services
from payments.models import ExchangeRate


class Command(BaseCommand):
    help = "Fetches USD/TRY rates from TCMB and stores them."

    def add_arguments(self, parser):
        parser.add_argument("--date", help="A single date to fetch (YYYY-MM-DD).")
        parser.add_argument(
            "--days", type=int, default=7,
            help="How many days back to fill in when a rate is missing (default 7).",
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Fetch again even for days already stored, replacing manual entries.",
        )

    def handle(self, *args, **options):
        if options["date"]:
            try:
                date = dt.date.fromisoformat(options["date"])
            except ValueError as exc:
                raise CommandError(f"Invalid date: {exc}") from exc
            rate = services.fetch_tcmb_rate(date)
            if rate is None:
                raise CommandError(
                    f"No rate published for {date} (weekend or public holiday?)"
                )
            self.stdout.write(self.style.SUCCESS(f"{rate.rate_date}: {rate.usd_try_rate}"))
            return

        stored = services.backfill_rates(options["days"], force=options["force"])
        effective = services.effective_rate_date()
        current = services.get_rate()
        if current is None:
            raise CommandError(
                "No usable rate is stored. Check that www.tcmb.gov.tr is reachable."
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"{stored} new rate(s) stored. In effect for {effective}: "
                f"{current.rate_date} = {current.usd_try_rate}"
            )
        )
        missing = ExchangeRate.objects.filter(
            rate_date=timezone.localdate()
        ).exists()
        if not missing:
            self.stdout.write(
                "Today has no published rate yet - TCMB publishes at 15:30 on business days."
            )
