"""Database growth: from the daily snapshots, how fast it grows and where it's heading."""

from datetime import timedelta

from .models import DatabaseSnapshot

WINDOW_DAYS = 30


def database_growth(disk_free=None):
    snapshots = list(DatabaseSnapshot.objects.order_by("taken_on"))
    sized = [s for s in snapshots if s.db_size is not None]
    result = {
        "snapshots": snapshots,
        "labels": [s.taken_on.strftime("%d %b") for s in sized],
        "sizes_mb": [round(s.db_size / 1024 / 1024, 2) for s in sized],
        "rows": [s.total_rows for s in snapshots],
        "per_day": None,
        "rows_per_day": None,
        "in_30_days": None,
        "in_90_days": None,
        "days_until_full": None,
        "tables": [],
    }
    if not snapshots:
        return result
    latest = snapshots[-1]

    # Average growth over the last 30 days (or since the first snapshot)
    start = next((s for s in snapshots if s.taken_on >= latest.taken_on - timedelta(days=WINDOW_DAYS)), snapshots[0])
    days = (latest.taken_on - start.taken_on).days
    if days > 0:
        result["rows_per_day"] = round((latest.total_rows - start.total_rows) / days, 1)
        if latest.db_size is not None and start.db_size is not None:
            per_day = (latest.db_size - start.db_size) / days
            result["per_day"] = per_day
            result["in_30_days"] = latest.db_size + per_day * 30
            result["in_90_days"] = latest.db_size + per_day * 90
            if disk_free and per_day > 0:
                result["days_until_full"] = int(disk_free / per_day)

    # Which tables grow: rows now vs about a week ago
    week_ago = next((s for s in reversed(snapshots) if s.taken_on <= latest.taken_on - timedelta(days=7)), snapshots[0])
    before = {t["table"]: t["rows"] for t in week_ago.tables}
    for table in latest.tables:
        result["tables"].append({**table, "added_7_days": table["rows"] - before.get(table["table"], 0) if week_ago != latest else None})
    return result
