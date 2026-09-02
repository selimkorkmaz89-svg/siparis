from decimal import Decimal

from django import forms
from django.utils.translation import gettext_lazy as _

from catalog.models import DealerSpecialPrice, DeviceModel, Product
from core.constants import Currency
from dealers.forms import BootstrapModelForm

TWO_PLACES = Decimal("0.01")


class ProductForm(BootstrapModelForm):
    """For a CHF-listed product, ``base_price_usd`` isn't typed in - it's
    derived from ``list_price`` and the current TCMB CHF rate, the same way
    the Excel import and the daily rate refresh price it (see
    ``catalog.services.reprice_foreign_currency_products``)."""

    class Meta:
        model = Product
        fields = (
            "code", "name", "brand", "device_model", "product_group",
            "tests_per_pack", "price_currency", "list_price", "base_price_usd",
            "vat_rate", "description", "is_active", "mikro_stok_kodu",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Computed automatically for CHF - see clean() below.
        self.fields["base_price_usd"].required = False

    def clean(self):
        cleaned_data = super().clean()
        currency = cleaned_data.get("price_currency")
        if currency == Currency.CHF:
            list_price = cleaned_data.get("list_price")
            if not list_price:
                self.add_error(
                    "list_price",
                    _("Enter the CHF list price - the USD price is calculated from it."),
                )
            else:
                from payments import services as fx

                rate = fx.get_rate()
                cross_rate = rate.chf_to_usd_rate if rate else None
                if not cross_rate:
                    self.add_error(
                        "list_price",
                        _(
                            "No CHF exchange rate is available yet, so the USD price "
                            "can't be calculated. Fetch or enter today's rate first."
                        ),
                    )
                else:
                    cleaned_data["base_price_usd"] = (list_price * cross_rate).quantize(
                        TWO_PLACES
                    )
        else:
            cleaned_data["list_price"] = None
            if not cleaned_data.get("base_price_usd"):
                self.add_error("base_price_usd", _("This field is required."))
        return cleaned_data


class DeviceModelForm(BootstrapModelForm):
    class Meta:
        model = DeviceModel
        fields = ("name", "brand", "is_active")


class DealerSpecialPriceForm(BootstrapModelForm):
    class Meta:
        model = DealerSpecialPrice
        fields = ("dealer", "product", "price_usd")


class ImportUploadForm(forms.Form):
    KIND_CHOICES = [("product", _("Product catalogue")), ("dealer", _("Dealer cards"))]

    kind = forms.ChoiceField(
        label=_("Import type"),
        choices=KIND_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    file = forms.FileField(
        label=_("Excel file (.xlsx)"),
        widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".xlsx"}),
    )

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        if not uploaded.name.lower().endswith(".xlsx"):
            raise forms.ValidationError(_("Please upload a file in .xlsx format."))
        if uploaded.size > 10 * 1024 * 1024:
            raise forms.ValidationError(_("The file may not be larger than 10 MB."))
        return uploaded
