"""
- A company boss can create roles for their own company (Role.company).
- Role names are unique per company instead of across the platform.
- "Employees attendance" is for receptionists only: the boss role loses it.
"""

import django.db.models.deletion
from django.db import migrations, models


def boss_without_attendance(apps, schema_editor):
    Role = apps.get_model("wellness", "Role")
    Permission = apps.get_model("wellness", "Permission")
    boss = Role.objects.filter(code="COMPANY_BOSS").first()
    if boss is not None:
        boss.permissions.remove(*Permission.objects.filter(code="take_attendance"))


def boss_with_attendance(apps, schema_editor):
    Role = apps.get_model("wellness", "Role")
    Permission = apps.get_model("wellness", "Permission")
    boss = Role.objects.filter(code="COMPANY_BOSS").first()
    if boss is not None:
        boss.permissions.add(*Permission.objects.filter(code="take_attendance"))


class Migration(migrations.Migration):

    dependencies = [
        ("wellness", "0014_company_page_roles"),
    ]

    operations = [
        migrations.AlterField(
            model_name="role",
            name="name",
            field=models.CharField(max_length=100),
        ),
        migrations.AddField(
            model_name="role",
            name="company",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="own_roles",
                to="wellness.company",
            ),
        ),
        migrations.RunPython(boss_without_attendance, boss_with_attendance),
    ]
