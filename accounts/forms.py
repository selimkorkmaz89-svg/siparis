from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.utils.translation import gettext_lazy as _

from core.constants import Role, UserStatus
from dealers.models import DomainDealerMap

User = get_user_model()


class EmailLoginForm(AuthenticationForm):
    username = forms.EmailField(
        label=_("Email address"),
        widget=forms.EmailInput(attrs={"autofocus": True, "class": "form-control"}),
    )
    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": _("The email address or password is incorrect."),
        "inactive": _("This account is not active."),
    }

    def clean(self):
        try:
            return super().clean()
        except forms.ValidationError:
            # The backend refuses users that are not approved, which would
            # otherwise surface as a plain "wrong password". Re-check the
            # credentials so the user learns the real reason.
            email = (self.cleaned_data.get("username") or "").strip().lower()
            user = User.objects.filter(email=email).first()
            if user is not None and user.check_password(self.data.get("password", "")):
                self.confirm_login_allowed(user)
            raise

    def confirm_login_allowed(self, user):
        if user.status == UserStatus.PENDING_APPROVAL and not user.is_superuser:
            raise forms.ValidationError(
                _("Your account is waiting for administrator approval."),
                code="pending",
            )
        if user.status == UserStatus.REJECTED:
            raise forms.ValidationError(
                _("Your registration request was rejected."), code="rejected"
            )
        super().confirm_login_allowed(user)


class RegistrationForm(UserCreationForm):
    """Self sign-up for dealer users; the dealer comes from the email domain."""

    first_name = forms.CharField(label=_("First name"), max_length=150)
    last_name = forms.CharField(label=_("Last name"), max_length=150)
    email = forms.EmailField(label=_("Email address"))
    phone = forms.CharField(label=_("Phone"), max_length=40, required=False)
    language = forms.ChoiceField(
        label=_("Interface language"),
        choices=[("tr", _("Turkish")), ("en", _("English"))],
        initial="tr",
    )

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone", "language")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(_("An account with this email already exists."))
        dealer = DomainDealerMap.resolve(email)
        if dealer is None:
            raise forms.ValidationError(
                _(
                    "This email domain is not registered to any dealer. Please contact "
                    "your administrator."
                )
            )
        self.dealer = dealer
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.username = user.email
        user.dealer = self.dealer
        user.role = Role.DEALER
        user.status = UserStatus.PENDING_APPROVAL
        user.is_active = True
        if commit:
            user.save()
        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "phone",
            "profile_photo",
            "language",
            "email_notifications_enabled",
        )
        labels = {
            "email_notifications_enabled": _("Send me email notifications"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name == "email_notifications_enabled":
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            else:
                field.widget.attrs.setdefault("class", "form-control")


class UserAdminForm(forms.ModelForm):
    """Admin-side create/edit form for any role."""

    password = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
        required=False,
        help_text=_("Leave blank to keep the current password."),
    )

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "email",
            "phone",
            "role",
            "dealer",
            "status",
            "language",
            "email_notifications_enabled",
            "is_active",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            else:
                field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        data = super().clean()
        role = data.get("role")
        dealer = data.get("dealer")
        if role == Role.DEALER and dealer is None:
            self.add_error("dealer", _("Dealer users must be linked to a dealer."))
        if role and role != Role.DEALER and dealer is not None:
            data["dealer"] = None
        if not self.instance.pk and not data.get("password"):
            self.add_error("password", _("A password is required for a new user."))
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = user.email
        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user


class RejectUserForm(forms.Form):
    reason = forms.CharField(
        label=_("Rejection reason"),
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
    )
