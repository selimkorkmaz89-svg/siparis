"""Reporting queries.

Everything is derived from existing order data; there is no cost or margin
information anywhere in this module by design.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db.models import Avg, Count, DecimalField, F, Sum
from django.db.models.functions import Coalesce, TruncMonth

from core.constants import OrderStatus, PaymentStatus
from orders.models import Order, OrderItem
from payments.models import Payment

#: Orders that count towards turnover (drafts and cancellations never do).
COUNTED_STATUSES = [OrderStatus.PENDING_PAYMENT, OrderStatus.PAID, OrderStatus.SHIPPED]

MONEY = DecimalField(max_digits=16, decimal_places=2)


def base_orders(date_from: dt.date | None, date_to: dt.date | None, dealer=None):
    queryset = Order.objects.filter(status__in=COUNTED_STATUSES)
    if dealer is not None:
        queryset = queryset.filter(dealer=dealer)
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)
    return queryset


def dealer_breakdown(orders):
    return list(
        orders.values("dealer__id", "dealer__name")
        .annotate(
            total=Coalesce(Sum("total_amount_usd"), Decimal("0"), output_field=MONEY),
            count=Count("id"),
            average=Coalesce(Avg("total_amount_usd"), Decimal("0"), output_field=MONEY),
        )
        .order_by("-total")
    )


def product_breakdown(orders, limit: int = 20):
    items = OrderItem.objects.filter(order__in=orders)
    return list(
        items.values("product_code", "product_name")
        .annotate(
            quantity=Coalesce(Sum("quantity"), 0),
            total=Coalesce(
                Sum(F("line_total_usd") + F("vat_amount_usd")), Decimal("0"),
                output_field=MONEY,
            ),
        )
        .order_by("-total")[:limit]
    )


def brand_breakdown(orders):
    items = OrderItem.objects.filter(order__in=orders).exclude(brand="")
    return list(
        items.values("brand")
        .annotate(
            quantity=Coalesce(Sum("quantity"), 0),
            total=Coalesce(
                Sum(F("line_total_usd") + F("vat_amount_usd")), Decimal("0"),
                output_field=MONEY,
            ),
        )
        .order_by("-total")
    )


def monthly_trend(orders):
    return list(
        orders.annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(
            total=Coalesce(Sum("total_amount_usd"), Decimal("0"), output_field=MONEY),
            count=Count("id"),
        )
        .order_by("month")
    )


def finance_summary(date_from, date_to, dealer=None):
    """Collections, outstanding balance and the rejection ratio."""
    payments = Payment.objects.all()
    if dealer is not None:
        payments = payments.filter(order__dealer=dealer)
    if date_from:
        payments = payments.filter(payment_date__gte=date_from)
    if date_to:
        payments = payments.filter(payment_date__lte=date_to)
    approved = payments.filter(status=PaymentStatus.APPROVED)
    collected = approved.aggregate(
        total_try=Coalesce(Sum("amount_try"), Decimal("0"), output_field=MONEY),
        total_usd=Coalesce(Sum("amount_usd"), Decimal("0"), output_field=MONEY),
        count=Count("id"),
    )
    pending_orders = Order.objects.filter(status=OrderStatus.PENDING_PAYMENT)
    if dealer is not None:
        pending_orders = pending_orders.filter(dealer=dealer)
    outstanding = pending_orders.aggregate(
        total_usd=Coalesce(Sum("total_amount_usd"), Decimal("0"), output_field=MONEY),
        count=Count("id"),
    )
    total_decisions = payments.exclude(status=PaymentStatus.PENDING).count()
    rejected = payments.filter(status=PaymentStatus.REJECTED).count()
    rejection_rate = (rejected / total_decisions * 100) if total_decisions else 0
    return {
        "collected": collected,
        "outstanding": outstanding,
        "rejected_count": rejected,
        "decision_count": total_decisions,
        "rejection_rate": round(rejection_rate, 1),
    }


def operations_summary(date_from, date_to, dealer=None):
    """Average hours spent in each stage: submitted → paid → shipped."""
    orders = base_orders(date_from, date_to, dealer).exclude(submitted_at=None)
    to_payment: list[float] = []
    to_shipment: list[float] = []
    end_to_end: list[float] = []
    for order in orders.only("submitted_at", "paid_at", "shipped_at"):
        if order.paid_at and order.submitted_at:
            to_payment.append((order.paid_at - order.submitted_at).total_seconds() / 3600)
        if order.shipped_at and order.paid_at:
            to_shipment.append((order.shipped_at - order.paid_at).total_seconds() / 3600)
        if order.shipped_at and order.submitted_at:
            end_to_end.append((order.shipped_at - order.submitted_at).total_seconds() / 3600)

    def average(values):
        return round(sum(values) / len(values), 1) if values else None

    return {
        "avg_hours_to_payment": average(to_payment),
        "avg_hours_to_shipment": average(to_shipment),
        "avg_hours_end_to_end": average(end_to_end),
        "sample_size": orders.count(),
    }


def totals(orders):
    return orders.aggregate(
        total=Coalesce(Sum("total_amount_usd"), Decimal("0"), output_field=MONEY),
        subtotal=Coalesce(Sum("subtotal_usd"), Decimal("0"), output_field=MONEY),
        vat=Coalesce(Sum("vat_total_usd"), Decimal("0"), output_field=MONEY),
        count=Count("id"),
        average=Coalesce(Avg("total_amount_usd"), Decimal("0"), output_field=MONEY),
    )
