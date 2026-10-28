from django.contrib import admin

from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("created_at", "period_type", "period_start", "company", "format", "is_automatic", "requested_by", "status")
    list_filter = ("period_type", "status", "format", "is_automatic")
