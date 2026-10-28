from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from accounts.scope import me_view
from indicators.periods import KINDS, Month, period_from_request
from indicators.periods import period_of as period_of_kind
from indicators.progress import indicator_rows, status_summary
from warehouse.models import Company, SyncState

from . import charts, metrics


def period_of(request):
    """The day, week or month asked for (?period=...&date=...); this month by default."""
    return period_from_request(request.GET)


def company_param(request):
    try:
        return int(request.GET.get("company")) if request.GET.get("company") else None
    except ValueError:
        return None


def with_params(request, **changes):
    """The current URL with some query parameters changed (None removes one)."""
    params = request.GET.copy()
    for key, value in changes.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = value
    return f"{request.path}?{params.urlencode()}" if params else request.path


def period_nav(request, period):
    """Everything the Day / Week / Month switch and the arrows need."""
    def url(p):
        return with_params(request, period=p.kind, date=p.url_value, month=None)

    nxt = period.next()
    return {
        # `month` stays the name used by the templates; it can be any period
        "month": period,
        "period": period,
        "period_query": period.query,
        "period_kinds": [
            {"kind": kind, "label": label, "url": url(_same_time(period, kind)), "active": kind == period.kind}
            for kind, label in KINDS
        ],
        "previous_url": url(period.previous()),
        "next_url": url(nxt) if not nxt.is_future() else None,
    }


def _same_time(period, kind):
    """Switching Day / Week / Month keeps the same moment (e.g. the week of the chosen day)."""
    return period if kind == period.kind else period_of_kind(kind, period.start)


def healthz(request):
    return HttpResponse("ok", content_type="text/plain")


@me_view()
def overview(request):
    # A service provider only has its own company dashboard
    if not request.scope.all:
        url = reverse("dashboards:company", args=[request.scope.company_id])
        return redirect(f"{url}?{request.GET.urlencode()}" if request.GET else url)

    month = period_of(request)
    scope = request.scope
    # Targets are monthly: indicators only for a whole month
    rows = indicator_rows(month, scope, with_trend=False) if month.is_month else []
    trend = metrics.trend(month, scope)
    companies = metrics.by_company(month, scope)
    departments = metrics.by_department(month, scope)
    return render(request, "dashboards/overview.html", {
        **period_nav(request, month),
        "kpis": metrics.kpis(month, scope),
        "trend_chart": charts.trend_chart(trend),
        "participants_chart": charts.participants_chart(trend),
        "company_chart": charts.company_share_chart(companies),
        "department_chart": charts.department_chart(departments),
        "companies": companies,
        "departments": departments,
        "top_employees": metrics.top_employees(month, scope) if request.access.can_see_names else [],
        "indicators": rows,
        "indicator_summary": status_summary(rows),
        "sync": SyncState.get(),
    })


@me_view(lambda access: access.sees_all)
def companies(request):
    month = period_of(request)
    stats = {row["company_id"]: row for row in metrics.by_company(month, request.scope)}
    rows = []
    for company in Company.objects.annotate(
        n_services=Count("services", filter=Q(services__is_active=True), distinct=True),
        n_covered=Count("services", filter=Q(services__is_active=True, services__is_covered=True), distinct=True),
    ):
        stat = stats.get(company.id, {})
        rows.append({
            "company": company,
            "services": company.n_services,
            "covered": company.n_covered,
            "visits": stat.get("visits", 0),
            "participants": stat.get("participants", 0),
            "spend": stat.get("spend") or 0,
            "unpaid": stat.get("unpaid") or 0,
            "share": stat.get("share") or 0,
        })
    rows.sort(key=lambda r: (-r["visits"], r["company"].name))
    return render(request, "dashboards/companies.html", {**period_nav(request, month), "rows": rows})


@me_view()
def company(request, company_id):
    scope = request.scope.narrowed(company_id)
    company = get_object_or_404(Company, pk=company_id)
    month = period_of(request)
    rows = indicator_rows(month, scope, with_trend=False) if month.is_month else []
    trend = metrics.trend(month, scope)
    services = metrics.by_service(month, scope)
    top = services[:8]
    return render(request, "dashboards/company.html", {
        **period_nav(request, month),
        "company": company,
        "kpis": metrics.kpis(month, scope),
        "trend_chart": charts.trend_chart(trend),
        "services_chart": charts.services_chart(
            [s["name"] for s in top], [s["visits"] for s in top], [s["previous_visits"] for s in top], month.unit
        ),
        "services": services,
        "departments": metrics.by_department(month, scope),
        "indicators": rows,
        "indicator_summary": status_summary(rows),
    })


@me_view()
def services(request):
    company_id = company_param(request) if request.scope.all else None
    scope = request.scope.narrowed(company_id)
    month = period_of(request)
    rows = metrics.by_service(month, scope)
    top = rows[:10]
    return render(request, "dashboards/services.html", {
        **period_nav(request, month),
        "rows": rows,
        "chart": charts.services_chart(
            [f"{r['name']} · {r['company']}" if scope.all else r["name"] for r in top],
            [r["visits"] for r in top],
            [r["previous_visits"] for r in top],
            month.unit,
        ),
        "companies": Company.objects.all() if request.scope.all else [],
        "company_id": company_id,
        "totals": {
            "visits": sum(r["visits"] for r in rows),
            "spend": sum(r["spend"] for r in rows),
            "services": sum(1 for r in rows if r["visits"]),
        },
    })


@me_view()
def indicators(request):
    company_id = company_param(request) if request.scope.all else None
    scope = request.scope.narrowed(company_id)
    month = Month.of(period_of(request).start)
    rows = indicator_rows(month, scope)
    for index, row in enumerate(rows):
        row["chart"] = charts.indicator_chart(row)
        row["chart_id"] = f"indicator-chart-{index}"
    return render(request, "dashboards/indicators.html", {
        **period_nav(request, month),
        "period_kinds": [],  # indicators are monthly: no Day / Week switch
        "rows": rows,
        "summary": status_summary(rows),
        "companies": Company.objects.all() if request.scope.all else [],
        "company_id": company_id,
        "scope_company": None if scope.all else get_object_or_404(Company, pk=scope.company_id),
    })
