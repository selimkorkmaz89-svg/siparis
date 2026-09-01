from django.urls import path

from logistics import views

app_name = "logistics"

urlpatterns = [
    path("pending/", views.pending_shipments, name="pending"),
    path("order/<int:order_id>/ship/", views.mark_shipped, name="mark_shipped"),
]
