def notifications(request):
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return {}
    queryset = user.notifications.all()[:10]
    return {
        "unread_notification_count": user.notifications.filter(is_read=False).count(),
        "recent_notifications": queryset,
    }
