from django import forms
from django.utils.translation import gettext_lazy as _

from catalog.models import DealerSpecialPrice, DeviceModel, Product
from dealers.forms import BootstrapModelForm


class ProductForm(BootstrapModelForm):
    class Meta:
        model = Product
        fields = (
            "code", "name", "brand", "device_model", "product_group",
            "tests_per_pack", "price_currency", "list_price", "base_price_usd",
            "vat_rate", "description", "is_active", "mikro_stok_kodu",
        )


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
