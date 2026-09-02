from django.urls import path

from orders import views

app_name = "orders"

urlpatterns = [
    path("", views.order_list, name="list"),
    path("drafts/", views.my_drafts, name="drafts"),
    path("new/", views.order_create, name="create"),
    path("new/review/", views.order_review, name="review"),
    path("basket/add/", views.basket_add, name="basket_add"),
    path("basket/<int:item_id>/update/", views.basket_update, name="basket_update"),
    path("basket/<int:item_id>/remove/", views.basket_remove, name="basket_remove"),
    path("<int:pk>/", views.order_detail, name="detail"),
    path("<int:pk>/pdf/", views.order_pdf, name="pdf"),
    path("<int:pk>/form/", views.order_form_preview, name="form_preview"),
    path("<int:pk>/reorder/", views.order_reorder, name="reorder"),
    path("<int:pk>/cancel/", views.order_cancel, name="cancel"),
]
