from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.report_list, name="list"),
    path("rows/", views.report_rows, name="rows"),
    path("new/", views.report_create, name="create"),
    path("<uuid:report_id>/download/", views.report_download, name="download"),
]
