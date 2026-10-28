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
    ("view_all_visits", "See all visits", "See every visit at every company", "Platform"),
    ("manage_payments", "Manage payments", "See amounts owed and mark periods as paid", "Platform"),
    # EUCL
    ("manage_employees", "Manage EUCL employees", "Onboard, edit and deactivate EUCL employees", "EUCL"),
    # Company (service provider) staff
    ("record_visits", "Record visits", "Tick the services an employee used at the company", "Company"),
    ("view_company_visits", "See company visits & payments", "See the company's visits, amounts and payments", "Company"),
    ("manage_company_services", "Manage company services", "Add services and set their prices", "Company"),
    ("manage_company_staff", "Manage company staff", "Create receptionist and other staff logins for the company", "Company"),
    ("view_company_dashboard", "Company dashboard", "Open the company dashboard", "Company"),
    ("view_company_services", "See services & prices", "See the company's services, prices and what EUCL covers", "Company"),
    ("view_employees_attended", "See employees attended", "See which EUCL employees came, what they used and the amounts", "Company"),
    ("take_attendance", "Take employees' attendance", "Tick, on the list of EUCL employees, the services each one is taking", "Company"),
    # M&E tool (a separate application that reads this system's data)
    ("export_data", "Export data for M&E", "Read-only access used by the M&E tool to sync its data", "M&E"),
    ("view_me_dashboards", "See M&E dashboards", "Open the M&E dashboards, indicators and reports for all companies", "M&E"),
    ("manage_me_targets", "Manage M&E targets", "Set the targets of the M&E indicators", "M&E"),
    # EUCL employees
    ("use_services", "Use wellness services", "Browse companies and services, see own visits", "Employee"),
]

ALL_PERMISSIONS = {code for code, *_ in PERMISSIONS}

# What a company boss may put in a role they create for their own company:
# the company pages, but not managing staff (only EUCL decides who may do that)
COMPANY_ROLE_PERMISSIONS = {
    code for code, _name, _description, area in PERMISSIONS if area == "Company"
} - {"manage_company_staff"}


def get_permissions(user):
    """The set of permission codes a user has through all of their roles."""
    if not user or not user.is_authenticated:
        return set()
    if user.is_superuser:
        return set(ALL_PERMISSIONS)
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


def get_company(user):
    """The service provider a company staff member works for, or None."""
    profile = getattr(user, "userprofile", None)
    return profile.company if profile else None


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
        if request.user.is_superuser:
            return True
        deny_if_company_deactivated(request.user)
        if request.method in SAFE_METHODS:
            if getattr(view, "open_read", False):
                return True
            needed = getattr(view, "read_perms", ())
        else:
            needed = getattr(view, "write_perms", ())
        return has_perm(request.user, *needed)
