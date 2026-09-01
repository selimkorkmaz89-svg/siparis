from django.contrib import messages
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _

from core.constants import OrderStatus, Role
from core.decorators import role_required
from core.exports import excel_response
from core.filters import ListFilter
from orders import services as order_services
from orders.forms import ShipmentForm
from orders.models import Order


@role_required(Role.LOGISTICS)
def pending_shipments(request):
    """Orders whose payment finance has already approved."""
    queryset = (
        Order.objects.filter(status=OrderStatus.PAID)
        .select_related("dealer", "created_by")
        .prefetch_related("items")
    )
    list_filter = ListFilter(
        request,
        search_fields=("order_no", "dealer__name", "items__product_code",
                       "items__product_name"),
        ordering_map={"order_no": "order_no", "date": "paid_at",
                      "dealer": "dealer__name", "total": "total_amount_usd"},
        default_ordering="paid_at",
    )
    queryset = list_filter.apply(queryset).distinct()
    if request.GET.get("export") == "excel":
        return excel_response(
            "pending-shipments",
            str(_("Orders awaiting shipment")),
            [_("Order number"), _("Dealer"), _("Paid at"), _("Grand total (USD)")],
            [(o.order_no, o.dealer.name, o.paid_at, o.total_amount_usd) for o in queryset],
        )
    return render(
        request,
        "logistics/pending_shipments.html",
        {
            "orders": queryset,
            "totals": queryset.aggregate(total_usd=Sum("total_amount_usd"), count=Count("id")),
            **list_filter.as_context(),
        },
    )


@role_required(Role.LOGISTICS)
def mark_shipped(request, order_id):
    """Mark a paid order as shipped. Shipment is per order, never per line."""
    order = get_object_or_404(Order, pk=order_id)
    form = ShipmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            order_services.mark_shipped(
                order,
                request.user,
                note=form.cleaned_data.get("note", ""),
                tracking_no=form.cleaned_data.get("tracking_no", ""),
                carrier=form.cleaned_data.get("carrier", ""),
            )
            messages.success(
                request,
                _("Order %(no)s has been marked as shipped.") % {"no": order.order_no},
            )
            return redirect("logistics:pending")
        except order_services.WorkflowError as exc:
            messages.error(request, str(exc))
            return redirect("orders:detail", pk=order.pk)
    return render(
        request, "logistics/mark_shipped.html", {"order": order, "form": form}
    )
