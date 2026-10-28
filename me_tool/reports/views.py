from datetime import timedelta

from django.contrib import messages
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.scope import me_view
from indicators.periods import period_from_request
from warehouse.models import Company

from .models import Report
from .tasks import generate_report


def _visible_reports(request):
    """Admins: every report. EUCL: their own and the automatic ones. Companies: their own, for their company."""
    reports = Report.objects.select_related("company", "requested_by")
    if request.access.is_admin:
        return reports
    if request.scope.all:
        return reports.filter(Q(requested_by=request.user) | Q(is_automatic=True))
    return reports.filter(requested_by=request.user, company_id=request.scope.company_id)


def _filtered(request, reports):
    kind = request.GET.get("type")
    return reports.filter(period_type=kind) if kind in dict(Report.PERIOD_TYPES) else reports


@me_view()
def report_list(request):
    reports = _filtered(request, _visible_reports(request))[:60]
    return render(request, "reports/list.html", {
        "reports": reports,
        "default_date": timezone.localdate() - timedelta(days=1),
        "period_types": Report.PERIOD_TYPES,
        "selected_type": request.GET.get("type", ""),
        "companies": Company.objects.all() if request.scope.all else Company.objects.filter(pk=request.scope.company_id),
        "selected_company": request.GET.get("company", "" if request.scope.all else str(request.scope.company_id)),
        "formats": Report.FORMATS,
        "waiting": any(not r.is_finished for r in reports),
    })


@me_view()
def report_rows(request):
    """The table only (HTMX refreshes it while reports are being prepared)."""
    reports = _filtered(request, _visible_reports(request))[:60]
    return render(request, "reports/_rows.html", {"reports": reports, "waiting": any(not r.is_finished for r in reports)})


@require_POST
@me_view()
def report_create(request):
    # ?period=day|week|month & date=<any day in it>; older forms send month=YYYY-MM
    period = period_from_request(request.POST)
    fmt = request.POST.get("format")
    if fmt not in dict(Report.FORMATS):
        messages.error(request, "Choose PDF or Excel.")
        return redirect("reports:list")
    if period.is_future():
        messages.error(request, f"{period.label} hasn't started yet.")
        return redirect("reports:list")
    company = None
    if request.POST.get("company"):
        company = get_object_or_404(Company, pk=request.POST["company"])
    if not request.scope.allows_company(company.id if company else None) or (company is None and not request.scope.all):
        raise Http404("Company not found")
    report = Report.objects.create(
        requested_by=request.user, period_type=period.kind, period_start=period.start, company=company, format=fmt,
        include_names=request.access.can_see_names,
    )
    generate_report.delay(str(report.id))
    messages.success(request, f"Preparing the {report.get_period_type_display().lower()} {report.get_format_display()} report: {report.title}.")
    return redirect("reports:list")


@me_view()
def report_download(request, report_id):
    report = get_object_or_404(_visible_reports(request), pk=report_id, status=Report.DONE)
    if not report.file:
        raise Http404("The file is missing")
    return FileResponse(report.file.open("rb"), as_attachment=True, filename=report.filename)
