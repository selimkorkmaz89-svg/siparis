"""Template helpers shared by the list screens."""
from decimal import Decimal, InvalidOperation

from django import template
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

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
