from django import forms
from django.utils.translation import gettext_lazy as _


class RejectionForm(forms.Form):
    """Finance rejection; the reason is mandatory by specification."""

    reason = forms.CharField(
        label=_("Rejection reason"),
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        help_text=_("The dealer sees this text, so please be specific."),
    )


class ShipmentForm(forms.Form):
    carrier = forms.CharField(
        label=_("Carrier"), max_length=120, required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    tracking_no = forms.CharField(
        label=_("Tracking number"), max_length=120, required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    note = forms.CharField(
        label=_("Note"), required=False,
        widget=forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
    )


class OrderNoteForm(forms.Form):
    note = forms.CharField(
        label=_("Order note"), required=False,
        widget=forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
    )


class CancelOrderForm(forms.Form):
    note = forms.CharField(
        label=_("Cancellation reason"),
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
    )
