from django.contrib import admin

from notifications.models import Notification, NotificationLog, NotificationTemplate


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "event_type", "title", "is_read", "created_at")
    list_filter = ("event_type", "is_read")
    search_fields = ("user__email", "title")


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ("event_type", "language", "subject", "is_active")
    list_filter = ("event_type", "language", "is_active")


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ("event_type", "recipient", "channel", "status", "sent_at")
    list_filter = ("event_type", "channel", "status")
    search_fields = ("recipient__email",)
