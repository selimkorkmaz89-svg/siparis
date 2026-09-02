import datetime as dt
import hashlib
import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Product
from core.constants import MikroSyncStatus, OrderStatus, PaymentStatus, Role, UserStatus
from dealers.models import Dealer
from integrations import services
from integrations.models import MikroSettings, VatRateMapping
from orders import services as order_services
from payments.models import ExchangeRate, Payment

User = get_user_model()


class PasswordHashTests(TestCase):
    def test_the_hash_matches_mikros_documented_formula(self):
        # Confirmed from Mikro's own docs: MD5("YYYY-MM-DD " + password).
        when = dt.date(2025, 3, 9)
        expected = hashlib.md5("2025-03-09 123asd".encode("utf-8")).hexdigest()
        self.assertEqual(services.hash_sifre("123asd", when), expected)

    def test_the_hash_changes_with_the_date(self):
        first = services.hash_sifre("secret", dt.date(2025, 1, 1))
        second = services.hash_sifre("secret", dt.date(2025, 1, 2))
        self.assertNotEqual(first, second)


class MikroIntegrationTestCase(TestCase):
    """Shared setup: a paid order with a dealer, product, rate and mapping."""

    def setUp(self):
        self.dealer = Dealer.objects.create(name="Mikro Bayi", mikro_cari_kodu="CR01")
        self.product = Product.objects.create(
            code="MK-1", name="Test Kit", base_price_usd=Decimal("100.00"),
            vat_rate=Decimal("20.00"), mikro_stok_kodu="STK01",
        )
        self.dealer_user = User.objects.create_user(
            email="bayi@mikro.test", password="x", role=Role.DEALER,
            dealer=self.dealer, status=UserStatus.APPROVED,
        )
        self.finance = User.objects.create_user(
            email="finans@mikro.test", password="x", role=Role.FINANCE,
            status=UserStatus.APPROVED,
        )
        self.admin = User.objects.create_user(
            email="admin@mikro.test", password="x", role=Role.ADMIN,
            status=UserStatus.APPROVED,
        )
        ExchangeRate.objects.create(
            rate_date=timezone.localdate() - dt.timedelta(days=1),
            usd_try_rate=Decimal("34.0000"),
        )
        VatRateMapping.objects.create(vat_rate=Decimal("20.00"), mikro_vergi_pntr=4)
        settings_ = MikroSettings.load()
        settings_.enabled = True
        settings_.api_key = "test-key"
        settings_.firma_kodu = "Api"
        settings_.kullanici_kodu = "SRV"
        settings_.sifre = "123asd"
        settings_.calisma_yili = 2025
        settings_.depo_no = 2
        settings_.evrak_seri = "T"
        settings_.save()

    def _paid_order(self, quantity=2):
        draft = order_services.get_or_create_draft(self.dealer_user)
        order_services.add_item(draft, self.product, quantity)
        order = order_services.submit_order(draft, self.dealer_user)
        payment = Payment.objects.create(
            order=order, amount_try=Decimal("6800.00"), reference_no="REF-1",
            payment_date=timezone.localdate(), declared_by=self.dealer_user,
        )
        return order_services.approve_payment(order, payment, self.finance)


