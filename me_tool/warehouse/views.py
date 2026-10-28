from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from accounts.scope import me_view

from .models import Company, Employee, Payment, Service, SyncRun, SyncState, Visit
from .tasks import sync_wellness


@me_view(lambda access: access.can_run_sync)
def sync_status(request):
    return render(request, "warehouse/sync.html", {
        "state": SyncState.get(),
        "runs": SyncRun.objects.all()[:25],
        "counts": {
            "Companies": Company.objects.count(),
            "Services": Service.objects.count(),
            "EUCL employees": Employee.objects.count(),
            "Payments": Payment.objects.count(),
            "Visits": Visit.objects.count(),
        },
    })


@require_POST
@me_view(lambda access: access.can_run_sync)
def sync_now(request):
    full = request.POST.get("full") == "1"
    try:
        sync_wellness.delay(full=full)
        messages.success(request, "Sync started. Refresh this page in a moment to see the result.")
    except Exception as exc:  # e.g. Redis not reachable, or the sync itself failed (eager mode)
        messages.error(request, f"The sync could not run: {exc}")
    return redirect("warehouse:sync")
