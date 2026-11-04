"""
Company boss and Receptionist are always company roles, and HR, M&E officer,
Employee and Super admin always EUCL roles (a role used to change kind by
itself when one non-company permission was switched on, which could unlink
bosses from their company).
"""

from django.db import migrations

FIXED_KIND = {
    "SUPER_ADMIN": False, "EMPLOYEE": False, "EUCL_HR": False, "ME_OFFICER": False,
    "COMPANY_BOSS": True, "COMPANY_RECEPTIONIST": True,
}


def forwards(apps, schema_editor):
    Role = apps.get_model("wellness", "Role")

    for code, kind in FIXED_KIND.items():
        Role.objects.filter(code=code).update(is_company_role=kind)
    Role.objects.filter(company__isnull=False).update(is_company_role=True)


class Migration(migrations.Migration):

    dependencies = [
        ("wellness", "0026_one_role_per_user"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
