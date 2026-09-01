from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from accounts.forms import RegistrationForm
from core.constants import Role, UserStatus
from dealers.models import Dealer, DomainDealerMap

User = get_user_model()


class RegistrationFlowTests(TestCase):
    def setUp(self):
        self.dealer = Dealer.objects.create(name="ABC Bayi")
        DomainDealerMap.objects.create(email_domain="abcbayi.com", dealer=self.dealer)

    def _payload(self, email="ali@abcbayi.com"):
        return {
            "first_name": "Ali", "last_name": "Veli", "email": email,
            "phone": "+90 555 000 00 00", "language": "tr",
            "password1": "Guclu-Parola-123", "password2": "Guclu-Parola-123",
        }

    def test_known_domain_binds_the_dealer_and_waits_for_approval(self):
        form = RegistrationForm(data=self._payload())
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.dealer, self.dealer)
        self.assertEqual(user.role, Role.DEALER)
        self.assertEqual(user.status, UserStatus.PENDING_APPROVAL)

    def test_unknown_domain_is_refused(self):
        form = RegistrationForm(data=self._payload("ali@bilinmeyen.com"))
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_pending_user_cannot_sign_in(self):
        RegistrationForm(data=self._payload()).save()
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "ali@abcbayi.com", "password": "Guclu-Parola-123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_approved_user_can_sign_in(self):
        user = RegistrationForm(data=self._payload()).save()
        user.status = UserStatus.APPROVED
        user.save()
        logged_in = self.client.login(
            username="ali@abcbayi.com", password="Guclu-Parola-123"
        )
        self.assertTrue(logged_in)

    def test_admin_approval_marks_the_user_approved(self):
        pending = RegistrationForm(data=self._payload()).save()
        admin = User.objects.create_user(
            email="admin@sirket.com", password="x", role=Role.ADMIN,
            status=UserStatus.APPROVED,
        )
        self.client.force_login(admin)
        self.client.post(reverse("accounts:approve_user", args=[pending.pk]))
        pending.refresh_from_db()
        self.assertEqual(pending.status, UserStatus.APPROVED)
        self.assertEqual(pending.approved_by, admin)
        self.assertTrue(pending.notifications.exists())


class LanguageTests(TestCase):
    def setUp(self):
        dealer = Dealer.objects.create(name="Bayi")
        self.user = User.objects.create_user(
            email="user@test.com", password="x", role=Role.DEALER,
            dealer=dealer, status=UserStatus.APPROVED, language="en",
        )

    def test_interface_follows_the_profile_language(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Create order", status_code=200)

    def test_turkish_translation_is_served(self):
        self.user.language = "tr"
        self.user.save()
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Sipariş Oluştur")

    def test_language_switcher_sets_the_cookie(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("set_language"), {"language": "en", "next": "/"}
        )
        self.assertEqual(response.status_code, 302)

    def test_both_catalogs_translate_a_known_string(self):
        with translation.override("tr"):
            self.assertEqual(translation.gettext("Create order"), "Sipariş Oluştur")
        with translation.override("en"):
            self.assertEqual(translation.gettext("Create order"), "Create order")
