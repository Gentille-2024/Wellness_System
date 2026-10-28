"""
A read-only copy of the wellness system's data, kept up to date by the sync.

Every row keeps the id it has in the wellness system (it is the primary key
here too), so syncing again simply updates the same rows.
"""

from django.db import models


class Company(models.Model):
    """A service provider (gym, spa...)."""

    id = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "companies"

    def __str__(self):
        return self.name

    @property
    def is_open(self):
        return self.is_active and self.deleted_at is None


class Service(models.Model):
    id = models.IntegerField(primary_key=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="services")
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    is_active = models.BooleanField(default=True)
    # Covered by EUCL, and the amount EUCL pays per visit
    is_covered = models.BooleanField(default=False)
    eucl_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["company__name", "name"]

    def __str__(self):
        return f"{self.name} ({self.company})"


class Employee(models.Model):
    """An EUCL employee."""

    id = models.IntegerField(primary_key=True)
    code = models.CharField(max_length=20)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    department = models.CharField(max_length=100, blank=True, db_index=True)
    position = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.name

    @property
    def name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.code


class Payment(models.Model):
    """EUCL paid a company for every unpaid visit in a period."""

    id = models.IntegerField(primary_key=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="payments")
    period_start = models.DateField()
    period_end = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reference = models.CharField(max_length=100, blank=True)
    paid_at = models.DateTimeField()

    class Meta:
        ordering = ["-paid_at"]


class Visit(models.Model):
    """One service used by one employee, at the price EUCL pays."""

    id = models.IntegerField(primary_key=True)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="visits")
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="visits")
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="visits")
    price = models.DecimalField(max_digits=12, decimal_places=2)
    visit_date = models.DateField(db_index=True)
    visited_at = models.DateTimeField()
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name="visits")
    # When the visit last changed in the wellness system (the sync cursor)
    updated_at = models.DateTimeField()

    class Meta:
        ordering = ["-visited_at"]
        indexes = [
            models.Index(fields=["company", "visit_date"]),
            models.Index(fields=["employee", "visit_date"]),
        ]

    @property
    def is_paid(self):
        return self.payment_id is not None


class SyncState(models.Model):
    """Where the last sync stopped (a single row)."""

    visits_cursor_time = models.DateTimeField(null=True, blank=True)
    visits_cursor_id = models.IntegerField(default=0)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    @classmethod
    def get(cls):
        state, _ = cls.objects.get_or_create(pk=1)
        return state


class SyncRun(models.Model):
    """One run of the sync, for the sync status page."""

    INCREMENTAL, FULL, RECONCILE = "incremental", "full", "reconcile"
    KINDS = [(INCREMENTAL, "New and changed"), (FULL, "Everything again"), (RECONCILE, "Nightly check")]
    RUNNING, OK, FAILED, SKIPPED = "running", "ok", "failed", "skipped"
    STATUSES = [(RUNNING, "Running"), (OK, "OK"), (FAILED, "Failed"), (SKIPPED, "Skipped")]

    kind = models.CharField(max_length=20, choices=KINDS, default=INCREMENTAL)
    status = models.CharField(max_length=20, choices=STATUSES, default=RUNNING)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    counts = models.JSONField(default=dict, blank=True)
    message = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]

    @property
    def duration(self):
        if self.finished_at:
            return self.finished_at - self.started_at
        return None
