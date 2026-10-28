"""
The numbers behind the dashboards and reports, calculated from the synced
visits for a period (day, week or month) and a scope. Each function is one or two queries.
"""

from decimal import Decimal

from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncMonth, TruncWeek

from indicators.calculations import active_employees, participants, visits_in
from warehouse.models import Employee, Visit

ZERO = Decimal("0")


def _change(now, before):
    """% change from before to now (None when there is nothing to compare)."""
    if not before:
        return None
    return round((Decimal(now) - Decimal(before)) * 100 / Decimal(before), 1)


def _share(part, whole):
    return round(Decimal(part) * 100 / Decimal(whole), 1) if whole else Decimal(0)


def totals(month, scope):
    agg = visits_in(month, scope).aggregate(
        visits=Count("id"),
        participants=Count("employee", distinct=True),
        spend=Sum("price"),
        unpaid=Sum("price", filter=Q(payment__isnull=True)),
    )
    agg["spend"] = agg["spend"] or ZERO
    agg["unpaid"] = agg["unpaid"] or ZERO
    return agg


def kpis(month, scope):
    now, before = totals(month, scope), totals(month.previous(), scope)
    active = active_employees(month)
    owed_all = scope.visits(Visit.objects.filter(payment__isnull=True)).aggregate(s=Sum("price"))["s"] or ZERO
    return {
        **now,
        "active_employees": active,
        "participation": _share(now["participants"], active) if active else None,
        "cost_per_visit": (now["spend"] / now["visits"]) if now["visits"] else None,
        "owed_all": owed_all,
        "visits_change": _change(now["visits"], before["visits"]),
        "spend_change": _change(now["spend"], before["spend"]),
        "participants_change": _change(now["participants"], before["participants"]),
    }


def trend(period, scope, count=None):
    """Visits, spend and participants for each of the last `count` days, weeks or months."""
    periods = period.last(count or period.trend_count)
    visits = scope.visits(Visit.objects.filter(visit_date__gte=periods[0].start, visit_date__lte=period.end))
    if period.kind == "day":
        grouped = visits.values(start=F("visit_date"))
    else:
        grouped = visits.annotate(start=(TruncWeek if period.kind == "week" else TruncMonth)("visit_date")).values("start")
    rows = grouped.annotate(visits=Count("id"), spend=Sum("price"), participants=Count("employee", distinct=True))
    by_start = {_as_date(row["start"]): row for row in rows}
    return {
        "labels": [p.short_label for p in periods],
        "keys": [p.key for p in periods],
        "visits": [by_start.get(p.start, {}).get("visits", 0) for p in periods],
        "spend": [float(by_start.get(p.start, {}).get("spend") or 0) for p in periods],
        "participants": [by_start.get(p.start, {}).get("participants", 0) for p in periods],
    }


def _as_date(value):
    return value.date() if hasattr(value, "date") and callable(value.date) else value


def by_company(month, scope):
    rows = list(
        visits_in(month, scope)
        .values("company_id", "company__name")
        .annotate(
            visits=Count("id"),
            participants=Count("employee", distinct=True),
            spend=Sum("price"),
            unpaid=Sum("price", filter=Q(payment__isnull=True)),
        )
        .order_by("-spend", "company__name")
    )
    total = sum((r["spend"] for r in rows), ZERO)
    for row in rows:
        row["unpaid"] = row["unpaid"] or ZERO
        row["share"] = _share(row["spend"], total)
    return rows


def by_service(month, scope):
    """Service performance: this month, the change from last month, and share of spending."""
    def grouped(m):
        return {
            row["service_id"]: row
            for row in visits_in(m, scope)
            .values("service_id", "service__name", "service__company__name", "service__company_id",
                    "service__is_covered", "service__eucl_price", "service__is_active")
            .annotate(visits=Count("id"), participants=Count("employee", distinct=True), spend=Sum("price"))
        }

    now, before = grouped(month), grouped(month.previous())
    total = sum((r["spend"] for r in now.values()), ZERO)
    rows = []
    for service_id, row in now.items():
        prev = before.get(service_id, {}).get("visits", 0)
        rows.append({
            "id": service_id,
            "name": row["service__name"],
            "company": row["service__company__name"],
            "company_id": row["service__company_id"],
            "covered": row["service__is_covered"],
            "eucl_price": row["service__eucl_price"],
            "offered": row["service__is_active"],
            "visits": row["visits"],
            "participants": row["participants"],
            "spend": row["spend"],
            "previous_visits": prev,
            "change": _change(row["visits"], prev),
            "share": _share(row["spend"], total),
        })
    # Services used last month but not at all this month (a drop to watch)
    for service_id, row in before.items():
        if service_id not in now:
            rows.append({
                "id": service_id, "name": row["service__name"], "company": row["service__company__name"],
                "company_id": row["service__company_id"], "covered": row["service__is_covered"],
                "eucl_price": row["service__eucl_price"], "offered": row["service__is_active"],
                "visits": 0, "participants": 0, "spend": ZERO, "previous_visits": row["visits"],
                "change": Decimal(-100), "share": Decimal(0),
            })
    rows.sort(key=lambda r: (-r["visits"], r["name"]))
    return rows


def by_department(month, scope):
    """Participation by department (EUCL employees), most used first."""
    used = {
        row["employee__department"] or "—": row
        for row in visits_in(month, scope)
        .values("employee__department")
        .annotate(visits=Count("id"), participants=Count("employee", distinct=True), spend=Sum("price"))
    }
    staff = {
        row["department"] or "—": row["n"]
        for row in Employee.objects.filter(is_active=True).exclude(created_at__date__gt=month.end)
        .values("department").annotate(n=Count("id"))
    }
    rows = []
    for department in sorted(set(used) | set(staff)):
        row = used.get(department, {})
        people = staff.get(department, 0)
        rows.append({
            "department": department,
            "employees": people,
            "participants": row.get("participants", 0),
            "visits": row.get("visits", 0),
            "spend": row.get("spend") or ZERO,
            "participation": _share(row.get("participants", 0), people) if people else None,
        })
    rows.sort(key=lambda r: (-(r["participation"] or 0), r["department"]))
    return rows


def top_employees(month, scope, limit=10):
    """Most active EUCL employees (names: EUCL only, see Access.can_see_names)."""
    return list(
        visits_in(month, scope)
        .values("employee_id", "employee__code", "employee__first_name", "employee__last_name", "employee__department")
        .annotate(visits=Count("id"), days=Count("visit_date", distinct=True), spend=Sum("price"))
        .order_by("-visits", "-spend")[:limit]
    )


def month_visits(month, scope):
    """Every visit of the month (for the Excel report)."""
    return (
        visits_in(month, scope)
        .select_related("employee", "service", "company")
        .order_by("visit_date", "company__name", "employee__code")
    )


__all__ = [
    "kpis", "trend", "by_company", "by_service", "by_department", "top_employees", "month_visits", "participants",
]
