from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.utils import timezone

from catalog.models import Product
from core.constants import NotificationChannel, NotificationEvent, Role, UserStatus
from dealers.models import Dealer
from notifications import services as notify
from notifications.models import EmailSettings, Notification, NotificationLog, NotificationTemplate
from orders import services as order_services
from payments import services as fx
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
            rate_date=fx.effective_rate_date(), usd_try_rate=Decimal("34.0000")
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


class NotificationBellMarkupTests(TestCase):
    """The bell renders twice per page, so it must not rely on element ids."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="bell@test.com", password="x", role=Role.ADMIN,
            status=UserStatus.APPROVED,
        )
        self.client.force_login(self.user)

    def test_the_bell_markup_carries_no_duplicated_ids(self):
        body = self.client.get("/").content.decode()
        self.assertEqual(body.count("data-bell-panel"), 2)  # desktop + mobile
        for dead_id in ('id="notificationBell"', 'id="notificationPanel"',
                        'id="notificationBadge"'):
            self.assertNotIn(dead_id, body)

    def test_a_bell_entry_links_to_the_page_it_is_about_not_the_post_view(self):
        Notification.objects.create(
            user=self.user, event_type=NotificationEvent.USER_REGISTERED,
            title="Yeni kullanıcı", body="", url="/accounts/pending/",
        )
        body = self.client.get("/").content.decode()
        self.assertIn('href="/accounts/pending/"', body)
        self.assertNotIn('href="/notifications/1/read/"', body)

    def test_marking_read_is_a_post_and_the_link_target_answers_a_get(self):
        notification = Notification.objects.create(
            user=self.user, event_type=NotificationEvent.USER_REGISTERED,
            title="Yeni kullanıcı", body="", url="/accounts/pending/",
        )
        # A GET on the mark-read view is refused; that is why the anchor must
        # point at the target page instead.
        self.assertEqual(
            self.client.get(f"/notifications/{notification.pk}/read/").status_code, 405
        )
        self.assertEqual(self.client.get(notification.url).status_code, 200)
        self.assertEqual(
            self.client.post(f"/notifications/{notification.pk}/read/").status_code, 302
        )
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)


class EmailSettingsTests(TestCase):
    """The SMTP settings screen: saving, the password round-trip, and the
    per-user email toggle staying independent of the master switch."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="smtp-admin@test.com", password="x", role=Role.ADMIN,
            status=UserStatus.APPROVED,
        )
        self.client.force_login(self.admin)

    def test_saving_settings_creates_the_singleton_row(self):
        response = self.client.post("/payments/exchange-rates/", {
            "save_email_settings": "1", "provider": "SMTP",
            "enabled": "on", "host": "smtp.example.com", "port": "587",
            "username": "no-reply@example.com", "password": "secret123",
            "use_tls": "on", "from_email": "BASH Medikal <no-reply@example.com>",
        })
        self.assertEqual(response.status_code, 302)
        settings_row = EmailSettings.load()
        self.assertTrue(settings_row.enabled)
        self.assertEqual(settings_row.host, "smtp.example.com")
        self.assertEqual(settings_row.password, "secret123")
        self.assertEqual(EmailSettings.objects.count(), 1)

    def test_a_blank_password_on_save_keeps_the_stored_one(self):
        EmailSettings.objects.create(
            pk=EmailSettings.SINGLETON_ID, enabled=True, host="smtp.example.com",
            password="original-secret",
        )
        self.client.post("/payments/exchange-rates/", {
            "save_email_settings": "1", "provider": "SMTP",
            "enabled": "on", "host": "smtp.example.com", "port": "587",
            "username": "", "password": "",
            "use_tls": "on", "from_email": "",
        })
        self.assertEqual(EmailSettings.load().password, "original-secret")

    def test_the_stored_password_is_never_rendered_back_to_the_browser(self):
        EmailSettings.objects.create(
            pk=EmailSettings.SINGLETON_ID, host="smtp.example.com",
            password="super-secret-value",
        )
        body = self.client.get("/payments/exchange-rates/").content.decode()
        self.assertNotIn("super-secret-value", body)

    def test_tls_and_ssl_cannot_both_be_on(self):
        response = self.client.post("/payments/exchange-rates/", {
            "save_email_settings": "1", "provider": "SMTP",
            "enabled": "on", "host": "smtp.example.com", "port": "587",
            "username": "", "password": "x",
            "use_tls": "on", "use_ssl": "on", "from_email": "",
        })
        self.assertEqual(EmailSettings.load().host, "")  # nothing was saved

    def test_enabling_without_a_host_is_refused(self):
        response = self.client.post("/payments/exchange-rates/", {
            "save_email_settings": "1", "provider": "SMTP",
            "enabled": "on", "host": "", "port": "587",
            "username": "", "password": "",
            "use_tls": "on", "from_email": "",
        })
        self.assertFalse(EmailSettings.load().enabled)

    def test_disabled_settings_use_the_project_fallback_connection(self):
        EmailSettings.objects.create(pk=EmailSettings.SINGLETON_ID, enabled=False)
        self.assertIsNone(EmailSettings.load().get_connection())

    def test_enabled_settings_build_an_smtp_connection(self):
        settings_row = EmailSettings.objects.create(
            pk=EmailSettings.SINGLETON_ID, enabled=True, host="smtp.example.com",
            port=587, username="u", password="p", use_tls=True,
        )
        connection = settings_row.get_connection()
        self.assertIsNotNone(connection)
        self.assertEqual(connection.host, "smtp.example.com")

    def test_the_per_user_email_toggle_stays_independent_of_the_master_switch(self):
        # The master switch only changes HOW mail is delivered, never whether
        # a given user wants it - that stays entirely on the user's profile.
        EmailSettings.objects.create(pk=EmailSettings.SINGLETON_ID, enabled=True)
        dealer_user = User.objects.create_user(
            email="off@test.com", password="x", role=Role.DEALER,
            status=UserStatus.APPROVED, email_notifications_enabled=False,
        )
        from unittest import mock

        with mock.patch("notifications.services._send_email") as send_email:
            notify.notify([dealer_user], NotificationEvent.USER_APPROVED, {"user": "x"})
        send_email.assert_called_once()
        # _send_email itself is what checks the per-user flag and skips.

    def test_send_test_email_uses_the_stored_settings(self):
        EmailSettings.objects.create(pk=EmailSettings.SINGLETON_ID, enabled=False)
        notify.send_test_email("someone@example.com")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("someone@example.com", mail.outbox[0].to)

    def test_the_admin_screen_offers_the_test_email_action(self):
        response = self.client.post("/payments/exchange-rates/", {
            "send_test_email": "1", "recipient": "check@example.com",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)

    def test_saving_graph_settings(self):
        response = self.client.post("/payments/exchange-rates/", {
            "save_email_settings": "1", "provider": "MS_GRAPH",
            "enabled": "on", "port": "587",
            "graph_tenant_id": "tenant-1", "graph_client_id": "client-1",
            "graph_client_secret": "secret-1",
            "from_email": "B2B Mail <mailer@example.com>",
        })
        self.assertEqual(response.status_code, 302)
        settings_row = EmailSettings.load()
        self.assertEqual(settings_row.provider, EmailSettings.Provider.MS_GRAPH)
        self.assertEqual(settings_row.graph_tenant_id, "tenant-1")
        self.assertEqual(settings_row.graph_client_secret, "secret-1")

    def test_a_blank_graph_secret_on_save_keeps_the_stored_one(self):
        EmailSettings.objects.create(
            pk=EmailSettings.SINGLETON_ID, enabled=True,
            provider=EmailSettings.Provider.MS_GRAPH,
            graph_tenant_id="t", graph_client_id="c",
            graph_client_secret="original-secret", from_email="a@example.com",
        )
        self.client.post("/payments/exchange-rates/", {
            "save_email_settings": "1", "provider": "MS_GRAPH",
            "enabled": "on", "port": "587",
            "graph_tenant_id": "t", "graph_client_id": "c", "graph_client_secret": "",
            "from_email": "a@example.com",
        })
        self.assertEqual(EmailSettings.load().graph_client_secret, "original-secret")

    def test_the_stored_graph_secret_is_never_rendered_back(self):
        EmailSettings.objects.create(
            pk=EmailSettings.SINGLETON_ID, provider=EmailSettings.Provider.MS_GRAPH,
            graph_client_secret="super-secret-value",
        )
        body = self.client.get("/payments/exchange-rates/").content.decode()
        self.assertNotIn("super-secret-value", body)

    def test_enabling_graph_without_a_client_secret_is_refused(self):
        self.client.post("/payments/exchange-rates/", {
            "save_email_settings": "1", "provider": "MS_GRAPH",
            "enabled": "on", "port": "587",
            "graph_tenant_id": "t", "graph_client_id": "c", "graph_client_secret": "",
            "from_email": "a@example.com",
        })
        self.assertFalse(EmailSettings.load().enabled)

    def test_enabled_graph_settings_build_a_graph_connection(self):
        settings_row = EmailSettings.objects.create(
            pk=EmailSettings.SINGLETON_ID, enabled=True,
            provider=EmailSettings.Provider.MS_GRAPH,
            graph_tenant_id="t", graph_client_id="c", graph_client_secret="s",
            from_email="B2B Mail <mailer@example.com>",
        )
        from notifications.graph_backend import GraphEmailBackend

        connection = settings_row.get_connection()
        self.assertIsInstance(connection, GraphEmailBackend)
        self.assertEqual(connection.sender_email, "mailer@example.com")

    def test_graph_settings_missing_a_piece_build_no_connection(self):
        settings_row = EmailSettings.objects.create(
            pk=EmailSettings.SINGLETON_ID, enabled=True,
            provider=EmailSettings.Provider.MS_GRAPH,
            graph_tenant_id="t", graph_client_id="c", graph_client_secret="",
            from_email="mailer@example.com",
        )
        self.assertIsNone(settings_row.get_connection())


class GraphEmailBackendTests(TestCase):
    """The Microsoft Graph sendMail backend, with the HTTP calls mocked out."""

    def setUp(self):
        from notifications import graph_backend

        graph_backend._token_cache.clear()
        self.graph_backend = graph_backend

    def _backend(self, **overrides):
        kwargs = dict(
            tenant_id="tenant-1", client_id="client-1", client_secret="secret-1",
            sender_email="B2B Mail <mailer@example.com>",
        )
        kwargs.update(overrides)
        return self.graph_backend.GraphEmailBackend(**kwargs)

    def test_the_sender_email_is_extracted_from_a_display_name(self):
        backend = self._backend()
        self.assertEqual(backend.sender_email, "mailer@example.com")

    def test_send_messages_fetches_a_token_then_posts_to_send_mail(self):
        from unittest import mock

        backend = self._backend()
        token_response = mock.Mock(status_code=200)
        token_response.json.return_value = {"access_token": "tok-1", "expires_in": 3600}
        send_response = mock.Mock(status_code=202, text="")

        with mock.patch.object(
            self.graph_backend.requests, "post",
            side_effect=[token_response, send_response],
        ) as mocked_post:
            sent = backend.send_messages([
                mail.EmailMultiAlternatives(
                    subject="Hi", body="Plain body", from_email="mailer@example.com",
                    to=["dest@example.com"],
                )
            ])
        self.assertEqual(sent, 1)
        self.assertEqual(mocked_post.call_count, 2)
        send_call = mocked_post.call_args_list[1]
        self.assertIn(
            "https://graph.microsoft.com/v1.0/users/mailer@example.com/sendMail",
            send_call.args[0],
        )
        payload = send_call.kwargs["json"]["message"]
        self.assertEqual(payload["subject"], "Hi")
        self.assertEqual(payload["body"]["contentType"], "Text")
        self.assertEqual(payload["toRecipients"][0]["emailAddress"]["address"], "dest@example.com")

    def test_an_html_alternative_is_preferred_over_the_plain_body(self):
        from unittest import mock

        backend = self._backend()
        token_response = mock.Mock(status_code=200)
        token_response.json.return_value = {"access_token": "tok-1", "expires_in": 3600}
        send_response = mock.Mock(status_code=202, text="")
        message = mail.EmailMultiAlternatives(
            subject="Hi", body="Plain", from_email="mailer@example.com", to=["dest@example.com"],
        )
        message.attach_alternative("<p>Rich</p>", "text/html")

        with mock.patch.object(
            self.graph_backend.requests, "post",
            side_effect=[token_response, send_response],
        ) as mocked_post:
            backend.send_messages([message])
        payload = mocked_post.call_args_list[1].kwargs["json"]["message"]
        self.assertEqual(payload["body"]["contentType"], "HTML")
        self.assertEqual(payload["body"]["content"], "<p>Rich</p>")

    def test_a_failed_send_mail_call_raises_by_default(self):
        from unittest import mock

        backend = self._backend()
        token_response = mock.Mock(status_code=200)
        token_response.json.return_value = {"access_token": "tok-1", "expires_in": 3600}
        send_response = mock.Mock(status_code=403, text="Forbidden")

        with mock.patch.object(
            self.graph_backend.requests, "post",
            side_effect=[token_response, send_response],
        ):
            with self.assertRaises(self.graph_backend.GraphAPIError):
                backend.send_messages([
                    mail.EmailMultiAlternatives(
                        subject="Hi", body="x", from_email="mailer@example.com",
                        to=["dest@example.com"],
                    )
                ])

    def test_a_failed_send_is_swallowed_when_fail_silently(self):
        from unittest import mock

        backend = self._backend()
        backend.fail_silently = True
        token_response = mock.Mock(status_code=200)
        token_response.json.return_value = {"access_token": "tok-1", "expires_in": 3600}
        send_response = mock.Mock(status_code=500, text="boom")

        with mock.patch.object(
            self.graph_backend.requests, "post",
            side_effect=[token_response, send_response],
        ):
            sent = backend.send_messages([
                mail.EmailMultiAlternatives(
                    subject="Hi", body="x", from_email="mailer@example.com",
                    to=["dest@example.com"],
                )
            ])
        self.assertEqual(sent, 0)

    def test_a_second_send_reuses_the_cached_token(self):
        from unittest import mock

        backend = self._backend()
        token_response = mock.Mock(status_code=200)
        token_response.json.return_value = {"access_token": "tok-1", "expires_in": 3600}
        send_response = mock.Mock(status_code=202, text="")

        with mock.patch.object(
            self.graph_backend.requests, "post",
            side_effect=[token_response, send_response, send_response],
        ) as mocked_post:
            backend.send_messages([
                mail.EmailMultiAlternatives(
                    subject="One", body="x", from_email="mailer@example.com",
                    to=["dest@example.com"],
                )
            ])
            backend.send_messages([
                mail.EmailMultiAlternatives(
                    subject="Two", body="x", from_email="mailer@example.com",
                    to=["dest@example.com"],
                )
            ])
        # One token fetch, two sendMail calls - the token was cached and reused.
        self.assertEqual(mocked_post.call_count, 3)

    def test_missing_credentials_raise_when_not_fail_silently(self):
        backend = self.graph_backend.GraphEmailBackend(
            tenant_id="", client_id="", client_secret="", sender_email="a@example.com",
        )
        with self.assertRaises(Exception):
            backend.send_messages([
                mail.EmailMultiAlternatives(
                    subject="Hi", body="x", from_email="a@example.com", to=["dest@example.com"],
                )
            ])
