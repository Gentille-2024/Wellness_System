from django.contrib import admin

from .models import Access


@admin.register(Access)
class AccessAdmin(admin.ModelAdmin):
    list_display = ("user", "full_name", "company_name", "refreshed_at")
    readonly_fields = ("refreshed_at",)
