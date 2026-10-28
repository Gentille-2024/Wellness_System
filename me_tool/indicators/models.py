from decimal import Decimal

from django.db import models

from .calculations import CALCULATION_CHOICES, calculate


class Indicator(models.Model):
    """Something the programme measures every month, e.g. participation rate."""

    PERCENT, COUNT, MONEY, DAYS, NUMBER = "percent", "count", "money", "days", "number"
    UNITS = [(PERCENT, "%"), (COUNT, "count"), (MONEY, "RWF"), (DAYS, "days"), (NUMBER, "number")]
    HIGHER, LOWER = "higher", "lower"
    DIRECTIONS = [(HIGHER, "Higher is better"), (LOWER, "Lower is better")]

    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    calculation = models.CharField(max_length=50, choices=CALCULATION_CHOICES)
    unit = models.CharField(max_length=10, choices=UNITS)
    direction = models.CharField(max_length=10, choices=DIRECTIONS, default=HIGHER)
    baseline = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    # Some indicators only make sense for EUCL as a whole (e.g. participation
    # of all EUCL employees), not inside one company
    per_company = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    def actual(self, month, scope):
        return calculate(self.calculation, month, scope)


class Target(models.Model):
    """The value aimed for, for one month (for EUCL overall, or one company)."""

    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE, related_name="targets")
    period = models.DateField(help_text="First day of the month")
    # Empty: the target for EUCL as a whole
    company = models.ForeignKey("warehouse.Company", null=True, blank=True, on_delete=models.CASCADE, related_name="targets")
    value = models.DecimalField(max_digits=14, decimal_places=2)
    note = models.CharField(max_length=255, blank=True)
    set_by = models.CharField(max_length=150, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["period", "indicator__order"]
        constraints = [
            models.UniqueConstraint(fields=["indicator", "period", "company"], name="one_target_per_indicator_month_company"),
            # NULL company values are all "different" in a unique constraint,
            # so EUCL-wide targets need their own rule
            models.UniqueConstraint(
                fields=["indicator", "period"], condition=models.Q(company__isnull=True), name="one_eucl_target_per_indicator_month"
            ),
        ]


ON_TRACK, AT_RISK, OFF_TRACK, NO_TARGET, NO_DATA = "on_track", "at_risk", "off_track", "no_target", "no_data"
STATUS_LABELS = {
    ON_TRACK: "On track",
    AT_RISK: "At risk",
    OFF_TRACK: "Off track",
    NO_TARGET: "No target",
    NO_DATA: "No data",
}
# Within 10% of the target counts as "at risk", further as "off track"
TOLERANCE = Decimal("0.10")


def status(actual, target, direction):
    if target is None:
        return NO_TARGET
    if actual is None:
        return NO_DATA
    if direction == Indicator.HIGHER:
        if actual >= target:
            return ON_TRACK
        return AT_RISK if actual >= target * (1 - TOLERANCE) else OFF_TRACK
    if actual <= target:
        return ON_TRACK
    return AT_RISK if actual <= target * (1 + TOLERANCE) else OFF_TRACK


def achievement(actual, target, direction):
    """How far towards the target, in % (100 = target met), for the progress bars."""
    if actual is None or target in (None, 0):
        return None
    if direction == Indicator.HIGHER:
        return min(Decimal(200), actual * 100 / target)
    return min(Decimal(200), target * 100 / actual) if actual else Decimal(200)
