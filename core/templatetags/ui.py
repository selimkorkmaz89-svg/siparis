"""Template helpers shared by the list screens."""
import os
from decimal import Decimal, InvalidOperation

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from django.contrib.staticfiles import finders
from django.templatetags.static import static as static_url

from core.icons import ICONS

from core.constants import OrderStatus, PaymentStatus

register = template.Library()

STATUS_CLASSES = {
    OrderStatus.DRAFT: "badge-draft",
    OrderStatus.PENDING_PAYMENT: "badge-pending",
    OrderStatus.PAID: "badge-paid",
    OrderStatus.SHIPPED: "badge-shipped",
    OrderStatus.CANCELLED: "badge-cancelled",
    PaymentStatus.PENDING: "badge-pending",
    PaymentStatus.APPROVED: "badge-paid",
    PaymentStatus.REJECTED: "badge-cancelled",
}


@register.simple_tag(takes_context=True)
def url_replace(context, **kwargs):
    """Rebuild the current query string with the given parameters replaced."""
    query = context["request"].GET.copy()
    for key, value in kwargs.items():
        if value in (None, ""):
            query.pop(key, None)
        else:
            query[key] = value
    query.pop("page", None)
    encoded = query.urlencode()
    return f"?{encoded}" if encoded else "?"


@register.simple_tag(takes_context=True)
def sort_link(context, field, label):
    """Column header that toggles ascending/descending ordering."""
    request = context["request"]
    current = request.GET.get("sort", "")
    new_value = f"-{field}" if current == field else field
    arrow = ""
    if current == field:
        arrow = " ▲"
    elif current == f"-{field}":
        arrow = " ▼"
    query = request.GET.copy()
    query["sort"] = new_value
    query.pop("page", None)
    return format_html('<a class="sort" href="?{}">{}{}</a>', query.urlencode(), label, arrow)


@register.filter
def money(value, places: int = 2):
    """Format a decimal for display with thousands separators."""
    if value in (None, ""):
        return "0.00"
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return value
    return f"{amount:,.{int(places)}f}"


@register.filter
def status_badge(value):
    return STATUS_CLASSES.get(value, "badge-default")


@register.filter
def currency_symbol(code):
    return {"USD": "$", "TRY": "₺"}.get(code, code)


@register.simple_tag
def order_status_label(status):
    return dict(OrderStatus.choices).get(status, status)


@register.filter
def get_item(mapping, key):
    if hasattr(mapping, "get"):
        return mapping.get(key)
    return None


@register.simple_tag
def brand_color():
    from django.conf import settings

    return settings.BRAND_COLOR


@register.simple_tag
def icon(name, size=18, css_class="icon"):
    """Render one of the inline Phosphor duotone icons."""
    body = ICONS.get(name)
    if body is None:
        return ""
    return mark_safe(
        f'<svg class="{css_class}" width="{size}" height="{size}" viewBox="0 0 256 256" '
        f'fill="currentColor" aria-hidden="true" focusable="false">{body}</svg>'
    )


@register.simple_tag
def asset(path):
    """Static URL carrying the file's modification time as a cache buster.

    The development server serves static files straight from ``static/``, so a
    browser that cached an earlier stylesheet keeps using it after a pull and
    the page renders half-styled. Stamping the URL sidesteps that entirely.
    """
    url = static_url(path)
    try:
        located = finders.find(path)
        if located:
            return f"{url}?v={int(os.path.getmtime(located))}"
    except Exception:  # pragma: no cover - never let an asset break a page
        pass
    return url


@register.filter
def multiply(value, factor):
    """Multiply two decimals in a template - `widthratio` truncates to integers."""
    try:
        return (Decimal(str(value or 0)) * Decimal(str(factor or 0))).quantize(
            Decimal("0.01")
        )
    except (InvalidOperation, ValueError, TypeError):
        return ""
