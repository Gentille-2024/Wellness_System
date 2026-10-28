import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone

ROLES = [
    ("COMPANY", "Company admin"),
    ("HR", "HR"),
    ("RECEPTIONIST", "Receptionist"),
    ("EMPLOYEE", "Employee"),
]


def create_roles(apps, schema_editor):
    Role = apps.get_model("wellness", "Role")
    for code, name in ROLES:
        Role.objects.get_or_create(code=code, defaults={"name": name})


def copy_single_role_to_roles(apps, schema_editor):
    """Each profile had ONE role in `role`; give it the same role in `roles`."""
    Role = apps.get_model("wellness", "Role")
    UserProfile = apps.get_model("wellness", "UserProfile")
    roles = {role.code: role for role in Role.objects.all()}
    for profile in UserProfile.objects.all():
        role = roles.get((profile.role or "").upper())
        if role is not None:
            profile.roles.add(role)


def copy_roles_back(apps, schema_editor):
    """Undo: keep the first role as the single role."""
    UserProfile = apps.get_model("wellness", "UserProfile")
    for profile in UserProfile.objects.all():
        first = profile.roles.order_by("id").first()
        profile.role = first.code if first else ""
        profile.save(update_fields=["role"])


def make_current_benefits_ongoing(apps, schema_editor):
    """Benefits that have not ended yet now renew every day with no end date."""
    WellnessBenefit = apps.get_model("wellness", "WellnessBenefit")
    WellnessBenefit.objects.filter(valid_until__gte=timezone.localdate()).update(valid_until=None)


class Migration(migrations.Migration):

    dependencies = [
        ("wellness", "0009_free_text_service_names"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1) The Role table, with its four roles
        migrations.CreateModel(
            name="Role",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=20, unique=True)),
                ("name", models.CharField(max_length=50)),
            ],
        ),
        migrations.RunPython(create_roles, migrations.RunPython.noop),

        # 2) Profiles get MANY roles instead of one, keeping what they had
        migrations.AddField(
            model_name="userprofile",
            name="roles",
            field=models.ManyToManyField(blank=True, related_name="profiles", to="wellness.role"),
        ),
        migrations.RunPython(copy_single_role_to_roles, copy_roles_back),
        migrations.RemoveField(
            model_name="userprofile",
            name="role",
        ),
        migrations.AlterField(
            model_name="userprofile",
            name="company",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="managers", to="wellness.company",
            ),
        ),

        # 3) Benefits can be open-ended, and remember who switched them on/off
        migrations.AlterField(
            model_name="wellnessbenefit",
            name="valid_until",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="wellnessbenefit",
            name="activated_by",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="+", to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="wellnessbenefit",
            name="deactivated_by",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="+", to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(make_current_benefits_ongoing, migrations.RunPython.noop),
    ]
