from django.test import TestCase

from config.testing import World, make_user


class PageAccessTests(TestCase):
    """Admin and EUCL see everything; a company's staff only their own company."""

    def setUp(self):
        self.w = World()
        self.admin = make_user("admin", superuser=True, roles=["Super admin"])
        self.hr = make_user("hr", ["view_me_dashboards", "manage_employees"], roles=["EUCL HR"])
        self.boss = make_user("fit_boss", ["view_company_visits", "manage_company_services"], company=self.w.fitzone, roles=["Company boss"])
        self.desk = make_user("fit_desk", ["record_visits"], company=self.w.fitzone, roles=["Record visits"])
        self.employee = make_user("john", ["use_services"], roles=["Employee"])

    def get(self, user, url):
        self.client.force_login(user)
        return self.client.get(url)

    def test_login_is_required(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_eucl_sees_every_page(self):
        for user in (self.admin, self.hr):
            for url in ["/?month=2026-10", "/companies/?month=2026-10", "/companies/2/?month=2026-10",
                        "/services/?month=2026-10", "/services/?company=2&month=2026-10", "/indicators/?month=2026-10",
                        "/indicators/?company=1&month=2026-10", "/reports/"]:
                self.assertEqual(self.get(user, url).status_code, 200, (user.username, url))

    def test_overview_numbers(self):
        response = self.get(self.hr, "/?month=2026-10")
        self.assertContains(response, "75.0%")          # participation
        self.assertContains(response, "RWF 26,000")     # spend
        self.assertContains(response, "John Doe")        # names: EUCL only

    def test_company_staff_only_see_their_company(self):
        response = self.get(self.boss, "/?month=2026-10")
        self.assertRedirects(response, "/companies/1/?month=2026-10", fetch_redirect_response=False)
        response = self.get(self.boss, "/companies/1/?month=2026-10")
        self.assertContains(response, "RWF 11,000")
        self.assertNotContains(response, "BlueSpa")
        self.assertNotContains(response, "John Doe")
        self.assertEqual(self.get(self.boss, "/companies/2/").status_code, 404)
        self.assertEqual(self.get(self.boss, "/companies/").status_code, 403)
        # the ?company= filter can't widen what they see
        response = self.get(self.boss, "/services/?company=2&month=2026-10")
        self.assertContains(response, "Gym")
        self.assertNotContains(response, "Massage")
        response = self.get(self.boss, "/indicators/?company=2&month=2026-10")
        self.assertContains(response, "FitZone")

    def test_people_without_an_m_and_e_permission(self):
        for user in (self.desk, self.employee):
            self.assertEqual(self.get(user, "/").status_code, 403, user.username)

    def test_sync_page_is_for_admins(self):
        self.assertEqual(self.get(self.hr, "/sync/").status_code, 403)
        self.assertEqual(self.get(self.admin, "/sync/").status_code, 200)

    def test_health_check(self):
        self.assertEqual(self.client.get("/healthz/").content, b"ok")


class PeriodDashboardTests(TestCase):
    def setUp(self):
        self.w = World()
        self.hr = make_user("hr", ["view_me_dashboards", "manage_employees"])
        self.client.force_login(self.hr)

    def test_weekly_and_daily_overview(self):
        response = self.client.get("/?period=week&date=2026-10-07")
        self.assertContains(response, "Week 41")
        self.assertContains(response, "RWF 18,000")
        self.assertContains(response, "Targets are set per month")  # no target statuses for a week
        self.assertContains(response, "Last 12 weeks")
        response = self.client.get("/?period=day&date=2026-10-02")
        self.assertContains(response, "Friday 2 October 2026")
        self.assertContains(response, "RWF 8,000")

    def test_switching_keeps_the_same_moment(self):
        response = self.client.get("/?period=day&date=2026-10-07")
        urls = {k["kind"]: k["url"] for k in response.context["period_kinds"]}
        self.assertIn("period=week&date=2026-10-05", urls["week"])
        self.assertIn("period=month&date=2026-10", urls["month"])

    def test_weekly_trend(self):
        from datetime import date

        from accounts.scope import Scope
        from indicators.periods import Week

        from .metrics import trend

        t = trend(Week.of(date(2026, 10, 7)), Scope(all=True), count=3)
        self.assertEqual(t["visits"], [0, 2, 2])  # 21-27 Sep, 28 Sep to 4 Oct, 5-11 Oct

    def test_company_and_services_pages_by_week(self):
        self.assertContains(self.client.get("/companies/1/?period=week&date=2026-10-07"), "Week report (PDF)")
        self.assertContains(self.client.get("/services/?period=week&date=2026-10-07"), "Previous week")

    def test_indicators_page_shows_the_month_of_the_period(self):
        response = self.client.get("/indicators/?period=week&date=2026-10-07")
        self.assertEqual(response.context["month"].key, "2026-10")
