import secrets
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core import signing
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.db.models import Count, Exists, OuterRef, Prefetch, Q, Sum
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import AnonRateThrottle
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from . import employee_import
from .models import display_name
from .models import Company, Employee, Payment, Permission, PriceChange, Role, Service, Visit
from .permissions import active_roles, company_role_permissions, deny_if_company_deactivated, get_company, get_permissions, has_perm
from .serializers import (
    PriceChangeSerializer,
    record_price_change,
    FeedbackSerializer,
    FirstLoginSerializer,
    ChangePasswordSerializer,
    CompanySerializer,
    CustomTokenObtainPairSerializer,
    EmployeeRegistrationSerializer,
    EmployeeSerializer,
    PaymentSerializer,
    PermissionSerializer,
    ProfileUpdateSerializer,
    PublicCompanySerializer,
    RecordVisitsSerializer,
    RoleSerializer,
    ServiceSerializer,
    SetPasswordSerializer,
    UserAccountSerializer,
    VisitSerializer,
    role_names,
)

ZERO = Decimal("0")


# ------------------------------------------------------------------ helpers

def date_param(request, name):
    """Read ?name=YYYY-MM-DD from the URL, or None. Bad dates give a clear 400."""
    value = request.query_params.get(name)
    if not value:
        return None
    try:
        parsed = parse_date(value)
    except ValueError:
        parsed = None
    if parsed is None:
        raise ValidationError({name: "Use the format YYYY-MM-DD."})
    return parsed


def money(value):
    return value if value is not None else ZERO


# Company staff with any of these see their own company's visits
COMPANY_VISIT_PERMS = {
    "view_company_visits",
    "view_company_dashboard",
    "view_employees_attended",
    "record_visits",
    "take_attendance",
}


def visits_for(user):
    """
    The visits this user may see. Each permission adds what it allows:
      view_all_visits                     -> every visit
      view_company_visits / record_visits -> visits at their own company
      Overview / My services pages        -> their own visits
    (COMPANY_VISIT_PERMS lists every permission that shows the company's visits)
    """
    perms = get_permissions(user)
    visits = Visit.objects.all()
    if "view_all_visits" in perms or "manage_payments" in perms:
        return visits

    allowed = Q(pk__in=[])  # nothing yet
    company = get_company(user)
    if perms & COMPANY_VISIT_PERMS and company is not None:
        allowed |= Q(company=company)
    if perms & {"view_my_overview", "view_my_services"}:
        allowed |= Q(employee__user=user)
    return visits.filter(allowed)


def filter_visits(request, visits):
    """Shared filters for visit lists, stats and PDF data."""
    params = request.query_params
    if params.get("mine"):
        visits = visits.filter(employee__user=request.user)
    if params.get("today"):
        visits = visits.filter(visit_date=timezone.localdate())
    date_from = date_param(request, "date_from")
    date_to = date_param(request, "date_to")
    if date_from:
        visits = visits.filter(visit_date__gte=date_from)
    if date_to:
        visits = visits.filter(visit_date__lte=date_to)
    for field in ("company", "service", "employee"):
        if params.get(field):
            visits = visits.filter(**{f"{field}_id": params[field]})
    if params.get("department"):
        visits = visits.filter(employee__department__iexact=params["department"])
    if params.get("paid") == "yes":
        visits = visits.filter(payment__isnull=False)
    elif params.get("paid") == "no":
        visits = visits.filter(payment__isnull=True)
    if params.get("search"):
        text = params["search"]
        visits = visits.filter(
            Q(employee__employee_id__icontains=text)
            | Q(employee__user__first_name__icontains=text)
            | Q(employee__user__last_name__icontains=text)
            | Q(service__name__icontains=text)
            | Q(company__name__icontains=text)
        )
    return visits


def amounts(visits):
    """Total, paid and unpaid amounts of a set of visits."""
    totals = visits.aggregate(
        total=Sum("price"),
        unpaid=Sum("price", filter=Q(payment__isnull=True)),
        paid=Sum("price", filter=Q(payment__isnull=False)),
    )
    return {key: money(value) for key, value in totals.items()}


def daily_counts(visits, days=14):
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    per_day = dict(
        visits.filter(visit_date__gte=start).values_list("visit_date").annotate(count=Count("id"))
    )
    return [
        {"date": start + timedelta(days=i), "count": per_day.get(start + timedelta(days=i), 0)}
        for i in range(days)
    ]


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


# --------------------------------------------------------------- my account

def me_payload(request=None, user=None):
    user = user or request.user
    profile = getattr(user, "userprofile", None)
    company = profile.company if profile else None
    employee = Employee.objects.filter(user=user).select_related("user").first()
    return {
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": display_name(user),
        "email": user.email,
        "is_superuser": user.is_superuser,
        "role_names": role_names(user),
        # Everything the user may do (a super admin may do everything)...
        "permissions": sorted(get_permissions(user)),
        # ...and only what their roles give them (decides which company /
        # employee menus to show: a super admin isn't automatically an employee)
        "role_permissions": sorted(
            set(
                active_roles(profile).exclude(code=Role.SUPER_ADMIN)
                .values_list("permissions__code", flat=True).exclude(permissions__code=None)
            )
        ) if profile else [],
        "company": CompanySerializer(company).data if company else None,
        "employee": EmployeeSerializer(employee).data if employee else None,
    }


