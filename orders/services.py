"""Order workflow services.

Every state change goes through this module so the audit trail and the
notifications are never forgotten by a caller.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from core.constants import OrderStatus, PaymentStatus
from notifications import services as notify
from orders.models import Order, OrderItem, OrderStatusHistory
from payments import services as fx


class WorkflowError(Exception):
    """Raised when a transition is not allowed for the current state."""


def _log(order: Order, from_status: str, to_status: str, user, note: str = "",
         order_no: str = "") -> OrderStatusHistory:
    return OrderStatusHistory.objects.create(
        order=order,
        from_status=from_status,
        to_status=to_status,
        order_no_at_change=order_no,
        changed_by=user,
        note=note,
    )


@transaction.atomic
def add_item(order: Order, product, quantity: int) -> OrderItem:
    """Add a product to a draft order, merging with an existing line."""
    if not order.is_editable:
        raise WorkflowError(_("This order can no longer be edited."))
    quantity = max(int(quantity), 1)
    item = order.items.filter(product=product).first()
    if item is None:
        item = OrderItem(
            order=order,
            product=product,
            product_code=product.code,
            product_name=product.name,
            brand=product.brand,
            quantity=quantity,
            # Price and VAT rate are frozen at the moment the line is created.
            unit_price_usd=product.price_for(order.dealer),
            vat_rate=product.vat_rate,
        )
    else:
        item.quantity += quantity
    item.save()
    order.recalculate()
    return item


@transaction.atomic
def set_item_quantity(order: Order, item: OrderItem, quantity: int) -> None:
    if not order.is_editable:
        raise WorkflowError(_("This order can no longer be edited."))
    if quantity <= 0:
        item.delete()
    else:
        item.quantity = quantity
        item.save()
    order.recalculate()


@transaction.atomic
def remove_item(order: Order, item: OrderItem) -> None:
    if not order.is_editable:
        raise WorkflowError(_("This order can no longer be edited."))
    item.delete()
    order.recalculate()


@transaction.atomic
def submit_order(order: Order, user, note: str = "") -> Order:
    """DRAFT → PENDING_PAYMENT: issue an order number and alert finance."""
    if order.status != OrderStatus.DRAFT:
        raise WorkflowError(_("Only draft orders can be submitted."))
    if not order.items.exists():
        raise WorkflowError(_("Add at least one product before submitting the order."))
    order.recalculate()
    previous = order.status
    order.submit(user=user, note=note)
    order.save()
    _log(order, previous, order.status, user, note, order_no=order.order_no or "")
    transaction.on_commit(lambda: notify.order_submitted(order))
    return order


@transaction.atomic
def approve_payment(order: Order, payment, user, note: str = "") -> Order:
    """PENDING_PAYMENT → PAID once finance confirms the declared payment."""
    if order.status != OrderStatus.PENDING_PAYMENT:
        raise WorkflowError(_("Only orders awaiting payment approval can be approved."))
    rate = fx.get_rate()
    payment.exchange_rate = payment.exchange_rate or (rate.usd_try_rate if rate else None)
    if payment.exchange_rate:
        payment.amount_usd = fx.try_to_usd(payment.amount_try, payment.exchange_rate)
    payment.status = PaymentStatus.APPROVED
    payment.approved_by = user
    payment.approved_at = timezone.now()
    payment.note = note or payment.note
    payment.save()
    previous = order.status
    order.mark_paid(user=user, note=note)
    order.save()
    _log(order, previous, order.status, user, note, order_no=order.order_no or "")
    transaction.on_commit(lambda: notify.payment_approved(order))
    return order


@transaction.atomic
def reject_payment(order: Order, user, reason: str, payment=None) -> Order:
    """PENDING_PAYMENT → DRAFT. The rejection reason is mandatory."""
    reason = (reason or "").strip()
    if not reason:
        raise WorkflowError(_("A rejection reason is required."))
    if order.status != OrderStatus.PENDING_PAYMENT:
        raise WorkflowError(_("Only orders awaiting payment approval can be rejected."))
    if payment is not None:
        payment.status = PaymentStatus.REJECTED
        payment.approved_by = user
        payment.approved_at = timezone.now()
        payment.note = reason
        payment.save()
    previous = order.status
    previous_no = order.order_no or ""
    order.reject_payment(user=user, note=reason)
    order.save()
    # The old number is kept in the history so the trail stays followable.
    _log(order, previous, order.status, user, reason, order_no=previous_no)
    transaction.on_commit(lambda: notify.payment_rejected(order, reason))
    return order


@transaction.atomic
def mark_shipped(order: Order, user, note: str = "", tracking_no: str = "",
                 carrier: str = "") -> Order:
    """PAID → SHIPPED. Finance approval is a hard precondition."""
    if order.status != OrderStatus.PAID:
        raise WorkflowError(
            _("An order can only be shipped after its payment has been approved.")
        )
    order.tracking_no = tracking_no or order.tracking_no
    order.carrier = carrier or order.carrier
    previous = order.status
    order.mark_shipped(user=user, note=note)
    order.save()
    _log(order, previous, order.status, user, note, order_no=order.order_no or "")
    transaction.on_commit(lambda: notify.order_shipped(order))
    return order


@transaction.atomic
def cancel_order(order: Order, user, note: str = "") -> Order:
    if order.status not in (OrderStatus.DRAFT, OrderStatus.PENDING_PAYMENT):
        raise WorkflowError(_("Only draft or pending orders can be cancelled."))
    previous = order.status
    order.cancel(user=user, note=note)
    order.save()
    _log(order, previous, order.status, user, note, order_no=order.order_no or "")
    return order


@transaction.atomic
def reorder(source: Order, user) -> Order:
    """Copy a previous order's basket into a fresh draft ("order again").

    Prices are re-read from the catalogue: the copy is a new order, so today's
    prices apply rather than the frozen ones.
    """
    draft = Order.objects.create(
        dealer=source.dealer,
        created_by=user,
        note=source.note,
    )
    for item in source.items.select_related("product"):
        if not item.product.is_active:
            continue
        OrderItem.objects.create(
            order=draft,
            product=item.product,
            product_code=item.product.code,
            product_name=item.product.name,
            brand=item.product.brand,
            quantity=item.quantity,
            unit_price_usd=item.product.price_for(draft.dealer),
            vat_rate=item.product.vat_rate,
        )
    draft.recalculate()
    return draft


def get_or_create_draft(user) -> Order:
    """The dealer user's working basket, created on demand."""
    draft = (
        Order.objects.filter(
            dealer=user.dealer, created_by=user, status=OrderStatus.DRAFT
        )
        .order_by("-created_at")
        .first()
    )
    if draft is None:
        draft = Order.objects.create(dealer=user.dealer, created_by=user)
    return draft


def payment_mismatch(order: Order, amount_try: Decimal, rate: Decimal | None) -> dict | None:
    """Compare a declared TRY payment with the order total.

    Returns a warning payload when the gap exceeds the configured tolerance;
    the caller shows it but never blocks approval on it.
    """
    if not rate:
        return {"reason": "no_rate"}
    converted = fx.try_to_usd(amount_try, rate)
    expected = order.total_amount_usd
    if not expected:
        return None
    tolerance = Decimal(str(settings.PAYMENT_MISMATCH_TOLERANCE))
    difference = converted - expected
    if abs(difference) > (expected * tolerance):
        return {
            "reason": "mismatch",
            "converted_usd": converted,
            "expected_usd": expected,
            "difference_usd": difference.quantize(Decimal("0.01")),
        }
    return None
