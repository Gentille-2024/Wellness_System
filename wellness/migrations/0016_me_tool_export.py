"""
For the M&E tool:
- Visit.updated_at, so the M&E tool syncs only what changed.
- Three permissions (area "M&E") and two roles:
    M&E officer       -> see M&E dashboards, manage targets
    M&E sync service  -> export data (for the M&E tool's service account)
  EUCL HR can also see the M&E dashboards.
"""

import django.utils.timezone
from django.db import migrations, models

PERMISSIONS = [
    ("export_data", "Export data for M&E", "Read-only access used by the M&E tool to sync its data", "M&E"),
    ("view_me_dashboards", "See M&E dashboards", "Open the M&E dashboards, indicators and reports for all companies", "M&E"),
    ("manage_me_targets", "Manage M&E targets", "Set the targets of the M&E indicators", "M&E"),
]

ROLES = [
    ("ME_OFFICER", "M&E officer", "Follows the M&E dashboards and sets the indicator targets", ["view_me_dashboards", "manage_me_targets"]),
    ("ME_SYNC", "M&E sync service", "Service account the M&E tool uses to read this system's data", ["export_data"]),
]


def add_permissions(apps, schema_editor):
    Permission = apps.get_model("wellness", "Permission")
    Role = apps.get_model("wellness", "Role")
    for code, name, description, area in PERMISSIONS:
        Permission.objects.update_or_create(code=code, defaults={"name": name, "description": description, "area": area})
    for code, name, description, perms in ROLES:
        role = Role.objects.filter(code=code).first() or Role.objects.filter(name=name, company__isnull=True).first() or Role(code=code)
        role.name, role.description, role.is_company_role, role.is_system = name, description, False, True
        role.save()
        role.permissions.set(Permission.objects.filter(code__in=perms))
    hr = Role.objects.filter(code="EUCL_HR").first()
    if hr is not None:
        hr.permissions.add(*Permission.objects.filter(code="view_me_dashboards"))


class Migration(migrations.Migration):

    dependencies = [
        ("wellness", "0015_company_own_roles"),
    ]

    operations = [
        migrations.AddField(
            model_name="visit",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, db_index=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.RunPython(add_permissions, migrations.RunPython.noop),
    ]
