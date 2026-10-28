"""Reports can be daily, weekly or monthly, and made automatically."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0001_initial"),
    ]

    operations = [
        # Existing reports are monthly: their "month" (the 1st) becomes the period start
        migrations.RenameField(model_name="report", old_name="month", new_name="period_start"),
        migrations.AlterField(
            model_name="report",
            name="period_start",
            field=models.DateField(),
        ),
        migrations.AddField(
            model_name="report",
            name="period_type",
            field=models.CharField(
                choices=[("day", "Daily"), ("week", "Weekly"), ("month", "Monthly")], default="month", max_length=10
            ),
        ),
        migrations.AddField(
            model_name="report",
            name="is_automatic",
            field=models.BooleanField(default=False),
        ),
        migrations.AddIndex(
            model_name="report",
            index=models.Index(fields=["period_type", "period_start"], name="reports_period_idx"),
        ),
    ]
