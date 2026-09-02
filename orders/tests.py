import datetime as dt
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone, translation

from catalog.models import DealerSpecialPrice, Product
from core.constants import OrderStatus, PaymentStatus, Role, ShipmentStatus, UserStatus
from dealers.models import Dealer
from orders import services
from orders.models import Order, OrderNumberSequence
from payments.models import ExchangeRate, Payment

User = get_user_model()


class OrderWorkflowTests(TestCase):
    def setUp(self):
        self.dealer = Dealer.objects.create(name="Test Bayi")
        self.dealer_user = User.objects.create_user(
            email="bayi@test.com", password="x", role=Role.DEALER,
            dealer=self.dealer, status=UserStatus.APPROVED,
        )
        self.finance = User.objects.create_user(
            email="finans@test.com", password="x", role=Role.FINANCE,
            status=UserStatus.APPROVED,
        )
        self.logistics = User.objects.create_user(
            email="lojistik@test.com", password="x", role=Role.LOGISTICS,
            status=UserStatus.APPROVED,
        )
        self.product = Product.objects.create(
            code="PRD-1", name="Kit", base_price_usd=Decimal("100.00"),
            vat_rate=Decimal("20.00"),
        )
        ExchangeRate.objects.create(
            rate_date=timezone.localdate() - dt.timedelta(days=1),
            usd_try_rate=Decimal("34.0000"),
        )

    def _draft_with_item(self, quantity=2):
        draft = services.get_or_create_draft(self.dealer_user)
        services.add_item(draft, self.product, quantity)
        draft.refresh_from_db()
        return draft

    def test_totals_and_vat_are_computed(self):
        draft = self._draft_with_item(3)
        self.assertEqual(draft.subtotal_usd, Decimal("300.00"))
        self.assertEqual(draft.vat_total_usd, Decimal("60.00"))
        self.assertEqual(draft.total_amount_usd, Decimal("360.00"))

    def test_dealer_special_price_wins(self):
        DealerSpecialPrice.objects.create(
            dealer=self.dealer, product=self.product, price_usd=Decimal("80.00")
        )
        draft = self._draft_with_item(1)
        self.assertEqual(draft.items.first().unit_price_usd, Decimal("80.00"))

    def test_price_is_frozen_on_the_line(self):
        draft = self._draft_with_item(1)
        self.product.base_price_usd = Decimal("500.00")
        self.product.vat_rate = Decimal("10.00")
        self.product.save()
        draft.refresh_from_db()
        item = draft.items.first()
        self.assertEqual(item.unit_price_usd, Decimal("100.00"))
        self.assertEqual(item.vat_rate, Decimal("20.00"))

    def test_draft_has_no_official_number_until_submitted(self):
        draft = self._draft_with_item()
        self.assertIsNone(draft.order_no)
        self.assertIn("#", str(draft.reference))
        services.submit_order(draft, self.dealer_user)
        draft.refresh_from_db()
        self.assertEqual(draft.status, OrderStatus.PENDING_PAYMENT)
        self.assertTrue(draft.order_no.startswith("BSH-"))

    def test_order_numbers_are_sequential_per_year(self):
        year = timezone.localdate().year
        first = OrderNumberSequence.next_order_no()
        second = OrderNumberSequence.next_order_no()
        self.assertEqual(first, f"BSH-{year}-000001")
        self.assertEqual(second, f"BSH-{year}-000002")

    def test_empty_order_cannot_be_submitted(self):
        draft = services.get_or_create_draft(self.dealer_user)
        with self.assertRaises(services.WorkflowError):
            services.submit_order(draft, self.dealer_user)

    def test_rejection_requires_a_reason_and_returns_to_draft(self):
        order = self._draft_with_item()
        services.submit_order(order, self.dealer_user)
        old_number = order.order_no
        with self.assertRaises(services.WorkflowError):
            services.reject_payment(order, self.finance, "  ")
        services.reject_payment(order, self.finance, "Dekont eksik")
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.DRAFT)
        self.assertIsNone(order.order_no)
        history = order.history.first()
        self.assertEqual(history.note, "Dekont eksik")
        self.assertEqual(history.order_no_at_change, old_number)

    def test_resubmission_issues_a_new_number(self):
        order = self._draft_with_item()
        services.submit_order(order, self.dealer_user)
        first_number = order.order_no
        services.reject_payment(order, self.finance, "Tutar hatalı")
        order.refresh_from_db()
        services.submit_order(order, self.dealer_user)
        order.refresh_from_db()
        self.assertNotEqual(order.order_no, first_number)

    def test_shipping_requires_finance_approval(self):
        order = self._draft_with_item()
        services.submit_order(order, self.dealer_user)
        with self.assertRaises(services.WorkflowError):
            services.mark_shipped(order, self.logistics)

    def test_full_happy_path(self):
        order = self._draft_with_item()
        services.submit_order(order, self.dealer_user)
        payment = Payment.objects.create(
            order=order, amount_try=Decimal("8160.00"), reference_no="REF-1",
            payment_date=timezone.localdate(), declared_by=self.dealer_user,
        )
        services.approve_payment(order, payment, self.finance)
        order.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PAID)
        self.assertEqual(payment.status, PaymentStatus.APPROVED)
        self.assertIsNotNone(payment.exchange_rate)
        services.mark_shipped(order, self.logistics, tracking_no="TRK-1")
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.SHIPPED)
        self.assertEqual(order.shipment_status, ShipmentStatus.SHIPPED)
        self.assertEqual(order.tracking_no, "TRK-1")
        self.assertEqual(order.history.count(), 3)

    def test_only_one_approved_payment_per_order(self):
        from django.db.utils import IntegrityError

        order = self._draft_with_item()
        services.submit_order(order, self.dealer_user)
        Payment.objects.create(
            order=order, amount_try=Decimal("100.00"), reference_no="A",
            payment_date=timezone.localdate(), declared_by=self.dealer_user,
            status=PaymentStatus.APPROVED,
        )
        with self.assertRaises(IntegrityError):
            Payment.objects.create(
                order=order, amount_try=Decimal("100.00"), reference_no="B",
                payment_date=timezone.localdate(), declared_by=self.dealer_user,
                status=PaymentStatus.APPROVED,
            )

    def test_order_scoping_by_role(self):
        other_dealer = Dealer.objects.create(name="Diğer Bayi")
        other_user = User.objects.create_user(
            email="diger@test.com", password="x", role=Role.DEALER,
            dealer=other_dealer, status=UserStatus.APPROVED,
        )
        order = self._draft_with_item()
        services.submit_order(order, self.dealer_user)
        self.assertEqual(Order.objects.visible_to(self.dealer_user).count(), 1)
        self.assertEqual(Order.objects.visible_to(other_user).count(), 0)
        self.assertEqual(Order.objects.visible_to(self.finance).count(), 1)

    def test_reorder_copies_the_basket(self):
        order = self._draft_with_item(4)
        services.submit_order(order, self.dealer_user)
        copy = services.reorder(order, self.dealer_user)
        self.assertEqual(copy.status, OrderStatus.DRAFT)
        self.assertEqual(copy.items.first().quantity, 4)
        self.assertIsNone(copy.order_no)


