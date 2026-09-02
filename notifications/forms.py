from django import forms
from django.utils.translation import gettext_lazy as _

from notifications.models import EmailSettings


class EmailSettingsForm(forms.ModelForm):
    """SMTP configuration, edited from System Settings."""

    password = forms.CharField(
        label=_("SMTP password"),
        required=False,
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "autocomplete": "new-password"},
        ),
        help_text=_("Stored on the server. Leave unchanged to keep the current password."),
    )

    class Meta:
        model = EmailSettings
        fields = (
            "enabled", "host", "port", "username", "password",
            "use_tls", "use_ssl", "from_email",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            elif name != "password":
                field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        data = super().clean()
        if data.get("use_tls") and data.get("use_ssl"):
            self.add_error("use_ssl", _("TLS and SSL cannot both be enabled."))
        if data.get("enabled") and not data.get("host"):
            self.add_error("host", _("An SMTP host is required to enable email sending."))
        return data


class TestEmailForm(forms.Form):
    recipient = forms.EmailField(
        label=_("Send test email to"),
        widget=forms.EmailInput(attrs={"class": "form-control"}),
    )
