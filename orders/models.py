from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_fsm import FSMField, transition

from core.constants import OrderStatus, ShipmentStatus
from core.models import TimeStampedModel

TWO_PLACES = Decimal("0.01")


class OrderNumberSequence(models.Model):
    """Per-year counter for official order numbers.

    Rows are locked with ``SELECT FOR UPDATE`` while a number is issued so two
    concurrent submissions can never receive the same value.
    """

    year = models.PositiveIntegerField(_("year"), primary_key=True)
    last_number = models.PositiveIntegerField(_("last issued number"), default=0)

    class Meta:
        verbose_name = _("order number sequence")
        verbose_name_plural = _("order number sequences")

    def __str__(self) -> str:
        return f"{self.year}: {self.last_number}"

    @classmethod
    def next_order_no(cls, year: int | None = None) -> str:
        year = year or timezone.localdate().year
        with transaction.atomic():
            sequence, _created = cls.objects.select_for_update().get_or_create(year=year)
            sequence.last_number += 1
            sequence.save(update_fields=["last_number"])
            counter = sequence.last_number
        return f"{settings.ORDER_NO_PREFIX}-{year}-{counter:06d}"


class OrderQuerySet(models.QuerySet):
    def visible_to(self, user):
        if user.can_see_all_dealers:
            return self
        return self.filter(dealer=user.dealer)

    def active(self):
        """Orders that are live in the workflow (drafts and cancellations are not)."""
        return self.filter(
            status__in=[OrderStatus.PENDING_PAYMENT, OrderStatus.PAID, OrderStatus.SHIPPED]
        )


