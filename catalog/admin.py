from django.contrib import admin

from catalog.models import DealerSpecialPrice, DeviceModel, Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "code", "name", "brand", "device_model", "product_group",
        "base_price_usd", "price_currency", "vat_rate", "is_active",
    )
    search_fields = ("code", "name", "brand", "mikro_stok_kodu")
    list_filter = ("brand", "device_model", "product_group", "price_currency", "is_active")


@admin.register(DeviceModel)
class DeviceModelAdmin(admin.ModelAdmin):
    list_display = ("name", "brand", "is_active")
    search_fields = ("name", "brand")
    list_filter = ("brand", "is_active")


@admin.register(DealerSpecialPrice)
class DealerSpecialPriceAdmin(admin.ModelAdmin):
    list_display = ("dealer", "product", "price_usd")
    search_fields = ("dealer__name", "product__code", "product__name")
    list_filter = ("dealer",)
