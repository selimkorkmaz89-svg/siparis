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
  <Currency CurrencyCode="CHF">
    <ForexBuying>42.0000</ForexBuying>
    <ForexSelling>42.1000</ForexSelling>
    <BanknoteSelling>42.7500</BanknoteSelling>
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

    def test_tcmb_xml_parsing_also_reads_chf(self):
        self.assertEqual(services._parse_tcmb_xml(TCMB_XML, "CHF"), Decimal("42.7500"))

    def test_chf_to_usd_rate_is_derived_from_both_try_legs(self):
        rate = ExchangeRate(usd_try_rate=Decimal("34.0000"), chf_try_rate=Decimal("42.5000"))
        self.assertEqual(rate.chf_to_usd_rate, Decimal("1.2500"))

    def test_chf_to_usd_rate_is_none_without_a_chf_leg(self):
        rate = ExchangeRate(usd_try_rate=Decimal("34.0000"))
        self.assertIsNone(rate.chf_to_usd_rate)


class TcmbFetchTests(TestCase):
    """fetch_tcmb_rate stores both legs and reprices CHF-listed products."""

    def test_fetching_stores_both_usd_and_chf(self):
        response = mock.Mock(content=TCMB_XML)
        response.raise_for_status = mock.Mock()
        with mock.patch("payments.services.requests.get", return_value=response):
            rate = services.fetch_tcmb_rate(dt.date(2026, 9, 1))
        self.assertEqual(rate.usd_try_rate, Decimal("34.2500"))
        self.assertEqual(rate.chf_try_rate, Decimal("42.7500"))

    def test_fetching_reprices_chf_listed_products(self):
        from catalog.models import Product

        product = Product.objects.create(
            code="CHF-1", name="Swiss item", price_currency="CHF",
            list_price=Decimal("100.00"), base_price_usd=Decimal("0.00"),
        )
        response = mock.Mock(content=TCMB_XML)
        response.raise_for_status = mock.Mock()
        with mock.patch("payments.services.requests.get", return_value=response):
            services.fetch_tcmb_rate(dt.date(2026, 9, 1))
        product.refresh_from_db()
        # 42.7500 / 34.2500 = 1.2482 (quantized to 4dp), * 100 = 124.82
        self.assertEqual(product.base_price_usd, Decimal("124.82"))

    def test_a_missing_chf_leg_does_not_block_the_usd_rate(self):
        xml_without_chf = b"""<?xml version="1.0" encoding="UTF-8"?>
<Tarih_Date Tarih="01.09.2026">
  <Currency CurrencyCode="USD">
    <BanknoteSelling>34.2500</BanknoteSelling>
  </Currency>
</Tarih_Date>"""
        response = mock.Mock(content=xml_without_chf)
        response.raise_for_status = mock.Mock()
        with mock.patch("payments.services.requests.get", return_value=response):
            rate = services.fetch_tcmb_rate(dt.date(2026, 9, 1))
        self.assertEqual(rate.usd_try_rate, Decimal("34.2500"))
        self.assertIsNone(rate.chf_try_rate)


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


class DemoRateShadowingTests(TestCase):
    """A seeded placeholder must never outrank a real TCMB rate."""

    def test_backfill_replaces_a_demo_row_but_keeps_a_manual_one(self):
        today = timezone.localdate()
        ExchangeRate.objects.create(
            rate_date=today, usd_try_rate=Decimal("34.0000"), source="DEMO"
        )
        ExchangeRate.objects.create(
            rate_date=today - dt.timedelta(days=1),
            usd_try_rate=Decimal("30.0000"), source="MANUAL",
        )
        fetched = []

        def fake_fetch(date=None):
            fetched.append(date)
            return ExchangeRate.objects.update_or_create(
                rate_date=date,
                defaults={"usd_try_rate": Decimal("48.3337"), "source": "TCMB"},
            )[0]

        with mock.patch("payments.services.fetch_tcmb_rate", side_effect=fake_fetch):
            services.backfill_rates(days=2)

        self.assertIn(today, fetched)                       # DEMO was replaced
        self.assertNotIn(today - dt.timedelta(days=1), fetched)  # MANUAL kept
        self.assertEqual(
            ExchangeRate.objects.get(rate_date=today).source, "TCMB"
        )
        self.assertEqual(
            ExchangeRate.objects.get(rate_date=today - dt.timedelta(days=1)).usd_try_rate,
            Decimal("30.0000"),
        )

    def test_force_replaces_a_manual_row_too(self):
        today = timezone.localdate()
        ExchangeRate.objects.create(
            rate_date=today, usd_try_rate=Decimal("30.0000"), source="MANUAL"
        )
        with mock.patch("payments.services.fetch_tcmb_rate") as fetch:
            services.backfill_rates(days=1, force=True)
        fetch.assert_called_once()

    def test_seeding_demo_data_leaves_real_rates_alone(self):
        # Dated on the effective day, so it is the rate in force whatever the
        # clock says relative to the 15:30 publication.
        ExchangeRate.objects.create(
            rate_date=services.effective_rate_date(),
            usd_try_rate=Decimal("48.3337"), source="TCMB",
        )
        call_command("seed_demo", orders=0, force=True, stdout=StringIO())
        self.assertFalse(ExchangeRate.objects.filter(source="DEMO").exists())
        self.assertEqual(services.get_rate().source, "TCMB")
