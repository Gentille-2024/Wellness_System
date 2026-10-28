from django.contrib import admin

from .models import DatabaseSnapshot, ResourceSample


@admin.register(ResourceSample)
class ResourceSampleAdmin(admin.ModelAdmin):
    list_display = ("taken_at", "cpu_percent", "memory_percent", "disk_percent", "db_size", "db_ms", "queue_length", "workers_online", "api_ok")
    date_hierarchy = "taken_at"


@admin.register(DatabaseSnapshot)
class DatabaseSnapshotAdmin(admin.ModelAdmin):
    list_display = ("taken_on", "db_size", "total_rows")
