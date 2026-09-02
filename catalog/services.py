"""Keeps foreign-currency list prices converted to the USD the app runs on."""
from __future__ import annotations

from decimal import Decimal

from core.constants import Currency
from catalog.models import Product

TWO_PLACES = Decimal("0.01")


def reprice_foreign_currency_products(currency: str, rate_to_usd: Decimal) -> int:
    """Recompute ``base_price_usd`` for every product priced in ``currency``.

    ``rate_to_usd`` is how many USD one unit of ``currency`` is worth (e.g.
    the CHF/USD cross-rate). Called after each fresh exchange-rate fetch so a
    Swiss-Franc list price never drifts far from the real TCMB rate, without
    the rest of the app ever needing to know a product wasn't quoted in USD.
    """
    if currency == Currency.USD or not rate_to_usd:
        return 0
    updated = 0
    products = Product.objects.filter(price_currency=currency, list_price__isnull=False)
    for product in products:
        new_price = (product.list_price * rate_to_usd).quantize(TWO_PLACES)
        if product.base_price_usd != new_price:
            product.base_price_usd = new_price
            product.save(update_fields=["base_price_usd"])
            updated += 1
    return updated
