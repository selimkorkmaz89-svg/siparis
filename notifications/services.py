"""Dispatch layer for in-app and email notifications.

In-app notifications are always written; the email copy is sent only when the
recipient has ``email_notifications_enabled`` turned on. Every attempt is
recorded in :class:`NotificationLog`.
"""
from __future__ import annotations

import logging
from typing import Iterable

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.template import Context, Template
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext as _

from core.constants import NotificationChannel, NotificationEvent, Role, UserStatus
from notifications.models import (
    EmailRoutingRule,
    EmailSettings,
    Notification,
    NotificationLog,
    NotificationTemplate,
)

logger = logging.getLogger(__name__)
User = get_user_model()

#: Fallback copy used when no :class:`NotificationTemplate` row exists.
DEFAULT_TEMPLATES: dict[str, dict[str, str]] = {
    NotificationEvent.ORDER_SUBMITTED: {
        "subject": "New order awaiting payment approval: {order}",
        "body": "Order {order} from {dealer} totalling {total} USD is waiting for "
        "your payment approval.",
    },
    NotificationEvent.PAYMENT_APPROVED: {
        "subject": "Payment approved: {order}",
        "body": "The payment for order {order} from {dealer} has been approved.",
    },
    NotificationEvent.PAYMENT_REJECTED: {
        "subject": "Payment rejected: {order}",
        "body": "The payment for order {order} from {dealer} was rejected. Reason: {note}",
    },
    NotificationEvent.ORDER_SHIPPED: {
        "subject": "Your order has been shipped: {order}",
        "body": "Order {order} has been shipped.",
    },
    NotificationEvent.USER_REGISTERED: {
        "subject": "New user awaiting approval: {user}",
        "body": "{user} signed up for dealer {dealer} and is waiting for approval.",
    },
    NotificationEvent.USER_APPROVED: {
        "subject": "Your account has been approved",
        "body": "Your account has been approved. You can now sign in.",
    },
}


def users_with_role(*roles: str) -> Iterable:
    return User.objects.filter(role__in=roles, status=UserStatus.APPROVED, is_active=True)


def finance_users():
    return users_with_role(Role.FINANCE, Role.ADMIN)


def logistics_users():
    return users_with_role(Role.LOGISTICS, Role.ADMIN)


def admin_users():
    return users_with_role(Role.ADMIN)


def dealer_users(dealer):
    if dealer is None:
        return User.objects.none()
    return User.objects.filter(
        dealer=dealer, status=UserStatus.APPROVED, is_active=True
    )


def _render(template_text: str, context: dict) -> str:
    try:
        return Template(template_text).render(Context(context))
    except Exception:  # pragma: no cover - a bad template must not block the flow
        logger.exception("Notification template could not be rendered")
        return template_text


def _resolve_copy(event_type: str, language: str, context: dict) -> tuple[str, str, str]:
    """Return ``(subject, email_body, inapp_body)`` for an event and language."""
    template = (
        NotificationTemplate.objects.filter(
            event_type=event_type, language=language, is_active=True
        ).first()
        or NotificationTemplate.objects.filter(
            event_type=event_type, is_active=True
        ).first()
    )
    if template is not None:
        return (
            _render(template.subject, context),
            _render(template.email_body_template, context),
            _render(template.inapp_body_template, context),
        )
    fallback = DEFAULT_TEMPLATES.get(event_type, {"subject": event_type, "body": ""})
    safe = {key: ("" if value is None else value) for key, value in context.items()}
    subject = fallback["subject"].format_map(_Default(safe))
    body = fallback["body"].format_map(_Default(safe))
    return subject, body, body


class _Default(dict):
    def __missing__(self, key):  # pragma: no cover - defensive
        return ""


def _email_routing_for(event_type: str) -> dict[str, bool] | None:
    """Per-role email toggle for ``event_type``, or ``None`` when the event
    isn't role-routed at all (email always allowed, e.g. an account notice)."""
    if event_type not in EmailRoutingRule.ROUTABLE_EVENTS:
        return None
    return {
        rule.role: rule.email_enabled
        for rule in EmailRoutingRule.objects.filter(event_type=event_type)
    }


