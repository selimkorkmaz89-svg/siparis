from django.contrib import admin

from integrations.models import MikroSettings, VatRateMapping


@admin.register(MikroSettings)
class MikroSettingsAdmin(admin.ModelAdmin):
    list_display = ("__str__", "enabled", "firma_kodu", "updated_at")


@admin.register(VatRateMapping)
class VatRateMappingAdmin(admin.ModelAdmin):
    list_display = ("vat_rate", "mikro_vergi_pntr")
    ordering = ("vat_rate",)
