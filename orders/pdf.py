"""Order form PDF.

The document is explicitly *not* an official waybill or invoice; it is a
readable summary of the order record, regenerated from live data on every
download.
"""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.templatetags.static import static
from django.template.loader import render_to_string
from django.utils import translation

from payments import services as fx


class PdfEngineUnavailable(RuntimeError):
    """WeasyPrint is installed but its native libraries are missing.

    Typical on Windows without GTK. The order form is still viewable as HTML,
    so the caller falls back to the printable preview instead of erroring out.
    """


def render_order_html(order, language: str | None = None, preview: bool = False) -> str:
    """The order form as HTML - the exact document the PDF is made from.

    ``preview=True`` adds the small toolbar the browser view needs; WeasyPrint
    is never given it.
    """
    language = language or translation.get_language() or settings.LANGUAGE_CODE
    with translation.override(language):
        approved_payment = order.payments.filter(status="APPROVED").first()
        return render_to_string(
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
                # WeasyPrint reads the files off disk; a browser cannot open a
                # file:// URL from an http page, so the preview uses web paths.
                "logo_url": _company_logo(preview),
                "dealer_logo_url": _dealer_logo(order.dealer, preview),
                "exchange_rate": fx.current_rate_value(),
                "is_preview": preview,
            },
        )


def render_order_pdf(order, language: str | None = None, request=None) -> bytes:
    """The order form as a PDF, from the same HTML the preview shows."""
    try:
        from weasyprint import HTML  # imported lazily: heavy native dependency
    except Exception as exc:  # OSError when cairo/pango are missing (Windows)
        raise PdfEngineUnavailable(str(exc)) from exc

    html = render_order_html(order, language=language)
    base_url = (
        request.build_absolute_uri("/") if request is not None else str(settings.BASE_DIR)
    )
    try:
        return HTML(string=html, base_url=base_url).write_pdf()
    except OSError as exc:  # native libraries present but unusable
        raise PdfEngineUnavailable(str(exc)) from exc


def _company_logo(preview: bool) -> str:
    return static(settings.COMPANY_LOGO) if preview else _logo_path()


def _dealer_logo(dealer, preview: bool) -> str:
    if not getattr(dealer, "logo", None):
        return ""
    return dealer.logo.url if preview else _dealer_logo_path(dealer)


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
