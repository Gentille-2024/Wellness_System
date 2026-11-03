"""
A history of service prices: every price given or changed, with who did it
(name, username and roles at that moment) and when. Read by the permission
"See price changes": Super admin and HR.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def add_permission(apps, schema_editor):
    Permission = apps.get_model("wellness", "Permission")
    Role = apps.get_model("wellness", "Role")
    permission, _ = Permission.objects.update_or_create(
        code="view_price_changes",
        defaults={
            "name": "See price changes",
            "description": "See every change of a service price: old and new price, who changed it (boss, receptionist…) and when",
            "area": "Platform",
            "is_builtin": True,
        },
    )
    for role in Role.objects.filter(code__in=["SUPER_ADMIN", "EUCL_HR"]):
        role.permissions.add(permission)


def remove_permission(apps, schema_editor):
    apps.get_model("wellness", "Permission").objects.filter(code="view_price_changes").delete()


class Migration(migrations.Migration):

    dependencies = [
        ('wellness', '0022_feedback_comment_or_complaint'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PriceChange',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('old_price', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('new_price', models.DecimalField(decimal_places=2, max_digits=12)),
                ('changed_by_name', models.CharField(blank=True, max_length=310)),
                ('changed_by_username', models.CharField(blank=True, max_length=150)),
                ('changed_by_roles', models.CharField(blank=True, max_length=255)),
                ('changed_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('changed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='price_changes', to='wellness.company')),
                ('service', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='price_changes', to='wellness.service')),
            ],
            options={
                'ordering': ['-changed_at', '-id'],
            },
        ),
        migrations.RunPython(add_permission, remove_permission),
    ]
