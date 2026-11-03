"""
"See employees attended" for EUCL: which EUCL employees used services at
every company, what they used and the amounts. Given to HR (and the super
admin, who starts with every permission).
"""

from django.db import migrations


def add_permission(apps, schema_editor):
    Permission = apps.get_model("wellness", "Permission")
    Role = apps.get_model("wellness", "Role")
    permission, _ = Permission.objects.update_or_create(
        code="view_all_employees_attended",
        defaults={
            "name": "See employees attended (all companies)",
            "description": "See which EUCL employees used services at every company, what they used and the amounts",
            "area": "EUCL",
            "is_builtin": True,
        },
    )
    for role in Role.objects.filter(code__in=["SUPER_ADMIN", "EUCL_HR"]):
        role.permissions.add(permission)


def remove_permission(apps, schema_editor):
    apps.get_model("wellness", "Permission").objects.filter(code="view_all_employees_attended").delete()


class Migration(migrations.Migration):
    dependencies = [("wellness", "0024_edit_service_prices")]
    operations = [migrations.RunPython(add_permission, remove_permission)]
