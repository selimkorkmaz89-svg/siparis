from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import TimeStampedModel


class Product(TimeStampedModel):
    """Catalogue item. All list prices are kept in USD."""

    code = models.CharField(_("product code"), max_length=64, unique=True)
    name = models.CharField(_("product name"), max_length=255)
    brand = models.CharField(_("brand"), max_length=120, blank=True, db_index=True)
    tests_per_pack = models.PositiveIntegerField(_("tests per pack"), default=0)
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
