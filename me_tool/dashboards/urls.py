from django.urls import path

from . import views

app_name = "dashboards"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("companies/", views.companies, name="companies"),
    path("companies/<int:company_id>/", views.company, name="company"),
    path("services/", views.services, name="services"),
    path("indicators/", views.indicators, name="indicators"),
]