class MeView(APIView):
    """GET: who is logged in and what they may do. PATCH: update my email (and phone)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        deny_if_company_deactivated(request.user)
        return Response(me_payload(request))

    def patch(self, request):
        serializer = ProfileUpdateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.email = serializer.validated_data["email"]
        request.user.save(update_fields=["email"])
        phone = serializer.validated_data.get("phone")
        if phone:
            Employee.objects.filter(user=request.user).update(phone=phone)
        return Response(me_payload(request))


# ------------------------------------------------- sign-in to the M&E tool
# The M&E tool is a separate website. "Open the M&E tool" asks here for a
# ticket; the browser carries it to the M&E tool, whose server trades it
# (once, within a minute) for this user's /api/me/ data and signs them in as
# themselves: no second password, and never as whoever used that browser before.

ME_TICKET_SALT = "wellness.me-tool-ticket"
ME_TICKET_SECONDS = 60


class MeToolTicketView(APIView):
    """POST /api/me-tool/ticket/ -> a one-time ticket to sign in to the M&E tool."""

    write_perms = ("view_me_dashboards", "manage_me_targets")

    def post(self, request):
        ticket = signing.dumps({"u": request.user.pk, "n": secrets.token_urlsafe(16)}, salt=ME_TICKET_SALT)
        return Response({"ticket": ticket, "expires_in": ME_TICKET_SECONDS})


class MeToolTicketThrottle(AnonRateThrottle):
    rate = "30/minute"


class MeToolRedeemView(APIView):
    """POST /api/me-tool/redeem/ {ticket} (called by the M&E tool's server) -> the user's /api/me/ data."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [MeToolTicketThrottle]
    INVALID = "This sign-in link has expired or was already used. Open the M&E tool again from the wellness system."

    def post(self, request):
        try:
            data = signing.loads(str(request.data.get("ticket", "")), salt=ME_TICKET_SALT, max_age=ME_TICKET_SECONDS)
        except signing.BadSignature:
            raise ValidationError({"detail": self.INVALID})
        # Each ticket works once
        if not cache.add(f"me-tool-ticket:{data['n']}", True, ME_TICKET_SECONDS * 2):
            raise ValidationError({"detail": self.INVALID})
        user = User.objects.filter(pk=data["u"], is_active=True).first()
        if user is None:
            raise ValidationError({"detail": self.INVALID})
        deny_if_company_deactivated(user)
        if not has_perm(user, "view_me_dashboards", "manage_me_targets"):
            raise PermissionDenied("Your account has no access to the M&E tool.")
        return Response(me_payload(user=user))


class ChangePasswordView(APIView):
    """POST /api/me/password/ -> change my own password."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["password"])
        request.user.save()
        return Response({"detail": "Your password has been changed."})


class FirstLoginThrottle(AnonRateThrottle):
    """Slows down guessing: a few tries per hour from one address."""
    rate = "20/hour"


class FirstLoginView(APIView):
    """
    POST /api/first-login/ {employee_id, contact (email or phone), password, password_confirm}
    An employee HR added creates their account (their own password).
    Open to visitors who are not signed in.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [FirstLoginThrottle]

    def post(self, request):
        serializer = FirstLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response({"username": user.username, "detail": "Your account is ready. Sign in with your username and new password."})


# -------------------------------------------------------- roles & permissions

class PermissionListView(APIView):
    """
    GET  /api/permissions/ -> every permission a role can be given
    POST /api/permissions/ {name, description, area} -> the super admin adds one
    """

    # Company bosses get the permissions they may put in their own roles
    read_perms = ("manage_users", "manage_company_staff")
    write_perms = ("manage_users",)

    def get(self, request):
        permissions = Permission.objects.all()
        if not has_perm(request.user, "manage_users"):
            permissions = permissions.filter(code__in=company_role_permissions())
        return Response(PermissionSerializer(permissions, many=True).data)

    def post(self, request):
        serializer = PermissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(PermissionSerializer(serializer.save()).data, status=status.HTTP_201_CREATED)


class PermissionDetailView(APIView):
    """PATCH / DELETE /api/permissions/<code>/ -> only permissions the super admin added."""

    read_perms = ("manage_users",)
    write_perms = ("manage_users",)

    def _get(self, code):
        permission = Permission.objects.filter(code=code).first()
        if permission is None:
            raise NotFound("This permission doesn't exist.")
        if permission.is_builtin:
            raise ValidationError({"detail": "Built-in permissions can't be changed or deleted; give or take them through roles."})
        return permission

    def patch(self, request, code):
        serializer = PermissionSerializer(self._get(code), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response(PermissionSerializer(serializer.save()).data)

    def delete(self, request, code):
        self._get(code).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RoleViewSet(viewsets.ModelViewSet):
    """
    Super admin: create roles and choose their permissions.
    Company bosses: see the company roles they can give, and create, edit and
    delete their own company's roles.
    """

    serializer_class = RoleSerializer
    read_perms = ("manage_users", "manage_company_staff")
    write_perms = ("manage_users", "manage_company_staff")
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        roles = (
            Role.objects.prefetch_related("permissions")
            .annotate(user_count=Count("profiles", distinct=True))
            .order_by("name")
        )
        if not has_perm(self.request.user, "manage_users"):
            roles = roles.filter(is_company_role=True).filter(
                Q(company__isnull=True) | Q(company=get_company(self.request.user))
            )
        return roles

    def _check_own(self, role):
        """A boss may only change their own company's roles, never EUCL's."""
        user = self.request.user
        if not has_perm(user, "manage_users") and (role.company is None or role.company != get_company(user)):
            raise PermissionDenied("Only EUCL can change this role.")

    def perform_update(self, serializer):
        self._check_own(serializer.instance)
        serializer.save()

    def perform_destroy(self, role):
        self._check_own(role)
        if role.is_system:
            raise ValidationError("Built-in roles can't be deleted; you can change their permissions.")
        if role.profiles.exists():
            raise ValidationError("Remove this role from its users before deleting it.")
        role.delete()


# ---------------------------------------------------------------- dashboard

class StatsView(APIView):
    """
    GET /api/stats/?scope=platform  -> super admin / EUCL dashboard
    GET /api/stats/?scope=company   -> a company's dashboard (its boss and receptionists)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        scope = request.query_params.get("scope", "platform")
        today = timezone.localdate()
        perms = get_permissions(request.user)

        if scope == "company":
            company = get_company(request.user)
            if request.user.is_superuser and request.query_params.get("company"):
                company = Company.objects.filter(pk=request.query_params["company"]).first()
            if company is None or not (perms & {"view_company_visits", "view_company_dashboard"}):
                raise PermissionDenied("You don't have permission to see this company's dashboard.")
            visits = Visit.objects.filter(company=company)
            per_service = (
                visits.values("service_id", "service__name", "service__price")
                .annotate(
                    visits=Count("id"),
                    total=Sum("price"),
                    unpaid=Sum("price", filter=Q(payment__isnull=True)),
                    paid=Sum("price", filter=Q(payment__isnull=False)),
                )
                .order_by("-total")
            )
            return Response({
                "company": CompanySerializer(company).data,
                # How many different EUCL employees came
                "employees_today": visits.filter(visit_date=today).values("employee").distinct().count(),
                "employees_this_month": visits.filter(
                    visit_date__year=today.year, visit_date__month=today.month
                ).values("employee").distinct().count(),
                "employees_total": visits.values("employee").distinct().count(),
                "visits_today": visits.filter(visit_date=today).count(),
                "visits_this_month": visits.filter(visit_date__year=today.year, visit_date__month=today.month).count(),
                "total_visits": visits.count(),
                "amount_this_month": money(
                    visits.filter(visit_date__year=today.year, visit_date__month=today.month).aggregate(s=Sum("price"))["s"]
                ),
                **amounts(visits),
                "services": company.services.filter(is_active=True, is_approved=True).count(),
                "services_waiting": company.services.filter(is_active=True, is_approved=False).count(),
                "daily": daily_counts(visits),
                "by_service": [
                    {
                        "service": row["service__name"],
                        "current_price": row["service__price"],
                        "visits": row["visits"],
                        "total": money(row["total"]),
                        "paid": money(row["paid"]),
                        "unpaid": money(row["unpaid"]),
                    }
                    for row in per_service
                ],
            })

        if not perms & {"view_all_visits", "manage_payments", "manage_companies", "manage_users", "manage_employees"}:
            raise PermissionDenied("You don't have permission to see the platform dashboard.")

        visits = Visit.objects.all()
        per_company = (
            visits.values("company_id", "company__name")
            .annotate(
                visits=Count("id"),
                total=Sum("price"),
                unpaid=Sum("price", filter=Q(payment__isnull=True)),
            )
            .order_by("-total")[:8]
        )
        companies = Company.objects.all()
        return Response({
            "companies_open": companies.filter(is_active=True, deleted_at__isnull=True).count(),
            "companies_deactivated": companies.filter(is_active=False, deleted_at__isnull=True).count(),
            "companies_deleted": companies.filter(deleted_at__isnull=False).count(),
            "employees": Employee.objects.count(),
            "active_employees": Employee.objects.filter(user__is_active=True).count(),
            "visits_today": visits.filter(visit_date=today).count(),
            "visits_this_month": visits.filter(visit_date__year=today.year, visit_date__month=today.month).count(),
            "total_visits": visits.count(),
            "amount_this_month": money(
                visits.filter(visit_date__year=today.year, visit_date__month=today.month).aggregate(s=Sum("price"))["s"]
            ),
            **amounts(visits),
            "daily": daily_counts(visits),
            "by_company": [
                {
                    "company_id": row["company_id"],
                    "company": row["company__name"],
                    "visits": row["visits"],
                    "total": money(row["total"]),
                    "unpaid": money(row["unpaid"]),
                }
                for row in per_company
            ],
        })


# ----------------------------------------------------------------- companies

class CompanyViewSet(viewsets.ModelViewSet):
    """
    Service providers.
    manage_companies: everything. Company staff: read their own company.
    """

    serializer_class = CompanySerializer
    # HR reads the list too, to filter the price changes and employees attended by
    # company; Users & roles reads it to link a login to its company
    read_perms = (
        "manage_companies", "manage_payments", "view_all_visits", "manage_company_services", "view_price_changes",
        "view_all_employees_attended", "manage_users",
    ) + tuple(COMPANY_VISIT_PERMS)
    write_perms = ("manage_companies",)

    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "email", "phone", "address"]

    def get_queryset(self):
        companies = Company.objects.annotate(
            service_count=Count("services", filter=Q(services__is_active=True), distinct=True),
            covered_count=Count(
                "services", filter=Q(services__is_active=True, services__is_approved=True), distinct=True
            ),
            staff_count=Count("staff", distinct=True),
        ).order_by("name")

        user = self.request.user
        if not has_perm(
            user, "manage_companies", "manage_payments", "view_all_visits", "view_price_changes",
            "view_all_employees_attended", "manage_users",
        ):
            company = get_company(user)
            return companies.filter(pk=getattr(company, "pk", None), deleted_at__isnull=True)

        # ?status=open | deactivated | deleted   (default: all)
        status_filter = self.request.query_params.get("status")
        if status_filter == "open":
            companies = companies.filter(is_active=True, deleted_at__isnull=True)
        elif status_filter == "deactivated":
            companies = companies.filter(is_active=False, deleted_at__isnull=True)
        elif status_filter == "deleted":
            companies = companies.filter(deleted_at__isnull=False)
        elif status_filter == "current":
            companies = companies.filter(deleted_at__isnull=True)
        return companies

    def _fresh(self, company):
        return Response(self.get_serializer(self.get_queryset().get(pk=company.pk)).data)

    def perform_destroy(self, company):
        # Never erase a company: archive it and block its staff's logins
        company.soft_delete()

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        company = self.get_object()
        company.restore()
        return self._fresh(company)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        """Pause the company: hidden from employees, no new visits."""
        company = self.get_object()
        company.is_active = False
        company.save(update_fields=["is_active"])
        return self._fresh(company)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        company = self.get_object()
        company.is_active = True
        company.save(update_fields=["is_active"])
        return self._fresh(company)

    @action(detail=True, methods=["post"], url_path="covered-services")
    def covered_services(self, request, pk=None):
        """
        POST /api/companies/<id>/covered-services/
             {"services": [{"id": 3}, {"id": 5}]}   (or just [3, 5])
        EUCL chooses which of the company's services its employees may use.
        EUCL pays the company's own price, so no separate amount is sent.
        Services not in the list are not covered.
        """
        company = self.get_object()
        chosen = request.data.get("services")
        if not isinstance(chosen, list):
            raise ValidationError({"services": "Send the services EUCL covers."})

        chosen_ids = set()
        for item in chosen:
            try:
                chosen_ids.add(int(item["id"] if isinstance(item, dict) else item))
            except (KeyError, TypeError, ValueError):
                raise ValidationError({"services": "Each covered service needs its id."})

        company_services = {service.pk: service for service in company.services.all()}
        if chosen_ids - set(company_services):
            raise ValidationError({"services": "Some of these services don't belong to this company."})

        with transaction.atomic():
            for service in company_services.values():
                service.is_approved = service.pk in chosen_ids
                # Kept equal to the company's price (the M&E tool still reads it)
                service.eucl_price = service.price if service.is_approved else None
                service.save(update_fields=["is_approved", "eucl_price"])

        services = Service.objects.filter(company=company).annotate(visit_count=Count("visits")).order_by("name")
        return Response(ServiceSerializer(services, many=True, context={"request": request}).data)

def open_places():
    """Open companies that offer at least one service, with their services."""
    return (
        Company.objects.filter(is_active=True, deleted_at__isnull=True, services__is_active=True)
        .distinct()
        .prefetch_related(Prefetch("services", queryset=Service.objects.order_by("name")))
        .order_by("name")
    )


class PlacesView(APIView):
    """
    GET /api/places/ -> open companies and everything they offer, each service
    marked covered by EUCL or not, for EUCL employees choosing where to go.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        companies = open_places()
        search = request.query_params.get("search")
        if search:
            companies = companies.filter(
                Q(name__icontains=search) | Q(services__name__icontains=search, services__is_active=True)
            ).distinct()
        if request.query_params.get("covered") == "yes":
            companies = companies.filter(services__is_active=True, services__is_approved=True).distinct()
        return Response(PublicCompanySerializer(companies, many=True).data)


class PlaceDetailView(APIView):
    """GET /api/places/<id>/ -> one place and all of its services."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        company = open_places().filter(pk=pk).first()
        if company is None:
            raise NotFound("This place is not available.")
        return Response(PublicCompanySerializer(company).data)

# ------------------------------------------------------------------ services

class ServiceViewSet(viewsets.ModelViewSet):
    """
    Services and their prices.
    Company staff with manage_company_services manage their own company's.
    """

    serializer_class = ServiceSerializer
    open_read = True
    write_perms = ("manage_companies", "manage_company_services", "edit_service_prices")

    def _prices_only(self):
        """Staff who may only change prices (e.g. a receptionist), not manage services."""
        return not has_perm(self.request.user, "manage_companies", "manage_company_services")
    # No DELETE: a service with history is switched off with is_active instead
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        services = Service.objects.select_related("company").annotate(visit_count=Count("visits"))
        user = self.request.user
        params = self.request.query_params

        if has_perm(user, "manage_companies"):
            pass  # everything
        elif get_company(user) is not None:
            services = services.filter(company=get_company(user))
        else:
            # Employees only see what they can actually use today
            services = services.filter(
                is_active=True, is_approved=True, company__is_active=True, company__deleted_at__isnull=True
            )

        if params.get("company"):
            services = services.filter(company_id=params["company"])
        if params.get("active") == "yes":
            services = services.filter(is_active=True)
        if params.get("available") == "yes":
            # Offered AND covered by EUCL: what reception may record
            services = services.filter(is_active=True, is_approved=True)
        return services.order_by("company__name", "name")

    # Every price given or changed is written down with who did it
    def perform_create(self, serializer):
        if self._prices_only():
            raise PermissionDenied("You can change prices, but not add services.")
        service = serializer.save()
        record_price_change(service, None, self.request.user)

    def perform_update(self, serializer):
        if self._prices_only() and set(self.request.data) - {"price"}:
            raise PermissionDenied("You can only change the price.")
        old_price = serializer.instance.price
        service = serializer.save()
        record_price_change(service, old_price, self.request.user)


class PriceChangeListView(APIView):
    """
    GET /api/price-changes/?company=&service=&date_from=&date_to=&changed=yes
    Who gave or changed each service price, and when (admin, HR).
    changed=yes leaves out the first price of new services.
    """

    read_perms = ("view_price_changes",)

    def get(self, request):
        changes = PriceChange.objects.select_related("service", "company")
        params = request.query_params
        for field in ("company", "service"):
            if params.get(field):
                changes = changes.filter(**{f"{field}_id": params[field]})
        date_from, date_to = date_param(request, "date_from"), date_param(request, "date_to")
        if date_from:
            changes = changes.filter(changed_at__date__gte=date_from)
        if date_to:
            changes = changes.filter(changed_at__date__lte=date_to)
        if params.get("changed") == "yes":
            changes = changes.filter(old_price__isnull=False)
        return Response(PriceChangeSerializer(changes[:1000], many=True).data)


# ------------------------------------------------------------- EUCL employees

def _rows(errors):
    """Turns the error rows into text: "row 3" or "rows 3, 5 and 9"."""
    rows = sorted({e["row"] for e in errors})
    if len(rows) == 1:
        return f"row {rows[0]}"
    return "rows " + ", ".join(str(r) for r in rows[:-1]) + f" and {rows[-1]}"


class EmployeeViewSet(viewsets.ModelViewSet):
    serializer_class = EmployeeSerializer
    # Receptionists search employees to record their visits
    READ_PERMS = ("manage_employees", "record_visits", "take_attendance", "view_all_visits")

    @property
    def read_perms(self):
        action = getattr(self, "action", None)
        if action == "departments":
            # Only the department names, for the filters of every list that has one
            return self.READ_PERMS + ("manage_payments", "view_all_employees_attended") + tuple(COMPANY_VISIT_PERMS)
        if action == "download_template":
            return ("import_employees",)
        return self.READ_PERMS

    @property
    def write_perms(self):
        # "Upload employees from Excel" works on its own, without "Manage EUCL employees"
        if getattr(self, "action", None) == "import_file":
            return ("manage_employees", "import_employees")
        return ("manage_employees",)
    # No DELETE: removing an employee would erase their history.
    http_method_names = ["get", "post", "patch", "head", "options"]

    filter_backends = [filters.SearchFilter]
    search_fields = ["employee_id", "user__username", "user__first_name", "user__last_name", "user__email", "department"]

    def get_queryset(self):
        employees = Employee.objects.select_related("user").order_by("-created_at")
        params = self.request.query_params
        user = self.request.user
        if not has_perm(user, "manage_employees", "view_all_visits"):
            # Company staff: only people who can actually use services...
            employees = employees.filter(user__is_active=True)
            company = get_company(user)
            # ...and only those who came to this company, except on the attendance
            # page (the full list) or when reception searches for someone to record
            searching = len(params.get("search", "").strip()) >= 2
            if self.action == "list" and not searching and not has_perm(user, "take_attendance"):
                employees = employees.filter(visits__company=company).distinct()
            # Who already used services at another company today (one company a day)
            employees = employees.annotate(
                elsewhere_today=Exists(
                    Visit.objects.filter(employee=OuterRef("pk"), visit_date=timezone.localdate()).exclude(company=company)
                )
            )
        if params.get("status") == "active":
            employees = employees.filter(user__is_active=True)
        elif params.get("status") == "inactive":
            employees = employees.filter(user__is_active=False)
        if params.get("department"):
            employees = employees.filter(department__iexact=params["department"])
        return employees

    def create(self, request, *args, **kwargs):
        raise MethodNotAllowed("POST", detail="Use /api/employees/register/ to onboard employees.")

    @action(detail=False, methods=["post"])
    def register(self, request):
        """POST /api/employees/register/ -> login + Employee role + employee record."""
        serializer = EmployeeRegistrationSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        employee = serializer.save()
        return Response(self.get_serializer(employee).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="template")
    def download_template(self, request):
        """GET /api/employees/template/ -> the empty Excel template for HR."""
        if not has_perm(request.user, "import_employees"):
            raise PermissionDenied("You don't have permission to upload employees.")
        response = HttpResponse(
            employee_import.template_bytes(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="eucl-employees-template.xlsx"'
        return response

    @action(detail=False, methods=["post"], url_path="import")
    def import_file(self, request):
        """
        POST /api/employees/import/  (multipart, field "file": .xlsx or .csv)
        -> {"created": n, "updated": n}, or 400 {"detail", "errors": [{"row", "message"}]}
        Nothing is saved when any row has a problem.
        """
        if not has_perm(request.user, "import_employees"):
            raise PermissionDenied("You don't have permission to upload employees.")
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"detail": "Choose the Excel file to upload."})
        try:
            records, errors = employee_import.parse(upload)
        except employee_import.ImportError_ as exc:
            raise ValidationError({"detail": str(exc)})
        if errors:
            return Response(
                {
                    "detail": (
                        f"Nothing was saved. Fix {'this problem' if len(errors) == 1 else f'these {len(errors)} problems'} "
                        f"in the file ({_rows(errors)}) and upload it again."
                    ),
                    "errors": errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        created, updated = employee_import.apply(records)
        return Response({"created": created, "updated": updated})

    @action(detail=True, methods=["post"], url_path="set-active")
    def set_active(self, request, pk=None):
        """POST /api/employees/<id>/set-active/ {"is_active": true|false}"""
        employee = self.get_object()
        employee.user.is_active = bool(request.data.get("is_active"))
        employee.user.save(update_fields=["is_active"])
        return Response(self.get_serializer(employee).data)

    @action(detail=False, methods=["get"])
    def departments(self, request):
        """GET /api/employees/departments/ -> the department names (for filters)."""
        names = (
            Employee.objects.exclude(department="")
            .values_list("department", flat=True)
            .distinct()
            .order_by("department")
        )
        return Response(list(names))


# -------------------------------------------------------------------- visits

class VisitViewSet(viewsets.ModelViewSet):
    """
    GET  -> visits this user may see (with filters)
    POST -> the receptionist records one or more services for an employee
    """

    serializer_class = VisitSerializer
    read_perms = (
        "view_all_visits", "view_my_overview", "view_my_services", "manage_payments", "view_all_employees_attended",
    ) + tuple(COMPANY_VISIT_PERMS)
    http_method_names = ["get", "post", "delete", "head", "options"]

    @property
    def write_perms(self):
        # Employees write only feedback on their own services
        if getattr(self, "action", None) == "feedback":
            return ("view_my_services", "view_my_overview")
        return ("record_visits", "take_attendance")

    @action(detail=True, methods=["post", "delete"])
    def feedback(self, request, pk=None):
        """
        POST   /api/visits/<id>/feedback/ {"kind": "comment|complaint", "message": "…"}
        DELETE /api/visits/<id>/feedback/  -> take the feedback back
        Only the employee who used the service.
        """
        visit = self.get_object()
        if visit.employee.user_id != request.user.id:
            raise PermissionDenied("You can only give feedback on your own services.")
        if request.method == "DELETE":
            visit.feedback_kind, visit.feedback_message, visit.feedback_at = "", "", None
        else:
            serializer = FeedbackSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            visit.feedback_kind = serializer.validated_data["kind"]
            visit.feedback_message = serializer.validated_data["message"]
            visit.feedback_at = timezone.now()
        visit.save(update_fields=["feedback_kind", "feedback_message", "feedback_at", "updated_at"])
        return Response(VisitSerializer(visit).data)

    def get_queryset(self):
        visits = visits_for(self.request.user).select_related(
            "employee__user", "service", "company", "recorded_by"
        )
        return filter_visits(self.request, visits).order_by("-visited_at")

    def create(self, request, *args, **kwargs):
        serializer = RecordVisitsSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        employee = serializer.validated_data["employee"]
        today = timezone.localdate()

        created, skipped = [], []
        with transaction.atomic():
            for service in serializer.validated_data["services"]:
                if Visit.objects.filter(employee=employee, service=service, visit_date=today).exists():
                    skipped.append(service.name)
                    continue
                try:
                    with transaction.atomic():
                        created.append(Visit.objects.create(
                            employee=employee,
                            service=service,
                            company=service.company,
                            # EUCL pays the company's own price for this service
                            price=service.price,
                            visit_date=today,
                            recorded_by=request.user,
                        ))
                except IntegrityError:
                    skipped.append(service.name)

        if not created:
            raise ValidationError({"services": f"Already recorded today: {', '.join(skipped)}."})
        return Response(
            {"visits": VisitSerializer(created, many=True).data, "skipped": skipped},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get"], url_path="by-employee")
    def by_employee(self, request):
        """
        GET /api/visits/by-employee/?date_from=&date_to=&...
        One line per EUCL employee: the services they used, how many times,
        and the amount; plus the totals for all employees together.
        Uses the same permissions and filters as the visit list, so a company's
        staff only ever see their own company's employees.
        view_all_employees_attended (EUCL HR): every company (?company= narrows
        it to one), without opening the full list of usage records.
        """
        if not has_perm(
            request.user, "view_employees_attended", "view_company_visits", "view_all_visits", "manage_payments",
            "view_all_employees_attended",
        ):
            raise PermissionDenied("You don't have permission to see the employees attended.")
        if has_perm(request.user, "view_all_employees_attended"):
            visits = filter_visits(request, Visit.objects.all())
        else:
            visits = self.get_queryset()
        # .order_by() clears the list ordering so grouping stays per employee
        visits = visits.order_by()

        services_per_employee = {}
        for row in (
            visits.values("employee_id", "service__name", "company__name")
            .annotate(count=Count("id"), amount=Sum("price"))
            .order_by("service__name", "company__name")
        ):
            services_per_employee.setdefault(row["employee_id"], []).append({
                "service": row["service__name"],
                "company": row["company__name"],
                "count": row["count"],
                "amount": money(row["amount"]),
            })

        employees = (
            visits.values(
                "employee_id",
                "employee__employee_id",
                "employee__user__first_name",
                "employee__user__last_name",
                "employee__department",
            )
            .annotate(visits=Count("id"), days=Count("visit_date", distinct=True), total=Sum("price"))
            .order_by("-total", "employee__user__last_name", "employee__user__first_name")
        )

        rows = [
            {
                "employee": row["employee_id"],
                "employee_code": row["employee__employee_id"],
                "employee_name": f'{row["employee__user__last_name"]} {row["employee__user__first_name"]}'.strip(),
                "department": row["employee__department"],
                "visits": row["visits"],
                "days": row["days"],
                "total": money(row["total"]),
                "services": services_per_employee.get(row["employee_id"], []),
            }
            for row in employees
        ]
        return Response({
            "employees": rows,
            "totals": {
                "employees": len(rows),
                "visits": sum(row["visits"] for row in rows),
                "amount": sum((row["total"] for row in rows), ZERO),
            },
        })

    def perform_destroy(self, visit):
        """Undo a mistake: super admin any unpaid visit; reception today's unpaid visits at their company."""
        if visit.payment_id is not None:
            raise ValidationError("This service is already paid and can't be removed.")
        user = self.request.user
        if not user.is_superuser:
            if visit.company != get_company(user) or visit.visit_date != timezone.localdate():
                raise PermissionDenied("You can only undo today's services at your own company.")
        visit.delete()


# ------------------------------------------------------------------ payments

class FeedbackListView(APIView):
    """
    GET /api/feedback/?kind=&date_from=&date_to=&company=&search=
    The feedback employees sent about the services they used.
      view_feedback          -> every company (HR, super admin)
      view_company_feedback  -> the user's own company (boss, receptionist)
    """

    read_perms = ("view_feedback", "view_company_feedback")

    def get(self, request):
        visits = Visit.objects.exclude(feedback_kind="").select_related("employee__user", "service", "company", "recorded_by")
        if not has_perm(request.user, "view_feedback"):
            company = get_company(request.user)
            visits = visits.filter(company=company) if company else visits.none()
        if request.query_params.get("kind"):
            visits = visits.filter(feedback_kind=request.query_params["kind"])
        visits = filter_visits(request, visits).order_by("-feedback_at")
        return Response(VisitSerializer(visits, many=True).data)


class PaymentViewSet(viewsets.ModelViewSet):
    """
    manage_payments: see what is owed and mark a period as paid.
    Company staff with view_company_visits: see their company's payments.
    """

    serializer_class = PaymentSerializer
    read_perms = ("manage_payments", "view_company_visits")
    write_perms = ("manage_payments",)
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        payments = Payment.objects.select_related("company", "recorded_by").annotate(visit_count=Count("visits"))
        if not has_perm(self.request.user, "manage_payments"):
            payments = payments.filter(company=get_company(self.request.user))
        if self.request.query_params.get("company"):
            payments = payments.filter(company_id=self.request.query_params["company"])
        return payments.order_by("-paid_at")

    def create(self, request, *args, **kwargs):
        """Mark every unpaid visit of a company in a period as paid."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        unpaid = Visit.objects.filter(
            company=data["company"],
            payment__isnull=True,
            visit_date__gte=data["period_start"],
            visit_date__lte=data["period_end"],
        )
        total = unpaid.aggregate(s=Sum("price"))["s"]
        if not total and not unpaid.exists():
            raise ValidationError("There are no unpaid services for this company in that period.")

        with transaction.atomic():
            payment = serializer.save(amount=money(total), recorded_by=request.user)
            # .update() skips auto_now, so set updated_at for the M&E sync
            unpaid.update(payment=payment, updated_at=timezone.now())
        return Response(self.get_serializer(self.get_queryset().get(pk=payment.pk)).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def balances(self, request):
        """
        GET /api/payments/balances/?date_from=&date_to=
        -> per company: visits, total, paid and unpaid amounts.
        """
        visits = filter_visits(request, visits_for(request.user))
        rows = (
            visits.values("company_id", "company__name")
            .annotate(
                visits=Count("id"),
                employees=Count("employee", distinct=True),
                unpaid_employees=Count("employee", distinct=True, filter=Q(payment__isnull=True)),
                total=Sum("price"),
                unpaid=Sum("price", filter=Q(payment__isnull=True)),
                unpaid_visits=Count("id", filter=Q(payment__isnull=True)),
                paid=Sum("price", filter=Q(payment__isnull=False)),
            )
            .order_by("company__name")
        )
        return Response([
            {
                "company": row["company_id"],
                "company_name": row["company__name"],
                "visits": row["visits"],
                "unpaid_visits": row["unpaid_visits"],
                "employees": row["employees"],
                "unpaid_employees": row["unpaid_employees"],
                "total": money(row["total"]),
                "paid": money(row["paid"]),
                "unpaid": money(row["unpaid"]),
            }
            for row in rows
        ])

    @action(detail=False, methods=["get"])
    def statement(self, request):
        """
        GET /api/payments/statement/?date_from=&date_to=&paid=no|yes&company=
        Per company: every EUCL employee who came, their visits and amount,
        the company's total and the grand total (for the PDF / Excel export).
        Company staff only get their own company.
        """
        visits = filter_visits(request, visits_for(request.user))
        if not has_perm(request.user, "manage_payments"):
            visits = visits.filter(company=get_company(request.user))

        rows = (
            visits.order_by()
            .values(
                "company_id",
                "company__name",
                "employee_id",
                "employee__employee_id",
                "employee__user__first_name",
                "employee__user__last_name",
                "employee__department",
            )
            .annotate(visits=Count("id"), amount=Sum("price"))
            .order_by("company__name", "employee__user__last_name", "employee__user__first_name")
        )

        companies = {}
        for row in rows:
            company = companies.setdefault(row["company_id"], {
                "company": row["company_id"],
                "company_name": row["company__name"],
                "employees": [],
                "visits": 0,
                "amount": ZERO,
            })
            company["employees"].append({
                "employee": row["employee_id"],
                "employee_code": row["employee__employee_id"],
                "employee_name": f'{row["employee__user__last_name"]} {row["employee__user__first_name"]}'.strip(),
                "department": row["employee__department"],
                "visits": row["visits"],
                "amount": money(row["amount"]),
            })
            company["visits"] += row["visits"]
            company["amount"] += money(row["amount"])

        companies = list(companies.values())
        for company in companies:
            company["employee_count"] = len(company["employees"])
        return Response({
            "companies": companies,
            "totals": {
                "companies": len(companies),
                "employees": len({e["employee"] for c in companies for e in c["employees"]}),
                "visits": sum(c["visits"] for c in companies),
                "amount": sum((c["amount"] for c in companies), ZERO),
            },
        })


# --------------------------------------------------------------------- users

class UserViewSet(viewsets.ModelViewSet):
    """
    Logins and their roles.
    manage_users: everyone. manage_company_staff: the staff of their own company.
    """

    serializer_class = UserAccountSerializer
    read_perms = ("manage_users", "manage_company_staff")
    write_perms = ("manage_users", "manage_company_staff")
    # No DELETE: block logins instead, so records keep their author
    http_method_names = ["get", "post", "patch", "head", "options"]

    filter_backends = [filters.SearchFilter]
    search_fields = ["username", "first_name", "last_name", "email"]

    def get_queryset(self):
        users = (
            User.objects.select_related("userprofile__company", "employee")
            .prefetch_related("userprofile__roles")
            .order_by("username")
        )
        if not has_perm(self.request.user, "manage_users"):
            company = get_company(self.request.user)
            if company is None:
                return users.none()
            users = users.filter(userprofile__company=company)

        params = self.request.query_params
        if params.get("role") == "SUPERUSER":
            users = users.filter(is_superuser=True)
        elif params.get("role"):
            users = users.filter(userprofile__roles__code=params["role"])
        if params.get("company"):
            users = users.filter(userprofile__company_id=params["company"])
        if params.get("status") == "active":
            users = users.filter(is_active=True)
        elif params.get("status") == "blocked":
            users = users.filter(is_active=False)
        if params.get("kind") == "staff":
            users = users.filter(employee__isnull=True)
        elif params.get("kind") == "employees":
            users = users.filter(employee__isnull=False)
        return users.distinct()

    @action(detail=True, methods=["get"])
    def access(self, request, pk=None):
        """
        GET /api/users/<id>/access/ -> what this login may do, and which role
        gives each permission (to take one away, switch it off in every role
        listed next to it).
        """
        account = self.get_object()
        profile = getattr(account, "userprofile", None)
        roles = list(profile.roles.prefetch_related("permissions").order_by("name")) if profile else []
        counting = {role.pk for role in active_roles(profile)} if profile else set()

        sources = {}  # permission code -> names of the roles that give it
        for role in roles:
            if role.pk not in counting:
                continue
            for permission in role.permissions.all():
                sources.setdefault(permission.code, []).append(role.name)
        if account.is_superuser:
            # A Django superuser does what the Super admin role allows, with or without the role
            super_admin = Role.objects.filter(code=Role.SUPER_ADMIN).first()
            label = super_admin.name if super_admin else "Super admin"
            for code in get_permissions(account):
                if label not in sources.setdefault(code, []):
                    sources[code].append(label)

        permissions = Permission.objects.filter(code__in=sources)
        return Response({
            "user": account.id,
            "username": account.username,
            "is_superuser": account.is_superuser,
            "roles": [
                {"id": role.id, "code": role.code, "name": role.name, "counts": role.pk in counting}
                for role in roles
            ],
            "permissions": [
                {
                    "code": p.code,
                    "name": p.name,
                    "description": p.description,
                    "area": p.area,
                    "roles": sources[p.code],
                }
                for p in permissions.order_by("area", "name")
            ],
        })

    @action(detail=True, methods=["post"], url_path="set-password")
    def set_password(self, request, pk=None):
        """POST /api/users/<id>/set-password/ {"password", "password_confirm"}"""
        user = self.get_object()
        serializer = SetPasswordSerializer(data=request.data, context={"user": user})
        serializer.is_valid(raise_exception=True)
        user.set_password(serializer.validated_data["password"])
        user.save()
        return Response({"detail": f"Password for {user.username} has been changed."})
