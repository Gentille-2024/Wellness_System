"""
One role per user: every role has its own permissions, so nobody holds two.
- Everyone who has several roles keeps only one, in this order:
  Super admin, Company boss, HR, M&E officer, Receptionist, any other role,
  Employee. (An EUCL employee keeps their Employee record whatever role they have.)
- HR-department employees now have HR instead of Employee + HR: the HR role
  already holds every "My wellness" page.
- Receptionist no longer has "See feedback on our services" (the company's
  Feedback page): only the Company boss reads it.
"""

from django.db import migrations

PRIORITY = ["SUPER_ADMIN", "COMPANY_BOSS", "EUCL_HR", "ME_OFFICER", "COMPANY_RECEPTIONIST"]


def rank(role):
    if role.code in PRIORITY:
        return (PRIORITY.index(role.code), "")
    if role.code == "EMPLOYEE":
        return (len(PRIORITY) + 1, "")
    return (len(PRIORITY), role.name.lower())


def forwards(apps, schema_editor):
    Permission = apps.get_model("wellness", "Permission")
    Role = apps.get_model("wellness", "Role")
    UserProfile = apps.get_model("wellness", "UserProfile")

    receptionist = Role.objects.filter(code="COMPANY_RECEPTIONIST").first()
    if receptionist is not None:
        receptionist.permissions.remove(*Permission.objects.filter(code="view_company_feedback"))

    super_admin = Role.objects.filter(code="SUPER_ADMIN").first()
    for profile in UserProfile.objects.select_related("user").prefetch_related("roles"):
        roles = list(profile.roles.all())
        if profile.user.is_superuser and super_admin is not None:
            keep = super_admin
        elif len(roles) > 1:
            keep = min(roles, key=rank)
        else:
            continue
        profile.roles.set([keep])
        if not keep.is_company_role and profile.company_id is not None:
            profile.company = None  # only company staff are linked to a company
            profile.save(update_fields=["company"])


class Migration(migrations.Migration):

    dependencies = [
        ("wellness", "0025_hr_employees_attended"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
