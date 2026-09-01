from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.constants import NotificationChannel, NotificationEvent


class Notification(models.Model):
    """In-app notification shown in the bell panel. Always created."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    event_type = models.CharField(
        _("event"), max_length=40, choices=NotificationEvent.choices
    )
    title = models.CharField(_("title"), max_length=255)
    body = models.TextField(_("body"), blank=True)
    order = models.ForeignKey(
        "orders.Order",
        verbose_name=_("order"),
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    url = models.CharField(_("link"), max_length=255, blank=True)
    is_read = models.BooleanField(_("read"), default=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=["user", "is_read"])]

    def __str__(self) -> str:
        return f"{self.user_id}: {self.title}"


class NotificationTemplate(models.Model):
    """Editable subject/body templates per event, rendered with Django syntax."""

    event_type = models.CharField(
        _("event"), max_length=40, choices=NotificationEvent.choices
    )
    language = models.CharField(
        _("language"),
        max_length=5,
        choices=[("tr", _("Turkish")), ("en", _("English"))],
        default="tr",
    )
    subject = models.CharField(_("email subject"), max_length=255)
    email_body_template = models.TextField(_("email body"))
    inapp_body_template = models.TextField(_("in-app body"))
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("notification template")
        verbose_name_plural = _("notification templates")
        ordering = ("event_type", "language")
        constraints = [
            models.UniqueConstraint(
                fields=["event_type", "language"], name="unique_event_language_template"
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_event_type_display()} ({self.language})"


class NotificationLog(models.Model):
    """Delivery record for both channels, used for troubleshooting."""

    class Status(models.TextChoices):
        SENT = "SENT", _("Sent")
        FAILED = "FAILED", _("Failed")
        SKIPPED = "SKIPPED", _("Skipped")

    event_type = models.CharField(
        _("event"), max_length=40, choices=NotificationEvent.choices
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("recipient"),
        on_delete=models.CASCADE,
        related_name="notification_logs",
    )
    channel = models.CharField(
        _("channel"), max_length=10, choices=NotificationChannel.choices
    )
    order = models.ForeignKey(
        "orders.Order",
        verbose_name=_("order"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notification_logs",
    )
    sent_at = models.DateTimeField(_("sent at"), auto_now_add=True)
    status = models.CharField(_("status"), max_length=10, choices=Status.choices)
    detail = models.TextField(_("detail"), blank=True)

    class Meta:
        verbose_name = _("notification log")
        verbose_name_plural = _("notification logs")
        ordering = ("-sent_at", "-id")

    def __str__(self) -> str:
        return f"{self.event_type} → {self.recipient_id} ({self.channel})"
