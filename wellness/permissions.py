from contextvars import ContextVar

from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission, SAFE_METHODS

COMPANY_DEACTIVATED = "This company has been deactivated! Please contact EUCL for more information."

# ---------------------------------------------------------------------------
# Every permission the code can check. The migration creates them in the
# database; the super admin then bundles them into roles from the app.
# (code, name, description, area)
# ---------------------------------------------------------------------------
PERMISSIONS = [
    # Platform (super admin and anyone they trust with these)
    ("manage_companies", "Manage companies", "Add, edit, deactivate and delete service providers", "Platform"),
    ("manage_users", "Manage users & roles", "Create logins, roles and permissions", "Platform"),
    ("view_all_visits", "See all services used", "See every service used at every company", "Platform"),
    ("manage_payments", "Manage payments", "See amounts owed and mark periods as paid", "Platform"),
    ("view_price_changes", "See price changes", "See every change of a service price: old and new price, who changed it (boss, receptionist…) and when", "Platform"),
    ("view_feedback", "See employees' feedback", "Read the comments and complaints employees send about services, at every company", "Platform"),
    # EUCL
    ("manage_employees", "Manage EUCL employees", "Onboard, edit and deactivate EUCL employees", "EUCL"),
    ("import_employees", "Upload employees from Excel", "Download the Excel template and upload EUCL employees", "EUCL"),
    ("view_all_employees_attended", "See employees attended (all companies)", "See which EUCL employees used services at every company, what they used and the amounts", "EUCL"),
    # Company (service provider) staff
    ("record_visits", "Record services", "Tick the services an employee used at the company", "Company"),
    ("view_company_visits", "See company services used & payments", "See the services used at the company, amounts and payments", "Company"),
    ("manage_company_services", "Manage company services", "Add services and set their prices", "Company"),
    ("edit_service_prices", "Edit service prices", "Change the prices of the company's services (not add or switch them off)", "Company"),
    ("manage_company_staff", "Manage company staff", "Create receptionist and other staff logins for the company", "Company"),
    ("view_company_dashboard", "Company dashboard", "Open the company dashboard", "Company"),
    ("view_company_services", "See services & prices", "See the company's services, prices and what EUCL covers", "Company"),
    ("view_employees_attended", "See employees attended", "See which EUCL employees came, what they used and the amounts", "Company"),
    ("take_attendance", "Take employees' attendance", "Tick, on the list of EUCL employees, the services each one is taking", "Company"),
    ("view_company_feedback", "See feedback on our services", "Read the comments and complaints EUCL employees send about this company's services", "Company"),
    # M&E tool (a separate application that reads this system's data)
    ("export_data", "Export data for M&E", "Read-only access used by the M&E tool to sync its data", "M&E"),
    ("view_me_dashboards", "See M&E dashboards", "Open the M&E dashboards, indicators and reports for all companies", "M&E"),
    ("manage_me_targets", "Manage M&E targets", "Set the targets of the M&E indicators", "M&E"),
    # EUCL employees
    # One per page of "My wellness"
    ("view_my_overview", "Overview", "Open My wellness: today, this month and the latest services", "Employee"),
    ("view_places", "Places & services", "Browse the partner places and the services EUCL covers", "Employee"),
    ("view_my_services", "My services", "See and export the services I used", "Employee"),
]

ALL_PERMISSIONS = {code for code, *_ in PERMISSIONS}

# The "My wellness" pages of an EUCL employee (one permission per page)
EMPLOYEE_PAGE_PERMISSIONS = {"view_my_overview", "view_places", "view_my_services"}

# What a company boss may put in a role they create for their own company:
# the company pages, but not managing staff (only EUCL decides who may do that)
COMPANY_ROLE_PERMISSIONS = {
    code for code, _name, _description, area in PERMISSIONS if area == "Company"
} - {"manage_company_staff"}


def company_role_permissions():
    """COMPANY_ROLE_PERMISSIONS plus the company permissions the super admin added."""
    from .models import Permission

    added = Permission.objects.filter(area="Company", is_builtin=False).values_list("code", flat=True)
    return COMPANY_ROLE_PERMISSIONS | set(added)


def super_admin_permissions():
    """
    What super admins may do: the permissions switched on for the Super admin role.
    Every switch can be turned off, "Manage users & roles" too. If it is, the
    roles page is closed to super admins until a Django superuser switches it
    back on in the Django admin (/admin/ -> Roles -> Super admin).
    """
    from .models import Role

    role = Role.objects.filter(code=Role.SUPER_ADMIN).first()
    if role is None:
        return all_permission_codes()
    return set(role.permissions.values_list("code", flat=True))


