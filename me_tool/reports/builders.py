"""Collects everything a daily, weekly or monthly report shows (for the PDF and Excel builders)."""

from django.utils import timezone

from accounts.scope import Scope
from dashboards import metrics
from indicators.progress import indicator_rows, status_summary

# How far back the trend table in a report goes
TREND_IN_REPORT = {"day": 7, "week": 8, "month": 6}


def report_data(report):
    period = report.period
    scope = Scope(all=True) if report.company_id is None else Scope(all=False, company_id=report.company_id)
    # Targets are set per month: indicators (targets vs actuals) only in monthly reports
    indicators = indicator_rows(period, scope, with_trend=False) if period.is_month else []
    count = TREND_IN_REPORT[period.kind]
    trend = metrics.trend(period, scope, count=count)
    return {
        "title": f"{report.get_period_type_display()} M&E report",
        "subtitle": report.title,
        "period": period,
        "month": period,  # the PDF template's older name
        "unit": period.unit,
        "trend_title": f"Last {count} {period.unit}s",
        "company": report.company,
        "all_companies": scope.all,
        "generated_at": timezone.localtime(),
        "kpis": metrics.kpis(period, scope),
        "trend": [
            {"label": label, "visits": visits, "spend": spend, "participants": people}
            for label, visits, spend, people in zip(trend["labels"], trend["visits"], trend["spend"], trend["participants"])
        ],
        "indicators": indicators,
        "indicator_summary": status_summary(indicators),
        "services": metrics.by_service(period, scope),
        "companies": metrics.by_company(period, scope) if scope.all else [],
        "departments": metrics.by_department(period, scope),
        "employees": metrics.top_employees(period, scope, limit=25) if report.include_names else [],
        "include_names": report.include_names,
        "scope": scope,
    }
