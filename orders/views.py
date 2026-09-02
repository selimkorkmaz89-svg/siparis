

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from catalog.models import Product
from core.constants import OrderStatus, Role
from core.decorators import role_required
from core.exports import excel_response
from core.filters import ListFilter
from orders import services
from orders.forms import CancelOrderForm, RejectionForm
from orders.models import Order, OrderItem
from orders.pdf import PdfEngineUnavailable, render_order_html, render_order_pdf
from payments import services as fx


def _visible_orders(user):
    return (
        Order.objects.visible_to(user)
        .select_related("dealer", "created_by")
        .prefetch_related("items")
    )


def _order_or_404(request, pk) -> Order:
    return get_object_or_404(_visible_orders(request.user), pk=pk)


@login_required
def order_list(request):
    """Every role's order list; the queryset is already scoped by role."""
    queryset = _visible_orders(request.user).exclude(status=OrderStatus.DRAFT)
    status = request.GET.get("status") or ""
    dealer_id = request.GET.get("dealer") or ""
    if status:
        queryset = queryset.filter(status=status)
    if dealer_id and request.user.can_see_all_dealers:
        queryset = queryset.filter(dealer_id=dealer_id)
    list_filter = ListFilter(
        request,
        search_fields=("order_no", "items__product_code", "items__product_name",
                       "dealer__name"),
        ordering_map={
            "order_no": "order_no", "date": "created_at", "dealer": "dealer__name",
            "total": "total_amount_usd", "status": "status",
        },
    )
    queryset = list_filter.apply(queryset).distinct()
    if request.GET.get("export") == "excel":
        return _orders_excel(queryset)
    totals = queryset.aggregate(
        total_usd=Sum("total_amount_usd"),
        vat_usd=Sum("vat_total_usd"),
        average_usd=Avg("total_amount_usd"),
        count=Count("id"),
    )
    page = Paginator(queryset, 25).get_page(request.GET.get("page"))
    from dealers.models import Dealer

    return render(
        request,
        "orders/order_list.html",
        {
            "page_obj": page,
            "orders": page.object_list,
            "statuses": OrderStatus.choices,
            "selected_status": status,
            "selected_dealer": dealer_id,
            "dealers": Dealer.objects.filter(is_active=True)
            if request.user.can_see_all_dealers
            else [],
            "totals": totals,
            **list_filter.as_context(),
        },
    )


def _orders_excel(queryset):
    return excel_response(
        "orders",
        str(_("Orders")),
        [_("Order number"), _("Dealer"), _("Date"), _("Status"), _("Shipment status"),
         _("Subtotal (USD)"), _("VAT total (USD)"), _("Grand total (USD)"),
         _("Created by")],
        [
            (
                order.order_no or "-", order.dealer.name, order.created_at,
                order.get_status_display(), order.get_shipment_status_display(),
                order.subtotal_usd, order.vat_total_usd, order.total_amount_usd,
                str(order.created_by),
            )
            for order in queryset
        ],
    )


@login_required
def order_detail(request, pk):
    order = _order_or_404(request, pk)
    payments = order.payments.select_related("declared_by", "approved_by")
    rate = fx.current_rate_value()
    return render(
        request,
        "orders/order_detail.html",
        {
            "order": order,
            "items": order.items.all(),
            "history": order.history.select_related("changed_by"),
            "payments": payments,
            "rejection_form": RejectionForm(),
            "cancel_form": CancelOrderForm(),
            "exchange_rate": rate,
            "total_try": (order.total_amount_usd * rate) if rate else None,
        },
    )


@login_required
def order_pdf(request, pk):
    """Order form as a PDF, falling back to the printable preview."""
    order = _order_or_404(request, pk)
    try:
        pdf = render_order_pdf(order, request=request)
    except PdfEngineUnavailable:
        # WeasyPrint needs cairo/pango, which a Windows machine usually lacks.
        # The document itself is fine, so show it and let the browser print it.
        messages.warning(
            request,
            _(
                "PDF generation is unavailable on this machine (the WeasyPrint "
                "system libraries are missing), so the order form is shown as a "
                "printable page. Use your browser's print dialogue to save it as "
                "a PDF."
            ),
        )
        return redirect("orders:form_preview", pk=order.pk)
    filename = (order.order_no or f"draft-{order.pk}").lower()
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}.pdf"'
    return response


@login_required
def order_form_preview(request, pk):
    """The order form as a web page - the same document the PDF renders."""
    order = _order_or_404(request, pk)
    return HttpResponse(render_order_html(order, preview=True))


