"""
- The company boss can open "Employees attendance" again.
- EUCL pays the company's own price: eucl_price now mirrors Service.price.
- "Visits" are called "Services" on screen: permission and role names follow.
"""

from django.db import migrations
from django.db.models import F

NAMES = [
    # permission code, new name, new description
    ("view_all_visits", "See all services used", "See every service used at every company"),
    ("record_visits", "Record services", "Tick the services an employee used at the company"),
    ("view_company_visits", "See company services used & payments", "See the services used at the company, amounts and payments"),
    ("use_services", "Use wellness services", "Browse companies and services, see own services used"),
]


def forwards(apps, schema_editor):
    Permission = apps.get_model("wellness", "Permission")
    Role = apps.get_model("wellness", "Role")
    Service = apps.get_model("wellness", "Service")

    boss = Role.objects.filter(code="COMPANY_BOSS").first()
    if boss is not None:
        boss.permissions.add(*Permission.objects.filter(code="take_attendance"))

    Service.objects.filter(is_approved=True).update(eucl_price=F("price"))
    Service.objects.filter(is_approved=False).update(eucl_price=None)

    for code, name, description in NAMES:
        Permission.objects.filter(code=code).update(name=name, description=description)
    Role.objects.filter(code="COMPANY_RECORD_VISITS", name="Record visits").update(
        name="Record services", description="Finds an EUCL employee and ticks the services they used"
    )


def backwards(apps, schema_editor):
    Permission = apps.get_model("wellness", "Permission")
    Role = apps.get_model("wellness", "Role")
    boss = Role.objects.filter(code="COMPANY_BOSS").first()
    if boss is not None:
        boss.permissions.remove(*Permission.objects.filter(code="take_attendance"))
    Role.objects.filter(code="COMPANY_RECORD_VISITS", name="Record services").update(name="Record visits")


class Migration(migrations.Migration):

    dependencies = [
        ("wellness", "0016_me_tool_export"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