class PayloadBuilderTests(MikroIntegrationTestCase):
    def test_a_paid_order_builds_a_valid_payload(self):
        order = self._paid_order(quantity=2)
        payload = services.build_siparis_payload(order)
        mikro = payload["Mikro"]
        self.assertEqual(mikro["FirmaKodu"], "Api")
        self.assertEqual(mikro["CalismaYili"], 2025)
        satirlar = mikro["evraklar"][0]["satirlar"]
        self.assertEqual(len(satirlar), 1)
        row = satirlar[0]
        self.assertEqual(row["sip_musteri_kod"], "CR01")
        self.assertEqual(row["sip_stok_kod"], "STK01")
        self.assertEqual(row["sip_miktar"], 2)
        self.assertEqual(row["sip_vergi_pntr"], 4)
        self.assertEqual(row["sip_depono"], 2)
        self.assertEqual(row["sip_evrakno_seri"], "T")
        # 100 USD unit price * 34.0000 frozen rate = 3400 TRY (the default currency).
        self.assertEqual(row["sip_b_fiyat"], 3400.0)
        self.assertEqual(row["sip_tutar"], 6800.0)

    def test_the_order_number_is_included_as_a_description_line(self):
        order = self._paid_order()
        payload = services.build_siparis_payload(order)
        aciklamalar = payload["Mikro"]["evraklar"][0]["evrak_aciklamalari"]
        self.assertIn(order.order_no, [a["aciklama"] for a in aciklamalar])

    def test_a_dealer_without_a_mikro_code_is_refused(self):
        self.dealer.mikro_cari_kodu = ""
        self.dealer.save()
        order = self._paid_order()
        with self.assertRaises(services.MikroPayloadError):
            services.build_siparis_payload(order)

    def test_a_product_without_a_mikro_code_is_refused(self):
        self.product.mikro_stok_kodu = ""
        self.product.save()
        order = self._paid_order()
        with self.assertRaises(services.MikroPayloadError):
            services.build_siparis_payload(order)

    def test_a_missing_vat_pointer_mapping_is_refused(self):
        VatRateMapping.objects.all().delete()
        order = self._paid_order()
        with self.assertRaises(services.MikroPayloadError):
            services.build_siparis_payload(order)

    def test_a_disabled_integration_refuses_to_build(self):
        order = self._paid_order()
        settings_ = MikroSettings.load()
        settings_.enabled = False
        settings_.save()
        with self.assertRaises(services.MikroPayloadError):
            services.build_siparis_payload(order)


class SyncQueueTests(MikroIntegrationTestCase):
    def test_approving_a_payment_queues_the_order_when_enabled(self):
        order = self._paid_order()
        self.assertEqual(order.mikro_sync_status, MikroSyncStatus.PENDING)

    def test_approving_a_payment_does_not_queue_when_disabled(self):
        settings_ = MikroSettings.load()
        settings_.enabled = False
        settings_.save()
        order = self._paid_order()
        self.assertEqual(order.mikro_sync_status, MikroSyncStatus.NOT_QUEUED)

    def test_pending_payloads_returns_a_ready_order(self):
        order = self._paid_order()
        results = services.pending_payloads()
        self.assertEqual([r["order_id"] for r in results], [order.pk])

    def test_pending_payloads_auto_fails_an_order_with_a_missing_mapping(self):
        order = self._paid_order()
        self.product.mikro_stok_kodu = ""
        self.product.save()
        results = services.pending_payloads()
        self.assertEqual(results, [])
        order.refresh_from_db()
        self.assertEqual(order.mikro_sync_status, MikroSyncStatus.FAILED)
        self.assertIn("MK-1", order.mikro_sync_error)

    def test_mark_synced_records_the_reference_and_clears_errors(self):
        order = self._paid_order()
        services.mark_failed(order, "boom")
        services.mark_synced(order, reference="EVRAK-123")
        order.refresh_from_db()
        self.assertEqual(order.mikro_sync_status, MikroSyncStatus.SYNCED)
        self.assertEqual(order.mikro_reference, "EVRAK-123")
        self.assertEqual(order.mikro_sync_error, "")
        self.assertIsNotNone(order.mikro_synced_at)

    def test_mark_failed_records_the_error(self):
        order = self._paid_order()
        services.mark_failed(order, "Mikro rejected the request")
        order.refresh_from_db()
        self.assertEqual(order.mikro_sync_status, MikroSyncStatus.FAILED)
        self.assertEqual(order.mikro_sync_error, "Mikro rejected the request")


