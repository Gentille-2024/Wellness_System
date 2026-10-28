"""Targets vs actuals: one row per indicator, for a month and a scope."""

from .models import Indicator, Target, STATUS_LABELS, achievement, status

TREND_MONTHS = 6


def targets_for(months, company_id):
    """{(indicator_id, month_key): value} for EUCL overall (company_id None) or one company."""
    targets = Target.objects.filter(period__in=[m.start for m in months])
    targets = targets.filter(company__isnull=True) if company_id is None else targets.filter(company_id=company_id)
    return {(t.indicator_id, f"{t.period:%Y-%m}"): t.value for t in targets}


def indicator_rows(month, scope, with_trend=True):
    company_id = None if scope.all else scope.company_id
    indicators = Indicator.objects.filter(is_active=True)
    if company_id is not None:
        indicators = indicators.filter(per_company=True)
    months = month.last(TREND_MONTHS) if with_trend else [month]
    targets = targets_for(months, company_id)

    rows = []
    for indicator in indicators:
        actual = indicator.actual(month, scope)
        target = targets.get((indicator.id, month.key))
        state = status(actual, target, indicator.direction)
        trend = []
        if with_trend:
            for m in months:
                value = actual if m == month else indicator.actual(m, scope)
                trend.append({
                    "month": m.short_label,
                    "actual": float(value) if value is not None else None,
                    "target": float(targets[(indicator.id, m.key)]) if (indicator.id, m.key) in targets else None,
                })
        rows.append({
            "indicator": indicator,
            "actual": actual,
            "target": target,
            "baseline": indicator.baseline,
            "status": state,
            "status_label": STATUS_LABELS[state],
            "achievement": achievement(actual, target, indicator.direction),
            "trend": trend,
        })
    return rows


def status_summary(rows):
    summary = {key: 0 for key in STATUS_LABELS}
    for row in rows:
        summary[row["status"]] += 1
    return summary
