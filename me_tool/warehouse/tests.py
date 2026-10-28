from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from .client import WellnessError
from .models import Company, Employee, Payment, Service, SyncRun, SyncState, Visit
from .sync import run_sync


def iso(dt):
    return dt.isoformat()


class FakeWellness:
    """Stands in for the wellness system's export API."""

    def __init__(self):
        now = timezone.now()
        self.now = now
        self.snapshot_calls = 0
        self.fail = False
        self.data = {
            "companies": [{"id": 1, "name": "FitZone", "is_active": True, "deleted_at": None, "created_at": iso(now)}],
            "services": [{"id": 11, "company_id": 1, "name": "Gym", "price": "3000.00", "is_active": True,
                          "is_approved": True, "eucl_price": "3000.00", "created_at": iso(now)}],
            "employees": [{"id": 101, "employee_id": "EMP0001", "first_name": "John", "last_name": "Doe",
                           "department": "Finance", "position": "Accountant", "is_active": True, "created_at": iso(now)}],
            "payments": [],
        }
        self.visit_rows = []

    def add_visit(self, visit_id, minutes_ago=10, payment_id=None, employee_id=101):
        day = timezone.localdate()
        self.visit_rows.append({
            "id": visit_id, "employee_id": employee_id, "service_id": 11, "company_id": 1, "price": "3000.00",
            "visit_date": day.isoformat(), "visited_at": iso(self.now), "payment_id": payment_id,
            "updated_at": iso(self.now - timedelta(minutes=minutes_ago)),
        })

    # ---- the WellnessClient methods the sync uses
    def snapshot(self):
        if self.fail:
            raise WellnessError("The wellness system can't be reached")
        self.snapshot_calls += 1
        return self.data

    def visits(self, updated_since=None, after_id=0, limit=1000):
        rows = sorted(self.visit_rows, key=lambda r: (r["updated_at"], r["id"]))
        if updated_since:
            rows = [r for r in rows if (r["updated_at"], r["id"]) > (updated_since, after_id)]
        page, more = rows[:limit], len(rows) > limit
        nxt = {"updated_since": page[-1]["updated_at"], "after_id": page[-1]["id"]} if more else None
        return {"results": page, "next": nxt}

    def visit_ids(self, date_from):
        return [r["id"] for r in self.visit_rows if r["visit_date"] >= date_from.isoformat()]