class ConnectorApiTests(MikroIntegrationTestCase):
    def _token(self):
        return MikroSettings.load().connector_token

    def test_a_missing_token_is_refused(self):
        response = self.client.get(reverse("integrations:mikro_ping"))
        self.assertEqual(response.status_code, 401)

    def test_a_wrong_token_is_refused(self):
        response = self.client.get(
            reverse("integrations:mikro_ping"), HTTP_AUTHORIZATION="Bearer wrong"
        )
        self.assertEqual(response.status_code, 401)

    def test_the_correct_token_pings_successfully(self):
        response = self.client.get(
            reverse("integrations:mikro_ping"),
            HTTP_AUTHORIZATION=f"Bearer {self._token()}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["enabled"])

    def test_pending_orders_lists_a_ready_payload(self):
        order = self._paid_order()
        response = self.client.get(
            reverse("integrations:mikro_pending"),
            HTTP_AUTHORIZATION=f"Bearer {self._token()}",
        )
        self.assertEqual(response.status_code, 200)
        orders = response.json()["orders"]
        self.assertEqual([o["order_id"] for o in orders], [order.pk])

    def test_mark_synced_endpoint_updates_the_order(self):
        order = self._paid_order()
        response = self.client.post(
            reverse("integrations:mikro_mark_synced", args=[order.pk]),
            data=json.dumps({"reference": "EVRAK-9"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self._token()}",
        )
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.mikro_sync_status, MikroSyncStatus.SYNCED)
        self.assertEqual(order.mikro_reference, "EVRAK-9")

    def test_mark_failed_endpoint_updates_the_order(self):
        order = self._paid_order()
        response = self.client.post(
            reverse("integrations:mikro_mark_failed", args=[order.pk]),
            data=json.dumps({"error": "duplicate cari"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self._token()}",
        )
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.mikro_sync_status, MikroSyncStatus.FAILED)
        self.assertEqual(order.mikro_sync_error, "duplicate cari")


class SettingsScreenTests(MikroIntegrationTestCase):
    def test_a_non_admin_cannot_open_the_screen(self):
        self.client.force_login(self.finance)
        response = self.client.get(reverse("integrations:settings"))
        self.assertEqual(response.status_code, 403)

    def test_a_blank_password_on_save_keeps_the_stored_one(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("integrations:settings"), {
            "save_settings": "1", "enabled": "on", "api_key": "test-key",
            "firma_kodu": "Api", "kullanici_kodu": "SRV", "sifre": "",
            "calisma_yili": 2025, "depo_no": 2, "evrak_seri": "T",
            "sip_tip": "1", "sip_cins": "0", "birim_pntr": 1,
            "para_birimi": "TRY",
        })
        self.assertEqual(MikroSettings.load().sifre, "123asd")

    def test_adding_a_vat_mapping(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("integrations:settings"), {
            "add_vat_mapping": "1", "vat_rate": "10.00", "mikro_vergi_pntr": "7",
        })
        self.assertTrue(VatRateMapping.objects.filter(vat_rate=Decimal("10.00")).exists())

    def test_deleting_a_vat_mapping(self):
        mapping = VatRateMapping.objects.get(vat_rate=Decimal("20.00"))
        self.client.force_login(self.admin)
        self.client.post(reverse("integrations:vat_mapping_delete", args=[mapping.pk]))
        self.assertFalse(VatRateMapping.objects.filter(pk=mapping.pk).exists())

    def test_regenerating_the_connector_token(self):
        old_token = MikroSettings.load().connector_token
        self.client.force_login(self.admin)
        self.client.post(reverse("integrations:settings"), {"regenerate_token": "1"})
        self.assertNotEqual(MikroSettings.load().connector_token, old_token)

    def test_retrying_a_failed_order_queues_it_again(self):
        order = self._paid_order()
        services.mark_failed(order, "boom")
        self.client.force_login(self.admin)
        self.client.post(reverse("integrations:retry_sync", args=[order.pk]))
        order.refresh_from_db()
        self.assertEqual(order.mikro_sync_status, MikroSyncStatus.PENDING)
        self.assertEqual(order.mikro_sync_error, "")
