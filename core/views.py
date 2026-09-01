from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.shortcuts import render
from django.utils import timezone

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
    context = {
        "exchange_rate": fx.current_rate_value(),
        "recent_orders": orders.exclude(status=OrderStatus.DRAFT)
        .select_related("dealer")[:8],
        "today": timezone.localdate(),
    }
    context["stats"] = _stats_for(user, orders)
    return render(request, "core/home.html", context)


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
