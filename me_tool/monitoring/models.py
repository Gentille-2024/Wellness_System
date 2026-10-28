"""
Resource history for the System resources page.

ResourceSample     every few minutes: CPU, memory, disk, database, Redis,
                   Celery and the wellness API (kept MONITOR_RETENTION_DAYS)
DatabaseSnapshot   once a day: the database size and every table's rows and
                   size, for the growth chart and projections (kept for good)
"""

from django.db import models


class ResourceSample(models.Model):
    taken_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # Server (in Docker: the Docker host / VM as seen from the container)
    cpu_percent = models.FloatField(null=True, blank=True)
    cpu_count = models.PositiveSmallIntegerField(null=True, blank=True)
    cpu_mhz = models.FloatField(null=True, blank=True)
    load_1 = models.FloatField(null=True, blank=True, help_text="Average runnable processes over 1 minute")
    memory_used = models.BigIntegerField(null=True, blank=True)
    memory_total = models.BigIntegerField(null=True, blank=True)
    disk_used = models.BigIntegerField(null=True, blank=True)
    disk_total = models.BigIntegerField(null=True, blank=True)

    # Database, Redis and Celery
    db_size = models.BigIntegerField(null=True, blank=True)
    db_ms = models.FloatField(null=True, blank=True, help_text="Time for a simple query")
    redis_memory = models.BigIntegerField(null=True, blank=True)
    redis_ms = models.FloatField(null=True, blank=True)
    queue_length = models.IntegerField(null=True, blank=True, help_text="Tasks waiting for a worker")
    workers_online = models.IntegerField(null=True, blank=True)

    # The wellness system's API
    api_ms = models.FloatField(null=True, blank=True)
    api_ok = models.BooleanField(null=True, blank=True)

    # Report files
    media_size = models.BigIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-taken_at"]

    @property
    def memory_percent(self):
        return round(self.memory_used * 100 / self.memory_total, 1) if self.memory_used and self.memory_total else None

    @property
    def disk_percent(self):
        return round(self.disk_used * 100 / self.disk_total, 1) if self.disk_used and self.disk_total else None


class DatabaseSnapshot(models.Model):
    taken_on = models.DateField(unique=True)
    db_size = models.BigIntegerField(null=True, blank=True)
    # [{"table": "warehouse_visit", "label": "Visits", "rows": 1234, "bytes": 245760}, ...]
    tables = models.JSONField(default=list, blank=True)
    total_rows = models.BigIntegerField(default=0)

    class Meta:
        ordering = ["-taken_on"]
