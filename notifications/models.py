from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.constants import NotificationChannel, NotificationEvent, Role


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


class EmailRoutingRule(models.Model):
    """Whether a role receives an email when a given order/payment event
    fires - configurable from System Settings rather than hard-coded.

    The in-app notification is unaffected: it is always created for every
    recipient the event's recipient-resolution decides on (see
    ``notifications.services``). This rule only gates the email copy for
    the recipients who happen to hold ``role``. A missing row behaves as
    enabled, so an event added later (with no rows seeded for it yet)
    keeps emailing everyone until an administrator narrows it down.
    """

    #: Only order/payment lifecycle events are routed by role - an account
    #: notice like USER_APPROVED always goes to the one person it is about,
    #: regardless of their role, so it is not part of this matrix.
    ROUTABLE_EVENTS = (
        NotificationEvent.ORDER_SUBMITTED,
        NotificationEvent.PAYMENT_APPROVED,
        NotificationEvent.PAYMENT_REJECTED,
        NotificationEvent.ORDER_SHIPPED,
    )

    event_type = models.CharField(
        _("event"), max_length=40, choices=NotificationEvent.choices
    )
    role = models.CharField(_("role"), max_length=20, choices=Role.choices)
    email_enabled = models.BooleanField(_("send email"), default=True)

    class Meta:
        verbose_name = _("email routing rule")
        verbose_name_plural = _("email routing rules")
        constraints = [
            models.UniqueConstraint(
                fields=["event_type", "role"], name="unique_email_routing_rule"
            )
        ]

    def __str__(self) -> str:
        state = "on" if self.email_enabled else "off"
        return f"{self.event_type} → {self.role}: {state}"


class EmailSettings(models.Model):
    """Outgoing notification email configuration: SMTP or Microsoft Graph.

    A singleton row (always primary key 1), editable from System Settings so
    an administrator can change it without a deployment. While disabled or
    unconfigured, email sending falls back to Django's own EMAIL_* settings
    (the console backend in development).
    """

    class Provider(models.TextChoices):
        SMTP = "SMTP", _("SMTP")
        MS_GRAPH = "MS_GRAPH", _("Microsoft Graph (Office 365)")

    SINGLETON_ID = 1

    enabled = models.BooleanField(
        _("enabled"),
        default=False,
        help_text=_(
            "While off, notification emails use the fallback configured on the "
            "server (the console backend in development)."
        ),
    )
    provider = models.CharField(
        _("sending method"), max_length=10, choices=Provider.choices,
        default=Provider.SMTP,
        help_text=_(
            "Use Microsoft Graph instead of SMTP when the Office 365 tenant's "
            "Security Defaults policy blocks basic SMTP authentication."
        ),
    )
    host = models.CharField(_("SMTP host"), max_length=255, blank=True)
    port = models.PositiveIntegerField(_("SMTP port"), default=587)
    username = models.CharField(_("SMTP username"), max_length=255, blank=True)
    password = models.CharField(_("SMTP password"), max_length=255, blank=True)
    use_tls = models.BooleanField(_("use TLS"), default=True)
    use_ssl = models.BooleanField(_("use SSL"), default=False)
    graph_tenant_id = models.CharField(_("Azure tenant ID"), max_length=100, blank=True)
    graph_client_id = models.CharField(
        _("Azure application (client) ID"), max_length=100, blank=True,
    )
    graph_client_secret = models.CharField(
        _("Azure client secret"), max_length=255, blank=True,
        help_text=_(
            "The app registration's client secret value. Needs the Mail.Send "
            "application permission on Microsoft Graph, with admin consent granted."
        ),
    )
    from_email = models.CharField(
        _("from address"), max_length=255, blank=True,
        help_text=_(
            'Example: "BASH Medikal" <noreply@example.com>. With Microsoft Graph, '
            "this must be a real mailbox the app registration is allowed to send as."
        ),
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("updated by"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("email settings")
        verbose_name_plural = _("email settings")

    def __str__(self) -> str:
        return str(_("Email settings"))

    def save(self, *args, **kwargs):
        self.pk = self.SINGLETON_ID
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "EmailSettings":
        obj, _created = cls.objects.get_or_create(pk=cls.SINGLETON_ID)
        return obj

    def get_connection(self):
        """A connection built from these settings, or ``None`` for the
        project's default (settings.EMAIL_BACKEND, the console in dev)."""
        if not self.enabled:
            return None
        from django.core.mail import get_connection

        if self.provider == self.Provider.MS_GRAPH:
            if not (self.graph_tenant_id and self.graph_client_id
                    and self.graph_client_secret and self.from_email):
                return None
            return get_connection(
                backend="notifications.graph_backend.GraphEmailBackend",
                tenant_id=self.graph_tenant_id,
                client_id=self.graph_client_id,
                client_secret=self.graph_client_secret,
                sender_email=self.from_email,
            )
        if not self.host:
            return None
        return get_connection(
            backend="django.core.mail.backends.smtp.EmailBackend",
            host=self.host,
            port=self.port,
            username=self.username or None,
            password=self.password or None,
            use_tls=self.use_tls,
            use_ssl=self.use_ssl,
        )
