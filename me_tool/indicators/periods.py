"""
Periods: a day, a week (Monday to Sunday) or a month.

Every dashboard, indicator and report works with one of them. The three
classes share the same interface:

    start, end          first and last day (dates)
    key                 '2026-10-21' / '2026-W43' / '2026-10'
    label, short_label  'Wednesday 21 October 2026' / 'Week 43 · 19–25 Oct 2026' / 'October 2026'
    unit                'day' / 'week' / 'month'
    previous(), next(), shift(n), last(n)

In URLs: ?period=day|week|month&date=<a date, or YYYY-MM for a month>
"""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from urllib.parse import urlencode

from django.utils import timezone
from django.utils.dateparse import parse_date

DAY, WEEK, MONTH = "day", "week", "month"
KINDS = [(DAY, "Day"), (WEEK, "Week"), (MONTH, "Month")]
# How many periods the trend charts show
TREND_COUNT = {DAY: 14, WEEK: 12, MONTH: 12}


class _Period:
    kind = None

    @property
    def unit(self):
        return self.kind

    @property
    def trend_count(self):
        return TREND_COUNT[self.kind]

    @property
    def is_month(self):
        return self.kind == MONTH

    @property
    def query(self):
        """'period=week&date=2026-10-19' for links."""
        return urlencode({"period": self.kind, "date": self.url_value})

    @property
    def url_value(self):
        return self.start.isoformat()

    def next(self):
        return self.shift(1)

    def previous(self):
        return self.shift(-1)

    def last(self, count):
        """The `count` periods ending with this one, oldest first."""
        return [self.shift(-i) for i in range(count - 1, -1, -1)]

    def contains(self, day):
        return self.start <= day <= self.end

    def is_future(self):
        return self.start > timezone.localdate()

    def __str__(self):
        return self.label


@dataclass(frozen=True)
class Day(_Period):
    day: date
    kind = DAY

    @classmethod
    def of(cls, day):
        return cls(day)

    @classmethod
    def current(cls):
        return cls(timezone.localdate())

    @property
    def start(self):
        return self.day

    @property
    def end(self):
        return self.day

    @property
    def key(self):
        return self.day.isoformat()

    @property
    def label(self):
        return f"{self.day:%A} {self.day.day} {self.day:%B %Y}"

    @property
    def short_label(self):
        return f"{self.day.day} {self.day:%b}"

    def shift(self, count):
        return Day(self.day + timedelta(days=count))


@dataclass(frozen=True)
class Week(_Period):
    """Monday to Sunday (ISO week)."""

    monday: date
    kind = WEEK

    @classmethod
    def of(cls, day):
        return cls(day - timedelta(days=day.weekday()))

    @classmethod
    def current(cls):
        return cls.of(timezone.localdate())

    @property
    def start(self):
        return self.monday

    @property
    def end(self):
        return self.monday + timedelta(days=6)

    @property
    def number(self):
        return self.monday.isocalendar()[1]

    @property
    def key(self):
        year, week, _ = self.monday.isocalendar()
        return f"{year}-W{week:02d}"

    @property
    def label(self):
        end = self.end
        start = f"{self.start.day}" if self.start.month == end.month else f"{self.start.day} {self.start:%b}"
        return f"Week {self.number} · {start}–{end.day} {end:%b %Y}"

    @property
    def short_label(self):
        return f"W{self.number} · {self.start.day} {self.start:%b}"

    def shift(self, count):
        return Week(self.monday + timedelta(weeks=count))


@dataclass(frozen=True)
class Month(_Period):
    year: int
    month: int
    kind = MONTH

    @classmethod
    def current(cls):
        today = timezone.localdate()
        return cls(today.year, today.month)

    @classmethod
    def parse(cls, text, default=None):
        """'2026-10' (or '2026-10-21') -> Month(2026, 10); anything else -> default (this month)."""
        try:
            year, month = (int(part) for part in str(text).split("-")[:2])
            if 2000 <= year <= 2100 and 1 <= month <= 12:
                return cls(year, month)
        except (TypeError, ValueError):
            pass
        return default or cls.current()

    @classmethod
    def of(cls, day):
        return cls(day.year, day.month)

    @property
    def start(self):
        return date(self.year, self.month, 1)

    @property
    def end(self):
        return date(self.year, self.month, calendar.monthrange(self.year, self.month)[1])

    @property
    def key(self):
        return f"{self.year:04d}-{self.month:02d}"

    @property
    def url_value(self):
        return self.key

    @property
    def label(self):
        return self.start.strftime("%B %Y")

    @property
    def short_label(self):
        return self.start.strftime("%b %Y")

    def shift(self, months):
        index = self.year * 12 + (self.month - 1) + months
        return Month(index // 12, index % 12 + 1)


CLASSES = {DAY: Day, WEEK: Week, MONTH: Month}


def period_of(kind, day):
    """The day / week / month that contains `day`."""
    return CLASSES.get(kind, Month).of(day)


def parse_period(kind, text):
    """A period from the URL; today's period when the date is missing or wrong."""
    kind = kind if kind in CLASSES else MONTH
    if kind == MONTH:
        return Month.parse(text)
    day = parse_date(str(text or "")) if text else None
    return CLASSES[kind].of(day or timezone.localdate())


def period_from_request(params, default_kind=MONTH):
    """?period=day|week|month&date=...  (the older ?month=YYYY-MM still works)."""
    if params.get("period") or params.get("date"):
        return parse_period(params.get("period") or default_kind, params.get("date"))
    if params.get("month"):
        return Month.parse(params["month"])
    return CLASSES[default_kind].current()