class Order(TimeStampedModel):
    """A dealer order. Totals are stored in USD and frozen per line item."""

    order_no = models.CharField(
        _("order number"), max_length=32, unique=True, null=True, blank=True
    )
    dealer = models.ForeignKey(
        "dealers.Dealer",
        verbose_name=_("dealer"),
        on_delete=models.PROTECT,
        related_name="orders",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("created by"),
        on_delete=models.PROTECT,
        related_name="created_orders",
    )
    status = FSMField(
        _("status"),
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.DRAFT,
        protected=True,
        db_index=True,
    )
    subtotal_usd = models.DecimalField(
        _("subtotal (USD)"), max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    vat_total_usd = models.DecimalField(
        _("VAT total (USD)"), max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    total_amount_usd = models.DecimalField(
        _("grand total (USD)"), max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    shipment_status = models.CharField(
        _("shipment status"),
        max_length=20,
        choices=ShipmentStatus.choices,
        default=ShipmentStatus.NOT_SHIPPED,
    )
    shipped_at = models.DateTimeField(_("shipped at"), null=True, blank=True)
    shipped_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("shipped by"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shipped_orders",
    )
    tracking_no = models.CharField(_("tracking number"), max_length=120, blank=True)
    carrier = models.CharField(_("carrier"), max_length=120, blank=True)
    submitted_at = models.DateTimeField(_("submitted at"), null=True, blank=True)
    paid_at = models.DateTimeField(_("paid at"), null=True, blank=True)
    note = models.TextField(_("dealer note"), blank=True)

    objects = OrderQuerySet.as_manager()

    class Meta:
        verbose_name = _("order")
        verbose_name_plural = _("orders")
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["dealer", "status"])]

    def __str__(self) -> str:
        return self.reference

    def refresh_from_db(self, *args, **kwargs):
        # ``status`` is a protected FSM field, so the descriptor refuses a plain
        # assignment once a value is cached. Dropping the cached value lets the
        # reload behave like an initial read while direct writes stay blocked.
        self.__dict__.pop("status", None)
        super().refresh_from_db(*args, **kwargs)

    @property
    def reference(self) -> str:
        """Official number once issued, otherwise the internal draft reference."""
        if self.order_no:
            return self.order_no
        return _("Draft #%(pk)s") % {"pk": self.pk}

    @property
    def is_editable(self) -> bool:
        return self.status == OrderStatus.DRAFT

    @property
    def is_shipped(self) -> bool:
        return self.shipment_status == ShipmentStatus.SHIPPED

    def recalculate(self, save: bool = True) -> None:
        subtotal = Decimal("0.00")
        vat_total = Decimal("0.00")
        for item in self.items.all():
            subtotal += item.line_total_usd
            vat_total += item.vat_amount_usd
        self.subtotal_usd = subtotal.quantize(TWO_PLACES)
        self.vat_total_usd = vat_total.quantize(TWO_PLACES)
        self.total_amount_usd = (self.subtotal_usd + self.vat_total_usd).quantize(TWO_PLACES)
        if save:
            self.save(
                update_fields=["subtotal_usd", "vat_total_usd", "total_amount_usd", "updated_at"]
            )

    # -- state machine ----------------------------------------------------
    @transition(field=status, source=OrderStatus.DRAFT, target=OrderStatus.PENDING_PAYMENT)
    def submit(self, user=None, note: str = ""):
        """Send the order to finance and issue a fresh official order number."""
        self.order_no = OrderNumberSequence.next_order_no()
        self.submitted_at = timezone.now()

    @transition(
        field=status, source=OrderStatus.PENDING_PAYMENT, target=OrderStatus.PAID
    )
    def mark_paid(self, user=None, note: str = ""):
        self.paid_at = timezone.now()

    @transition(
        field=status, source=OrderStatus.PENDING_PAYMENT, target=OrderStatus.DRAFT
    )
    def reject_payment(self, user=None, note: str = ""):
        """Finance rejected the payment; the dealer may edit and resubmit.

        The official number is cleared: resubmission issues a new one and the
        old value stays visible through ``OrderStatusHistory``.
        """
        self.order_no = None
        self.submitted_at = None

    @transition(field=status, source=OrderStatus.PAID, target=OrderStatus.SHIPPED)
    def mark_shipped(self, user=None, note: str = ""):
        self.shipment_status = ShipmentStatus.SHIPPED
        self.shipped_at = timezone.now()
        self.shipped_by = user

    @transition(
        field=status,
        source=[OrderStatus.DRAFT, OrderStatus.PENDING_PAYMENT],
        target=OrderStatus.CANCELLED,
    )
    def cancel(self, user=None, note: str = ""):
        pass


class OrderItem(models.Model):
    """Order line. Price and VAT rate are copied here and never change again."""

    order = models.ForeignKey(
        Order, verbose_name=_("order"), on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey(
        "catalog.Product",
        verbose_name=_("product"),
        on_delete=models.PROTECT,
        related_name="order_items",
    )
    product_code = models.CharField(_("product code"), max_length=64)
    product_name = models.CharField(_("product name"), max_length=255)
    brand = models.CharField(_("brand"), max_length=120, blank=True)
    quantity = models.PositiveIntegerField(
        _("quantity"), validators=[MinValueValidator(1)]
    )
    unit_price_usd = models.DecimalField(
        _("unit price (USD)"), max_digits=12, decimal_places=2
    )
    vat_rate = models.DecimalField(_("VAT rate (%)"), max_digits=5, decimal_places=2)
    line_total_usd = models.DecimalField(
        _("line total (USD)"), max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    vat_amount_usd = models.DecimalField(
        _("VAT amount (USD)"), max_digits=14, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        verbose_name = _("order item")
        verbose_name_plural = _("order items")
        ordering = ("id",)

    def __str__(self) -> str:
        return f"{self.product_code} x {self.quantity}"

    def compute_totals(self) -> None:
        self.line_total_usd = (self.unit_price_usd * self.quantity).quantize(TWO_PLACES)
        self.vat_amount_usd = (
            self.line_total_usd * self.vat_rate / Decimal("100")
        ).quantize(TWO_PLACES)

    @property
    def total_with_vat_usd(self) -> Decimal:
        return self.line_total_usd + self.vat_amount_usd

    def save(self, *args, **kwargs):
        if self.product_id and not self.product_code:
            self.product_code = self.product.code
            self.product_name = self.product.name
            self.brand = self.product.brand
        self.compute_totals()
        super().save(*args, **kwargs)


class OrderStatusHistory(models.Model):
    """Audit trail of every status transition, including rejection reasons."""

    order = models.ForeignKey(
        Order, verbose_name=_("order"), on_delete=models.CASCADE, related_name="history"
    )
    from_status = models.CharField(
        _("from status"), max_length=20, choices=OrderStatus.choices, blank=True
    )
    to_status = models.CharField(
        _("to status"), max_length=20, choices=OrderStatus.choices
    )
    order_no_at_change = models.CharField(
        _("order number at the time"), max_length=32, blank=True
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("changed by"),
        on_delete=models.SET_NULL,
        null=True,
        related_name="order_status_changes",
    )
    changed_at = models.DateTimeField(_("changed at"), auto_now_add=True)
    note = models.TextField(_("note"), blank=True)

    class Meta:
        verbose_name = _("order status change")
        verbose_name_plural = _("order status history")
        ordering = ("-changed_at", "-id")

    def __str__(self) -> str:
        return f"{self.order_id}: {self.from_status} → {self.to_status}"
