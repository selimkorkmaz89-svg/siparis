from django.contrib import admin

from dealers.models import Dealer, DomainDealerMap


@admin.register(Dealer)
class DealerAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "tax_no", "city", "contact_person", "is_active")
    search_fields = ("name", "code", "tax_no", "city")
    list_filter = ("is_active", "city")


@admin.register(DomainDealerMap)
class DomainDealerMapAdmin(admin.ModelAdmin):
    list_display = ("email_domain", "dealer", "is_active")
    search_fields = ("email_domain", "dealer__name")
    list_filter = ("is_active",)
