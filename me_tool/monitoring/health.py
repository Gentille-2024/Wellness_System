"""
Turns the measurements into checks with a status:
  ok, warn (needs attention), fail (not working), unknown (can't be measured here)
The limits come from settings (MONITOR_ALERT_* in .env).
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from warehouse.models import SyncState

OK, WARN, FAIL, UNKNOWN = "ok", "warn", "fail", "unknown"
LABELS = {OK: "OK", WARN: "Attention", FAIL: "Down", UNKNOWN: "Not measured"}


def _pct(used, total):
    return round(used * 100 / total, 1) if used is not None and total else None


def _p(value):
    """12% / 0.4% (one decimal below 10, so small values don't show as 0%)."""
    return f"{value:.1f}%" if value < 10 else f"{value:.0f}%"


def _check(name, status, value, detail=""):
    return {"name": name, "status": status, "label": LABELS[status], "value": value, "detail": detail}


def checks(now, growth=None):
    """`now` is collectors.collect_all(); `growth` is growth.database_growth()."""
    limits = settings.MONITOR_ALERTS
    out = []
    server = now["server"]

    if server:
        cpu = server["cpu_percent"]
        out.append(_check("CPU", WARN if cpu >= limits["cpu"] else OK, _p(cpu),
                          f"{server['cpu_count']} cores" + (f" · {server['cpu_mhz']} MHz" if server["cpu_mhz"] else "")))
        mem = _pct(server["memory_used"], server["memory_total"])
        out.append(_check("Memory", WARN if mem >= limits["memory"] else OK, _p(mem), "used"))
        disk = _pct(server["disk_used"], server["disk_total"])
        disk_status = FAIL if disk >= 95 else WARN if disk >= limits["disk"] else OK
        detail = "used"
        if growth and growth.get("days_until_full") is not None:
            days = growth["days_until_full"]
            detail = f"full in about {days:,} days at the current growth"
            if days < 30 and disk_status == OK:
                disk_status = WARN
        out.append(_check("Disk", disk_status, _p(disk), detail))
    else:
        out.append(_check("Server", UNKNOWN, "—", "CPU, memory and disk could not be read"))

    if now["db_ms"] is None:
        out.append(_check("Database", FAIL, "—", "no answer"))
    else:
        out.append(_check("Database", WARN if now["db_ms"] >= limits["db_ms"] else OK, f"{now['db_ms']:.1f} ms", "simple query"))

    redis = now["redis"]
    if redis is None:
        uses_redis = settings.CELERY_BROKER_URL.startswith("redis") and not settings.CELERY_TASK_ALWAYS_EAGER
        out.append(_check("Redis", FAIL if uses_redis else UNKNOWN, "—", "no answer" if uses_redis else "not used here"))
    else:
        queue = redis["queue_length"]
        out.append(_check("Task queue", WARN if queue >= limits["queue"] else OK, f"{queue} waiting", "jobs not started yet"))

    workers = now["workers"]
    if workers is None:
        out.append(_check("Celery workers", UNKNOWN, "—", "tasks run straight away here"))
    else:
        out.append(_check("Celery workers", OK if workers else FAIL, f"{len(workers)} online", ", ".join(workers) or "none answered"))

    api = now["api"]
    if api is None or not api["ok"]:
        out.append(_check("Wellness API", FAIL, "—", f"can't reach {settings.WELLNESS_API_URL}"))
    else:
        out.append(_check("Wellness API", WARN if api["ms"] >= limits["api_ms"] else OK, f"{api['ms']:.0f} ms", "response time"))

    state = SyncState.get()
    if state.last_success_at is None:
        out.append(_check("Data sync", WARN, "never", "no successful sync yet"))
    else:
        age = timezone.now() - state.last_success_at
        hours = age.total_seconds() / 3600
        stale = age > timedelta(hours=limits["sync_hours"])
        status = FAIL if state.last_error and stale else WARN if stale or state.last_error else OK
        detail = f"last error: {state.last_error[:80]}" if state.last_error else "last successful sync"
        value = f"{int(age.total_seconds() // 60)} min ago" if hours < 1 else f"{hours:.1f} h ago"
        out.append(_check("Data sync", status, value, detail))
    return out


def overall(items):
    statuses = {c["status"] for c in items}
    return FAIL if FAIL in statuses else WARN if WARN in statuses else OK
