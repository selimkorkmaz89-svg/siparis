from django import forms
from django.utils.translation import gettext_lazy as _

from dealers.models import Dealer, DomainDealerMap


class BootstrapModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs.setdefault("class", "form-control")
                field.widget.attrs.setdefault("rows", 3)
            else:
                field.widget.attrs.setdefault("class", "form-control")


class DealerForm(BootstrapModelForm):
    class Meta:
        model = Dealer
        fields = (
            "name", "code", "tax_no", "tax_office", "contact_person", "phone",
            "email", "city", "address", "notes", "is_active",
        )


class DomainDealerMapForm(BootstrapModelForm):
    class Meta:
        model = DomainDealerMap
        fields = ("email_domain", "dealer", "is_active")
        help_texts = {
            "email_domain": _("Domain only, without the @ sign. Example: abcdealer.com"),
        }
