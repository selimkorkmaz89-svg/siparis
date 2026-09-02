from django.urls import path

from reports import views

app_name = "reports"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("finance/", views.finance_report, name="finance"),
]
