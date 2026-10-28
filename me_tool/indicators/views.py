from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render

from accounts.scope import me_view
from warehouse.models import Company

from .models import Indicator, Target
from .periods import Month, period_from_request

MAX_REPEAT = 11


@me_view(lambda access: access.can_manage_targets)
def targets(request):
    """Set the targets of one month, for EUCL overall or for one company."""
    source = request.POST if request.method == "POST" else request.GET
    # Targets are per month; a link from a day or week view opens its month
    month = Month.of(period_from_request(source).start)
    try:
        company_id = int(source["company"]) if source.get("company") else None
    except ValueError:
        company_id = None
    company = Company.objects.filter(pk=company_id).first() if company_id else None

    indicators = Indicator.objects.filter(is_active=True)
    if company is not None:
        indicators = indicators.filter(per_company=True)

    if request.method == "POST":
        try:
            repeat = max(0, min(MAX_REPEAT, int(request.POST.get("repeat") or 0)))
        except ValueError:
            repeat = 0
        errors, changed = [], 0
        with transaction.atomic():
            for indicator in indicators:
                text = request.POST.get(f"target_{indicator.id}", "").strip().replace(",", "")
                note = request.POST.get(f"note_{indicator.id}", "").strip()[:255]
                for m in [month.shift(i) for i in range(repeat + 1)]:
                    existing = Target.objects.filter(indicator=indicator, period=m.start, company=company)
                    if text == "":
                        changed += existing.delete()[0]
                        continue
                    try:
                        value = Decimal(text)
                    except InvalidOperation:
                        errors.append(f"{indicator.name}: “{text}” is not a number.")
                        break
                    if value < 0:
                        errors.append(f"{indicator.name}: a target can't be negative.")
                        break
                    Target.objects.update_or_create(
                        indicator=indicator, period=m.start, company=company,
                        defaults={"value": value, "note": note, "set_by": request.user.username},
                    )
                    changed += 1
            if errors:
                transaction.set_rollback(True)
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            months = f"{month.label}" + (f" and the next {repeat} month{'s' if repeat != 1 else ''}" if repeat else "")
            messages.success(request, f"Targets saved for {company or 'EUCL overall'}: {months}.")
            query = f"?month={month.key}" + (f"&company={company.id}" if company else "")
            return redirect(f"{request.path}{query}")

    current = {t.indicator_id: t for t in Target.objects.filter(period=month.start, company=company)}
    rows = [{"indicator": i, "target": current.get(i.id)} for i in indicators]
    return render(request, "indicators/targets.html", {
        "month": month,
        "company": company,
        "companies": Company.objects.all(),
        "rows": rows,
        "repeat_choices": range(0, MAX_REPEAT + 1),
    })