class SyncTests(TestCase):
    def setUp(self):
        self.api = FakeWellness()

    def test_first_sync_copies_everything(self):
        self.api.add_visit(1)
        self.api.add_visit(2)
        run = run_sync(self.api)
        self.assertEqual(run.status, SyncRun.OK)
        self.assertEqual(run.counts["visits"], 2)
        self.assertEqual(Company.objects.get().name, "FitZone")
        self.assertTrue(Service.objects.get().is_covered)
        self.assertEqual(Employee.objects.get().code, "EMP0001")
        self.assertEqual(Visit.objects.count(), 2)
        state = SyncState.get()
        self.assertIsNotNone(state.last_success_at)
        self.assertEqual(state.visits_cursor_id, 2)

    def test_syncing_again_updates_rows_without_duplicates(self):
        self.api.add_visit(1)
        run_sync(self.api)
        self.api.data["companies"][0]["name"] = "FitZone Kigali"
        self.api.data["employees"][0]["department"] = "Audit"
        run_sync(self.api)
        self.assertEqual(Company.objects.get().name, "FitZone Kigali")
        self.assertEqual(Employee.objects.get().department, "Audit")
        self.assertEqual(Visit.objects.count(), 1)

    def test_only_changed_visits_are_read_and_paging_works(self):
        for i in range(1, 6):
            self.api.add_visit(i, minutes_ago=60 - i)
        from . import sync
        old = sync.PAGE_SIZE
        sync.PAGE_SIZE = 2  # 3 pages
        try:
            run_sync(self.api)
        finally:
            sync.PAGE_SIZE = old
        self.assertEqual(Visit.objects.count(), 5)
        # a visit paid later in the wellness system comes back as changed
        self.api.data["payments"] = [{"id": 9, "company_id": 1, "period_start": timezone.localdate().isoformat(),
                                      "period_end": timezone.localdate().isoformat(), "amount": "3000.00",
                                      "reference": "TRX", "paid_at": iso(self.api.now)}]
        self.api.visit_rows[0].update(payment_id=9, updated_at=iso(self.api.now))
        run = run_sync(self.api)
        self.assertTrue(Visit.objects.get(pk=1).is_paid)
        # only rows from just before the cursor (the overlap) were read again
        self.assertLess(run.counts["visits"], 5)

    def test_a_late_committed_visit_is_not_missed(self):
        self.api.add_visit(1, minutes_ago=5)
        run_sync(self.api)
        # saved 1 minute before the cursor, but committed after the last sync
        self.api.add_visit(2, minutes_ago=6)
        run_sync(self.api)
        self.assertTrue(Visit.objects.filter(pk=2).exists())

    def test_reconcile_removes_undone_visits(self):
        self.api.add_visit(1)
        self.api.add_visit(2)
        run_sync(self.api)
        self.api.visit_rows = [r for r in self.api.visit_rows if r["id"] != 2]  # undone at reception
        run = run_sync(self.api, reconcile_days=14)
        self.assertEqual(run.kind, SyncRun.RECONCILE)
        self.assertEqual(run.counts["visits_removed"], 1)
        self.assertEqual(list(Visit.objects.values_list("id", flat=True)), [1])

    def test_a_new_employee_after_the_snapshot_is_fetched(self):
        self.api.add_visit(1)
        run_sync(self.api)
        calls = self.api.snapshot_calls
        # a new employee and their visit, but the snapshot below is read first...
        original = self.api.snapshot

        def stale_snapshot():
            data = original()
            if self.api.snapshot_calls == calls + 1:
                return {**data, "employees": data["employees"][:1]}
            return data

        self.api.data["employees"].append({**self.api.data["employees"][0], "id": 102, "employee_id": "EMP0002"})
        self.api.add_visit(2, minutes_ago=1, employee_id=102)
        self.api.snapshot = stale_snapshot
        run_sync(self.api)
        self.assertTrue(Visit.objects.filter(pk=2, employee_id=102).exists())

    def test_failure_is_recorded(self):
        self.api.fail = True
        with self.assertRaises(WellnessError):
            run_sync(self.api)
        run = SyncRun.objects.get()
        self.assertEqual(run.status, SyncRun.FAILED)
        self.assertIn("can't be reached", run.message)
        self.assertIn("can't be reached", SyncState.get().last_error)

    def test_no_two_runs_at_the_same_time(self):
        SyncRun.objects.create(status=SyncRun.RUNNING)
        run = run_sync(self.api)
        self.assertEqual(run.status, SyncRun.SKIPPED)

    def test_full_sync_reads_everything_again(self):
        self.api.add_visit(1)
        run_sync(self.api)
        run = run_sync(self.api, full=True)
        self.assertEqual(run.kind, SyncRun.FULL)
        self.assertEqual(run.counts["visits"], 1)


class ClientTests(TestCase):
    """The real HTTP client, with a fake requests session."""

    class Response:
        def __init__(self, status, data):
            self.status_code, self._data = status, data

        def json(self):
            return self._data

    class Session:
        def __init__(self, responses):
            self.responses, self.calls = list(responses), []

        def post(self, url, json=None, timeout=None):
            self.calls.append(("POST", url))
            return self.responses.pop(0)

        def get(self, url, params=None, headers=None, timeout=None):
            self.calls.append(("GET", url, headers))
            return self.responses.pop(0)

    def test_signs_in_and_signs_in_again_when_the_token_expires(self):
        from .client import WellnessClient

        R = self.Response
        session = self.Session([
            R(200, {"access": "t1"}), R(401, {"detail": "expired"}), R(200, {"access": "t2"}), R(200, {"ids": [1, 2]}),
        ])
        client = WellnessClient("http://w", "me_sync", "pw", session=session)
        self.assertEqual(client.visit_ids(timezone.localdate()), [1, 2])
        self.assertEqual(session.calls[-1][2]["Authorization"], "Bearer t2")

    def test_wrong_service_account(self):
        from .client import WellnessClient

        session = self.Session([self.Response(401, {"detail": "No active account found"})])
        with self.assertRaisesMessage(WellnessError, "No active account found"):
            WellnessClient("http://w", "me_sync", "bad", session=session).snapshot()

    def test_missing_service_account_settings(self):
        from .client import WellnessClient

        with self.assertRaisesMessage(WellnessError, "WELLNESS_SYNC_USERNAME"):
            WellnessClient("http://w", "", "", session=self.Session([])).snapshot()


class DecimalTests(TestCase):
    def test_money_is_kept_exactly(self):
        api = FakeWellness()
        api.data["services"][0]["eucl_price"] = "2999.99"
        run_sync(api)
        self.assertEqual(Service.objects.get().eucl_price, Decimal("2999.99"))
        self.assertEqual(Payment.objects.count(), 0)
