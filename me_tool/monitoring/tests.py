from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from config.testing import World, make_user
from warehouse.models import SyncState

from . import collectors, health
from .growth import database_growth
from .models import DatabaseSnapshot, ResourceSample
from .tasks import collect_resources, database_snapshot, save_sample

GB = 1024 ** 3

SERVER = {
    "cpu_percent": 20.0, "cpu_count": 8, "cpu_mhz": 2400, "cpu_max_mhz": 3000, "load_1": 0.5,
    "memory_used": 4 * GB, "memory_total": 16 * GB, "disk_used": 50 * GB, "disk_total": 100 * GB,
    "disk_free": 50 * GB, "uptime_seconds": 90000, "processes": 120,
}


def measurements(**changes):
    now = {
        "server": dict(SERVER), "db_ms": 2.0, "db_size": 10 * 1024 * 1024,
        "redis": {"ms": 1.0, "memory": 2 * 1024 * 1024, "peak": 3 * 1024 * 1024, "queue_length": 0},
        "workers": ["celery@worker-1"], "api": {"ok": True, "status": 401, "ms": 40.0},
        "media": {"bytes": 2048, "files": 3},
    }
    now.update(changes)
    return now


class CollectorTests(TestCase):
    def test_server_numbers_are_real(self):
        server = collectors.server()
        self.assertGreater(server["cpu_count"], 0)
        self.assertGreater(server["memory_used"], 0)
        self.assertGreater(server["memory_total"], server["memory_used"])
        self.assertGreater(server["disk_total"], 0)
        self.assertTrue(0 <= server["cpu_percent"] <= 100)

    def test_database_answers_and_tables_are_counted(self):
        World()
        self.assertIsNotNone(collectors.database_ms())
        tables = {t["table"]: t for t in collectors.database_tables()}
        self.assertEqual(tables["warehouse_visit"]["rows"], 6)
        self.assertTrue(tables["warehouse_visit"]["own"])
        self.assertFalse(tables["auth_user"]["own"])

    def test_a_failure_returns_none_instead_of_an_error(self):
        with mock.patch("psutil.virtual_memory", side_effect=OSError("no access")):
            self.assertIsNone(collectors.server())
        with mock.patch("requests.get", side_effect=OSError("refused")):
            self.assertIsNone(collectors.wellness_api())

    def test_wellness_api_401_means_it_is_up(self):
        response = mock.Mock(status_code=401)
        with mock.patch("requests.get", return_value=response):
            self.assertTrue(collectors.wellness_api()["ok"])

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_workers_are_not_checked_when_tasks_run_straight_away(self):
        self.assertIsNone(collectors.workers())


class HealthTests(TestCase):
    def setUp(self):
        state = SyncState.get()
        state.last_success_at = timezone.now() - timedelta(minutes=10)
        state.save()

    def statuses(self, now, growth=None):
        return {c["name"]: c["status"] for c in health.checks(now, growth)}

    def test_all_ok(self):
        result = self.statuses(measurements())
        self.assertEqual(set(result.values()), {"ok"})
        self.assertEqual(health.overall(health.checks(measurements())), "ok")

    def test_limits(self):
        server = {**SERVER, "cpu_percent": 97.0, "memory_used": 15.5 * GB, "disk_used": 96 * GB}
        result = self.statuses(measurements(server=server))
        self.assertEqual((result["CPU"], result["Memory"], result["Disk"]), ("warn", "warn", "fail"))

    def test_down_services(self):
        result = self.statuses(measurements(db_ms=None, workers=[], api={"ok": False, "status": 502, "ms": 10.0}))
        self.assertEqual((result["Database"], result["Celery workers"], result["Wellness API"]), ("fail", "fail", "fail"))

    def test_disk_filling_soon(self):
        result = self.statuses(measurements(), growth={"days_until_full": 12})
        self.assertEqual(result["Disk"], "warn")

    def test_old_sync(self):
        state = SyncState.get()
        state.last_success_at = timezone.now() - timedelta(hours=5)
        state.save()
        self.assertEqual(self.statuses(measurements())["Data sync"], "warn")
        state.last_error = "can't reach the wellness system"
        state.save()
        self.assertEqual(self.statuses(measurements())["Data sync"], "fail")


class GrowthTests(TestCase):
    def test_growth_and_projection(self):
        today = timezone.localdate()
        MB = 1024 * 1024
        for days_ago, size, rows in [(10, 100 * MB, 1000), (5, 150 * MB, 1500), (0, 200 * MB, 2000)]:
            DatabaseSnapshot.objects.create(
                taken_on=today - timedelta(days=days_ago), db_size=size, total_rows=rows,
                tables=[{"table": "warehouse_visit", "label": "Visits", "own": True, "rows": rows, "bytes": size}],
            )
        g = database_growth(disk_free=1000 * MB)
        self.assertEqual(g["per_day"], 10 * MB)
        self.assertEqual(g["rows_per_day"], 100)
        self.assertEqual(g["in_30_days"], 500 * MB)
        self.assertEqual(g["days_until_full"], 100)
        self.assertEqual(g["tables"][0]["added_7_days"], 1000)  # vs the snapshot 10 days ago
        self.assertEqual(len(g["sizes_mb"]), 3)

    def test_no_history_yet(self):
        self.assertIsNone(database_growth()["per_day"])


class TaskTests(TestCase):
    def test_sample_is_saved_and_old_ones_removed(self):
        old = ResourceSample.objects.create()
        ResourceSample.objects.filter(pk=old.pk).update(taken_at=timezone.now() - timedelta(days=60))
        with mock.patch("monitoring.collectors.collect_all", return_value=measurements()):
            collect_resources()
        sample = ResourceSample.objects.get()
        self.assertEqual((sample.cpu_percent, sample.memory_percent, sample.disk_percent), (20.0, 25.0, 50.0))
        self.assertEqual((sample.workers_online, sample.api_ok, sample.queue_length), (1, True, 0))

    def test_sample_with_nothing_measurable(self):
        empty = measurements(server=None, redis=None, workers=None, api=None, media=None, db_ms=None, db_size=None)
        sample = save_sample(empty)
        self.assertIsNone(sample.memory_percent)

    def test_one_snapshot_a_day(self):
        World()
        database_snapshot()
        database_snapshot()
        snapshot = DatabaseSnapshot.objects.get()
        self.assertEqual(snapshot.taken_on, timezone.localdate())
        self.assertGreaterEqual(snapshot.total_rows, 6)


class PageTests(TestCase):
    def setUp(self):
        World()
        self.admin = make_user("admin", superuser=True)
        self.hr = make_user("hr", ["view_me_dashboards", "manage_employees"])

    def test_only_admins(self):
        self.client.force_login(self.hr)
        self.assertEqual(self.client.get("/system/").status_code, 403)
        self.assertEqual(self.client.post("/system/measure/").status_code, 403)

    def test_page_and_measure_now(self):
        self.client.force_login(self.admin)
        with mock.patch("monitoring.collectors.wellness_api", return_value={"ok": True, "status": 401, "ms": 12.0}):
            response = self.client.get("/system/?range=7d")
            self.assertContains(response, "System resources")
            self.assertContains(response, "Health checks")
            self.assertContains(response, "Database size")
            self.assertContains(response, "warehouse_visit")
            self.assertTrue(DatabaseSnapshot.objects.filter(taken_on=timezone.localdate()).exists())
            self.assertRedirects(self.client.post("/system/measure/"), "/system/")
        self.assertEqual(ResourceSample.objects.count(), 1)
