from decimal import Decimal

from django import forms
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from payments import services as fx
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

    def __init__(self, *args, order=None, rate=None, **kwargs):
        """``order`` and ``rate`` let ``clean_amount_try`` refuse an underpayment."""
        super().__init__(*args, **kwargs)
        self.fields["payment_date"].initial = timezone.localdate()
        self.order = order
        self.rate = rate

    def clean_amount_try(self):
        amount = self.cleaned_data["amount_try"]
        if amount <= Decimal("0"):
            raise forms.ValidationError(_("The amount must be greater than zero."))
        if self.order and self.rate and self.order.total_amount_usd:
            converted = fx.try_to_usd(amount, self.rate)
            tolerance = Decimal(str(settings.PAYMENT_MISMATCH_TOLERANCE))
            minimum = self.order.total_amount_usd * (Decimal("1") - tolerance)
            if converted < minimum:
                raise forms.ValidationError(
                    _(
                        "This amount converts to $%(converted)s, which is less than the "
                        "order total of $%(expected)s. Enter the full payment amount."
                    )
                    % {
                        "converted": f"{converted:,.2f}",
                        "expected": f"{self.order.total_amount_usd:,.2f}",
                    }
                )
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
    chf_try_rate = forms.DecimalField(
        label=_("CHF/TRY rate"),
        max_digits=12,
        decimal_places=4,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.0001"}),
        help_text=_("Optional - only needed to price Swiss-Franc list items."),
    )
