"""What part of the data a request may see, and helpers to enforce it."""

from dataclasses import dataclass
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404

from .models import access_for


@dataclass(frozen=True)
class Scope:
    """all=True: every company. Otherwise only company_id."""

    all: bool
    company_id: int | None = None

    def visits(self, queryset):
        return queryset if self.all else queryset.filter(company_id=self.company_id)

    def companies(self, queryset):
        return queryset if self.all else queryset.filter(id=self.company_id)

    def allows_company(self, company_id):
        return self.all or company_id == self.company_id

    def narrowed(self, company_id):
        """Scope for one company, if allowed (EUCL may look at any company)."""
        if company_id is None:
            return self
        if not self.allows_company(company_id):
            raise Http404("Company not found")
        return Scope(all=False, company_id=company_id)


def scope_for(user):
    access = access_for(user)
    if access.sees_all:
        return Scope(all=True)
    if access.own_company_id is not None:
        return Scope(all=False, company_id=access.own_company_id)
    raise PermissionDenied("Your account has no access to the M&E tool.")


def me_view(test=None):
    """Login required, M&E access required, and optionally test(access)."""

    def decorator(view):
        @login_required
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            access = access_for(request.user)
            if not access.has_access or (test and not test(access)):
                raise PermissionDenied("You don't have permission to open this page.")
            request.access = access
            request.scope = scope_for(request.user)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
