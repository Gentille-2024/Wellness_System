from decimal import Decimal

from django.test import TestCase

from accounts.scope import Scope
from config.testing import World, make_user

from .calculations import calculate
from .models import AT_RISK, NO_DATA, NO_TARGET, OFF_TRACK, ON_TRACK, Indicator, Target, status
from .periods import Month
from .progress import indicator_rows

ALL = Scope(all=True)


class PeriodTests(TestCase):
    def test_months(self):
        m = Month(2026, 1)
        self.assertEqual(m.previous(), Month(2025, 12))
        self.assertEqual(Month(2026, 12).next(), Month(2027, 1))
        self.assertEqual(str(Month(2026, 2).end), "2026-02-28")
        self.assertEqual([x.key for x in Month(2026, 2).last(3)], ["2025-12", "2026-01", "2026-02"])
        self.assertEqual(Month.parse("2026-10"), Month(2026, 10))
        self.assertEqual(Month.parse("rubbish", default=Month(2020, 5)), Month(2020, 5))


class CalculationTests(TestCase):
    """October 2026 in config.testing.World."""

    def setUp(self):
        self.w = World()
        self.month = self.w.month
        self.fitzone = Scope(all=False, company_id=self.w.fitzone.id)

    def value(self, code, scope=ALL):
        return calculate(code, self.month, scope)

    def test_participation_counts_active_employees_only(self):
        self.assertEqual(self.value("participation_rate"), Decimal("75.00"))  # 3 of 4 active

    def test_visits_spend_and_costs(self):
        self.assertEqual(self.value("total_visits"), 4)
        self.assertEqual(self.value("unique_participants"), 3)
        self.assertEqual(self.value("visits_per_participant"), Decimal("1.33"))
        self.assertEqual(self.value("total_spend"), Decimal("26000.00"))
        self.assertEqual(self.value("cost_per_visit"), Decimal("6500.00"))
        self.assertEqual(self.value("cost_per_participant"), Decimal("8666.67"))

    def test_one_company(self):
        self.assertEqual(self.value("total_visits", self.fitzone), 3)
        self.assertEqual(self.value("total_spend", self.fitzone), Decimal("11000.00"))
        self.assertEqual(self.value("service_coverage", self.fitzone), Decimal("66.67"))  # 2 of 3 services

    def test_repeat_rate(self):
        # Last month John (FitZone) and Mary (BlueSpa) came; both came again
        self.assertEqual(self.value("repeat_rate"), Decimal("100.00"))
        # At FitZone only John came last month, and he came again
        self.assertEqual(self.value("repeat_rate", self.fitzone), Decimal("100.00"))
        # BlueSpa: Mary came last month but not this month
        self.assertEqual(self.value("repeat_rate", Scope(all=False, company_id=self.w.spa.id)), Decimal("0.00"))

    def test_coverage_unpaid_and_payment_delay(self):
        self.assertEqual(self.value("service_coverage"), Decimal("75.00"))  # 3 of 4 services
        self.assertEqual(self.value("unpaid_amount"), Decimal("26000.00"))
        self.assertEqual(self.value("payment_delay_days"), Decimal("5.0"))  # period ended 30 Sep, paid 5 Oct

    def test_nothing_to_divide(self):
        empty = Month(2025, 1)
        self.assertIsNone(calculate("cost_per_visit", empty, ALL))
        self.assertIsNone(calculate("repeat_rate", empty, ALL))
        self.assertIsNone(calculate("payment_delay_days", empty, ALL))
        self.assertEqual(calculate("total_visits", empty, ALL), 0)


class StatusTests(TestCase):
    def test_higher_is_better(self):
        self.assertEqual(status(Decimal(80), Decimal(75), Indicator.HIGHER), ON_TRACK)
        self.assertEqual(status(Decimal(70), Decimal(75), Indicator.HIGHER), AT_RISK)
        self.assertEqual(status(Decimal(60), Decimal(75), Indicator.HIGHER), OFF_TRACK)

    def test_lower_is_better(self):
        self.assertEqual(status(Decimal(5000), Decimal(6000), Indicator.LOWER), ON_TRACK)
        self.assertEqual(status(Decimal(6500), Decimal(6000), Indicator.LOWER), AT_RISK)
        self.assertEqual(status(Decimal(9000), Decimal(6000), Indicator.LOWER), OFF_TRACK)

    def test_missing(self):
        self.assertEqual(status(Decimal(1), None, Indicator.HIGHER), NO_TARGET)
        self.assertEqual(status(None, Decimal(1), Indicator.HIGHER), NO_DATA)


