"""Smoke tests: every screen renders and role restrictions hold."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Product
from core.constants import Role, UserStatus
from dealers.models import Dealer
from orders import services
from payments.models import ExchangeRate

User = get_user_model()


class RoleAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dealer = Dealer.objects.create(name="Bayi A")
        cls.product = Product.objects.create(
            code="PRD-1", name="Kit", brand="Acme",
            base_price_usd=Decimal("100.00"), vat_rate=Decimal("20.00"),
        )
        ExchangeRate.objects.create(
            rate_date=timezone.localdate(), usd_try_rate=Decimal("34.0000")
        )
        cls.users = {}
        for role in [Role.ADMIN, Role.FINANCE, Role.LOGISTICS, Role.MANAGEMENT, Role.DEALER]:
            cls.users[role] = User.objects.create_user(
                email=f"{role.lower()}@test.com", password="x", role=role,
                status=UserStatus.APPROVED,
                dealer=cls.dealer if role == Role.DEALER else None,
            )
        order = services.get_or_create_draft(cls.users[Role.DEALER])
        services.add_item(order, cls.product, 2)
        services.submit_order(order, cls.users[Role.DEALER])
        cls.order = order

    def _get(self, role, name, *args):
        self.client.force_login(self.users[role])
        return self.client.get(reverse(name, args=args))

    def test_shared_screens_render_for_every_role(self):
        for role in self.users:
            for name in ["core:home", "orders:list", "accounts:profile",
                         "notifications:list", "payments:history"]:
                with self.subTest(role=role, view=name):
                    self.assertEqual(self._get(role, name).status_code, 200)

    def test_admin_screens(self):
        for name in ["accounts:user_list", "accounts:pending_users", "dealers:list",
                     "dealers:domain_list", "catalog:product_list",
                     "catalog:special_price_list", "catalog:import_upload",
                     "payments:exchange_rates", "reports:dashboard"]:
            with self.subTest(view=name):
                self.assertEqual(self._get(Role.ADMIN, name).status_code, 200)

    def test_finance_screens(self):
        self.assertEqual(self._get(Role.FINANCE, "payments:pending").status_code, 200)
        self.assertEqual(
            self._get(Role.FINANCE, "payments:approve", self.order.pk).status_code, 200
        )

    def test_logistics_screens(self):
        self.assertEqual(self._get(Role.LOGISTICS, "logistics:pending").status_code, 200)

    def test_dealer_screens(self):
        self.assertEqual(self._get(Role.DEALER, "orders:create").status_code, 200)
        self.assertEqual(self._get(Role.DEALER, "orders:drafts").status_code, 200)
        self.assertEqual(self._get(Role.DEALER, "reports:mine").status_code, 200)

    def test_dealer_cannot_reach_admin_or_finance_screens(self):
        for name in ["accounts:user_list", "dealers:list", "catalog:product_list",
                     "payments:pending", "logistics:pending", "payments:exchange_rates"]:
            with self.subTest(view=name):
                self.assertEqual(self._get(Role.DEALER, name).status_code, 403)

    def test_management_cannot_approve_or_ship(self):
        self.assertEqual(self._get(Role.MANAGEMENT, "payments:pending").status_code, 403)
        self.assertEqual(self._get(Role.MANAGEMENT, "logistics:pending").status_code, 403)

    def test_dealer_cannot_open_another_dealers_order(self):
        other = Dealer.objects.create(name="Bayi B")
        outsider = User.objects.create_user(
            email="outsider@test.com", password="x", role=Role.DEALER,
            dealer=other, status=UserStatus.APPROVED,
        )
        self.client.force_login(outsider)
        response = self.client.get(reverse("orders:detail", args=[self.order.pk]))
        self.assertEqual(response.status_code, 404)

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_excel_export_returns_a_workbook(self):
        self.client.force_login(self.users[Role.ADMIN])
        response = self.client.get(reverse("orders:list") + "?export=excel")
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])
        self.assertTrue(response["Content-Disposition"].startswith("attachment"))

    def test_order_form_pdf_is_generated(self):
        self.client.force_login(self.users[Role.ADMIN])
        response = self.client.get(reverse("orders:pdf", args=[self.order.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_basket_endpoints_update_the_draft(self):
        self.client.force_login(self.users[Role.DEALER])
        response = self.client.post(
            reverse("orders:basket_add"), {"product": self.product.pk, "quantity": 3}
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["total"], "360.00")
        item_id = payload["items"][0]["id"]
        response = self.client.post(
            reverse("orders:basket_update", args=[item_id]), {"quantity": 1}
        )
        self.assertEqual(response.json()["total"], "120.00")
        response = self.client.post(reverse("orders:basket_remove", args=[item_id]))
        self.assertEqual(response.json()["count"], 0)

    def test_product_search_api_returns_dealer_price(self):
        self.client.force_login(self.users[Role.DEALER])
        response = self.client.get(reverse("catalog:product_search_api") + "?q=PRD")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["price"], "100.00")
