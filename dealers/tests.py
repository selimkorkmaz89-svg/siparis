from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.constants import Role, UserStatus
from dealers.forms import DealerForm
from dealers.models import Dealer

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
        self.assertEqual(len(titles), 5)
        grouped = [f.name for _t, group in form.sections() for f in group]
        self.assertEqual(sorted(grouped), sorted(form.fields))

    def test_the_form_screen_renders_every_section(self):
        body = self.client.get(reverse("dealers:create")).content.decode()
        self.assertEqual(body.count('class="card form-section"'), 5)
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
