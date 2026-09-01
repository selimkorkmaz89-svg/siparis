import datetime as dt
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Product
from core.constants import PaymentStatus, Role, UserStatus
from dealers.models import Dealer
from orders import services as order_services
from payments.models import ExchangeRate, Payment
from reports import services

User = get_user_model()


class ReportingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dealer_a = Dealer.objects.create(name="Bayi A")
        cls.dealer_b = Dealer.objects.create(name="Bayi B")
        cls.user_a = User.objects.create_user(
            email="a@test.com", password="x", role=Role.DEALER,
            dealer=cls.dealer_a, status=UserStatus.APPROVED,
        )
        cls.user_b = User.objects.create_user(
            email="b@test.com", password="x", role=Role.DEALER,
            dealer=cls.dealer_b, status=UserStatus.APPROVED,
        )
        cls.finance = User.objects.create_user(
            email="f@test.com", password="x", role=Role.FINANCE,
            status=UserStatus.APPROVED,
        )
        cls.kit = Product.objects.create(
            code="PRD-1", name="Kit", brand="Acme",
            base_price_usd=Decimal("100.00"), vat_rate=Decimal("20.00"),
        )
        cls.strip = Product.objects.create(
            code="PRD-2", name="Strip", brand="Nordis",
            base_price_usd=Decimal("50.00"), vat_rate=Decimal("10.00"),
        )
        # Both days carry the same rate so the report is deterministic
        # whether the suite runs before or after the 15:30 TCMB publication.
        for offset in (0, 1):
            ExchangeRate.objects.create(
                rate_date=timezone.localdate() - dt.timedelta(days=offset),
                usd_try_rate=Decimal("40.0000"),
            )
        # Dealer A: 2 kits (240 USD with VAT). Dealer B: 4 strips (220 USD).
        cls.order_a = cls._order(cls.user_a, [(cls.kit, 2)])
        cls.order_b = cls._order(cls.user_b, [(cls.strip, 4)])
        # A draft must never appear in turnover.
        draft = order_services.get_or_create_draft(cls.user_a)
        order_services.add_item(draft, cls.kit, 99)

    @classmethod
    def _order(cls, user, lines):
        order = order_services.get_or_create_draft(user)
        for product, quantity in lines:
            order_services.add_item(order, product, quantity)
        order_services.submit_order(order, user)
        return order

    def test_drafts_are_excluded_from_turnover(self):
        totals = services.totals(services.base_orders(None, None))
        self.assertEqual(totals["count"], 2)
        self.assertEqual(totals["total"], Decimal("460.00"))

    def test_dealer_breakdown(self):
        rows = services.dealer_breakdown(services.base_orders(None, None))
        by_name = {row["dealer__name"]: row for row in rows}
        self.assertEqual(by_name["Bayi A"]["total"], Decimal("240.00"))
        self.assertEqual(by_name["Bayi B"]["total"], Decimal("220.00"))

    def test_product_and_brand_breakdowns_include_vat(self):
        orders = services.base_orders(None, None)
        products = {row["product_code"]: row for row in services.product_breakdown(orders)}
        self.assertEqual(products["PRD-1"]["quantity"], 2)
        self.assertEqual(products["PRD-1"]["total"], Decimal("240.00"))
        brands = {row["brand"]: row for row in services.brand_breakdown(orders)}
        self.assertEqual(brands["Nordis"]["total"], Decimal("220.00"))

    def test_date_filter_narrows_the_period(self):
        tomorrow = timezone.localdate() + dt.timedelta(days=1)
        self.assertEqual(
            services.totals(services.base_orders(tomorrow, None))["count"], 0
        )

    def test_dealer_scope(self):
        rows = services.dealer_breakdown(services.base_orders(None, None, self.dealer_a))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["dealer__name"], "Bayi A")

    def test_finance_summary_counts_collections_and_rejections(self):
        Payment.objects.create(
            order=self.order_a, amount_try=Decimal("9600.00"),
            amount_usd=Decimal("240.00"), exchange_rate=Decimal("40.0000"),
            reference_no="R1", payment_date=timezone.localdate(),
            declared_by=self.user_a, status=PaymentStatus.APPROVED,
        )
        Payment.objects.create(
            order=self.order_b, amount_try=Decimal("100.00"),
            reference_no="R2", payment_date=timezone.localdate(),
            declared_by=self.user_b, status=PaymentStatus.REJECTED,
        )
        summary = services.finance_summary(None, None)
        self.assertEqual(summary["collected"]["total_usd"], Decimal("240.00"))
        self.assertEqual(summary["collected"]["count"], 1)
        self.assertEqual(summary["rejection_rate"], 50.0)
        # Both orders are still awaiting approval, so both are outstanding.
        self.assertEqual(summary["outstanding"]["count"], 2)

    def test_currency_toggle_uses_the_live_rate(self):
        self.client.force_login(self.finance)
        usd = self.client.get(reverse("reports:dashboard"))
        self.assertEqual(usd.context["summary"]["total"], Decimal("460.00"))
        try_ = self.client.get(reverse("reports:dashboard") + "?currency=TRY")
        self.assertEqual(try_.context["summary"]["total"], Decimal("18400.00"))

    def test_dealer_only_sees_its_own_numbers(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse("reports:mine"))
        self.assertEqual(response.context["summary"]["total"], Decimal("240.00"))
        self.assertFalse(response.context["can_choose_dealer"])

    def test_dealer_cannot_widen_the_scope_with_a_query_parameter(self):
        self.client.force_login(self.user_a)
        response = self.client.get(
            reverse("reports:dashboard") + f"?dealer={self.dealer_b.pk}"
        )
        self.assertEqual(response.context["dealer"], self.dealer_a)
        self.assertEqual(response.context["summary"]["total"], Decimal("240.00"))

    def test_operations_summary_measures_the_stages(self):
        summary = services.operations_summary(None, None)
        self.assertEqual(summary["sample_size"], 2)
        self.assertIsNone(summary["avg_hours_to_payment"])
