from datetime import timedelta

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.scope import me_view

from . import collectors, health
from .growth import database_growth
from .models import DatabaseSnapshot, ResourceSample
from .tasks import save_database_snapshot, save_sample

RANGES = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}


def _history_chart(samples, range_key):
    fmt = "%H:%M" if range_key == "24h" else "%d %b %H:%M"
    return {
        "type": "line",
        "labels": [s.taken_at.astimezone(timezone.get_current_timezone()).strftime(fmt) for s in samples],
        "datasets": [
            {"label": "CPU (%)", "data": [s.cpu_percent for s in samples], "color": "--chart-1"},
            {"label": "Memory (%)", "data": [s.memory_percent for s in samples], "color": "--chart-2"},
            {"label": "Disk (%)", "data": [s.disk_percent for s in samples], "color": "--chart-3"},
        ],
    }


def _response_chart(samples, range_key):
    fmt = "%H:%M" if range_key == "24h" else "%d %b %H:%M"
    return {
        "type": "line",
        "labels": [s.taken_at.astimezone(timezone.get_current_timezone()).strftime(fmt) for s in samples],
        "datasets": [
            {"label": "Database (ms)", "data": [s.db_ms for s in samples], "color": "--chart-1"},
            {"label": "Wellness API (ms)", "data": [s.api_ms for s in samples], "color": "--chart-4"},
        ],
    }


@me_view(lambda access: access.is_admin)
def system(request):
    range_key = request.GET.get("range") if request.GET.get("range") in RANGES else "24h"
    now = collectors.collect_all()
    # The first visit of the day also takes today's database snapshot
    if not DatabaseSnapshot.objects.filter(taken_on=timezone.localdate()).exists():
        save_database_snapshot()
    disk_free = (now["server"] or {}).get("disk_free")
    growth = database_growth(disk_free)
    items = health.checks(now, growth)

    samples = list(ResourceSample.objects.filter(taken_at__gte=timezone.now() - RANGES[range_key]).order_by("taken_at"))
    tables = growth["tables"] or (collectors.database_tables() or [])
    top = [t for t in tables if t["own"]][:10]
    return render(request, "monitoring/system.html", {
        "now": now,
        "server": now["server"],
        "checks": items,
        "overall": health.overall(items),
        "growth": growth,
        "tables": tables,
        "range_key": range_key,
        "ranges": [("24h", "24 hours"), ("7d", "7 days"), ("30d", "30 days")],
        "samples_count": len(samples),
        "latest_sample": ResourceSample.objects.first(),
        "history_chart": _history_chart(samples, range_key),
        "response_chart": _response_chart(samples, range_key),
        "db_chart": {
            "type": "line",
            "labels": growth["labels"],
            "datasets": [{"label": "Database size (MB)", "data": growth["sizes_mb"], "color": "--chart-1"}],
            "legend": False,
        },
        "rows_chart": {
            "type": "bar",
            "horizontal": True,
            "labels": [t["label"] for t in top],
            "datasets": [{"label": "Rows", "data": [t["rows"] for t in top], "color": "--chart-2"}],
            "legend": False,
        },
    })


@require_POST
@me_view(lambda access: access.is_admin)
def measure_now(request):
    save_sample()
    save_database_snapshot()
    messages.success(request, "Measured now and saved to the history.")
    return redirect("monitoring:system")
