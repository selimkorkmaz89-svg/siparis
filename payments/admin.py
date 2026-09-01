from django.contrib import admin

from payments.models import ExchangeRate, Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("order", "amount_try", "exchange_rate", "amount_usd", "status",
                    "payment_date", "approved_by")
    list_filter = ("status", "payment_date")
    search_fields = ("order__order_no", "reference_no", "order__dealer__name")


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ("rate_date", "usd_try_rate", "rate_type", "source", "fetched_at")
    list_filter = ("source",)
