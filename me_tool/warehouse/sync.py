"""
Copies the wellness system's data into the warehouse.

Each run:
  1. snapshot: companies, services, employees and payments, in full (small)
  2. visits: only those changed since the last run (a cursor on updated_at, id),
     starting a little before the cursor (SYNC_OVERLAP) so nothing is missed
  3. reconcile (nightly, or when asked): visits of the last RECONCILE_DAYS days
     that no longer exist in the wellness system (undone) are removed here too
Writing the same row twice is harmless, so a run can always be repeated.
"""

import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from .client import WellnessClient
from .models import Company, Employee, Payment, Service, SyncRun, SyncState, Visit

log = logging.getLogger(__name__)

PAGE_SIZE = 1000


def _dt(value):
    if not value:
        return None
    parsed = parse_datetime(value) if isinstance(value, str) else value
    if parsed is not None and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _date(value):
    return parse_date(value) if isinstance(value, str) else value


def _money(value):
    return None if value in (None, "") else Decimal(str(value))


def _upsert(model, objects, fields):
    if objects:
        model.objects.bulk_create(objects, update_conflicts=True, unique_fields=["id"], update_fields=fields)
    return len(objects)


@transaction.atomic
def apply_snapshot(data):
    counts = {}
    counts["companies"] = _upsert(Company, [
        Company(id=c["id"], name=c["name"], is_active=c["is_active"], deleted_at=_dt(c.get("deleted_at")), created_at=_dt(c.get("created_at")))
        for c in data["companies"]
    ], ["name", "is_active", "deleted_at", "created_at"])
    counts["services"] = _upsert(Service, [
        Service(
            id=s["id"], company_id=s["company_id"], name=s["name"], price=_money(s["price"]), is_active=s["is_active"],
            is_covered=s["is_approved"], eucl_price=_money(s.get("eucl_price")), created_at=_dt(s.get("created_at")),
        )
        for s in data["services"]
    ], ["company", "name", "price", "is_active", "is_covered", "eucl_price", "created_at"])
    counts["employees"] = _upsert(Employee, [
        Employee(
            id=e["id"], code=e["employee_id"], first_name=e.get("first_name") or "", last_name=e.get("last_name") or "",
            department=e.get("department") or "", position=e.get("position") or "", is_active=e["is_active"],
            created_at=_dt(e.get("created_at")),
        )
        for e in data["employees"]
    ], ["code", "first_name", "last_name", "department", "position", "is_active", "created_at"])
    counts["payments"] = _upsert(Payment, [
        Payment(
            id=p["id"], company_id=p["company_id"], period_start=_date(p["period_start"]), period_end=_date(p["period_end"]),
            amount=_money(p["amount"]), reference=p.get("reference") or "", paid_at=_dt(p["paid_at"]),
        )
        for p in data["payments"]
    ], ["company", "period_start", "period_end", "amount", "reference", "paid_at"])
    return counts


def _save_visits(rows):
    return _upsert(Visit, [
        Visit(
            id=v["id"], employee_id=v["employee_id"], service_id=v["service_id"], company_id=v["company_id"],
            price=_money(v["price"]), visit_date=_date(v["visit_date"]), visited_at=_dt(v["visited_at"]),
            payment_id=v.get("payment_id"), updated_at=_dt(v["updated_at"]),
        )
        for v in rows
    ], ["employee", "service", "company", "price", "visit_date", "visited_at", "payment", "updated_at"])


def _missing_references(rows):
    def missing(model, key):
        wanted = {row[key] for row in rows if row.get(key)}
        return wanted and len(wanted) != model.objects.filter(id__in=wanted).count()

    return (
        missing(Employee, "employee_id") or missing(Service, "service_id")
        or missing(Company, "company_id") or missing(Payment, "payment_id")
    )


def pull_visits(client, state, full=False):
    """Visits changed since the cursor, page by page. Returns how many were saved."""
    if full or state.visits_cursor_time is None:
        since, after_id = None, 0
    else:
        since, after_id = state.visits_cursor_time - settings.SYNC_OVERLAP, 0
    saved = 0
    while True:
        page = client.visits(updated_since=since.isoformat() if since else None, after_id=after_id, limit=PAGE_SIZE)
        rows = page["results"]
        # A payment, employee or service created after this run's snapshot:
        # read the snapshot again before saving visits that point to it
        if _missing_references(rows):
            apply_snapshot(client.snapshot())
        with transaction.atomic():
            saved += _save_visits(rows)
            if rows:
                last = rows[-1]
                last_time = _dt(last["updated_at"])
                # never move the cursor backwards (the overlap re-reads older rows)
                if state.visits_cursor_time is None or last_time >= state.visits_cursor_time:
                    state.visits_cursor_time, state.visits_cursor_id = last_time, last["id"]
                    state.save(update_fields=["visits_cursor_time", "visits_cursor_id"])
        nxt = page.get("next")
        if not nxt:
            return saved
        since, after_id = _dt(nxt["updated_since"]), nxt["after_id"]


def reconcile(client, days):
    """Remove visits that were undone (deleted) in the wellness system."""
    date_from = timezone.localdate() - timedelta(days=days)
    remote = set(client.visit_ids(date_from))
    gone = Visit.objects.filter(visit_date__gte=date_from).exclude(id__in=remote)
    removed, _ = gone.delete()
    return removed


def run_sync(client=None, full=False, reconcile_days=None):
    """One sync run; returns the SyncRun. Errors are recorded, then raised."""
    kind = SyncRun.FULL if full else SyncRun.RECONCILE if reconcile_days else SyncRun.INCREMENTAL
    # Don't start while another run is busy (beat and "Sync now" at the same time)
    busy = SyncRun.objects.filter(status=SyncRun.RUNNING, started_at__gte=timezone.now() - timedelta(minutes=30))
    if busy.exists():
        return SyncRun.objects.create(kind=kind, status=SyncRun.SKIPPED, finished_at=timezone.now(), message="Another sync was still running.")

    run = SyncRun.objects.create(kind=kind)
    state = SyncState.get()
    client = client or WellnessClient()
    try:
        counts = apply_snapshot(client.snapshot())
        counts["visits"] = pull_visits(client, state, full=full)
        if reconcile_days:
            counts["visits_removed"] = reconcile(client, reconcile_days)
    except Exception as exc:  # recorded for the sync page, then raised for Celery
        log.exception("Sync failed")
        run.status, run.message, run.finished_at = SyncRun.FAILED, str(exc)[:2000], timezone.now()
        run.save()
        state.last_error = run.message
        state.save(update_fields=["last_error"])
        raise
    run.status, run.counts, run.finished_at = SyncRun.OK, counts, timezone.now()
    run.save()
    state.last_success_at, state.last_error = run.finished_at, ""
    state.save(update_fields=["last_success_at", "last_error"])
    return run
