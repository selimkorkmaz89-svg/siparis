from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.constants import OrderStatus, PaymentStatus, Role, UserStatus
from orders.models import Order
from payments import services as fx
from payments.models import Payment

User = get_user_model()


@login_required
def home(request):
    """Role aware landing page."""
    user = request.user
    orders = Order.objects.visible_to(user)
    rate = fx.get_rate()
    context = {
        "exchange_rate": rate.usd_try_rate if rate else None,
        "rate_note": _rate_note(rate),
        # The actual source (TCMB / MANUAL / a demo seed) shown as a small
        # badge on the KPI card, rather than assuming TCMB regardless.
        "rate_source": rate.source if rate else None,
        "recent_orders": orders.exclude(status=OrderStatus.DRAFT)
        .select_related("dealer")[:8],
        "today": timezone.localdate(),
        "links": _kpi_links(user),
        "stats": _stats_for(user, orders),
    }
    return render(request, "core/home.html", context)


def _rate_note(rate):
    """Caption under the rate KPI: which day it is from, or why it is missing."""
    effective = fx.effective_rate_date()
    if rate is None:
        return _("No rate recorded yet - run the sync")
    if rate.rate_date == effective:
        return rate.rate_date.strftime("%d.%m.%Y")
    return _("%(date)s · most recent business day") % {
        "date": rate.rate_date.strftime("%d.%m.%Y")
    }


def _kpi_links(user):
    """Only link a KPI to a screen the role is allowed to open."""
    links = {"orders": reverse("orders:list")}
    if user.role in (Role.ADMIN, Role.FINANCE):
        links["pending_payment"] = reverse("payments:pending")
        links["rates"] = reverse("payments:exchange_rates") if user.is_admin else None
    if user.role in (Role.ADMIN, Role.LOGISTICS):
        links["pending_shipment"] = reverse("logistics:pending")
    if user.is_admin:
        links["pending_users"] = reverse("accounts:pending_users")
    if user.is_dealer_user:
        links["drafts"] = reverse("orders:drafts")
    return links


def _stats_for(user, orders):
    stats = {
        "total_orders": orders.exclude(status=OrderStatus.DRAFT).count(),
        "pending_payment": orders.filter(status=OrderStatus.PENDING_PAYMENT).count(),
        "paid": orders.filter(status=OrderStatus.PAID).count(),
        "shipped": orders.filter(status=OrderStatus.SHIPPED).count(),
        "total_amount": orders.active().aggregate(total=Sum("total_amount_usd"))["total"],
    }
    if user.role in (Role.ADMIN, Role.FINANCE):
        stats["pending_amount"] = orders.filter(
            status=OrderStatus.PENDING_PAYMENT
        ).aggregate(total=Sum("total_amount_usd"))["total"]
        stats["collected"] = Payment.objects.filter(
            status=PaymentStatus.APPROVED
        ).aggregate(total=Sum("amount_usd"))["total"]
    if user.role == Role.ADMIN:
        stats["pending_users"] = User.objects.filter(
            status=UserStatus.PENDING_APPROVAL
        ).count()
    if user.role == Role.DEALER:
        stats["my_drafts"] = orders.filter(
            status=OrderStatus.DRAFT, created_by=user
        ).count()
    return stats


def health(request):
    from django.http import JsonResponse

    return JsonResponse({"status": "ok"})
