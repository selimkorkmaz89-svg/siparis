from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from catalog.models import Product
from core.constants import Role, UserStatus
from dealers.forms import DealerForm
from dealers.models import Dealer
from orders import services as order_services

User = get_user_model()

# Smallest valid PNG, so the upload path is exercised without a fixture file.
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class DealerFormTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@dealers.test", password="x", role=Role.ADMIN,
            status=UserStatus.APPROVED,
        )
        self.client.force_login(self.admin)

    def test_the_form_is_grouped_into_sections(self):
        form = DealerForm()
        titles = [str(title) for title, _fields in form.sections()]
        self.assertEqual(len(titles), 6)
        grouped = [f.name for _t, group in form.sections() for f in group]
        self.assertEqual(sorted(grouped), sorted(form.fields))

    def test_the_form_screen_renders_every_section(self):
        body = self.client.get(reverse("dealers:create")).content.decode()
        self.assertEqual(body.count('class="card form-section"'), 6)
        self.assertIn('enctype="multipart/form-data"', body)

    def test_a_logo_can_be_uploaded(self):
        response = self.client.post(reverse("dealers:create"), {
            "name": "Logo Bayi", "code": "L-1", "tax_no": "", "tax_office": "",
            "contact_person": "", "phone": "", "email": "", "city": "",
            "address": "", "notes": "", "is_active": "on",
            "logo": SimpleUploadedFile("logo.png", PNG, content_type="image/png"),
        })
        self.assertEqual(response.status_code, 302)
        dealer = Dealer.objects.get(name="Logo Bayi")
        self.assertTrue(dealer.logo)
        self.addCleanup(dealer.logo.delete, save=False)

    def test_initials_fall_back_when_there_is_no_logo(self):
        self.assertEqual(Dealer(name="Demo Bayi 1").initials, "DB")
        self.assertEqual(Dealer(name="Acme").initials, "AC")

    def test_the_dealer_list_shows_the_badge(self):
        Dealer.objects.create(name="Rozet Bayi")
        body = self.client.get(reverse("dealers:list")).content.decode()
        self.assertIn('class="dealer-logo"', body)
        self.assertIn("RB", body)


class DealerHistoryTests(TestCase):
    """The 'Tümü' (all dealers) option, alongside the single-dealer view."""

    def setUp(self):
        self.dealer_a = Dealer.objects.create(name="Tarih Bayi A")
        self.dealer_b = Dealer.objects.create(name="Tarih Bayi B")
        self.product = Product.objects.create(
            code="HIST-1", name="Kit", base_price_usd=Decimal("100.00"),
            vat_rate=Decimal("20.00"),
        )
        self.finance = User.objects.create_user(
            email="finans-history@test.com", password="x", role=Role.FINANCE,
            status=UserStatus.APPROVED,
        )
        self.order_a = self._submitted_order(self.dealer_a, "bayi-a-history@test.com")
        self.order_b = self._submitted_order(self.dealer_b, "bayi-b-history@test.com")
        self.client.force_login(self.finance)

    def _submitted_order(self, dealer, email):
        dealer_user = User.objects.create_user(
            email=email, password="x", role=Role.DEALER, dealer=dealer,
            status=UserStatus.APPROVED,
        )
        draft = order_services.get_or_create_draft(dealer_user)
        order_services.add_item(draft, self.product, 1)
        return order_services.submit_order(draft, dealer_user)

    def test_no_dealer_in_the_url_shows_every_dealers_orders(self):
        body = self.client.get(reverse("dealers:history")).content.decode()
        self.assertIn(self.order_a.order_no, body)
        self.assertIn(self.order_b.order_no, body)

    def test_a_single_dealer_only_shows_that_dealers_orders(self):
        body = self.client.get(
            reverse("dealers:history_detail", args=[self.dealer_a.pk])
        ).content.decode()
        self.assertIn(self.order_a.order_no, body)
        self.assertNotIn(self.order_b.order_no, body)

    def test_the_all_dealers_option_is_offered_and_selected_by_default(self):
        body = self.client.get(reverse("dealers:history")).content.decode()
        self.assertIn(f'"{reverse("dealers:history")}" selected', body)

    def test_excel_export_covers_every_dealer(self):
        response = self.client.get(reverse("dealers:history") + "?export=excel")
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])

    def test_a_dealer_with_no_orders_yet_is_not_mistaken_for_the_all_dealers_screen(self):
        empty_dealer = Dealer.objects.create(name="Bos Bayi")
        body = self.client.get(
            reverse("dealers:history_detail", args=[empty_dealer.pk])
        ).content.decode()
        self.assertIn("Bu bayinin henüz siparişi yok.", body)
