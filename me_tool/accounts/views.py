from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from warehouse.client import sign_in

from .models import Access

User = get_user_model()


def _save_access(profile):
    """Create or update the local user from the wellness /api/me/ data."""
    user, _ = User.objects.get_or_create(username=profile["username"])
    user.first_name = (profile.get("first_name") or "")[:150]
    user.last_name = (profile.get("last_name") or "")[:150]
    user.email = profile.get("email") or ""
    user.set_unusable_password()  # passwords stay in the wellness system
    user.save()
    company = profile.get("company") or {}
    Access.objects.update_or_create(
        user=user,
        defaults={
            "wellness_user_id": profile.get("id"),
            "full_name": profile.get("full_name") or profile["username"],
            "role_names": profile.get("role_names") or [],
            "permissions": profile.get("permissions") or [],
            "is_wellness_superuser": bool(profile.get("is_superuser")),
            "company_id": company.get("id"),
            "company_name": company.get("name") or "",
        },
    )
    return user


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboards:overview")
    error = ""
    username = ""
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        profile, error = sign_in(username, password)
        user = None
        if profile is not None:
            user = _save_access(profile)
            if not user.access.has_access:
                user, error = None, "Your account has no access to the M&E tool. Ask EUCL to give you an M&E role."
        else:
            # An emergency local account (createsuperuser) still works when
            # the wellness system is down
            local = authenticate(request, username=username, password=password)
            if local is not None and local.is_superuser:
                user, error = local, ""
        if user is not None:
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            target = request.POST.get("next") or request.GET.get("next")
            if target and url_has_allowed_host_and_scheme(target, {request.get_host()}, request.is_secure()):
                return redirect(target)
            return redirect("dashboards:overview")
    return render(request, "accounts/login.html", {"error": error, "username": username, "next": request.GET.get("next", "")})


@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, "You have signed out.")
    return redirect("accounts:login")
