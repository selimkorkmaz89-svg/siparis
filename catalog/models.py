from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.constants import Currency, ProductGroup
from core.models import TimeStampedModel


class DeviceModel(TimeStampedModel):
    """A physical device whose consumables a dealer's access can be limited to.

    Independent of ``Product.brand`` (free text used only for reporting
    breakdowns): this is the access-control axis. A dealer only sells
    consumables for some devices of a brand, not the whole brand, so
    ``Dealer.allowed_device_models`` restricts by device model rather than by
    brand.
    """

    name = models.CharField(_("device model"), max_length=120, unique=True)
    brand = models.CharField(_("brand"), max_length=120, blank=True, db_index=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("device model")
        verbose_name_plural = _("device models")
        ordering = ("brand", "name")

    def __str__(self) -> str:
        return f"{self.brand} {self.name}".strip() if self.brand else self.name


class ProductQuerySet(models.QuerySet):
    def visible_to_dealer(self, dealer):
        """Products a dealer may see and order.

        A product with no device model assigned is always visible — device
        model data is imported gradually, so an unclassified product must
        never disappear from anyone's catalogue. A dealer with no restrictions
        configured (the default) sees everything, so turning this feature on
        never starts as a lockout.
        """
        if dealer is None:
            return self
        allowed_ids = list(dealer.allowed_device_models.values_list("id", flat=True))
        if not allowed_ids:
            return self
        return self.filter(
            models.Q(device_model_id__isnull=True) | models.Q(device_model_id__in=allowed_ids)
        )


class Product(TimeStampedModel):
    """Catalogue item. Every calculation in the app (cart, orders, VAT,
    reports, the Mikro sync) reads ``base_price_usd`` - it is always in USD.

    A product priced by its supplier in another currency (``price_currency``
    + ``list_price``, e.g. Mikro's Swiss Franc items) still gets its
    ``base_price_usd`` kept in USD: it is recomputed from ``list_price``
    whenever a fresh exchange rate is fetched (see
    ``catalog.services.reprice_foreign_currency_products``), the same way a
    TRY payment is only ever converted through the live USD rate. USD-priced
    products simply have ``list_price`` blank - ``base_price_usd`` is already
    the authoritative number and nothing recomputes it.
    """

    code = models.CharField(_("product code"), max_length=64, unique=True)
    name = models.CharField(_("product name"), max_length=255)
    brand = models.CharField(_("brand"), max_length=120, blank=True, db_index=True)
    device_model = models.ForeignKey(
        DeviceModel,
        verbose_name=_("device model"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
        help_text=_("Used to restrict which dealers may order this product."),
    )
    product_group = models.CharField(
        _("product group"), max_length=12,
        choices=ProductGroup.choices, default=ProductGroup.CONSUMABLE,
    )
    tests_per_pack = models.PositiveIntegerField(_("tests per pack"), default=0)
    price_currency = models.CharField(
        _("list price currency"), max_length=3,
        choices=[(Currency.USD, Currency.USD.label), (Currency.CHF, Currency.CHF.label)],
        default=Currency.USD,
        help_text=_(
            "The currency the supplier actually quotes this product in. "
            "base_price_usd stays the authoritative USD figure either way."
        ),
    )
    list_price = models.DecimalField(
        _("list price (native currency)"), max_digits=12, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_(
            "Only used when the list price currency above isn't USD - the "
            "supplier's own price, before conversion."
        ),
    )
    base_price_usd = models.DecimalField(
        _("list price (USD)"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    vat_rate = models.DecimalField(
        _("VAT rate (%)"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("20.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    description = models.TextField(_("description"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    mikro_stok_kodu = models.CharField(
        _("Mikro stock code"), max_length=64, blank=True,
        help_text=_(
            "This product's stock (stok) code in Mikro. Required before an "
            "order containing it can be sent to Mikro."
        ),
    )

    objects = ProductQuerySet.as_manager()

    class Meta:
        verbose_name = _("product")
        verbose_name_plural = _("products")
        ordering = ("code",)

    def __str__(self) -> str:
        return f"{self.code} – {self.name}"

    def price_for(self, dealer) -> Decimal:
        """Dealer specific price when one exists, otherwise the list price."""
        if dealer is not None:
            special = self.special_prices.filter(dealer=dealer).first()
            if special is not None:
                return special.price_usd
        return self.base_price_usd


class DealerSpecialPrice(TimeStampedModel):
    """Dealer specific price that overrides ``Product.base_price_usd``."""

    dealer = models.ForeignKey(
        "dealers.Dealer",
        verbose_name=_("dealer"),
        on_delete=models.CASCADE,
        related_name="special_prices",
    )
    product = models.ForeignKey(
        Product,
        verbose_name=_("product"),
        on_delete=models.CASCADE,
        related_name="special_prices",
    )
    price_usd = models.DecimalField(
        _("special price (USD)"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta:
        verbose_name = _("dealer special price")
        verbose_name_plural = _("dealer special prices")
        ordering = ("dealer__name", "product__code")
        constraints = [
            models.UniqueConstraint(
                fields=["dealer", "product"], name="unique_dealer_product_price"
            )
        ]

    def __str__(self) -> str:
        return f"{self.dealer} / {self.product.code}: {self.price_usd} USD"
