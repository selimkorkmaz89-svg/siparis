from decimal import Decimal

from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from payments.models import Payment


class PaymentDeclarationForm(forms.ModelForm):
    """Used by dealers and finance to record a bank transfer against an order."""

    class Meta:
        model = Payment
        fields = ("amount_try", "reference_no", "payment_date", "receipt", "note")
        widgets = {
            "amount_try": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "reference_no": forms.TextInput(attrs={"class": "form-control"}),
            "payment_date": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"
            ),
            "receipt": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["payment_date"].initial = timezone.localdate()

    def clean_amount_try(self):
        amount = self.cleaned_data["amount_try"]
        if amount <= Decimal("0"):
            raise forms.ValidationError(_("The amount must be greater than zero."))
        return amount


class PaymentApprovalForm(forms.Form):
    note = forms.CharField(
        label=_("Note"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
    )


class ExchangeRateForm(forms.Form):
    rate_date = forms.DateField(
        label=_("Rate date"),
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    usd_try_rate = forms.DecimalField(
        label=_("USD/TRY rate"),
        max_digits=12,
        decimal_places=4,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.0001"}),
    )
