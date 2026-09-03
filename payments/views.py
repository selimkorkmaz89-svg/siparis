from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from core.constants import NotificationEvent, OrderStatus, PaymentStatus, Role
from core.decorators import role_required
from core.exports import excel_response
from core.filters import ListFilter
from notifications import services as notify
from notifications.forms import EmailSettingsForm, TestEmailForm
from notifications.models import EmailRoutingRule, EmailSettings
from orders import services as order_services
from orders.forms import RejectionForm
from orders.models import Order
from payments import services as fx
from payments.forms import ExchangeRateForm, PaymentApprovalForm, PaymentDeclarationForm
from payments.models import ExchangeRate, Payment


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
    current_rate = fx.get_rate()
    return render(
        request,
        "payments/pending_approvals.html",
        {
            "orders": queryset,
            "exchange_rate": current_rate.usd_try_rate if current_rate else None,
            "rate_source": current_rate.source if current_rate else None,
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
    rate = fx.current_rate_value()
    form = PaymentDeclarationForm(
        request.POST or None, request.FILES or None, order=order, rate=rate
    )
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
        rate, _created = ExchangeRate.objects.update_or_create(
            rate_date=form.cleaned_data["rate_date"],
            defaults={
                "usd_try_rate": form.cleaned_data["usd_try_rate"],
                "chf_try_rate": form.cleaned_data["chf_try_rate"],
                "source": "MANUAL",
            },
        )
        fx.reprice_chf_products(rate)
        messages.success(request, _("The exchange rate has been saved."))
        return redirect("payments:exchange_rates")
    if request.method == "POST" and "sync" in request.POST:
        # Fill in every missing recent day, not just today: before 15:30, or on
        # a weekend, today has no publication and only the backfill helps.
        try:
            stored = fx.backfill_rates(days=7)
        except Exception as exc:  # network problems must not break the screen
            messages.error(
                request,
                _("The rate could not be fetched: %(error)s") % {"error": exc},
            )
            return redirect("payments:exchange_rates")
        rate = fx.get_rate()
        if rate is None:
            messages.warning(
                request,
                _(
                    "No rate could be fetched. Check that www.tcmb.gov.tr is reachable "
                    "from the server; TCMB does not publish on weekends or holidays."
                ),
            )
        else:
            # The same TCMB request carries both legs, so surface CHF here
            # too - the sync button has no separate step for it.
            chf_display = f"{rate.chf_try_rate:.4f}" if rate.chf_try_rate else "—"
            if stored:
                messages.success(
                    request,
                    _("%(count)s new rate(s) fetched. In effect: %(date)s = %(rate)s (CHF: %(chf)s)")
                    % {
                        "count": stored,
                        "date": rate.rate_date.strftime("%d.%m.%Y"),
                        "rate": rate.usd_try_rate,
                        "chf": chf_display,
                    },
                )
            else:
                messages.info(
                    request,
                    _("Already up to date. In effect: %(date)s = %(rate)s (CHF: %(chf)s)")
                    % {
                        "date": rate.rate_date.strftime("%d.%m.%Y"),
                        "rate": rate.usd_try_rate,
                        "chf": chf_display,
                    },
                )
        return redirect("payments:exchange_rates")

    email_settings = EmailSettings.load()
    # Captured before any form binds to email_settings: ModelForm._post_clean()
    # writes cleaned values straight onto the instance during is_valid(), so
    # reading these back afterwards would already see the blank submitted
    # value rather than what was stored.
    stored_password = email_settings.password
    stored_graph_client_secret = email_settings.graph_client_secret
    email_form = EmailSettingsForm(instance=email_settings)
    test_email_form = TestEmailForm(initial={"recipient": request.user.email})
    if request.method == "POST" and "save_email_settings" in request.POST:
        email_form = EmailSettingsForm(request.POST, instance=email_settings)
        if email_form.is_valid():
            saved = email_form.save(commit=False)
            if not email_form.cleaned_data.get("password"):
                # Blank means "leave it alone" - the field never round-trips
                # the stored password back into the form for display.
                saved.password = stored_password
            if not email_form.cleaned_data.get("graph_client_secret"):
                saved.graph_client_secret = stored_graph_client_secret
            saved.updated_by = request.user
            saved.save()
            messages.success(request, _("Email settings saved."))
        else:
            messages.error(request, _("Please fix the errors below."))
        return redirect("payments:exchange_rates")
    if request.method == "POST" and "send_test_email" in request.POST:
        test_email_form = TestEmailForm(request.POST)
        if test_email_form.is_valid():
            try:
                notify.send_test_email(test_email_form.cleaned_data["recipient"])
            except Exception as exc:
                messages.error(
                    request, _("The test email could not be sent: %(error)s") % {"error": exc}
                )
            else:
                messages.success(
                    request,
                    _("Test email sent to %(recipient)s.")
                    % {"recipient": test_email_form.cleaned_data["recipient"]},
                )
        return redirect("payments:exchange_rates")
    if request.method == "POST" and "save_email_routing" in request.POST:
        EmailRoutingRule.objects.bulk_create(
            [
                EmailRoutingRule(
                    event_type=event_type, role=role,
                    email_enabled=f"route_{event_type}_{role}" in request.POST,
                )
                for event_type in EmailRoutingRule.ROUTABLE_EVENTS
                for role, _label in Role.choices
            ],
            update_conflicts=True,
            update_fields=["email_enabled"],
            unique_fields=["event_type", "role"],
        )
        messages.success(request, _("Email routing preferences saved."))
        return redirect("payments:exchange_rates")

    current = fx.get_rate()
    effective = fx.effective_rate_date()
    if current is None:
        status = _("No rate stored")
    elif current.rate_date == effective:
        status = _("Up to date")
    else:
        status = _("Using the most recent business day")
    return render(
        request,
        "payments/exchange_rates.html",
        {
            "rates": rates,
            "form": form,
            "current": current,
            "effective_date": effective,
            "rate_status": status,
            "rate_is_stale": current is None or current.rate_date != effective,
            "email_settings": email_settings,
            "email_form": email_form,
            "test_email_form": test_email_form,
            "email_routing_roles": [label for _value, label in Role.choices],
            "email_routing_rows": _email_routing_rows(),
        },
    )


def _email_routing_rows():
    """One row per routable event, one cell per role, for the System
    Settings email-routing grid - missing rows default to enabled, same as
    ``notifications.services.notify`` does at send time."""
    event_labels = dict(NotificationEvent.choices)
    enabled = {
        (rule.event_type, rule.role): rule.email_enabled
        for rule in EmailRoutingRule.objects.all()
    }
    return [
        {
            "event_type": event_type,
            "label": event_labels[event_type],
            "cells": [
                {
                    "field_name": f"route_{event_type}_{role}",
                    "checked": enabled.get((event_type, role), True),
                }
                for role, _label in Role.choices
            ],
        }
        for event_type in EmailRoutingRule.ROUTABLE_EVENTS
    ]
