"""Order form PDF.

The document is explicitly *not* an official waybill or invoice; it is a
readable summary of the order record, regenerated from live data on every
download.
"""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import translation

from payments import services as fx


def render_order_pdf(order, language: str | None = None, request=None) -> bytes:
    from weasyprint import HTML  # imported lazily: heavy native dependency

    language = language or translation.get_language() or settings.LANGUAGE_CODE
    with translation.override(language):
        approved_payment = order.payments.filter(status="APPROVED").first()
        html = render_to_string(
            "orders/order_form_pdf.html",
            {
                "order": order,
                "items": order.items.all(),
                "payment": approved_payment,
                "company": {
                    "name": settings.COMPANY_NAME,
                    "tax_no": settings.COMPANY_TAX_NO,
                    "address": settings.COMPANY_ADDRESS,
                    "phone": settings.COMPANY_PHONE,
                    "email": settings.COMPANY_EMAIL,
                },
                "brand_color": settings.BRAND_COLOR,
                "logo_url": _logo_path(),
                "dealer_logo_url": _dealer_logo_path(order.dealer),
                "exchange_rate": fx.current_rate_value(),
            },
        )
    base_url = request.build_absolute_uri("/") if request is not None else str(settings.BASE_DIR)
    return HTML(string=html, base_url=base_url).write_pdf()


def _dealer_logo_path(dealer) -> str:
    """Filesystem URL of the dealer's own logo, when one was uploaded."""
    if not getattr(dealer, "logo", None):
        return ""
    try:
        return Path(dealer.logo.path).as_uri()
    except (NotImplementedError, ValueError):  # non-filesystem storage
        return ""


def _logo_path() -> str:
    """Absolute filesystem URL for the logo so WeasyPrint can embed it."""
    for directory in settings.STATICFILES_DIRS:
        candidate = directory / settings.COMPANY_LOGO
        if candidate.exists():
            return candidate.as_uri()
    return ""
