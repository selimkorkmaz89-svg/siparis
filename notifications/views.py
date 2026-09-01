from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from notifications.models import Notification


@login_required
def notification_list(request):
    queryset = request.user.notifications.all()
    if request.GET.get("unread") == "1":
        queryset = queryset.filter(is_read=False)
    page = Paginator(queryset, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "notifications/notification_list.html",
        {"page_obj": page, "notifications": page.object_list},
    )


@login_required
def notification_feed(request):
    """JSON feed for the bell panel."""
    queryset = request.user.notifications.all()[:15]
    return JsonResponse(
        {
            "unread": request.user.notifications.filter(is_read=False).count(),
            "items": [
                {
                    "id": item.pk,
                    "title": item.title,
                    "body": item.body,
                    "url": item.url,
                    "is_read": item.is_read,
                    "created_at": item.created_at.strftime("%d.%m.%Y %H:%M"),
                }
                for item in queryset
            ],
        }
    )


@login_required
@require_POST
def mark_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.is_read = True
    notification.save(update_fields=["is_read"])
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True})
    return redirect(notification.url or "notifications:list")


@login_required
@require_POST
def mark_all_read(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True})
    messages.success(request, _("All notifications have been marked as read."))
    return redirect("notifications:list")


@login_required
@require_POST
def delete(request, pk):
    get_object_or_404(Notification, pk=pk, user=request.user).delete()
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True})
    return redirect("notifications:list")


@login_required
@require_POST
def bulk_delete(request):
    """Delete the selected notifications, or all of them."""
    ids = request.POST.getlist("ids")
    queryset = request.user.notifications.all()
    if request.POST.get("scope") == "read":
        queryset = queryset.filter(is_read=True)
    elif ids:
        queryset = queryset.filter(pk__in=ids)
    deleted, _detail = queryset.delete()
    messages.success(
        request, _("%(count)s notifications deleted.") % {"count": deleted}
    )
    return redirect("notifications:list")
