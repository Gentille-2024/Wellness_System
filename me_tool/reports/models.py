import uuid

from django.conf import settings
from django.db import models
from django.utils.text import slugify

from indicators.periods import DAY, MONTH, WEEK, period_of


class Report(models.Model):
    """A daily, weekly or monthly report; built in the background by Celery."""

    PDF, EXCEL = "pdf", "xlsx"
    FORMATS = [(PDF, "PDF"), (EXCEL, "Excel")]
    PERIOD_TYPES = [(DAY, "Daily"), (WEEK, "Weekly"), (MONTH, "Monthly")]
    PENDING, RUNNING, DONE, FAILED = "pending", "running", "done", "failed"
    STATUSES = [(PENDING, "Waiting"), (RUNNING, "Preparing"), (DONE, "Ready"), (FAILED, "Failed")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="reports")
    period_type = models.CharField(max_length=10, choices=PERIOD_TYPES, default=MONTH)
    # The day, the Monday of the week, or the 1st of the month
    period_start = models.DateField()
    # Empty: all companies (EUCL only)
    company = models.ForeignKey("warehouse.Company", null=True, blank=True, on_delete=models.SET_NULL)
    format = models.CharField(max_length=10, choices=FORMATS)
    # Employee names are only included for EUCL (see Access.can_see_names)
    include_names = models.BooleanField(default=False)
    # Made by the schedule (every morning / Monday / 1st of the month), not by a person
    is_automatic = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUSES, default=PENDING)
    file = models.FileField(upload_to="reports/%Y/%m/", blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["period_type", "period_start"], name="reports_period_idx")]

    def __str__(self):
        return self.title

    @property
    def period(self):
        return period_of(self.period_type, self.period_start)

    @property
    def who(self):
        return self.company.name if self.company else "All companies"

    @property
    def title(self):
        return f"{self.who} — {self.period.label}"

    @property
    def filename(self):
        who = slugify(self.company.name) if self.company else "all-companies"
        return f"wellness-me-{self.get_period_type_display().lower()}-{self.period.key}-{who}.{self.format}"

    @property
    def is_finished(self):
        return self.status in (self.DONE, self.FAILED)
