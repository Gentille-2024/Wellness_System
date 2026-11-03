"""
"Use wellness services" becomes one permission per page of My wellness:
Overview, Places & services and My services. Every role that had it gets all
three (Employee, HR, Super admin...).
"""

from django.db import migrations

NEW = [
    ("view_my_overview", "Overview", "Open My wellness: today, this month and the latest services"),
    ("view_places", "Places & services", "Browse the partner places and the services EUCL covers"),
    ("view_my_services", "My services", "See and export the services I used"),
]


def forwards(apps, schema_editor):
    Permission = apps.get_model("wellness", "Permission")
    Role = apps.get_model("wellness", "Role")
    new = [
        Permission.objects.update_or_create(
            code=code, defaults={"name": name, "description": description, "area": "Employee", "is_builtin": True}
        )[0]
        for code, name, description in NEW
    ]
    old = Permission.objects.filter(code="use_services").first()
    roles = Role.objects.filter(permissions=old) if old else Role.objects.filter(code="EMPLOYEE")
    for role in roles:
        role.permissions.add(*new)
    if old is not None:
        old.delete()


def backwards(apps, schema_editor):
    Permission = apps.get_model("wellness", "Permission")
    Role = apps.get_model("wellness", "Role")
    old, _ = Permission.objects.get_or_create(
        code="use_services",
        defaults={"name": "Use wellness services", "description": "Browse companies and services, see own services used", "area": "Employee"},
    )
    for role in Role.objects.filter(permissions__code__in=[code for code, *_ in NEW]).distinct():
        role.permissions.add(old)
    Permission.objects.filter(code__in=[code for code, *_ in NEW]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("wellness", "0019_five_roles_custom_permissions"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
