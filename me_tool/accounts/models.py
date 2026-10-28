"""
Who may see what in the M&E tool.

People sign in with their wellness system login (see views.login_view). Their
permissions are copied from the wellness system's /api/me/ at every sign-in,
so roles and permissions are managed in one place: the wellness system.

  sees_all       EUCL: admin, M&E officer, HR (permission view_me_dashboards),
                 finance (manage_payments) or anyone who sees all visits
  company        a service provider's staff (company dashboard / visits
                 permissions): only their own company
  manage_targets admin or "Manage M&E targets"
"""

from django.conf import settings
from django.db import models

EUCL_WIDE = {"view_me_dashboards", "view_all_visits", "manage_payments"}
COMPANY_PAGES = {"view_company_visits", "view_company_dashboard", "view_employees_attended"}


class Access(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="access")
    wellness_user_id = models.IntegerField(null=True, blank=True)
    full_name = models.CharField(max_length=300, blank=True)
    role_names = models.JSONField(default=list, blank=True)
    permissions = models.JSONField(default=list, blank=True)
    is_wellness_superuser = models.BooleanField(default=False)
    company_id = models.IntegerField(null=True, blank=True)
    company_name = models.CharField(max_length=200, blank=True)
    refreshed_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "M&E access"
        verbose_name_plural = "M&E access"

    def __str__(self):
        return f"{self.user} ({', '.join(self.role_names)})"

    @property
    def perms(self):
        return set(self.permissions)

    @property
    def is_admin(self):
        return self.is_wellness_superuser or "manage_users" in self.perms

    @property
    def sees_all(self):
        return self.is_admin or bool(self.perms & EUCL_WIDE)

    @property
    def own_company_id(self):
        """The one company this person may see (service provider staff)."""
        if self.sees_all or self.company_id is None:
            return None
        return self.company_id if self.perms & COMPANY_PAGES else None

    @property
    def has_access(self):
        return self.sees_all or self.own_company_id is not None

    @property
    def can_manage_targets(self):
        return self.is_admin or "manage_me_targets" in self.perms

    @property
    def can_see_names(self):
        """Employee names are for EUCL only; providers see totals."""
        return self.sees_all

    @property
    def can_run_sync(self):
        return self.is_admin


class LocalAdminAccess:
    """A local Django superuser (e.g. created with createsuperuser) is an admin."""

    is_admin = sees_all = has_access = can_manage_targets = can_see_names = can_run_sync = True
    own_company_id = None
    company_name = ""
    role_names = ["Local admin"]

    def __init__(self, user):
        self.full_name = user.get_full_name() or user.username


class NoAccess:
    is_admin = sees_all = has_access = can_manage_targets = can_see_names = can_run_sync = False
    own_company_id = None
    company_name = ""
    role_names = []
    full_name = ""


def access_for(user):
    if not user.is_authenticated:
        return NoAccess()
    try:
        return user.access
    except Access.DoesNotExist:
        return LocalAdminAccess(user) if user.is_superuser else NoAccess()
