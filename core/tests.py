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
from orders.models import Order
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
        self.assertEqual(self._get(Role.DEALER, "reports:dashboard").status_code, 200)

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


class NavigationTests(TestCase):
    """The sidebar: one flat list per role, exactly one entry highlighted."""

    @classmethod
    def setUpTestData(cls):
        cls.dealer = Dealer.objects.create(name="Bayi A")
        cls.users = {}
        for role in [Role.ADMIN, Role.FINANCE, Role.LOGISTICS, Role.MANAGEMENT, Role.DEALER]:
            cls.users[role] = User.objects.create_user(
                email=f"nav-{role.lower()}@test.com", password="x", role=role,
                status=UserStatus.APPROVED,
                dealer=cls.dealer if role == Role.DEALER else None,
            )

    def _items(self, role, path="/"):
        self.client.force_login(self.users[role])
        return self.client.get(path).context["nav_items"]

    def test_every_role_gets_a_menu(self):
        for role in self.users:
            with self.subTest(role=role):
                self.assertTrue(self._items(role))

    def test_menu_stays_short_enough_to_scan(self):
        # Flat lists, hairlines instead of the uppercase headings that made the
        # sidebar noisy. The admin inherits every role, so its list is longest.
        for role in self.users:
            with self.subTest(role=role):
                self.assertLessEqual(len(self._items(role)), 22)

    def test_exactly_one_entry_is_active(self):
        pages = {
            Role.DEALER: ["/", "/orders/new/", "/orders/", "/orders/drafts/",
                          "/reports/", "/accounts/profile/"],
            Role.FINANCE: ["/", "/payments/pending/", "/orders/", "/payments/history/"],
            Role.LOGISTICS: ["/", "/logistics/pending/", "/orders/"],
            Role.MANAGEMENT: ["/", "/orders/", "/reports/", "/reports/finance/"],
            Role.ADMIN: ["/", "/orders/", "/catalog/products/", "/dealers/",
                         "/accounts/users/", "/payments/exchange-rates/"],
        }
        for role, paths in pages.items():
            for path in paths:
                with self.subTest(role=role, path=path):
                    active = [i for i in self._items(role, path) if i["active"]]
                    self.assertEqual(len(active), 1, f"{role} {path}: {active}")

    def test_detail_screens_keep_their_section_lit(self):
        order = Order.objects.create(dealer=self.dealer, created_by=self.users[Role.DEALER])
        items = self._items(Role.FINANCE, f"/orders/{order.pk}/")
        active = [i["label"] for i in items if i["active"]]
        self.assertEqual([str(label) for label in active], ["Tüm Siparişler"])

    def test_menu_never_advertises_a_screen_the_role_cannot_open(self):
        for role in self.users:
            self.client.force_login(self.users[role])
            for item in self._items(role):
                with self.subTest(role=role, url=item["url"]):
                    response = self.client.get(item["url"])
                    self.assertNotEqual(response.status_code, 403)

    def test_the_icon_of_every_entry_exists(self):
        from core.icons import ICONS

        for role in self.users:
            for item in self._items(role):
                with self.subTest(role=role, icon=item["icon"]):
                    self.assertIn(item["icon"], ICONS)

    def test_anonymous_visitors_get_no_menu(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.context["nav_items"], [])


class RenderedMarkupTests(TestCase):
    """Guards against template syntax leaking onto the page."""

    PAGES = [
        "core:home", "orders:list", "dealers:list", "catalog:product_list",
        "catalog:special_price_list", "payments:history", "payments:pending",
        "logistics:pending", "reports:dashboard", "reports:finance",
        "accounts:user_list", "accounts:pending_users", "accounts:profile",
        "notifications:list", "payments:exchange_rates", "dealers:domain_list",
        "catalog:import_upload", "dealers:history",
    ]

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            email="markup@test.com", password="x", role=Role.ADMIN,
            status=UserStatus.APPROVED,
        )

    def test_no_template_syntax_reaches_the_browser(self):
        """A multi-line ``{# #}`` is not a comment in Django - it prints."""
        self.client.force_login(self.admin)
        for name in self.PAGES:
            with self.subTest(page=name):
                body = self.client.get(reverse(name)).content.decode()
                # Ignore the JSON payload scripts, which legitimately hold braces.
                for marker in ("{#", "{%", "%}", "#}"):
                    self.assertNotIn(marker, body, f"{name} leaks {marker}")

    def test_pages_start_with_the_doctype(self):
        """Anything before <!DOCTYPE html> puts the browser in quirks mode."""
        self.client.force_login(self.admin)
        for name in ["core:home", "accounts:profile"]:
            with self.subTest(page=name):
                body = self.client.get(reverse(name)).content.decode()
                self.assertTrue(
                    body.lstrip().lower().startswith("<!doctype html>"),
                    f"{name} starts with: {body[:60]!r}",
                )

    def test_login_page_is_standards_mode_too(self):
        body = self.client.get(reverse("accounts:login")).content.decode()
        self.assertTrue(body.lstrip().lower().startswith("<!doctype html>"))

    def test_stylesheet_url_carries_a_cache_busting_stamp(self):
        self.client.force_login(self.admin)
        body = self.client.get(reverse("core:home")).content.decode()
        self.assertRegex(body, r'href="/static/css/app\.css\?v=\d+"')


