from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.constants import PaymentStatus
from core.models import TimeStampedModel


class ExchangeRate(models.Model):
    """Daily USD/TRY rate published by TCMB (efektif satış / effective selling)."""

    rate_date = models.DateField(_("rate date"), primary_key=True)
    usd_try_rate = models.DecimalField(
        _("USD/TRY rate"),
        max_digits=12,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    rate_type = models.CharField(
        _("rate type"), max_length=40, default="efektif satış"
    )
    source = models.CharField(_("source"), max_length=40, default="TCMB")
    fetched_at = models.DateTimeField(_("fetched at"), auto_now=True)

    class Meta:
        verbose_name = _("exchange rate")
        verbose_name_plural = _("exchange rates")
        ordering = ("-rate_date",)

    def __str__(self) -> str:
        return f"{self.rate_date}: {self.usd_try_rate}"


class Payment(TimeStampedModel):
    """A payment declaration matched against an order by finance.

    Partial payments do not exist: an approved payment always settles the full
    order. An order can hold at most one ``APPROVED`` payment, while rejected
    declarations stay on record and can be replaced by a new attempt.
    """

    order = models.ForeignKey(
        "orders.Order",
        verbose_name=_("order"),
        on_delete=models.CASCADE,
        related_name="payments",
    )
    amount_try = models.DecimalField(
        _("amount (TRY)"),
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    exchange_rate = models.DecimalField(
        _("exchange rate used"), max_digits=12, decimal_places=4, null=True, blank=True
    )
    amount_usd = models.DecimalField(
        _("amount (USD)"), max_digits=14, decimal_places=2, null=True, blank=True
    )
    reference_no = models.CharField(_("bank reference / receipt no"), max_length=120)
    payment_date = models.DateField(_("payment date"))
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
    receipt = models.FileField(
        _("receipt file"), upload_to="receipts/", blank=True, null=True
    )
    declared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("declared by"),
        on_delete=models.PROTECT,
        related_name="declared_payments",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("approved by"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_payments",
    )
    approved_at = models.DateTimeField(_("approved at"), null=True, blank=True)
    note = models.TextField(_("note"), blank=True)

    class Meta:
        verbose_name = _("payment")
        verbose_name_plural = _("payments")
        ordering = ("-payment_date", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=["order"],
                condition=models.Q(status=PaymentStatus.APPROVED),
                name="one_approved_payment_per_order",
            )
        ]

    def __str__(self) -> str:
        return f"{self.order.reference} – {self.amount_try} TRY"

    @property
    def difference_usd(self) -> Decimal | None:
        """Signed gap between the converted payment and the order total."""
        if self.amount_usd is None:
            return None
        return (self.amount_usd - self.order.total_amount_usd).quantize(Decimal("0.01"))
