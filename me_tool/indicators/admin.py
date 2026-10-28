from django.contrib import admin

from .models import Indicator, Target


@admin.register(Indicator)
class IndicatorAdmin(admin.ModelAdmin):
    list_display = ("order", "name", "calculation", "unit", "direction", "per_company", "is_active")
    list_editable = ("is_active",)


@admin.register(Target)
class TargetAdmin(admin.ModelAdmin):
    list_display = ("indicator", "period", "company", "value", "set_by", "updated_at")
    list_filter = ("indicator", "company")
