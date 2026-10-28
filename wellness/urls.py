from django.urls import path
from rest_framework.routers import DefaultRouter

from .export import SnapshotExportView, VisitIdsExportView, VisitsExportView

from .views import (
    ChangePasswordView,
    CompanyViewSet,
    CustomTokenObtainPairView,
    EmployeeViewSet,
    MeView,
    PaymentViewSet,
    PermissionListView,
    PlaceDetailView,
    PlacesView,
    RoleViewSet,
    ServiceViewSet,
    StatsView,
    UserViewSet,
    VisitViewSet,
)


router = DefaultRouter()
router.register(r"companies", CompanyViewSet, basename="company")
router.register(r"services", ServiceViewSet, basename="service")
router.register(r"employees", EmployeeViewSet, basename="employee")
router.register(r"visits", VisitViewSet, basename="visit")
router.register(r"payments", PaymentViewSet, basename="payment")
router.register(r"roles", RoleViewSet, basename="role")
router.register(r"users", UserViewSet, basename="user")


urlpatterns = [
    path("login/", CustomTokenObtainPairView.as_view(), name="login"),
    path("me/", MeView.as_view(), name="me"),
    path("me/password/", ChangePasswordView.as_view(), name="change-password"),
    path("permissions/", PermissionListView.as_view(), name="permissions"),
    path("places/", PlacesView.as_view(), name="places"),
    path("places/<int:pk>/", PlaceDetailView.as_view(), name="place-detail"),
    path("stats/", StatsView.as_view(), name="stats"),
    # Read-only export for the M&E tool
    path("export/snapshot/", SnapshotExportView.as_view(), name="export-snapshot"),
    path("export/visits/", VisitsExportView.as_view(), name="export-visits"),
    path("export/visit-ids/", VisitIdsExportView.as_view(), name="export-visit-ids"),
]

urlpatterns += router.urls