class OrderScreenTests(TestCase):
    """Order detail and the confirmation step before submitting."""

    def setUp(self):
        self.dealer = Dealer.objects.create(name="Ekran Bayi")
        self.user = User.objects.create_user(
            email="ekran@test.com", password="x", role=Role.DEALER,
            dealer=self.dealer, status=UserStatus.APPROVED,
        )
        self.product = Product.objects.create(
            code="PRD-9", name="Kit", base_price_usd=Decimal("100.00"),
            vat_rate=Decimal("20.00"),
        )
        self.client.force_login(self.user)

    def _draft(self):
        draft = services.get_or_create_draft(self.user)
        services.add_item(draft, self.product, 2)
        return draft

    def test_review_screen_names_the_button_and_arms_a_confirmation(self):
        self._draft()
        body = self.client.get(reverse("orders:review")).content.decode()
        self.assertIn('data-confirm-dialog="confirmOrderDialog"', body)
        self.assertIn('id="confirmOrderDialog"', body)
        with translation.override("tr"):
            body = self.client.get(reverse("orders:review")).content.decode()
        self.assertIn("Onayla &amp; Sipariş Oluştur", body.replace("&", "&amp;"))

    def test_each_stage_carries_its_own_class(self):
        order = self._draft()
        services.submit_order(order, self.user)
        body = self.client.get(reverse("orders:detail", args=[order.pk])).content.decode()
        # The stage the order sits at is current; the one before it is done.
        self.assertIn('class="step draft done"', body.replace("\n", " "))
        self.assertRegex(body, r'class="step pending\s+current')
        # Four differently classed stages, not one repeated colour.
        for stage in ("draft", "pending", "paid", "shipped"):
            self.assertIn(f"step {stage}", body)

    def test_a_cancelled_order_shows_only_the_cancelled_stage(self):
        order = self._draft()
        services.cancel_order(order, self.user, note="vazgeçildi")
        body = self.client.get(reverse("orders:detail", args=[order.pk])).content.decode()
        self.assertIn("step cancelled current", body)
        self.assertNotIn("step pending", body)

    def test_the_dealer_badge_falls_back_to_initials(self):
        order = self._draft()
        services.submit_order(order, self.user)
        body = self.client.get(reverse("orders:detail", args=[order.pk])).content.decode()
        self.assertIn("EB", body)  # "Ekran Bayi"
