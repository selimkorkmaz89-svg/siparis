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
    """Dealer account card, grouped into sections by the template."""

    class Meta:
        model = Dealer
        fields = (
            "name", "code", "logo", "tax_no", "tax_office",
            "contact_person", "phone", "email", "city", "address",
            "allowed_device_models", "notes", "is_active",
        )
        widgets = {
            "allowed_device_models": forms.SelectMultiple(attrs={"size": 8}),
        }
        help_texts = {
            "allowed_device_models": _(
                "Leave empty to allow every device model. Selecting one or more "
                "hides every other device's products from this dealer."
            ),
        }

    #: Field names per section, used by templates/dealers/dealer_form.html.
    SECTIONS = (
        (_("Identity"), ("name", "code", "logo")),
        (_("Tax details"), ("tax_no", "tax_office")),
        (_("Contact"), ("contact_person", "phone", "email")),
        (_("Address"), ("city", "address")),
        (_("Catalogue access"), ("allowed_device_models",)),
        (_("Other"), ("notes", "is_active")),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["allowed_device_models"].queryset = (
            self.fields["allowed_device_models"].queryset.order_by("brand", "name")
        )

    def sections(self):
        """Yield ``(title, bound_fields)`` so the template stays declarative."""
        for title, names in self.SECTIONS:
            yield title, [self[name] for name in names]


class DomainDealerMapForm(BootstrapModelForm):
    class Meta:
        model = DomainDealerMap
        fields = ("email_domain", "dealer", "is_active")
        help_texts = {
            "email_domain": _("Domain only, without the @ sign. Example: abcdealer.com"),
        }
