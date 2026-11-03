"""
"Edit service prices": change the price of the company's services without
being able to add services or switch them off. Given to the receptionist
(and the boss and super admin, who can already do more).
"""

from django.db import migrations


def add_permission(apps, schema_editor):
    Permission = apps.get_model("wellness", "Permission")
    Role = apps.get_model("wellness", "Role")
    permission, _ = Permission.objects.update_or_create(
        code="edit_service_prices",
        defaults={
            "name": "Edit service prices",
            "description": "Change the prices of the company's services (not add or switch them off)",
            "area": "Company",
            "is_builtin": True,
        },
    )
    for role in Role.objects.filter(code__in=["SUPER_ADMIN", "COMPANY_BOSS", "COMPANY_RECEPTIONIST"]):
        role.permissions.add(permission)


def remove_permission(apps, schema_editor):
    apps.get_model("wellness", "Permission").objects.filter(code="edit_service_prices").delete()


class Migration(migrations.Migration):
    dependencies = [("wellness", "0023_price_changes")]
    operations = [migrations.RunPython(add_permission, remove_permission)]
