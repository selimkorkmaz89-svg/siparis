from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
    path("django-admin/", admin.site.urls),
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
    path("dealers/", include("dealers.urls")),
    path("catalog/", include("catalog.urls")),
    path("orders/", include("orders.urls")),
    path("payments/", include("payments.urls")),
    path("logistics/", include("logistics.urls")),
    path("reports/", include("reports.urls")),
    path("notifications/", include("notifications.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
