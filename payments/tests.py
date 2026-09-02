import datetime as dt
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from payments import services
from payments.models import ExchangeRate

TCMB_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<Tarih_Date Tarih="01.09.2026">
  <Currency CurrencyCode="USD">
    <ForexBuying>34.0000</ForexBuying>
    <ForexSelling>34.1000</ForexSelling>
    <BanknoteSelling>34.2500</BanknoteSelling>
  </Currency>
  <Currency CurrencyCode="EUR">
    <BanknoteSelling>40.0000</BanknoteSelling>
  </Currency>
</Tarih_Date>"""


class ExchangeRateRuleTests(TestCase):
    def test_before_1530_uses_the_previous_day(self):
        moment = timezone.make_aware(dt.datetime(2026, 9, 2, 10, 0))
        self.assertEqual(services.effective_rate_date(moment), dt.date(2026, 9, 1))

    def test_after_1530_uses_the_same_day(self):
        moment = timezone.make_aware(dt.datetime(2026, 9, 2, 16, 0))
        self.assertEqual(services.effective_rate_date(moment), dt.date(2026, 9, 2))

    def test_weekend_falls_back_to_friday(self):
        # 2026-09-04 is a Friday; Saturday afternoon must still use it.
        ExchangeRate.objects.create(
            rate_date=dt.date(2026, 9, 4), usd_try_rate=Decimal("35.0000")
        )
        saturday = timezone.make_aware(dt.datetime(2026, 9, 5, 18, 0))
        rate = services.get_rate(saturday)
        self.assertEqual(rate.rate_date, dt.date(2026, 9, 4))

    def test_holiday_gap_walks_further_back(self):
        ExchangeRate.objects.create(
            rate_date=dt.date(2026, 9, 1), usd_try_rate=Decimal("34.0000")
        )
        moment = timezone.make_aware(dt.datetime(2026, 9, 7, 16, 0))
        self.assertEqual(services.get_rate(moment).rate_date, dt.date(2026, 9, 1))

    def test_conversions(self):
        self.assertEqual(
            services.try_to_usd(Decimal("3400.00"), Decimal("34.00")), Decimal("100.00")
        )
        self.assertEqual(
            services.usd_to_try(Decimal("100.00"), Decimal("34.00")), Decimal("3400.00")
        )

    def test_tcmb_xml_parsing_prefers_the_effective_selling_rate(self):
        self.assertEqual(services._parse_tcmb_xml(TCMB_XML), Decimal("34.2500"))


class FetchRatesCommandTests(TestCase):
    """The command exists so a deployment without Celery can still get a rate."""

    def test_it_reports_the_rate_in_effect(self):
        ExchangeRate.objects.create(
            rate_date=timezone.localdate() - dt.timedelta(days=1),
            usd_try_rate=Decimal("35.0000"),
        )
        out = StringIO()
        with mock.patch("payments.services.fetch_tcmb_rate", return_value=None):
            call_command("fetch_rates", stdout=out)
        self.assertIn("35.0000", out.getvalue())

    def test_it_fails_loudly_when_nothing_can_be_fetched(self):
        with mock.patch("payments.services.fetch_tcmb_rate", return_value=None):
            with self.assertRaises(CommandError):
                call_command("fetch_rates", stdout=StringIO())

    def test_a_single_date_can_be_requested(self):
        target = dt.date(2026, 9, 1)

        def fake_fetch(date=None):
            return ExchangeRate.objects.create(
                rate_date=date, usd_try_rate=Decimal("34.5000")
            )

        out = StringIO()
        with mock.patch("payments.services.fetch_tcmb_rate", side_effect=fake_fetch):
            call_command("fetch_rates", date="2026-09-01", stdout=out)
        self.assertIn("34.5000", out.getvalue())
        self.assertTrue(ExchangeRate.objects.filter(rate_date=target).exists())

    def test_an_invalid_date_is_rejected(self):
        with self.assertRaises(CommandError):
            call_command("fetch_rates", date="not-a-date", stdout=StringIO())