# -- dealer basket ---------------------------------------------------------
@role_required(Role.DEALER)
def order_create(request):
    """Search + basket screen. The draft is the dealer user's live basket."""
    draft = services.get_or_create_draft(request.user)
    brands = (
        Product.objects.filter(is_active=True)
        .exclude(brand="")
        .values_list("brand", flat=True)
        .distinct()
        .order_by("brand")
    )
    return render(
        request,
        "orders/order_create.html",
        {"order": draft, "items": draft.items.all(), "brands": brands},
    )


def _basket_payload(order: Order) -> dict:
    return {
        "items": [
            {
                "id": item.pk,
                "code": item.product_code,
                "name": item.product_name,
                "quantity": item.quantity,
                "unit_price": f"{item.unit_price_usd:.2f}",
                "vat_rate": f"{item.vat_rate:.2f}",
                "line_total": f"{item.line_total_usd:.2f}",
                "vat_amount": f"{item.vat_amount_usd:.2f}",
            }
            for item in order.items.all()
        ],
        "subtotal": f"{order.subtotal_usd:.2f}",
        "vat_total": f"{order.vat_total_usd:.2f}",
        "total": f"{order.total_amount_usd:.2f}",
        "count": order.items.count(),
    }


@role_required(Role.DEALER)
@require_POST
def basket_add(request):
    draft = services.get_or_create_draft(request.user)
    product = get_object_or_404(Product, pk=request.POST.get("product"), is_active=True)
    try:
        quantity = int(request.POST.get("quantity") or 1)
    except (TypeError, ValueError):
        quantity = 1
    try:
        services.add_item(draft, product, quantity)
    except services.WorkflowError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(_basket_payload(draft))


@role_required(Role.DEALER)
@require_POST
def basket_update(request, item_id):
    draft = services.get_or_create_draft(request.user)
    item = get_object_or_404(OrderItem, pk=item_id, order=draft)
    try:
        quantity = int(request.POST.get("quantity") or 0)
    except (TypeError, ValueError):
        quantity = 0
    try:
        services.set_item_quantity(draft, item, quantity)
    except services.WorkflowError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(_basket_payload(draft))


@role_required(Role.DEALER)
@require_POST
def basket_remove(request, item_id):
    draft = services.get_or_create_draft(request.user)
    item = get_object_or_404(OrderItem, pk=item_id, order=draft)
    services.remove_item(draft, item)
    return JsonResponse(_basket_payload(draft))


@role_required(Role.DEALER)
def order_review(request):
    """Summary/confirmation step shown before the order goes to finance."""
    draft = services.get_or_create_draft(request.user)
    if not draft.items.exists():
        messages.warning(request, _("Your basket is empty."))
        return redirect("orders:create")
    if request.method == "POST":
        draft.note = request.POST.get("note", "")
        draft.save(update_fields=["note", "updated_at"])
        try:
            services.submit_order(draft, request.user, note=draft.note)
        except services.WorkflowError as exc:
            messages.error(request, str(exc))
            return redirect("orders:create")
        messages.success(
            request,
            _("Your order has been submitted to finance. Order number: %(no)s")
            % {"no": draft.order_no},
        )
        return redirect("orders:detail", pk=draft.pk)
    return render(
        request, "orders/order_review.html", {"order": draft, "items": draft.items.all()}
    )


@role_required(Role.DEALER)
@require_POST
def order_reorder(request, pk):
    source = _order_or_404(request, pk)
    services.reorder(source, request.user)
    messages.success(
        request, _("The items were copied into a new draft. You can edit it before sending.")
    )
    return redirect("orders:create")


@login_required
@require_POST
def order_cancel(request, pk):
    order = _order_or_404(request, pk)
    if not (request.user.is_admin or order.created_by_id == request.user.pk):
        messages.error(request, _("You are not allowed to cancel this order."))
        return redirect("orders:detail", pk=order.pk)
    form = CancelOrderForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("A cancellation reason is required."))
        return redirect("orders:detail", pk=order.pk)
    try:
        services.cancel_order(order, request.user, form.cleaned_data["note"])
        messages.success(request, _("The order has been cancelled."))
    except services.WorkflowError as exc:
        messages.error(request, str(exc))
    return redirect("orders:detail", pk=order.pk)


@login_required
def my_drafts(request):
    """Dealer's own drafts, kept out of the active order list."""
    queryset = _visible_orders(request.user).filter(status=OrderStatus.DRAFT)
    if request.user.is_dealer_user:
        queryset = queryset.filter(created_by=request.user)
    return render(request, "orders/draft_list.html", {"orders": queryset})
