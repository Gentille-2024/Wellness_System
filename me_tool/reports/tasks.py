import logging

from celery import shared_task
from django.core.files.base import ContentFile
from django.utils import timezone

from indicators.periods import DAY, MONTH, WEEK, period_of

from .builders import report_data
from .excel import build_xlsx
from .models import Report
from .pdf import build_pdf

log = logging.getLogger(__name__)


@shared_task
def generate_report(report_id):
    report = Report.objects.select_related("company").get(pk=report_id)
    report.status = Report.RUNNING
    report.save(update_fields=["status"])
    try:
        data = report_data(report)
        content = build_pdf(data, report) if report.format == Report.PDF else build_xlsx(data, report)
        report.file.save(report.filename, ContentFile(content), save=False)
        report.status, report.error = Report.DONE, ""
    except Exception as exc:
        log.exception("Report %s failed", report_id)
        report.status, report.error = Report.FAILED, str(exc)[:2000]
    report.finished_at = timezone.now()
    report.save()
    return report.status


def last_complete_period(kind, today=None):
    """Yesterday, last week (Monday-Sunday) or last month."""
    today = today or timezone.localdate()
    return period_of(kind, today).previous()


@shared_task
def scheduled_reports(kind):
    """
    Celery beat: every morning (yesterday), every Monday (last week) and on the
    1st (last month), a PDF and an Excel report for all companies.
    Running it twice for the same period creates nothing new.
    """
    if kind not in (DAY, WEEK, MONTH):
        raise ValueError(f"Unknown report period: {kind}")
    period = last_complete_period(kind)
    made = []
    for fmt, _label in Report.FORMATS:
        report, created = Report.objects.get_or_create(
            period_type=kind, period_start=period.start, company=None, format=fmt, is_automatic=True,
            defaults={"include_names": True},
        )
        if created:
            generate_report.delay(str(report.id))
            made.append(fmt)
    return f"{kind} {period.key}: {', '.join(made) or 'already made'}"
