from django.urls import path

from catalog import views

app_name = "catalog"

urlpatterns = [
    path("products/", views.product_list, name="product_list"),
    path("products/new/", views.product_form, name="product_create"),
    path("products/<int:pk>/edit/", views.product_form, name="product_edit"),
    path("products/<int:pk>/delete/", views.product_delete, name="product_delete"),
    path("special-prices/", views.special_price_list, name="special_price_list"),
    path("special-prices/new/", views.special_price_form, name="special_price_create"),
    path("special-prices/<int:pk>/edit/", views.special_price_form, name="special_price_edit"),
    path("special-prices/<int:pk>/delete/", views.special_price_delete, name="special_price_delete"),
    path("device-models/", views.device_model_list, name="device_model_list"),
    path("device-models/new/", views.device_model_form, name="device_model_create"),
    path("device-models/<int:pk>/edit/", views.device_model_form, name="device_model_edit"),
    path("device-models/<int:pk>/delete/", views.device_model_delete, name="device_model_delete"),
    path("import/", views.import_upload, name="import_upload"),
    path("import/confirm/", views.import_confirm, name="import_confirm"),
    path("import/cancel/", views.import_cancel, name="import_cancel"),
    path("import/template/<str:kind>/", views.import_template, name="import_template"),
    path("api/products/", views.product_search_api, name="product_search_api"),
]
