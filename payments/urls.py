from django.urls import path

from payments import views

app_name = "payments"

urlpatterns = [
    path("pending/", views.pending_approvals, name="pending"),
    path("history/", views.payment_history, name="history"),
    path("order/<int:order_id>/declare/", views.payment_declare, name="declare"),
    path("order/<int:order_id>/approve/", views.payment_approve, name="approve"),
    path("order/<int:order_id>/reject/", views.payment_reject, name="reject"),
    path("exchange-rates/", views.exchange_rates, name="exchange_rates"),
]
