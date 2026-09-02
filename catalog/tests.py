from decimal import Decimal
from io import BytesIO

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone, translation
from openpyxl import Workbook

from catalog import imports
from catalog.models import DealerSpecialPrice, DeviceModel, Product


def workbook_bytes(rows, headers=None):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers or [str(label) for _key, label in imports.PRODUCT_COLUMNS])
    for row in rows:
        sheet.append(row)
    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    return stream


class ProductImportTests(TestCase):
    def test_new_rows_are_previewed_not_written(self):
        stream = workbook_bytes(
            [["PRD-1", "Kit A", "50.00", "USD", "20", "Acme", "", "Sarf", 100, ""]]
        )
        preview = imports.parse_workbook(stream, "product")
        self.assertFalse(preview.blocked)
        self.assertEqual(len(preview.creates), 1)
        self.assertEqual(Product.objects.count(), 0)

    def test_duplicate_code_in_the_file_stops_the_whole_import(self):
        stream = workbook_bytes([
            ["PRD-1", "Kit A", "50.00", "USD", "20", "Acme", "", "Sarf", 100, ""],
            ["PRD-2", "Kit B", "60.00", "USD", "20", "Acme", "", "Sarf", 100, ""],
            ["PRD-1", "Kit C", "70.00", "USD", "20", "Acme", "", "Sarf", 100, ""],
        ])
        preview = imports.parse_workbook(stream, "product")
        self.assertTrue(preview.blocked)
        self.assertEqual(len(preview.duplicates), 1)
        self.assertEqual(Product.objects.count(), 0)

    def test_existing_code_is_classified_as_an_update_with_a_diff(self):
        Product.objects.create(
            code="PRD-1", name="Kit A", brand="Acme", tests_per_pack=100,
            base_price_usd=Decimal("50.00"), vat_rate=Decimal("20.00"),
            mikro_stok_kodu="PRD-1",
        )
        stream = workbook_bytes(
            [["PRD-1", "Kit A", "75.00", "USD", "20", "Acme", "", "Sarf", 100, ""]]
        )
        preview = imports.parse_workbook(stream, "product")
        self.assertEqual(len(preview.updates), 1)
        changes = preview.updates[0].changes
        with translation.override("en"):
            labels = [str(label) for label, _old, _new in changes]
        # Only the price differs; 20 and 20.00 must not read as a change.
        self.assertEqual(labels, ["List price (USD)"])
        self.assertEqual(changes[0][1], Decimal("50.00"))
        self.assertEqual(changes[0][2], Decimal("75.00"))

    def test_invalid_number_is_reported_as_an_error(self):
        stream = workbook_bytes(
            [["PRD-1", "Kit A", "abc", "USD", "20", "Acme", "", "Sarf", 100, ""]]
        )
        preview = imports.parse_workbook(stream, "product")
        self.assertTrue(preview.blocked)

    def test_an_unrecognised_currency_is_reported_as_an_error(self):
        stream = workbook_bytes(
            [["PRD-1", "Kit A", "50.00", "Yen", "20", "Acme", "", "Sarf", 100, ""]]
        )
        preview = imports.parse_workbook(stream, "product")
        self.assertTrue(preview.blocked)

    def test_an_unrecognised_product_group_is_reported_as_an_error(self):
        stream = workbook_bytes(
            [["PRD-1", "Kit A", "50.00", "USD", "20", "Acme", "", "Ekipman", 100, ""]]
        )
        preview = imports.parse_workbook(stream, "product")
        self.assertTrue(preview.blocked)

    def test_confirmed_preview_writes_the_rows(self):
        stream = workbook_bytes([
            ["PRD-1", "Kit A", "50.00", "USD", "20", "Acme", "", "Sarf", 100, ""],
            ["PRD-2", "Kit B", "80.00", "USD", "10", "Nordis", "", "Cihaz", 50, ""],
        ])
        preview = imports.parse_workbook(stream, "product")
        result = imports.apply_preview(preview)
        self.assertEqual(result, {"created": 2, "updated": 0})
        self.assertEqual(Product.objects.count(), 2)
        product_2 = Product.objects.get(code="PRD-2")
        self.assertEqual(product_2.base_price_usd, Decimal("80.00"))
        self.assertEqual(product_2.product_group, "DEVICE")
        self.assertEqual(product_2.mikro_stok_kodu, "PRD-2")

    def test_a_chf_row_is_converted_using_the_current_rate(self):
        from payments.models import ExchangeRate

        ExchangeRate.objects.create(
            rate_date=timezone.localdate(), usd_try_rate=Decimal("34.0000"),
            chf_try_rate=Decimal("42.5000"),
        )
        stream = workbook_bytes(
            [["PRD-CHF", "Swiss Kit", "100.00", "İsviçre Frangı", "20",
              "Acme", "", "Sarf", 0, ""]]
        )
        preview = imports.parse_workbook(stream, "product")
        self.assertFalse(preview.blocked)
        imports.apply_preview(preview)
        product = Product.objects.get(code="PRD-CHF")
        self.assertEqual(product.price_currency, "CHF")
        self.assertEqual(product.list_price, Decimal("100.00"))
        self.assertEqual(product.base_price_usd, Decimal("125.00"))

    def test_a_chf_row_with_no_rate_yet_imports_at_zero_with_a_warning(self):
        stream = workbook_bytes(
            [["PRD-CHF", "Swiss Kit", "100.00", "CHF", "20", "Acme", "", "Sarf", 0, ""]]
        )
        preview = imports.parse_workbook(stream, "product")
        self.assertFalse(preview.blocked)
        self.assertTrue(preview.warnings)
        imports.apply_preview(preview)
        self.assertEqual(Product.objects.get(code="PRD-CHF").base_price_usd, Decimal("0.00"))

    def test_template_download_has_the_expected_headers(self):
        payload = imports.build_template("product")
        self.assertTrue(payload.startswith(b"PK"))


class ProductDeleteTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        from core.constants import Role, UserStatus

        User = get_user_model()
        self.admin = User.objects.create_user(
            email="silme@test.com", password="x", role=Role.ADMIN,
            status=UserStatus.APPROVED,
        )
        self.client.force_login(self.admin)
        self.product = Product.objects.create(
            code="PRD-DEL", name="Silinecek", base_price_usd=Decimal("10.00"),
            vat_rate=Decimal("20.00"),
        )

    def test_an_unused_product_can_be_deleted(self):
        response = self.client.post(
            reverse("catalog:product_delete", args=[self.product.pk])
        )
        self.assertRedirects(response, reverse("catalog:product_list"))
        self.assertFalse(Product.objects.filter(pk=self.product.pk).exists())

    def test_a_product_used_in_an_order_is_refused_not_crashed(self):
        from dealers.models import Dealer
        from django.contrib.auth import get_user_model

        from core.constants import Role, UserStatus
        from orders import services

        User = get_user_model()
        dealer = Dealer.objects.create(name="Silme Bayi")
        dealer_user = User.objects.create_user(
            email="silme-bayi@test.com", password="x", role=Role.DEALER,
            dealer=dealer, status=UserStatus.APPROVED,
        )
        order = services.get_or_create_draft(dealer_user)
        services.add_item(order, self.product, 1)

        response = self.client.post(
            reverse("catalog:product_delete", args=[self.product.pk])
        )
        self.assertRedirects(response, reverse("catalog:product_list"))
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())
        # The message is rendered in the acting user's own language (the
        # admin's default is Turkish), so check for the interpolated product
        # code rather than an English phrase.
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any(self.product.code in str(m) for m in messages))

    def test_deleting_a_product_removes_its_special_price(self):
        from dealers.models import Dealer

        dealer = Dealer.objects.create(name="Fiyat Bayi")
        DealerSpecialPrice.objects.create(
            dealer=dealer, product=self.product, price_usd=Decimal("8.00")
        )
        self.client.post(reverse("catalog:product_delete", args=[self.product.pk]))
        self.assertFalse(DealerSpecialPrice.objects.filter(product_id=self.product.pk).exists())


