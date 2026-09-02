from django.urls import path

from integrations import views

app_name = "integrations"

urlpatterns = [
    path("mikro/", views.settings_view, name="settings"),
    path("mikro/vergi-eslemesi/<int:pk>/sil/", views.vat_mapping_delete, name="vat_mapping_delete"),
    path("mikro/siparisler/<int:order_id>/yeniden-dene/", views.retry_sync, name="retry_sync"),
    # Connector (token authenticated, not a browser session).
    path("mikro/api/ping/", views.ping, name="mikro_ping"),
    path("mikro/api/bekleyen/", views.pending_orders, name="mikro_pending"),
    path("mikro/api/siparisler/<int:order_id>/tamamlandi/", views.mark_synced, name="mikro_mark_synced"),
    path("mikro/api/siparisler/<int:order_id>/hata/", views.mark_failed, name="mikro_mark_failed"),
]
