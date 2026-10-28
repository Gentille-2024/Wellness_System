from django.contrib import admin
from django.urls import include, path

from dashboards.views import healthz

urlpatterns = [
    path("", include("dashboards.urls")),
    path("accounts/", include("accounts.urls")),
    path("indicators/", include("indicators.urls")),
    path("reports/", include("reports.urls")),
    path("sync/", include("warehouse.urls")),
    path("system/", include("monitoring.urls")),
    path("healthz/", healthz, name="healthz"),
    path("django-admin/", admin.site.urls),
]

handler403 = "dashboards.errors.forbidden"
