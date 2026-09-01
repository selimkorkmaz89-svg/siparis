import datetime as dt
from decimal import Decimal

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
