"""
Measures the resources the M&E tool depends on.

Every function is safe: if something can't be measured (no Redis in local
development, no CPU frequency inside some containers...) it returns None
instead of failing, so the page and the scheduled job always work.
"""

import logging
import os
import time
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.db import connection

log = logging.getLogger(__name__)

# Tables of our own apps, with a readable name (Django's own tables are added too)
OWN_APPS = ["warehouse", "indicators", "reports", "monitoring", "accounts"]


def _safe(fn):
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # measuring must never break the page
            log.warning("Could not measure %s: %s", fn.__name__, exc)
            return None

    wrapper.__name__ = fn.__name__
    return wrapper


# ------------------------------------------------------------------ server

@_safe
def server():
    import psutil

    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(str(settings.MONITOR_DISK_PATH))
    freq = psutil.cpu_freq()
    try:
        load_1 = os.getloadavg()[0]
    except (AttributeError, OSError):  # Windows has no load average
        load_1 = None
    return {
        # measured over half a second, so the value is real (not 0.0)
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "cpu_count": psutil.cpu_count(),
        "cpu_mhz": round(freq.current) if freq and freq.current else None,
        "cpu_max_mhz": round(freq.max) if freq and freq.max else None,
        "load_1": round(load_1, 2) if load_1 is not None else None,
        "memory_used": memory.total - memory.available,
        "memory_total": memory.total,
        "disk_used": disk.used,
        "disk_total": disk.total,
        "disk_free": disk.free,
        "uptime_seconds": int(time.time() - psutil.boot_time()),
        "processes": len(psutil.pids()),
    }


# ---------------------------------------------------------------- database

@_safe
def database_ms():
    started = time.perf_counter()
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return round((time.perf_counter() - started) * 1000, 2)


@_safe
def database_size():
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_database_size(current_database())")
            return cursor.fetchone()[0]
    if connection.vendor == "sqlite":
        name = connection.settings_dict["NAME"]
        if name in (":memory:", "") or "mode=memory" in str(name):
            return None
        return sum(os.path.getsize(p) for p in (name, f"{name}-wal") if os.path.exists(p))
    return None


def _table_bytes():
    """{table: bytes on disk} (PostgreSQL only; SQLite doesn't say per table)."""
    if connection.vendor != "postgresql":
        return {}
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT c.relname, pg_total_relation_size(c.oid) FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind = 'r' AND n.nspname = current_schema()"
        )
        return dict(cursor.fetchall())


@_safe
def database_tables():
    """Every table with its rows (exact) and size, largest first."""
    sizes = _table_bytes()
    rows = []
    for model in apps.get_models():
        meta = model._meta
        if meta.proxy or not meta.managed:
            continue
        own = meta.app_label in OWN_APPS
        rows.append({
            "table": meta.db_table,
            "label": str(meta.verbose_name_plural).capitalize() if own else f"{meta.app_label}: {meta.verbose_name_plural}",
            "own": own,
            "rows": model._default_manager.count(),
            "bytes": sizes.get(meta.db_table),
        })
    rows.sort(key=lambda r: (-(r["bytes"] or 0), -r["rows"], r["table"]))
    return rows


# ---------------------------------------------------------- Redis / Celery

def _redis():
    import redis

    return redis.Redis.from_url(settings.CELERY_BROKER_URL, socket_timeout=1.5, socket_connect_timeout=1.5)


@_safe
def redis_info():
    if not settings.CELERY_BROKER_URL.startswith("redis"):
        return None
    client = _redis()
    started = time.perf_counter()
    client.ping()
    ms = round((time.perf_counter() - started) * 1000, 2)
    info = client.info("memory")
    return {
        "ms": ms,
        "memory": info.get("used_memory"),
        "peak": info.get("used_memory_peak"),
        # tasks waiting in the default Celery queue
        "queue_length": client.llen("celery"),
    }


@_safe
def workers():
    """Names of the Celery workers that answer (None when it can't be checked)."""
    if settings.CELERY_TASK_ALWAYS_EAGER:
        return None
    from config.celery import app

    replies = app.control.inspect(timeout=1.0).ping() or {}
    return sorted(replies)


# ----------------------------------------------------------- wellness API

@_safe
def wellness_api():
    """Reachable and how fast. 401/403 still means the API is up (it just wants a login)."""
    import requests

    started = time.perf_counter()
    response = requests.get(f"{settings.WELLNESS_API_URL}/api/places/", timeout=5)
    return {"ok": response.status_code < 500, "status": response.status_code,
            "ms": round((time.perf_counter() - started) * 1000, 1)}


# --------------------------------------------------------------- storage

@_safe
def media_usage():
    root = Path(settings.MEDIA_ROOT)
    if not root.exists():
        return {"bytes": 0, "files": 0}
    files = [p for p in root.rglob("*") if p.is_file()]
    return {"bytes": sum(p.stat().st_size for p in files), "files": len(files)}


def collect_all():
    """Everything at once (the page and the scheduled job)."""
    api = wellness_api()
    redis_data = redis_info()
    return {
        "server": server(),
        "db_ms": database_ms(),
        "db_size": database_size(),
        "redis": redis_data,
        "workers": workers(),
        "api": api,
        "media": media_usage(),
    }
