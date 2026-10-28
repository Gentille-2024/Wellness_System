from django.urls import path

from . import views

app_name = "monitoring"

urlpatterns = [
    path("", views.system, name="system"),
    path("measure/", views.measure_now, name="measure"),
]
