from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from . import collectors
from .models import DatabaseSnapshot, ResourceSample


def save_sample(now=None):
    """Store one ResourceSample from collectors.collect_all() (taken now if not given)."""
    now = now or collectors.collect_all()
    server = now["server"] or {}
    redis = now["redis"] or {}
    api = now["api"] or {}
    return ResourceSample.objects.create(
        cpu_percent=server.get("cpu_percent"),
        cpu_count=server.get("cpu_count"),
        cpu_mhz=server.get("cpu_mhz"),
        load_1=server.get("load_1"),
        memory_used=server.get("memory_used"),
        memory_total=server.get("memory_total"),
        disk_used=server.get("disk_used"),
        disk_total=server.get("disk_total"),
        db_size=now["db_size"],
        db_ms=now["db_ms"],
        redis_memory=redis.get("memory"),
        redis_ms=redis.get("ms"),
        queue_length=redis.get("queue_length"),
        workers_online=len(now["workers"]) if now["workers"] is not None else None,
        api_ms=api.get("ms"),
        api_ok=api.get("ok"),
        media_size=(now["media"] or {}).get("bytes"),
    )


def save_database_snapshot():
    """Today's database size and table rows (one per day; re-running updates it)."""
    tables = collectors.database_tables() or []
    snapshot, _ = DatabaseSnapshot.objects.update_or_create(
        taken_on=timezone.localdate(),
        defaults={"db_size": collectors.database_size(), "tables": tables, "total_rows": sum(t["rows"] for t in tables)},
    )
    return snapshot


@shared_task
def collect_resources():
    """Every MONITOR_INTERVAL_MINUTES (Celery beat); old samples are removed."""
    sample = save_sample()
    cutoff = timezone.now() - timedelta(days=settings.MONITOR_RETENTION_DAYS)
    removed, _ = ResourceSample.objects.filter(taken_at__lt=cutoff).delete()
    return f"sample {sample.id}, removed {removed} old"


@shared_task
def database_snapshot():
    """Once a day (Celery beat)."""
    snapshot = save_database_snapshot()
    return f"{snapshot.taken_on}: {snapshot.total_rows} rows, {snapshot.db_size} bytes"
