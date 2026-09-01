from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from accounts.models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("email", "first_name", "last_name", "role", "dealer", "status")
    list_filter = ("role", "status", "is_active", "dealer")
    search_fields = ("email", "first_name", "last_name", "dealer__name")
    ordering = ("email",)
    fieldsets = (
        (None, {"fields": ("email", "username", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "phone", "profile_photo")}),
        (_("Role and dealer"), {"fields": ("role", "dealer", "status", "rejection_reason")}),
        (_("Preferences"), {"fields": ("language", "email_notifications_enabled")}),
        (_("Permissions"), {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        (_("Important dates"), {"fields": ("last_login", "date_joined", "approved_at", "approved_by")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "username", "password1", "password2", "role", "dealer", "status"),
        }),
    )