class SidebarContentTests(TestCase):
    """Entries that must never fall out of the menu."""

    @classmethod
    def setUpTestData(cls):
        cls.dealer = Dealer.objects.create(name="Menü Bayi")
        cls.users = {}
        for role in [Role.ADMIN, Role.FINANCE, Role.LOGISTICS, Role.MANAGEMENT, Role.DEALER]:
            cls.users[role] = User.objects.create_user(
                email=f"menu-{role.lower()}@test.com", password="x", role=role,
                status=UserStatus.APPROVED,
                dealer=cls.dealer if role == Role.DEALER else None,
            )

    def test_every_role_can_reach_notifications_and_the_profile_from_the_menu(self):
        for role in self.users:
            self.client.force_login(self.users[role])
            urls = [item["url"] for item in self.client.get("/").context["nav_items"]]
            with self.subTest(role=role):
                self.assertIn(reverse("notifications:list"), urls)
                self.assertIn(reverse("accounts:profile"), urls)


class MenuCompletenessTests(TestCase):
    """Every screen a role can open must be offered by its own menu.

    A KPI card or a bookmark can land on a page the sidebar never mentions,
    which is how "Onay Bekleyenler" and "Sevkiyat Bekleyenler" went missing for
    the admin. This walks the top-level screens for each role and compares what
    opens against what the menu links to.
    """

    #: Screens that stand on their own. Detail pages, forms, exports, API
    #: endpoints and the steps of a wizard are deliberately not listed.
    TOP_LEVEL_SCREENS = [
        "core:home", "orders:list", "orders:create", "orders:drafts",
        "payments:pending", "payments:history", "payments:exchange_rates",
        "logistics:pending",
        "dealers:list", "dealers:history", "dealers:domain_list",
        "catalog:product_list", "catalog:special_price_list", "catalog:import_upload",
        "accounts:pending_users", "accounts:user_list", "accounts:profile",
        "notifications:list", "reports:dashboard", "reports:finance",
    ]

    @classmethod
    def setUpTestData(cls):
        cls.dealer = Dealer.objects.create(name="Kapsam Bayi")
        cls.users = {}
        for role in [Role.ADMIN, Role.FINANCE, Role.LOGISTICS, Role.MANAGEMENT, Role.DEALER]:
            cls.users[role] = User.objects.create_user(
                email=f"kapsam-{role.lower()}@test.com", password="x", role=role,
                status=UserStatus.APPROVED,
                dealer=cls.dealer if role == Role.DEALER else None,
            )

    def test_no_reachable_screen_is_missing_from_the_menu(self):
        for role, user in self.users.items():
            self.client.force_login(user)
            menu = {item["url"] for item in self.client.get("/").context["nav_items"]}
            for name in self.TOP_LEVEL_SCREENS:
                url = reverse(name)
                if self.client.get(url).status_code != 200:
                    continue
                with self.subTest(role=role, screen=name):
                    self.assertIn(url, menu, f"{role} can open {name} but has no menu entry")

    def test_no_menu_entry_leads_to_a_refused_screen(self):
        for role, user in self.users.items():
            self.client.force_login(user)
            for item in self.client.get("/").context["nav_items"]:
                with self.subTest(role=role, url=item["url"]):
                    self.assertEqual(self.client.get(item["url"]).status_code, 200)

    def test_the_basket_is_refused_to_staff_who_have_no_dealer(self):
        # An admin has no dealer, so creating a draft would fail at the database.
        for role in [Role.ADMIN, Role.FINANCE, Role.LOGISTICS, Role.MANAGEMENT]:
            self.client.force_login(self.users[role])
            for name in ["orders:create", "orders:drafts"]:
                with self.subTest(role=role, screen=name):
                    self.assertEqual(self.client.get(reverse(name)).status_code, 403)


class MoneyFilterTests(TestCase):
    def test_multiply_keeps_the_decimals_widthratio_would_drop(self):
        from core.templatetags.ui import money, multiply

        # widthratio truncated the rate to 34, losing 353 TRY on this row.
        converted = multiply(Decimal("3271.14"), Decimal("34.1080"))
        self.assertEqual(converted, Decimal("111572.04"))
        self.assertEqual(money(converted), "111,572.04")

    def test_multiply_is_safe_with_missing_values(self):
        from core.templatetags.ui import multiply

        self.assertEqual(multiply(None, None), Decimal("0.00"))
        self.assertEqual(multiply("abc", 2), "")
