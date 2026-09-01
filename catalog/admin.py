from django.contrib import admin

from catalog.models import DealerSpecialPrice, Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "brand", "base_price_usd", "vat_rate", "is_active")
    search_fields = ("code", "name", "brand")
    list_filter = ("brand", "is_active")


@admin.register(DealerSpecialPrice)
class DealerSpecialPriceAdmin(admin.ModelAdmin):
    list_display = ("dealer", "product", "price_usd")
    search_fields = ("dealer__name", "product__code", "product__name")
    list_filter = ("dealer",)
