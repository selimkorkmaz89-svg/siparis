from django import forms
from django.utils.translation import gettext_lazy as _

from integrations.models import MikroSettings, VatRateMapping


class MikroSettingsForm(forms.ModelForm):
    """Mikro connection + document defaults, edited from System Settings."""

    sifre = forms.CharField(
        label=_("password (Sifre)"),
        required=False,
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "autocomplete": "new-password"},
        ),
        help_text=_("Stored on the server. Leave unchanged to keep the current password."),
    )

    class Meta:
        model = MikroSettings
        fields = (
            "enabled", "api_key", "firma_kodu", "kullanici_kodu", "sifre",
            "calisma_yili", "depo_no", "evrak_seri", "sip_tip", "sip_cins",
            "birim_pntr", "vergisiz_fl", "para_birimi",
        )

    #: Field names per section, used by templates/integrations/settings.html.
    SECTIONS = (
        (_("Credentials"), ("enabled", "api_key", "firma_kodu", "kullanici_kodu",
                             "sifre", "calisma_yili")),
        (_("Document defaults"), ("depo_no", "evrak_seri", "sip_tip", "sip_cins",
                                   "birim_pntr", "vergisiz_fl", "para_birimi")),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            elif name != "sifre":
                field.widget.attrs.setdefault("class", "form-control")

    def sections(self):
        for title, names in self.SECTIONS:
            yield title, [self[name] for name in names]


class VatRateMappingForm(forms.ModelForm):
    class Meta:
        model = VatRateMapping
        fields = ("vat_rate", "mikro_vergi_pntr")
        widgets = {
            "vat_rate": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "mikro_vergi_pntr": forms.NumberInput(attrs={"class": "form-control"}),
        }
