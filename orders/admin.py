from django.contrib import admin

from orders.models import Order, OrderItem, OrderNumberSequence, OrderStatusHistory


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("line_total_usd", "vat_amount_usd")


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ("from_status", "to_status", "changed_by", "changed_at", "note",
                       "order_no_at_change")
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("reference", "dealer", "status", "total_amount_usd",
                    "shipment_status", "created_at")
    list_filter = ("status", "shipment_status", "dealer")
    search_fields = ("order_no", "dealer__name")
    readonly_fields = ("status", "subtotal_usd", "vat_total_usd", "total_amount_usd")
    inlines = [OrderItemInline, OrderStatusHistoryInline]


@admin.register(OrderNumberSequence)
class OrderNumberSequenceAdmin(admin.ModelAdmin):
    list_display = ("year", "last_number")
