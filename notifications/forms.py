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
    graph_client_secret = forms.CharField(
        label=_("Azure client secret"),
        required=False,
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "autocomplete": "new-password"},
        ),
        help_text=_("Stored on the server. Leave unchanged to keep the current value."),
    )

    class Meta:
        model = EmailSettings
        fields = (
            "enabled", "provider", "host", "port", "username", "password",
            "use_tls", "use_ssl", "graph_tenant_id", "graph_client_id",
            "graph_client_secret", "from_email",
        )

    #: Field names per group, used by the template to toggle SMTP vs Graph.
    PROVIDER_FIELDS = {
        "SMTP": ("host", "port", "username", "password", "use_tls", "use_ssl"),
        "MS_GRAPH": ("graph_tenant_id", "graph_client_id", "graph_client_secret"),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            elif name not in ("password", "graph_client_secret"):
                field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        data = super().clean()
        if data.get("use_tls") and data.get("use_ssl"):
            self.add_error("use_ssl", _("TLS and SSL cannot both be enabled."))
        if not data.get("enabled"):
            return data
        if data.get("provider") == EmailSettings.Provider.MS_GRAPH:
            if not data.get("from_email"):
                self.add_error(
                    "from_email", _("A sender mailbox is required to enable Microsoft Graph.")
                )
            for field in ("graph_tenant_id", "graph_client_id"):
                if not data.get(field):
                    self.add_error(field, _("This field is required to enable Microsoft Graph."))
            if not (self.cleaned_data.get("graph_client_secret") or self.instance.graph_client_secret):
                self.add_error(
                    "graph_client_secret",
                    _("A client secret is required to enable Microsoft Graph."),
                )
        elif not data.get("host"):
            self.add_error("host", _("An SMTP host is required to enable email sending."))
        return data


class TestEmailForm(forms.Form):
    recipient = forms.EmailField(
        label=_("Send test email to"),
        widget=forms.EmailInput(attrs={"class": "form-control"}),
    )
