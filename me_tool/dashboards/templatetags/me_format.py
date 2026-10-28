"""Number formatting for the M&E pages and the PDF report."""

from decimal import Decimal

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()


def _number(value, places=0):
    if value is None or value == "":
        return "—"
    value = Decimal(value)
    return f"{value:,.{places}f}"


@register.filter
def rwf(value):
    """12345.5 -> 'RWF 12,346'"""
    return "—" if value is None else f"RWF {_number(value)}"


@register.filter
def num(value, places=0):
    return _number(value, int(places))


@register.filter
def pct(value, places=1):
    return "—" if value is None else f"{_number(value, int(places))}%"


@register.filter
def unit_value(value, unit):
    """An indicator value in its unit."""
    if value is None:
        return "—"
    if unit == "percent":
        return f"{_number(value, 1)}%"
    if unit == "money":
        return f"RWF {_number(value)}"
    if unit == "days":
        return f"{_number(value, 1)} days"
    if unit == "count":
        return _number(value)
    return _number(value, 2)


@register.filter
def change(value):
    """A coloured +/-% badge (month on month)."""
    if value is None:
        return mark_safe('<span class="change muted">new</span>')
    value = Decimal(value)
    css = "up" if value > 0 else "down" if value < 0 else "flat"
    sign = "+" if value > 0 else ""
    return format_html('<span class="change {}">{}{}%</span>', css, sign, f"{value:,.1f}")


@register.filter
def bar_width(value, maximum=100):
    """A 0-100 width for the CSS bars."""
    try:
        value, maximum = float(value or 0), float(maximum or 0)
    except (TypeError, ValueError):
        return 0
    if maximum <= 0:
        return 0
    return max(0, min(100, round(value * 100 / maximum, 1)))


@register.simple_tag
def max_of(rows, key):
    return max((row[key] or 0 for row in rows), default=0)


@register.filter
def size(value):
    """Bytes as KB / MB / GB."""
    if value is None or value == "":
        return "—"
    value = float(value)
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024 or unit == "TB":
            return f"{value:,.0f} {unit}" if unit == "bytes" else f"{value:,.1f} {unit}"
        value /= 1024
    return f"{value:,.1f} TB"


@register.filter
def duration(seconds):
    """Seconds as '3 d 4 h' / '5 h 12 min'."""
    if seconds is None:
        return "—"
    seconds = int(seconds)
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days} d {hours} h"
    if hours:
        return f"{hours} h {minutes} min"
    return f"{minutes} min"


@register.filter
def percent_of(used, total):
    try:
        return round(float(used) * 100 / float(total), 1)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
