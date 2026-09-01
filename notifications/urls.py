from django.urls import path

from notifications import views

app_name = "notifications"

urlpatterns = [
    path("", views.notification_list, name="list"),
    path("feed/", views.notification_feed, name="feed"),
    path("<int:pk>/read/", views.mark_read, name="mark_read"),
    path("read-all/", views.mark_all_read, name="mark_all_read"),
    path("<int:pk>/delete/", views.delete, name="delete"),
    path("delete/", views.bulk_delete, name="bulk_delete"),
]
