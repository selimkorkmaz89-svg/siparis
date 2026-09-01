from django.urls import path

from accounts import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.AppLoginView.as_view(), name="login"),
    path("logout/", views.AppLogoutView.as_view(), name="logout"),
    path("register/", views.register, name="register"),
    path("profile/", views.profile, name="profile"),
    path("pending/", views.pending_users, name="pending_users"),
    path("pending/<int:pk>/approve/", views.approve_user, name="approve_user"),
    path("pending/<int:pk>/reject/", views.reject_user, name="reject_user"),
    path("users/", views.user_list, name="user_list"),
    path("users/new/", views.user_form, name="user_create"),
    path("users/<int:pk>/edit/", views.user_form, name="user_edit"),
]
