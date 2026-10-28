from django.contrib import admin

from .models import (
    Company,
    Employee,
    Payment,
    Permission,
    Role,
    Service,
    UserProfile,
    Visit,
)

admin.site.register(Permission)
admin.site.register(Role)
admin.site.register(UserProfile)
admin.site.register(Company)
admin.site.register(Service)
admin.site.register(Employee)
admin.site.register(Visit)
admin.site.register(Payment)