def notify(recipients, event_type: str, context: dict, order=None, url: str = ""):
    """Create in-app notifications and send the optional email copies.

    The in-app notification always goes to every recipient passed in - who
    is a *candidate* recipient for an event is still decided by the event
    helpers below (finance_users, dealer_users, ...). Whether a candidate's
    email actually goes out is a second, independent check: their personal
    opt-out (``_send_email``) and, for order/payment events, whether their
    role is routed to receive email for this event at all (configured from
    System Settings; a role with no rule keeps the historical default of
    "yes").
    """
    recipients = [user for user in recipients if user is not None]
    if not recipients:
        return []
    email_routing = _email_routing_for(event_type)
    created = []
    for user in recipients:
        language = user.language or settings.LANGUAGE_CODE
        with translation.override(language):
            subject, email_body, inapp_body = _resolve_copy(event_type, language, context)
            notification = Notification.objects.create(
                user=user,
                event_type=event_type,
                title=subject,
                body=inapp_body,
                order=order,
                url=url,
            )
            created.append(notification)
            NotificationLog.objects.create(
                event_type=event_type,
                recipient=user,
                channel=NotificationChannel.INAPP,
                order=order,
                status=NotificationLog.Status.SENT,
            )
            if email_routing is not None and not email_routing.get(user.role, True):
                NotificationLog.objects.create(
                    event_type=event_type,
                    recipient=user,
                    channel=NotificationChannel.EMAIL,
                    order=order,
                    status=NotificationLog.Status.SKIPPED,
                    detail="Email routing turned off for this role",
                )
                continue
            _send_email(user, subject, email_body, event_type, order)
    return created


def send_test_email(recipient: str) -> None:
    """Send a one-off test message using the stored SMTP settings.

    Raises whatever the underlying send raises - the caller (the System
    Settings screen) reports the exact error to the administrator rather than
    swallowing it, since the whole point is to verify the configuration.
    """
    email_settings = EmailSettings.load()
    connection = email_settings.get_connection()
    from_email = (
        email_settings.from_email
        if (connection is not None and email_settings.from_email)
        else settings.DEFAULT_FROM_EMAIL
    )
    message = EmailMultiAlternatives(
        subject=_("Test email from %(system)s") % {"system": settings.COMPANY_NAME},
        body=_(
            "If you received this, the SMTP settings for %(system)s are working."
        )
        % {"system": settings.COMPANY_NAME},
        from_email=from_email,
        to=[recipient],
        connection=connection,
    )
    message.send(fail_silently=False)


def _send_email(user, subject: str, body: str, event_type: str, order) -> None:
    if not user.email_notifications_enabled:
        NotificationLog.objects.create(
            event_type=event_type,
            recipient=user,
            channel=NotificationChannel.EMAIL,
            order=order,
            status=NotificationLog.Status.SKIPPED,
            detail="Email notifications disabled by the user",
        )
        return
    if not user.email:
        return
    try:
        email_settings = EmailSettings.load()
        connection = email_settings.get_connection()
        from_email = (
            email_settings.from_email
            if (connection is not None and email_settings.from_email)
            else settings.DEFAULT_FROM_EMAIL
        )
        message = EmailMultiAlternatives(
            subject=subject,
            body=body,
            from_email=from_email,
            to=[user.email],
            connection=connection,
        )
        message.attach_alternative(
            f"<div style='font-family:Arial,sans-serif;font-size:14px'>"
            f"<p>{body}</p></div>",
            "text/html",
        )
        message.send(fail_silently=False)
        status, detail = NotificationLog.Status.SENT, ""
    except Exception as exc:  # pragma: no cover - depends on the SMTP server
        logger.warning("Notification email could not be sent: %s", exc)
        status, detail = NotificationLog.Status.FAILED, str(exc)[:500]
    NotificationLog.objects.create(
        event_type=event_type,
        recipient=user,
        channel=NotificationChannel.EMAIL,
        order=order,
        status=status,
        detail=detail,
    )


# -- event helpers ---------------------------------------------------------
def _order_context(order, **extra) -> dict:
    context = {
        "order": order.reference,
        "order_no": order.order_no or "",
        "dealer": order.dealer.name,
        "total": f"{order.total_amount_usd:,.2f}",
        "note": "",
    }
    context.update(extra)
    return context


def _order_url(order) -> str:
    return reverse("orders:detail", args=[order.pk])


def order_submitted(order):
    return notify(
        finance_users(), NotificationEvent.ORDER_SUBMITTED, _order_context(order),
        order=order, url=_order_url(order),
    )


def payment_approved(order):
    context = _order_context(order)
    url = _order_url(order)
    notify(dealer_users(order.dealer), NotificationEvent.PAYMENT_APPROVED, context,
           order=order, url=url)
    return notify(logistics_users(), NotificationEvent.PAYMENT_APPROVED, context,
                  order=order, url=url)


def payment_rejected(order, note: str):
    return notify(
        dealer_users(order.dealer),
        NotificationEvent.PAYMENT_REJECTED,
        _order_context(order, note=note),
        order=order,
        url=_order_url(order),
    )


def order_shipped(order):
    return notify(
        dealer_users(order.dealer),
        NotificationEvent.ORDER_SHIPPED,
        _order_context(order),
        order=order,
        url=_order_url(order),
    )


def user_registered(user):
    return notify(
        admin_users(),
        NotificationEvent.USER_REGISTERED,
        {
            "user": user.get_full_name() or user.email,
            "dealer": user.dealer.name if user.dealer else "",
        },
        url=reverse("accounts:pending_users"),
    )


def user_approved(user):
    return notify(
        [user],
        NotificationEvent.USER_APPROVED,
        {"user": user.get_full_name() or user.email},
        url=reverse("core:home"),
    )
