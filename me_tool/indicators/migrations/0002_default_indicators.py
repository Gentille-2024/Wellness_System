"""The starting set of indicators (targets are set on the Targets page)."""

from django.db import migrations

INDICATORS = [
    # code, name, description, calculation, unit, direction, per_company
    ("participation-rate", "Participation rate",
     "Share of active EUCL employees who used at least one service in the month.",
     "participation_rate", "percent", "higher", False),
    ("visits", "Services used",
     "Number of services EUCL employees used in the month.",
     "total_visits", "count", "higher", True),
    ("participants", "Employees who used a service",
     "Number of different EUCL employees who used at least one service.",
     "unique_participants", "count", "higher", True),
    ("visits-per-participant", "Visits per participating employee",
     "Average number of services used by each employee who came.",
     "visits_per_participant", "number", "higher", True),
    ("repeat-rate", "Repeat use",
     "Of last month's participants, the share who came again this month.",
     "repeat_rate", "percent", "higher", True),
    ("spend", "Amount spent",
     "What EUCL pays for the services used in the month (compare with the monthly budget).",
     "total_spend", "money", "lower", True),
    ("cost-per-visit", "Cost per visit",
     "Average amount EUCL pays per service used.",
     "cost_per_visit", "money", "lower", True),
    ("cost-per-participant", "Cost per participating employee",
     "Average amount EUCL pays per employee who came.",
     "cost_per_participant", "money", "lower", True),
    ("service-coverage", "Service coverage",
     "Share of the services companies offer that EUCL covers.",
     "service_coverage", "percent", "higher", True),
    ("unpaid", "Still owed for the month",
     "Amount for the month's services that EUCL has not paid yet.",
     "unpaid_amount", "money", "lower", True),
    ("payment-delay", "Payment delay",
     "Average days from the end of a paid period to the payment.",
     "payment_delay_days", "days", "lower", True),
]


def create(apps, schema_editor):
    Indicator = apps.get_model("indicators", "Indicator")
    for order, (code, name, description, calculation, unit, direction, per_company) in enumerate(INDICATORS, start=1):
        Indicator.objects.update_or_create(code=code, defaults={
            "name": name, "description": description, "calculation": calculation, "unit": unit,
            "direction": direction, "per_company": per_company, "order": order,
        })


def remove(apps, schema_editor):
    apps.get_model("indicators", "Indicator").objects.filter(code__in=[i[0] for i in INDICATORS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("indicators", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create, remove),
    ]
