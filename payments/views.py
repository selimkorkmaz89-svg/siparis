

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from core.constants import OrderStatus, PaymentStatus, Role
from core.decorators import role_required
from core.exports import excel_response
from core.filters import ListFilter
from orders import services as order_services
from orders.forms import RejectionForm
from orders.models import Order
from payments import services as fx
from payments.forms import ExchangeRateForm, PaymentApprovalForm, PaymentDeclarationForm
from payments.models import ExchangeRate, Payment
from payments.tasks import fetch_daily_exchange_rate


@role_required(Role.FINANCE)
def pending_approvals(request):
    """Finance work list: orders sitting in PENDING_PAYMENT."""
    queryset = (
        Order.objects.filter(status=OrderStatus.PENDING_PAYMENT)
        .select_related("dealer", "created_by")
        .prefetch_related("payments")
    )
    list_filter = ListFilter(
        request,
        search_fields=("order_no", "dealer__name", "items__product_code",
                       "items__product_name"),
        ordering_map={"order_no": "order_no", "date": "submitted_at",
                      "dealer": "dealer__name", "total": "total_amount_usd"},
        default_ordering="submitted_at",
    )
    queryset = list_filter.apply(queryset).distinct()
    if request.GET.get("export") == "excel":
        return excel_response(
            "pending-approvals",
            str(_("Orders awaiting approval")),
            [_("Order number"), _("Dealer"), _("Submitted at"), _("Grand total (USD)")],
            [(o.order_no, o.dealer.name, o.submitted_at, o.total_amount_usd)
             for o in queryset],
        )
    rate = fx.current_rate_value()
    return render(
        request,
        "payments/pending_approvals.html",
        {
            "orders": queryset,
            "exchange_rate": rate,
            "totals": queryset.aggregate(total_usd=Sum("total_amount_usd"), count=Count("id")),
            **list_filter.as_context(),
        },
    )


@login_required
def payment_declare(request, order_id):
    """Record a payment against an order (dealer or finance)."""
    order = get_object_or_404(Order.objects.visible_to(request.user), pk=order_id)
    if order.status != OrderStatus.PENDING_PAYMENT:
        messages.error(request, _("A payment can only be recorded for orders awaiting approval."))
        return redirect("orders:detail", pk=order.pk)
    form = PaymentDeclarationForm(request.POST or None, request.FILES or None)
    rate = fx.current_rate_value()
    if request.method == "POST" and form.is_valid():
        payment = form.save(commit=False)
        payment.order = order
        payment.declared_by = request.user
        payment.exchange_rate = rate
        if rate:
            payment.amount_usd = fx.try_to_usd(payment.amount_try, rate)
        payment.save()
        messages.success(request, _("The payment record has been saved for finance to review."))
        return redirect("orders:detail", pk=order.pk)
    return render(
        request,
        "payments/payment_form.html",
        {
            "form": form,
            "order": order,
            "exchange_rate": rate,
            "expected_try": fx.usd_to_try(order.total_amount_usd, rate) if rate else None,
        },
    )


@role_required(Role.FINANCE)
def payment_approve(request, order_id):
    """Finance approves the payment; the order moves to PAID."""
    order = get_object_or_404(Order, pk=order_id)
    payment = (
        order.payments.filter(status=PaymentStatus.PENDING).order_by("-created_at").first()
    )
    rate = fx.current_rate_value()
    warning = None
    if payment is not None:
        warning = order_services.payment_mismatch(order, payment.amount_try, rate)
    form = PaymentApprovalForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if payment is None:
            messages.error(
                request, _("Record the payment details before approving the order.")
            )
            return redirect("payments:declare", order_id=order.pk)
        try:
            order_services.approve_payment(
                order, payment, request.user, form.cleaned_data.get("note", "")
            )
            messages.success(
                request,
                _("Payment approved. Order %(no)s is now ready for shipment.")
                % {"no": order.order_no},
            )
        except order_services.WorkflowError as exc:
            messages.error(request, str(exc))
        return redirect("orders:detail", pk=order.pk)
    return render(
        request,
        "payments/payment_approve.html",
        {
            "order": order,
            "payment": payment,
            "form": form,
            "warning": warning,
            "exchange_rate": rate,
            "expected_try": fx.usd_to_try(order.total_amount_usd, rate) if rate else None,
        },
    )


