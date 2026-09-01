from django.urls import path

from dealers import views

app_name = "dealers"

urlpatterns = [
    path("", views.dealer_list, name="list"),
    path("new/", views.dealer_form, name="create"),
    path("<int:pk>/edit/", views.dealer_form, name="edit"),
    path("history/", views.dealer_history, name="history"),
    path("history/<int:pk>/", views.dealer_history, name="history_detail"),
    path("domains/", views.domain_list, name="domain_list"),
    path("domains/new/", views.domain_form, name="domain_create"),
    path("domains/<int:pk>/edit/", views.domain_form, name="domain_edit"),
    path("domains/<int:pk>/delete/", views.domain_delete, name="domain_delete"),
]
