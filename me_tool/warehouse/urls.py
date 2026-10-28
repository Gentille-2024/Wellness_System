from django.urls import path

from . import views

app_name = "warehouse"

urlpatterns = [
    path("", views.sync_status, name="sync"),
    path("now/", views.sync_now, name="sync-now"),
]
