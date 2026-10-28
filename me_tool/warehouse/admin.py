from django.contrib import admin

from .models import Company, Employee, Payment, Service, SyncRun, Visit


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "is_active", "deleted_at")


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "company", "price", "is_covered", "eucl_price", "is_active")
    list_filter = ("company", "is_covered")


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "first_name", "last_name", "department", "is_active")
    search_fields = ("code", "first_name", "last_name")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "period_start", "period_end", "amount", "paid_at")


@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display = ("id", "visit_date", "employee", "service", "company", "price", "payment")
    list_filter = ("company",)
    date_hierarchy = "visit_date"


@admin.register(SyncRun)
class SyncRunAdmin(admin.ModelAdmin):
    list_display = ("started_at", "kind", "status", "counts", "message")
