"""
How each indicator is calculated, for one month and one scope (all companies
or one company). Each function returns a Decimal, or None when it can't be
calculated (e.g. nobody came, so there is no cost per visit).
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, Sum

from warehouse.models import Employee, Payment, Service, Visit

ZERO = Decimal("0")


def _round(value, places=2):
    if value is None:
        return None
    return Decimal(value).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def _percent(part, whole):
    return _round(Decimal(part) * 100 / Decimal(whole)) if whole else None


def visits_in(month, scope):
    return scope.visits(Visit.objects.filter(visit_date__gte=month.start, visit_date__lte=month.end))


def participants(month, scope):
    return visits_in(month, scope).values("employee_id").distinct().count()


def active_employees(month):
    """EUCL employees who were active and already onboarded by the end of the month."""
    employees = Employee.objects.filter(is_active=True)
    return employees.exclude(created_at__date__gt=month.end).count()


# ----------------------------------------------------------- the calculations

def participation_rate(month, scope):
    return _percent(participants(month, scope), active_employees(month))


def total_visits(month, scope):
    return Decimal(visits_in(month, scope).count())


def unique_participants(month, scope):
    return Decimal(participants(month, scope))


def visits_per_participant(month, scope):
    people = participants(month, scope)
    return _round(Decimal(visits_in(month, scope).count()) / people) if people else None


def total_spend(month, scope):
    return _round(visits_in(month, scope).aggregate(s=Sum("price"))["s"] or ZERO)


def cost_per_visit(month, scope):
    agg = visits_in(month, scope).aggregate(s=Sum("price"), n=Count("id"))
    return _round(agg["s"] / agg["n"]) if agg["n"] else None


def cost_per_participant(month, scope):
    people = participants(month, scope)
    spend = visits_in(month, scope).aggregate(s=Sum("price"))["s"] or ZERO
    return _round(spend / people) if people else None


def repeat_rate(month, scope):
    """Of last month's participants, the % who came again this month."""
    before = set(visits_in(month.previous(), scope).values_list("employee_id", flat=True).distinct())
    if not before:
        return None
    again = visits_in(month, scope).filter(employee_id__in=before).values("employee_id").distinct().count()
    return _percent(again, len(before))


def service_coverage(month, scope):
    """% of the services offered (switched on) that EUCL covers. Current state, not history."""
    services = Service.objects.filter(is_active=True)
    if not scope.all:
        services = services.filter(company_id=scope.company_id)
    return _percent(services.filter(is_covered=True).count(), services.count())


def unpaid_amount(month, scope):
    """What EUCL still owes for this month's visits."""
    return _round(visits_in(month, scope).filter(payment__isnull=True).aggregate(s=Sum("price"))["s"] or ZERO)


def payment_delay_days(month, scope):
    """Average days from the end of the paid period to the payment, for payments made this month."""
    payments = Payment.objects.filter(paid_at__date__gte=month.start, paid_at__date__lte=month.end)
    if not scope.all:
        payments = payments.filter(company_id=scope.company_id)
    if not payments.exists():
        return None
    days = [(p.paid_at.date() - p.period_end).days for p in payments]
    return _round(Decimal(sum(days)) / len(days), 1)


CALCULATIONS = {
    "participation_rate": participation_rate,
    "total_visits": total_visits,
    "unique_participants": unique_participants,
    "visits_per_participant": visits_per_participant,
    "total_spend": total_spend,
    "cost_per_visit": cost_per_visit,
    "cost_per_participant": cost_per_participant,
    "repeat_rate": repeat_rate,
    "service_coverage": service_coverage,
    "unpaid_amount": unpaid_amount,
    "payment_delay_days": payment_delay_days,
}

CALCULATION_CHOICES = [
    ("participation_rate", "Participation rate (% of active employees who used a service)"),
    ("total_visits", "Services used (visits)"),
    ("unique_participants", "Employees who used a service"),
    ("visits_per_participant", "Visits per participating employee"),
    ("total_spend", "Amount spent (RWF)"),
    ("cost_per_visit", "Cost per visit (RWF)"),
    ("cost_per_participant", "Cost per participating employee (RWF)"),
    ("repeat_rate", "Repeat use (% of last month's participants who came again)"),
    ("service_coverage", "Service coverage (% of offered services covered by EUCL)"),
    ("unpaid_amount", "Still owed for the month (RWF)"),
    ("payment_delay_days", "Days from end of period to payment"),
]


def calculate(code, month, scope):
    return CALCULATIONS[code](month, scope)