class ProgressTests(TestCase):
    def setUp(self):
        self.w = World()

    def test_targets_vs_actuals(self):
        participation = Indicator.objects.get(code="participation-rate")
        Target.objects.create(indicator=participation, period=self.w.month.start, value=Decimal("80"))
        rows = {r["indicator"].code: r for r in indicator_rows(self.w.month, ALL)}
        row = rows["participation-rate"]
        self.assertEqual(row["actual"], Decimal("75.00"))
        self.assertEqual(row["status"], AT_RISK)
        self.assertEqual(len(row["trend"]), 6)
        self.assertEqual(row["trend"][-1]["target"], 80.0)
        self.assertEqual(rows["visits"]["status"], NO_TARGET)

    def test_company_rows_use_company_targets_and_skip_eucl_only_indicators(self):
        visits = Indicator.objects.get(code="visits")
        Target.objects.create(indicator=visits, period=self.w.month.start, value=Decimal("10"))  # EUCL overall
        Target.objects.create(indicator=visits, period=self.w.month.start, company=self.w.fitzone, value=Decimal("3"))
        rows = {r["indicator"].code: r for r in indicator_rows(self.w.month, Scope(all=False, company_id=1), with_trend=False)}
        self.assertNotIn("participation-rate", rows)
        self.assertEqual(rows["visits"]["target"], Decimal("3"))
        self.assertEqual(rows["visits"]["status"], ON_TRACK)


class TargetPageTests(TestCase):
    def setUp(self):
        self.w = World()
        self.officer = make_user("officer", ["view_me_dashboards", "manage_me_targets"])
        self.hr = make_user("hr", ["view_me_dashboards", "manage_employees"])

    def test_only_target_managers_can_open_it(self):
        self.client.force_login(self.hr)
        self.assertEqual(self.client.get("/indicators/targets/").status_code, 403)
        self.client.force_login(self.officer)
        self.assertEqual(self.client.get("/indicators/targets/?month=2026-10").status_code, 200)

    def test_save_repeat_and_clear(self):
        self.client.force_login(self.officer)
        participation = Indicator.objects.get(code="participation-rate")
        response = self.client.post("/indicators/targets/", {
            "month": "2026-10", "company": "", f"target_{participation.id}": "80", f"note_{participation.id}": "HR plan", "repeat": "2",
        })
        self.assertEqual(response.status_code, 302)
        targets = Target.objects.filter(indicator=participation, company__isnull=True).order_by("period")
        self.assertEqual([str(t.period) for t in targets], ["2026-10-01", "2026-11-01", "2026-12-01"])
        self.assertEqual(targets[0].set_by, "officer")
        # empty box removes the target
        self.client.post("/indicators/targets/", {"month": "2026-11", "company": "", f"target_{participation.id}": ""})
        self.assertFalse(Target.objects.filter(indicator=participation, period="2026-11-01").exists())

    def test_company_target_and_bad_numbers(self):
        self.client.force_login(self.officer)
        visits = Indicator.objects.get(code="visits")
        self.client.post("/indicators/targets/", {"month": "2026-10", "company": "1", f"target_{visits.id}": "50"})
        self.assertEqual(Target.objects.get(indicator=visits).company_id, 1)
        response = self.client.post("/indicators/targets/", {"month": "2026-10", "company": "1", f"target_{visits.id}": "lots"}, follow=True)
        self.assertContains(response, "is not a number")
        self.assertEqual(Target.objects.get(indicator=visits).value, Decimal("50"))


class DayAndWeekTests(TestCase):
    def test_week_runs_monday_to_sunday(self):
        from datetime import date

        from .periods import Week

        week = Week.of(date(2026, 10, 22))  # a Thursday
        self.assertEqual((str(week.start), str(week.end)), ("2026-10-19", "2026-10-25"))
        self.assertEqual(week.key, "2026-W43")
        self.assertEqual(week.label, "Week 43 \u00b7 19\u201325 Oct 2026")
        self.assertEqual(str(week.previous().start), "2026-10-12")
        self.assertEqual(Week.of(date(2026, 10, 1)).label, "Week 40 \u00b7 28 Sep\u20134 Oct 2026")

    def test_day(self):
        from datetime import date

        from .periods import Day

        day = Day(date(2026, 10, 23))
        self.assertEqual(day.label, "Friday 23 October 2026")
        self.assertEqual(str(day.next().start), "2026-10-24")
        self.assertEqual([d.short_label for d in day.last(3)], ["21 Oct", "22 Oct", "23 Oct"])

    def test_parsing_from_the_url(self):
        from .periods import Day, Month, Week, period_from_request

        self.assertIsInstance(period_from_request({"period": "week", "date": "2026-10-22"}), Week)
        self.assertIsInstance(period_from_request({"period": "day", "date": "2026-10-22"}), Day)
        self.assertEqual(period_from_request({"month": "2026-09"}), Month(2026, 9))  # older links
        self.assertEqual(period_from_request({"period": "month", "date": "2026-09"}), Month(2026, 9))
        self.assertIsInstance(period_from_request({"period": "week", "date": "rubbish"}), Week)

    def test_calculations_work_for_a_week(self):
        from datetime import date

        from .periods import Week

        World()
        week = Week.of(date(2026, 10, 7))  # 5 to 11 October: Mary 3,000 + Paul 15,000
        self.assertEqual(calculate("total_spend", week, ALL), Decimal("18000.00"))
        self.assertEqual(calculate("unique_participants", week, ALL), 2)
