from django.urls import path

from . import views

app_name = "indicators"

urlpatterns = [
    path("targets/", views.targets, name="targets"),
]
