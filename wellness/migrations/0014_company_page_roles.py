"""
Company staff get one role per page, so a boss can switch each page on or off
for a staff member: Dashboard, Record visits, Services & prices,
Employees attended and Employees attendance.
The old "Company receptionist" role is replaced by all five page roles.
"""

from django.db import migrations

NEW_PERMISSIONS = [
    ("view_company_dashboard", "Company dashboard", "Open the company dashboard", "Company"),
    ("view_company_services", "See services & prices", "See the company's services, prices and what EUCL covers", "Company"),
    ("view_employees_attended", "See employees attended", "See which EUCL employees came, what they used and the amounts", "Company"),
    ("take_attendance", "Take employees' attendance", "Tick, on the list of EUCL employees, the services each one is taking", "Company"),
]

PAGE_ROLES = [
    # code, name, description, permissions
    ("COMPANY_DASHBOARD", "Dashboard", "Opens the company dashboard", ["view_company_dashboard"]),
    ("COMPANY_RECORD_VISITS", "Record visits", "Finds an EUCL employee and ticks the services they used", ["record_visits"]),
    ("COMPANY_SERVICES", "Services & prices", "Sees the company's services, prices and what EUCL covers", ["view_company_services"]),
    ("COMPANY_EMPLOYEES_ATTENDED", "Employees attended", "Sees which EUCL employees came, what they used and the amounts", ["view_employees_attended"]),
    ("COMPANY_ATTENDANCE", "Employees attendance", "Ticks, on the list of EUCL employees, the services each one is taking", ["take_attendance"]),
]


def add_page_roles(apps, schema_editor):
    Permission = apps.get_model("wellness", "Permission")
    Role = apps.get_model("wellness", "Role")
    UserProfile = apps.get_model("wellness", "UserProfile")

    for code, name, description, area in NEW_PERMISSIONS:
        Permission.objects.update_or_create(code=code, defaults={"name": name, "description": description, "area": area})

    page_roles = []
    for code, name, description, perms in PAGE_ROLES:
        # A role the admin already created with the same name is reused
        role = Role.objects.filter(code=code).first() or Role.objects.filter(name=name).first() or Role(code=code)
        role.name, role.description, role.is_company_role, role.is_system = name, description, True, True
        role.save()
        role.permissions.set(Permission.objects.filter(code__in=perms))
        page_roles.append(role)

    # The boss can open every page
    boss = Role.objects.filter(code="COMPANY_BOSS").first()
    if boss is not None:
        boss.permissions.add(*Permission.objects.filter(code__in=[code for code, *_ in NEW_PERMISSIONS]))

    # Receptionists keep what they could do, now as page roles
    receptionist = Role.objects.filter(code="COMPANY_RECEPTIONIST").first()
    if receptionist is not None:
        for profile in UserProfile.objects.filter(roles=receptionist):
            profile.roles.add(*page_roles)
            profile.roles.remove(receptionist)
        receptionist.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("wellness", "0013_eucl_agreed_price"),
    ]

    operations = [
        migrations.RunPython(add_page_roles, migrations.RunPython.noop),
    ]