class DeviceModelAccessTests(TestCase):
    """A dealer with no restriction sees everything; one with a restriction
    sees only its allowed device models plus unclassified products."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        from core.constants import Role, UserStatus
        from dealers.models import Dealer

        User = get_user_model()
        self.device_a = DeviceModel.objects.create(name="X200", brand="Acme")
        self.device_b = DeviceModel.objects.create(name="Y300", brand="Nordis")
        self.product_a = Product.objects.create(
            code="PRD-A", name="A ürünü", device_model=self.device_a,
            base_price_usd=Decimal("10.00"), vat_rate=Decimal("20.00"),
        )
        self.product_b = Product.objects.create(
            code="PRD-B", name="B ürünü", device_model=self.device_b,
            base_price_usd=Decimal("10.00"), vat_rate=Decimal("20.00"),
        )
        self.product_unclassified = Product.objects.create(
            code="PRD-U", name="U ürünü",
            base_price_usd=Decimal("10.00"), vat_rate=Decimal("20.00"),
        )
        self.dealer = Dealer.objects.create(name="Kısıtlı Bayi")
        self.dealer_user = User.objects.create_user(
            email="kisitli@test.com", password="x", role=Role.DEALER,
            dealer=self.dealer, status=UserStatus.APPROVED,
        )

    def test_a_dealer_with_no_restriction_sees_everything(self):
        visible = set(Product.objects.visible_to_dealer(self.dealer))
        self.assertEqual(visible, {self.product_a, self.product_b, self.product_unclassified})

    def test_a_restricted_dealer_sees_its_device_plus_unclassified_products(self):
        self.dealer.allowed_device_models.add(self.device_a)
        visible = set(Product.objects.visible_to_dealer(self.dealer))
        self.assertEqual(visible, {self.product_a, self.product_unclassified})
        self.assertNotIn(self.product_b, visible)

    def test_the_search_api_enforces_the_restriction(self):
        self.dealer.allowed_device_models.add(self.device_a)
        self.client.force_login(self.dealer_user)
        codes = {
            item["code"]
            for item in self.client.get("/catalog/api/products/").json()["results"]
        }
        self.assertEqual(codes, {"PRD-A", "PRD-U"})

    def test_the_basket_refuses_a_hidden_product_even_by_direct_post(self):
        self.dealer.allowed_device_models.add(self.device_a)
        self.client.force_login(self.dealer_user)
        response = self.client.post(
            "/orders/basket/add/", {"product": self.product_b.pk, "quantity": 1}
        )
        self.assertEqual(response.status_code, 404)

    def test_the_basket_accepts_an_allowed_product(self):
        self.dealer.allowed_device_models.add(self.device_a)
        self.client.force_login(self.dealer_user)
        response = self.client.post(
            "/orders/basket/add/", {"product": self.product_a.pk, "quantity": 1}
        )
        self.assertEqual(response.status_code, 200)

    def test_staff_roles_are_never_restricted(self):
        # visible_to_dealer(None) is what every non-dealer screen passes.
        self.assertEqual(Product.objects.visible_to_dealer(None).count(), 3)


class DeviceModelImportTests(TestCase):
    def test_a_new_device_model_name_is_created_on_import(self):
        stream = workbook_bytes(
            [["PRD-1", "Kit A", "50.00", "USD", "20", "Acme", "Acme X200", "Sarf", 100, ""]]
        )
        preview = imports.parse_workbook(stream, "product")
        self.assertFalse(preview.blocked)
        imports.apply_preview(preview)
        product = Product.objects.get(code="PRD-1")
        self.assertEqual(product.device_model.name, "Acme X200")
        self.assertEqual(product.device_model.brand, "Acme")

    def test_a_blank_device_model_leaves_the_product_unclassified(self):
        stream = workbook_bytes(
            [["PRD-2", "Kit B", "50.00", "USD", "20", "Acme", "", "Sarf", 100, ""]]
        )
        preview = imports.parse_workbook(stream, "product")
        imports.apply_preview(preview)
        self.assertIsNone(Product.objects.get(code="PRD-2").device_model)

    def test_reimporting_reuses_the_existing_device_model(self):
        DeviceModel.objects.create(name="Acme X200", brand="Acme")
        stream = workbook_bytes(
            [["PRD-3", "Kit C", "50.00", "USD", "20", "Acme", "Acme X200", "Sarf", 100, ""]]
        )
        preview = imports.parse_workbook(stream, "product")
        imports.apply_preview(preview)
        self.assertEqual(DeviceModel.objects.filter(name="Acme X200").count(), 1)


class RepriceForeignCurrencyTests(TestCase):
    """catalog.services.reprice_foreign_currency_products, in isolation."""

    def test_a_chf_products_usd_price_is_recomputed_from_its_list_price(self):
        from catalog.services import reprice_foreign_currency_products

        product = Product.objects.create(
            code="CHF-A", name="Swiss item", price_currency="CHF",
            list_price=Decimal("200.00"), base_price_usd=Decimal("0.00"),
        )
        updated = reprice_foreign_currency_products("CHF", Decimal("1.2500"))
        self.assertEqual(updated, 1)
        product.refresh_from_db()
        self.assertEqual(product.base_price_usd, Decimal("250.00"))

    def test_usd_products_are_never_touched(self):
        from catalog.services import reprice_foreign_currency_products

        product = Product.objects.create(
            code="USD-A", name="Dollar item", base_price_usd=Decimal("100.00"),
        )
        updated = reprice_foreign_currency_products("CHF", Decimal("1.2500"))
        self.assertEqual(updated, 0)
        product.refresh_from_db()
        self.assertEqual(product.base_price_usd, Decimal("100.00"))

    def test_a_chf_product_with_no_list_price_yet_is_skipped(self):
        from catalog.services import reprice_foreign_currency_products

        Product.objects.create(
            code="CHF-B", name="Unpriced Swiss item", price_currency="CHF",
            base_price_usd=Decimal("0.00"),
        )
        updated = reprice_foreign_currency_products("CHF", Decimal("1.2500"))
        self.assertEqual(updated, 0)

    def test_a_zero_rate_is_a_no_op(self):
        from catalog.services import reprice_foreign_currency_products

        updated = reprice_foreign_currency_products("CHF", None)
        self.assertEqual(updated, 0)