@role_required(Role.FINANCE)
@require_POST
def payment_reject(request, order_id):
    """Finance rejects the payment; the order returns to DRAFT."""
    order = get_object_or_404(Order, pk=order_id)
    form = RejectionForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("A rejection reason is required."))
        return redirect("orders:detail", pk=order.pk)
    payment = (
        order.payments.filter(status=PaymentStatus.PENDING).order_by("-created_at").first()
    )
    try:
        order_services.reject_payment(
            order, request.user, form.cleaned_data["reason"], payment=payment
        )
        messages.warning(request, _("The order was rejected and returned to the dealer."))
    except order_services.WorkflowError as exc:
        messages.error(request, str(exc))
    return redirect("orders:detail", pk=order.pk)


@login_required
def payment_history(request):
    queryset = Payment.objects.select_related(
        "order", "order__dealer", "declared_by", "approved_by"
    )
    if not request.user.can_see_all_dealers:
        queryset = queryset.filter(order__dealer=request.user.dealer)
    status = request.GET.get("status") or ""
    if status:
        queryset = queryset.filter(status=status)
    list_filter = ListFilter(
        request,
        search_fields=("reference_no", "order__order_no", "order__dealer__name"),
        date_field="payment_date",
        ordering_map={
            "date": "payment_date", "amount": "amount_try", "status": "status",
            "order_no": "order__order_no", "dealer": "order__dealer__name",
        },
        default_ordering="-payment_date",
    )
    queryset = list_filter.apply(queryset)
    if request.GET.get("export") == "excel":
        return excel_response(
            "payments",
            str(_("Payment history")),
            [_("Payment date"), _("Order number"), _("Dealer"), _("Amount (TRY)"),
             _("Exchange rate used"), _("Amount (USD)"), _("Bank reference / receipt no"),
             _("Status"), _("Approved by")],
            [
                (p.payment_date, p.order.order_no or "-", p.order.dealer.name,
                 p.amount_try, p.exchange_rate, p.amount_usd, p.reference_no,
                 p.get_status_display(), str(p.approved_by) if p.approved_by else "")
                for p in queryset
            ],
        )
    totals = queryset.filter(status=PaymentStatus.APPROVED).aggregate(
        total_try=Sum("amount_try"), total_usd=Sum("amount_usd"), count=Count("id")
    )
    page = Paginator(queryset, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "payments/payment_history.html",
        {
            "page_obj": page,
            "payments": page.object_list,
            "statuses": PaymentStatus.choices,
            "selected_status": status,
            "totals": totals,
            **list_filter.as_context(),
        },
    )


@role_required(Role.ADMIN)
def exchange_rates(request):
    """System settings screen: rate history and a manual sync trigger."""
    rates = ExchangeRate.objects.all()[:60]
    form = ExchangeRateForm(request.POST or None)
    if request.method == "POST" and "manual" in request.POST and form.is_valid():
        ExchangeRate.objects.update_or_create(
            rate_date=form.cleaned_data["rate_date"],
            defaults={
                "usd_try_rate": form.cleaned_data["usd_try_rate"],
                "source": "MANUAL",
            },
        )
        messages.success(request, _("The exchange rate has been saved."))
        return redirect("payments:exchange_rates")
    if request.method == "POST" and "sync" in request.POST:
        try:
            result = fetch_daily_exchange_rate.apply().get()
        except Exception:  # Celery broker unavailable: run inline instead
            rate = fx.fetch_tcmb_rate()
            result = str(rate.usd_try_rate) if rate else None
        if result:
            messages.success(
                request, _("Today's rate has been fetched: %(rate)s") % {"rate": result}
            )
        else:
            messages.warning(
                request,
                _("No rate could be fetched. TCMB does not publish on weekends and holidays."),
            )
        return redirect("payments:exchange_rates")
    current = fx.get_rate()
    return render(
        request,
        "payments/exchange_rates.html",
        {
            "rates": rates,
            "form": form,
            "current": current,
            "effective_date": fx.effective_rate_date(),
        },
    )
