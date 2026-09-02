from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.utils import timezone

from catalog.models import Product
from core.constants import NotificationChannel, NotificationEvent, Role, UserStatus
from dealers.models import Dealer
from notifications.models import Notification, NotificationLog, NotificationTemplate
from orders import services as order_services
from payments.models import ExchangeRate, Payment

User = get_user_model()


class NotificationDeliveryTests(TestCase):
    def setUp(self):
        self.dealer = Dealer.objects.create(name="Bayi")
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
            rate_date=timezone.localdate(), usd_try_rate=Decimal("34.0000")
        )
        mail.outbox.clear()

    def _run(self, function, *args, **kwargs):
        """Run a service call and fire its on_commit notification hooks.

        The dispatch is deliberately tied to ``transaction.on_commit`` so a
        rolled back workflow never sends anything; tests have to execute the
        captured callbacks themselves.
        """
        with self.captureOnCommitCallbacks(execute=True):
            return function(*args, **kwargs)

    def _submitted_order(self):
        order = order_services.get_or_create_draft(self.dealer_user)
        order_services.add_item(order, self.product, 1)
        self._run(order_services.submit_order, order, self.dealer_user)
        return order

    def test_submission_notifies_finance(self):
        order = self._submitted_order()
        notification = Notification.objects.get(user=self.finance)
        self.assertEqual(notification.event_type, NotificationEvent.ORDER_SUBMITTED)
        self.assertEqual(notification.order, order)
        self.assertEqual(len(mail.outbox), 1)

    def test_in_app_notification_is_created_even_with_email_disabled(self):
        self.finance.email_notifications_enabled = False
        self.finance.save()
        self._submitted_order()
        self.assertTrue(Notification.objects.filter(user=self.finance).exists())
        self.assertEqual(len(mail.outbox), 0)
        log = NotificationLog.objects.get(
            recipient=self.finance, channel=NotificationChannel.EMAIL
        )
        self.assertEqual(log.status, NotificationLog.Status.SKIPPED)

    def test_approval_notifies_the_dealer_and_logistics(self):
        order = self._submitted_order()
        payment = Payment.objects.create(
            order=order, amount_try=Decimal("4080.00"), reference_no="R",
            payment_date=timezone.localdate(), declared_by=self.dealer_user,
        )
        self._run(order_services.approve_payment, order, payment, self.finance)
        for user in (self.dealer_user, self.logistics):
            self.assertTrue(
                Notification.objects.filter(
                    user=user, event_type=NotificationEvent.PAYMENT_APPROVED
                ).exists()
            )

    def test_rejection_notification_carries_the_reason(self):
        order = self._submitted_order()
        self._run(order_services.reject_payment, order, self.finance, "Dekont okunmuyor")
        notification = Notification.objects.get(
            user=self.dealer_user, event_type=NotificationEvent.PAYMENT_REJECTED
        )
        self.assertIn("Dekont okunmuyor", notification.body)

    def test_shipping_notifies_the_dealer(self):
        order = self._submitted_order()
        payment = Payment.objects.create(
            order=order, amount_try=Decimal("4080.00"), reference_no="R",
            payment_date=timezone.localdate(), declared_by=self.dealer_user,
        )
        self._run(order_services.approve_payment, order, payment, self.finance)
        self._run(order_services.mark_shipped, order, self.logistics)
        self.assertTrue(
            Notification.objects.filter(
                user=self.dealer_user, event_type=NotificationEvent.ORDER_SHIPPED
            ).exists()
        )

    def test_copy_is_rendered_in_the_recipient_language(self):
        NotificationTemplate.objects.create(
            event_type=NotificationEvent.ORDER_SUBMITTED, language="en",
            subject="New order: {{ order }}",
            email_body_template="Order {{ order }} from {{ dealer }}.",
            inapp_body_template="{{ dealer }} · awaiting approval",
        )
        NotificationTemplate.objects.create(
            event_type=NotificationEvent.ORDER_SUBMITTED, language="tr",
            subject="Yeni sipariş: {{ order }}",
            email_body_template="{{ dealer }} bayisinden {{ order }} siparişi.",
            inapp_body_template="{{ dealer }} · onay bekliyor",
        )
        self.finance.language = "en"
        self.finance.save()
        english_reader = User.objects.create_user(
            email="finans2@test.com", password="x", role=Role.FINANCE,
            status=UserStatus.APPROVED, language="tr",
        )
        self._submitted_order()
        self.assertIn(
            "New order", Notification.objects.get(user=self.finance).title
        )
        self.assertIn(
            "Yeni sipariş", Notification.objects.get(user=english_reader).title
        )

    def test_bell_panel_actions(self):
        self._submitted_order()
        self.client.force_login(self.finance)
        notification = Notification.objects.get(user=self.finance)
        feed = self.client.get("/notifications/feed/").json()
        self.assertEqual(feed["unread"], 1)
        self.client.post(f"/notifications/{notification.pk}/read/")
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
        self.client.post("/notifications/delete/", {"scope": "read"})
        self.assertFalse(Notification.objects.filter(user=self.finance).exists())

    def test_a_user_cannot_touch_another_users_notification(self):
        self._submitted_order()
        notification = Notification.objects.get(user=self.finance)
        self.client.force_login(self.dealer_user)
        response = self.client.post(f"/notifications/{notification.pk}/delete/")
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Notification.objects.filter(pk=notification.pk).exists())

    def test_a_rolled_back_workflow_sends_nothing(self):
        """Dispatch happens on commit, so a failed transaction is silent."""
        from django.db import transaction

        order = order_services.get_or_create_draft(self.dealer_user)
        order_services.add_item(order, self.product, 1)
        try:
            with transaction.atomic():
                order_services.submit_order(order, self.dealer_user)
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        self.assertFalse(Notification.objects.filter(user=self.finance).exists())
        self.assertEqual(len(mail.outbox), 0)