def all_permission_codes():
    from .models import Permission

    return ALL_PERMISSIONS | set(Permission.objects.values_list("code", flat=True))


def get_permissions(user):
    """The set of permission codes a user has through all of their roles."""
    if not user or not user.is_authenticated:
        return set()
    if user.is_superuser:
        return super_admin_permissions()
    profile = getattr(user, "userprofile", None)
    if profile is None:
        return set()
    return set(
        active_roles(profile).values_list("permissions__code", flat=True).exclude(permissions__code=None)
    )


def active_roles(profile):
    """
    The roles that count right now. While a company is deactivated, its staff
    lose what their company roles give them (other roles, e.g. Employee, stay).
    """
    roles = profile.roles.all()
    if profile.company_id is not None and company_is_deactivated(profile.company_id):
        roles = roles.filter(is_company_role=False)
    return roles


def company_is_deactivated(company_id):
    # Read from the database: a cached company object may be out of date
    from .models import Company

    return Company.objects.filter(pk=company_id, is_active=False).exists()


def company_deactivated(user):
    """True for company staff who can't do anything because their company is deactivated."""
    if not user or not user.is_authenticated or user.is_superuser:
        return False
    company = get_company(user)
    return company is not None and company_is_deactivated(company.pk) and not get_permissions(user)


def deny_if_company_deactivated(user):
    if company_deactivated(user):
        raise PermissionDenied({"detail": COMPANY_DEACTIVATED, "code": "company_deactivated"})


def has_perm(user, *codes):
    """True if the user has at least one of these permissions."""
    return bool(get_permissions(user) & set(codes))


# ---------------------------------------------------------------------------
# Any role may have any permission. Company permissions open the company
# pages; someone who isn't linked to a company (e.g. HR with "Take employees'
# attendance") chooses which company those pages are for. The app sends that
# choice in the X-Acting-Company header (ActingCompanyMiddleware keeps it for
# the request); it only counts for people who have a company permission.
# ---------------------------------------------------------------------------
_acting_company_id = ContextVar("acting_company_id", default=None)


class ActingCompanyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _acting_company_id.set(request.headers.get("X-Acting-Company"))
        try:
            return self.get_response(request)
        finally:
            _acting_company_id.reset(token)


def company_permission_codes():
    from .models import Permission

    return set(Permission.objects.filter(area="Company").values_list("code", flat=True))


def own_role_permissions(profile):
    """What the user's roles give them, without the Super admin role (as /api/me/ role_permissions)."""
    from .models import Role

    return set(
        active_roles(profile).exclude(code=Role.SUPER_ADMIN)
        .values_list("permissions__code", flat=True).exclude(permissions__code=None)
    )


def company_choices(user):
    """The companies someone not linked to a company may open company pages for (none if they can't)."""
    from .models import Company

    profile = getattr(user, "userprofile", None)
    if profile is None or profile.company_id is not None:
        return Company.objects.none()
    if not own_role_permissions(profile) & company_permission_codes():
        return Company.objects.none()
    return Company.objects.filter(deleted_at__isnull=True).order_by("name")


def get_company(user):
    """
    The service provider whose company pages this user works on: the company
    they work for, or, for someone not linked to one, the company they chose.
    """
    profile = getattr(user, "userprofile", None)
    if profile is None:
        return None
    if profile.company_id is not None:
        return profile.company
    raw = _acting_company_id.get()
    if not raw or not str(raw).isdigit():
        return None
    cached = getattr(user, "_acting_company", None)
    if cached is not None and str(cached.pk) == str(raw):
        return cached
    company = company_choices(user).filter(pk=int(raw)).first()
    user._acting_company = company
    return company


class PermissionRequired(BasePermission):
    """
    Each view lists which permissions it needs:
        read_perms  -> any of these allows GET
        write_perms -> any of these allows POST / PATCH / DELETE
    A view may also set `open_read = True`: any logged-in user may read it.
    """
    message = "You don't have permission to do this."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        deny_if_company_deactivated(request.user)
        if request.method in SAFE_METHODS:
            if getattr(view, "open_read", False):
                return True
            needed = getattr(view, "read_perms", ())
        else:
            needed = getattr(view, "write_perms", ())
        if request.user.is_superuser and not needed:
            return True  # a view that names no permission: super admins may use it
        # Super admins too: what the Super admin role has switched on
        return has_perm(request.user, *needed)
