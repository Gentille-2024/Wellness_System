from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import Company, Employee, Payment, Permission, Role, Service, UserProfile, Visit
from .permissions import COMPANY_DEACTIVATED


# A receptionist with every page switched on (see migration 0014)
DESK_ROLES = (
    "COMPANY_DASHBOARD",
    "COMPANY_RECORD_VISITS",
    "COMPANY_SERVICES",
    "COMPANY_EMPLOYEES_ATTENDED",
    "COMPANY_ATTENDANCE",
)


class EuclTestCase(APITestCase):
    """
    Every test starts from the same small world:
    two service providers (FitZone, BlueSpa) with services, prices and staff,
    an EUCL HR officer, two EUCL employees and a super admin.
    """

    def setUp(self):
        self.today = timezone.localdate()
        self.admin = User.objects.create_superuser("boss_admin", "admin@eucl.test", "Test@12345")

        self.fitzone = Company.objects.create(name="FitZone", email="info@fitzone.test")
        self.spa = Company.objects.create(name="BlueSpa", email="info@bluespa.test")
        # Services EUCL has already chosen to cover
        self.gym = Service.objects.create(company=self.fitzone, name="Gym", price=Decimal("3000"), is_approved=True, eucl_price=Decimal("3000"))
        self.pool = Service.objects.create(company=self.fitzone, name="Swimming", price=Decimal("5000"), is_approved=True, eucl_price=Decimal("5000"))
        self.massage = Service.objects.create(company=self.spa, name="Massage", price=Decimal("15000"), is_approved=True, eucl_price=Decimal("15000"))

        self.fit_boss = self.make_user("fit_boss", "COMPANY_BOSS", company=self.fitzone)
        self.fit_desk = self.make_user("fit_desk", *DESK_ROLES, company=self.fitzone)
        self.spa_desk = self.make_user("spa_desk", *DESK_ROLES, company=self.spa)
        self.hr = self.make_user("eucl_hr", "EUCL_HR")

        self.john = self.make_employee("john")
        self.mary = self.make_employee("mary")

    # ---- helpers -----------------------------------------------------------

    def make_user(self, username, *role_codes, company=None):
        user = User.objects.create_user(username, f"{username}@test.test", "Test@12345")
        profile = UserProfile.objects.create(user=user, company=company)
        profile.roles.set(Role.objects.filter(code__in=role_codes))
        return user

    def make_employee(self, username):
        user = self.make_user(username, "EMPLOYEE")
        return Employee.objects.create(user=user, phone="+250788000000", department="IT", position="Engineer")

    def as_user(self, user):
        self.client.force_authenticate(user)
        return self.client

    def past_visit(self, employee, service, days_ago=1):
        """A visit on an earlier day (an employee visits only one company a day)."""
        return Visit.objects.create(
            employee=employee, service=service, company=service.company, price=service.eucl_price,
            visit_date=self.today - timedelta(days=days_ago),
        )

    def record(self, desk, employee, *services):
        return self.as_user(desk).post(
            "/api/visits/", {"employee": employee.id, "services": [s.id for s in services]}, format="json"
        )


class AccessTests(EuclTestCase):

    def test_login_is_required(self):
        self.assertEqual(self.client.get("/api/visits/").status_code, 401)

    def test_me_lists_permissions_from_all_roles(self):
        both = self.make_user("both", "COMPANY_RECORD_VISITS", "EUCL_HR", company=self.fitzone)
        perms = self.as_user(both).get("/api/me/").data["permissions"]
        self.assertIn("record_visits", perms)
        self.assertIn("manage_employees", perms)

    def test_employee_cannot_record_visits(self):
        self.assertEqual(self.record(self.john.user, self.john, self.gym).status_code, 403)

    def test_receptionist_cannot_onboard_employees(self):
        response = self.as_user(self.fit_desk).post("/api/employees/register/", {}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_only_company_managers_can_add_companies(self):
        response = self.as_user(self.fit_boss).post(
            "/api/companies/", {"name": "X", "email": "x@x.test"}, format="json"
        )
        self.assertEqual(response.status_code, 403)


class PlacesAndServicesTests(EuclTestCase):

    def test_employee_sees_open_companies_and_their_services(self):
        places = self.as_user(self.john.user).get("/api/places/").data
        names = {place["name"]: [s["name"] for s in place["services"]] for place in places}
        self.assertEqual(names, {"BlueSpa": ["Massage"], "FitZone": ["Gym", "Swimming"]})

    def test_deactivated_company_and_inactive_services_are_hidden(self):
        self.as_user(self.admin).post(f"/api/companies/{self.spa.id}/deactivate/")
        self.pool.is_active = False
        self.pool.save()
        places = self.as_user(self.john.user).get("/api/places/").data
        self.assertEqual([(p["name"], [s["name"] for s in p["services"]]) for p in places], [("FitZone", ["Gym"])])

    def test_boss_adds_a_service_to_their_own_company(self):
        response = self.as_user(self.fit_boss).post(
            "/api/services/", {"name": "Yoga", "price": "4000", "company": self.spa.id}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["company"], self.fitzone.id)  # not BlueSpa

    def test_duplicate_service_name_in_a_company_is_refused(self):
        response = self.as_user(self.fit_boss).post(
            "/api/services/", {"name": " gym ", "price": "1"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_receptionist_cannot_change_prices(self):
        response = self.as_user(self.fit_desk).patch(f"/api/services/{self.gym.id}/", {"price": "1"}, format="json")
        self.assertEqual(response.status_code, 403)


class VisitTests(EuclTestCase):

    def test_several_services_on_the_same_day(self):
        response = self.record(self.fit_desk, self.john, self.gym, self.pool)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.data["visits"]), 2)
        # ...and more services at the same company later that day
        self.assertEqual(self.record(self.fit_desk, self.john, self.gym, self.pool).status_code, 400)  # already recorded
        self.assertEqual(Visit.objects.filter(employee=self.john).count(), 2)

    def test_the_same_service_twice_a_day_is_skipped(self):
        self.record(self.fit_desk, self.john, self.gym)
        again = self.record(self.fit_desk, self.john, self.gym)
        self.assertEqual(again.status_code, 400)
        mixed = self.record(self.fit_desk, self.john, self.gym, self.pool)
        self.assertEqual(mixed.status_code, 201)
        self.assertEqual(mixed.data["skipped"], ["Gym"])

    def test_price_is_saved_with_the_visit(self):
        self.record(self.fit_desk, self.john, self.gym)
        self.gym.price = Decimal("9999")
        self.gym.save()
        self.assertEqual(Visit.objects.get().price, Decimal("3000"))

    def test_receptionist_only_records_their_own_companys_services(self):
        self.assertEqual(self.record(self.fit_desk, self.john, self.massage).status_code, 400)

    def test_no_visits_at_a_deactivated_company(self):
        self.as_user(self.admin).post(f"/api/companies/{self.fitzone.id}/deactivate/")
        response = self.record(self.fit_desk, self.john, self.gym)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["detail"], COMPANY_DEACTIVATED)

    def test_deactivated_employee_cannot_be_recorded(self):
        self.john.user.is_active = False
        self.john.user.save()
        self.assertEqual(self.record(self.fit_desk, self.john, self.gym).status_code, 400)

    def test_everyone_sees_only_the_visits_they_should(self):
        self.record(self.fit_desk, self.john, self.gym)
        self.record(self.spa_desk, self.mary, self.massage)

        def count(user):
            return len(self.as_user(user).get("/api/visits/").data)

        self.assertEqual(count(self.john.user), 1)  # own visits
        self.assertEqual(count(self.fit_boss), 1)   # own company
        self.assertEqual(count(self.spa_desk), 1)
        self.assertEqual(count(self.hr), 2)         # all (view_all_visits)
        self.assertEqual(count(self.admin), 2)

    def test_reception_can_undo_todays_unpaid_visit(self):
        visit_id = self.record(self.fit_desk, self.john, self.gym).data["visits"][0]["id"]
        self.assertEqual(self.as_user(self.spa_desk).delete(f"/api/visits/{visit_id}/").status_code, 404)
        self.assertEqual(self.as_user(self.fit_desk).delete(f"/api/visits/{visit_id}/").status_code, 204)


class PaymentTests(EuclTestCase):

    def setUp(self):
        super().setUp()
        self.record(self.fit_desk, self.john, self.gym, self.pool)   # 8,000 at FitZone
        self.record(self.fit_desk, self.mary, self.gym)              # 3,000 at FitZone
        self.past_visit(self.mary, self.massage)                     # 15,000 at BlueSpa (yesterday)

    def pay_fitzone(self, user=None):
        return self.as_user(user or self.admin).post(
            "/api/payments/",
            {"company": self.fitzone.id, "period_start": str(self.today - timedelta(days=30)),
             "period_end": str(self.today), "reference": "TRX-1"},
            format="json",
        )

    def test_company_dashboard_shows_amount_per_service(self):
        data = self.as_user(self.fit_boss).get("/api/stats/", {"scope": "company"}).data
        rows = {row["service"]: (row["visits"], row["total"]) for row in data["by_service"]}
        self.assertEqual(rows, {"Gym": (2, Decimal("6000")), "Swimming": (1, Decimal("5000"))})
        self.assertEqual(data["unpaid"], Decimal("11000"))

    def test_mark_a_period_as_paid(self):
        response = self.pay_fitzone()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Decimal(response.data["amount"]), Decimal("11000"))
        self.assertEqual(Visit.objects.filter(company=self.fitzone, payment__isnull=True).count(), 0)
        # BlueSpa is untouched
        self.assertEqual(Visit.objects.filter(company=self.spa, payment__isnull=True).count(), 1)
        # Nothing left to pay for that period
        self.assertEqual(self.pay_fitzone().status_code, 400)

    def test_balances_per_company(self):
        rows = {row["company_name"]: row["unpaid"] for row in self.as_user(self.admin).get("/api/payments/balances/").data}
        self.assertEqual(rows, {"BlueSpa": Decimal("15000"), "FitZone": Decimal("11000")})

    def test_company_sees_its_payments_but_cannot_mark_paid(self):
        self.pay_fitzone()
        self.assertEqual(self.pay_fitzone(self.fit_boss).status_code, 403)
        payments = self.as_user(self.fit_boss).get("/api/payments/").data
        self.assertEqual(len(payments), 1)
        spa_boss = self.make_user("spa_boss", "COMPANY_BOSS", company=self.spa)
        self.assertEqual(self.as_user(spa_boss).get("/api/payments/").data, [])
        # Payments is not one of the receptionist's pages
        self.assertEqual(self.as_user(self.spa_desk).get("/api/payments/").status_code, 403)

    def test_paid_visits_cannot_be_undone(self):
        self.pay_fitzone()
        visit = Visit.objects.filter(company=self.fitzone).first()
        self.assertEqual(self.as_user(self.admin).delete(f"/api/visits/{visit.id}/").status_code, 400)


class CompanyLifecycleTests(EuclTestCase):

    def test_deactivate_keeps_staff_logins(self):
        response = self.as_user(self.admin).post(f"/api/companies/{self.fitzone.id}/deactivate/")
        self.assertFalse(response.data["is_active"])
        self.fit_desk.refresh_from_db()
        self.assertTrue(self.fit_desk.is_active)
        self.assertTrue(self.as_user(self.admin).post(f"/api/companies/{self.fitzone.id}/activate/").data["is_active"])

    def test_delete_archives_and_keeps_history(self):
        self.record(self.fit_desk, self.john, self.gym)
        self.assertEqual(self.as_user(self.admin).delete(f"/api/companies/{self.fitzone.id}/").status_code, 204)
        self.fitzone.refresh_from_db()
        self.fit_desk.refresh_from_db()
        self.assertTrue(self.fitzone.is_deleted)
        self.assertFalse(self.fit_desk.is_active)
        self.assertEqual(Visit.objects.count(), 1)  # nothing erased
        self.as_user(self.admin).post(f"/api/companies/{self.fitzone.id}/restore/")
        self.fit_desk.refresh_from_db()
        self.assertTrue(self.fit_desk.is_active)


class EmployeeTests(EuclTestCase):

    def register(self, user, **overrides):
        data = {
            "first_name": "New", "last_name": "Person", "username": "newperson",
            "email": "new@eucl.test", "phone": "+250 788 123 456",
            "department": "Finance", "position": "Accountant",
            "password": "Wellness@2026", "password_confirm": "Wellness@2026",
        }
        data.update(overrides)
        return self.as_user(user).post("/api/employees/register/", data, format="json")

    def test_hr_onboards_an_employee(self):
        response = self.register(self.hr)
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(username="newperson")
        self.assertEqual(list(user.userprofile.roles.values_list("code", flat=True)), ["EMPLOYEE"])

    def test_every_field_is_required(self):
        for field in ["email", "phone", "department", "position", "password_confirm"]:
            with self.subTest(missing=field):
                self.assertEqual(self.register(self.hr, **{field: ""}).status_code, 400)


class RoleAndUserTests(EuclTestCase):

    def test_admin_creates_a_role_with_permissions_and_it_works(self):
        response = self.as_user(self.admin).post(
            "/api/roles/",
            {"name": "Finance officer", "description": "Pays the companies", "permissions": ["manage_payments"]},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["code"], "FINANCE_OFFICER")

        finance = self.make_user("fin", "FINANCE_OFFICER")
        self.assertEqual(self.as_user(finance).get("/api/payments/balances/").status_code, 200)
        self.assertEqual(self.as_user(finance).get("/api/users/").status_code, 403)

    def test_role_needs_at_least_one_permission(self):
        response = self.as_user(self.admin).post("/api/roles/", {"name": "Empty", "permissions": []}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_built_in_and_used_roles_cannot_be_deleted(self):
        boss_role = Role.objects.get(code="COMPANY_BOSS")
        self.assertEqual(self.as_user(self.admin).delete(f"/api/roles/{boss_role.id}/").status_code, 400)
        custom = Role.objects.create(code="TEMP", name="Temp")
        self.assertEqual(self.as_user(self.admin).delete(f"/api/roles/{custom.id}/").status_code, 204)

    def test_boss_cannot_make_roles_with_eucl_permissions(self):
        response = self.as_user(self.fit_boss).post("/api/roles/", {"name": "X", "permissions": ["use_services"]}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("permissions", response.data)
        self.assertEqual(self.as_user(self.fit_desk).post("/api/roles/", {"name": "Y", "permissions": ["record_visits"]}, format="json").status_code, 403)

    def test_boss_creates_a_receptionist_in_their_company(self):
        response = self.as_user(self.fit_boss).post(
            "/api/users/",
            {"username": "desk2", "first_name": "Desk", "last_name": "Two", "email": "desk2@test.test",
             "roles": ["COMPANY_RECORD_VISITS"], "company": self.spa.id,
             "password": "Reception@2026", "password_confirm": "Reception@2026"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["company_name"], "FitZone")

    def test_boss_cannot_give_eucl_roles(self):
        response = self.as_user(self.fit_boss).post(
            "/api/users/",
            {"username": "sneaky", "first_name": "S", "last_name": "N", "email": "s@test.test",
             "roles": ["EUCL_HR"], "password": "Reception@2026", "password_confirm": "Reception@2026"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_company_roles_need_a_company(self):
        response = self.as_user(self.admin).post(
            "/api/users/",
            {"username": "nocomp", "first_name": "N", "last_name": "C", "email": "n@test.test",
             "roles": ["COMPANY_RECORD_VISITS"], "password": "Reception@2026", "password_confirm": "Reception@2026"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("company", response.data)

    def test_employee_role_only_comes_from_onboarding(self):
        response = self.as_user(self.admin).post(
            "/api/users/",
            {"username": "fake", "first_name": "F", "last_name": "E", "email": "f@test.test",
             "roles": ["EMPLOYEE"], "password": "Reception@2026", "password_confirm": "Reception@2026"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)


class MyAccountTests(EuclTestCase):

    def test_change_password(self):
        response = self.as_user(self.john.user).post(
            "/api/me/password/",
            {"current_password": "Test@12345", "password": "Brand@New2026", "password_confirm": "Brand@New2026"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.john.user.refresh_from_db()
        self.assertTrue(self.john.user.check_password("Brand@New2026"))


class CoveredServicesTests(EuclTestCase):
    """
    A company lists everything it offers at its own prices; EUCL ticks the
    services its employees may use and agrees the amount it pays for each.
    """

    def setUp(self):
        super().setUp()
        # FitZone also offers a sauna, which EUCL hasn't chosen yet
        self.sauna = Service.objects.create(company=self.fitzone, name="Sauna", price=Decimal("8000"))

    def choose(self, user, company, chosen):
        """chosen: [(service, amount), ...]"""
        return self.as_user(user).post(
            f"/api/companies/{company.id}/covered-services/",
            {"services": [{"id": s.id, "eucl_price": str(amount)} for s, amount in chosen]},
            format="json",
        )

    def test_new_services_wait_for_eucl(self):
        response = self.as_user(self.fit_boss).post("/api/services/", {"name": "Yoga", "price": "4000"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data["is_approved"])
        self.assertIsNone(response.data["eucl_price"])

    def test_boss_cannot_cover_or_set_the_eucl_amount(self):
        response = self.as_user(self.fit_boss).patch(
            f"/api/services/{self.sauna.id}/", {"is_approved": True, "eucl_price": "1"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.sauna.refresh_from_db()
        self.assertFalse(self.sauna.is_approved)
        self.assertIsNone(self.sauna.eucl_price)
        self.assertEqual(self.choose(self.fit_boss, self.fitzone, [(self.sauna, 5000)]).status_code, 403)

    def test_employees_see_every_service_marked_covered_or_not(self):
        place = self.as_user(self.john.user).get(f"/api/places/{self.fitzone.id}/").data
        marks = {s["name"]: s["is_covered"] for s in place["services"]}
        self.assertEqual(marks, {"Gym": True, "Swimming": True, "Sauna": False})
        self.assertEqual(place["covered_count"], 2)
        sauna = next(s for s in place["services"] if s["name"] == "Sauna")
        self.assertIsNone(sauna["eucl_price"])          # not covered: no EUCL amount...
        self.assertEqual(sauna["price"], Decimal("8000"))  # ...but the company's own price

    def test_uncovered_services_cannot_be_recorded(self):
        self.assertEqual(self.record(self.fit_desk, self.john, self.sauna).status_code, 400)

    def test_eucl_chooses_several_services_with_amounts(self):
        response = self.choose(self.admin, self.fitzone, [(self.gym, 2500), (self.sauna, 6000)])
        self.assertEqual(response.status_code, 200)
        # Money comes back as text ("2500.00"), so compare it as a Decimal
        covered = {
            s["name"]: (s["is_approved"], Decimal(s["eucl_price"]) if s["eucl_price"] else None)
            for s in response.data
        }
        self.assertEqual(covered["Gym"], (True, Decimal("2500")))
        self.assertEqual(covered["Sauna"], (True, Decimal("6000")))
        self.assertFalse(covered["Swimming"][0])
        # Takes effect straight away for reception
        self.assertEqual(self.record(self.fit_desk, self.john, self.sauna).status_code, 201)
        self.assertEqual(self.record(self.fit_desk, self.john, self.pool).status_code, 400)

    def test_visits_are_charged_at_the_eucl_amount(self):
        self.choose(self.admin, self.fitzone, [(self.sauna, 6000)])
        self.record(self.fit_desk, self.john, self.sauna)
        visit = Visit.objects.get(service=self.sauna)
        self.assertEqual(visit.price, Decimal("6000"))  # not the company's 8,000

    def test_each_covered_service_needs_an_amount(self):
        response = self.as_user(self.admin).post(
            f"/api/companies/{self.fitzone.id}/covered-services/", {"services": [{"id": self.sauna.id}]}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        response = self.as_user(self.admin).patch(f"/api/services/{self.sauna.id}/", {"is_approved": True}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("eucl_price", response.data)

    def test_another_companys_service_cannot_be_chosen(self):
        self.assertEqual(self.choose(self.admin, self.fitzone, [(self.massage, 1)]).status_code, 400)

    def test_places_can_be_filtered_to_those_with_covered_services(self):
        self.choose(self.admin, self.spa, [])
        everything = [p["name"] for p in self.as_user(self.john.user).get("/api/places/").data]
        covered = [p["name"] for p in self.as_user(self.john.user).get("/api/places/", {"covered": "yes"}).data]
        self.assertEqual(everything, ["BlueSpa", "FitZone"])
        self.assertEqual(covered, ["FitZone"])

class EmployeesAttendedTests(EuclTestCase):
    """Company staff see each EUCL employee who came: services, amounts and totals."""

    def setUp(self):
        super().setUp()
        self.record(self.fit_desk, self.john, self.gym, self.pool)   # John: 3,000 + 5,000
        self.record(self.fit_desk, self.mary, self.gym)              # Mary: 3,000
        self.past_visit(self.mary, self.massage)                     # BlueSpa, not FitZone (yesterday)

    def report(self, user, **params):
        return self.as_user(user).get("/api/visits/by-employee/", params)

    def test_receptionist_and_boss_see_each_employee_and_the_total(self):
        for user in (self.fit_desk, self.fit_boss):
            with self.subTest(user=user.username):
                response = self.report(user)
                self.assertEqual(response.status_code, 200)
                rows = {row["employee_code"]: (row["visits"], row["total"]) for row in response.data["employees"]}
                self.assertEqual(rows, {
                    self.john.employee_id: (2, Decimal("8000")),
                    self.mary.employee_id: (1, Decimal("3000")),
                })
                self.assertEqual(response.data["totals"], {"employees": 2, "visits": 3, "amount": Decimal("11000")})

    def test_services_are_listed_per_employee(self):
        john = next(row for row in self.report(self.fit_boss).data["employees"] if row["employee"] == self.john.id)
        self.assertEqual([(s["service"], s["count"]) for s in john["services"]], [("Gym", 1), ("Swimming", 1)])

    def test_each_company_only_sees_its_own_employees_visits(self):
        data = self.report(self.spa_desk).data
        self.assertEqual(data["totals"], {"employees": 1, "visits": 1, "amount": Decimal("15000")})

    def test_dashboard_counts_employees_attended(self):
        data = self.as_user(self.fit_desk).get("/api/stats/", {"scope": "company"}).data
        self.assertEqual(data["employees_today"], 2)
        self.assertEqual(data["employees_total"], 2)

    def test_access_follows_permissions_not_role_names(self):
        # A new role with only "See company visits & payments" gets the report...
        viewer_role = Role.objects.create(code="AUDITOR", name="Company auditor", is_company_role=True)
        viewer_role.permissions.set(Permission.objects.filter(code="view_company_visits"))
        auditor = self.make_user("auditor", "AUDITOR", company=self.fitzone)
        self.assertEqual(self.report(auditor).data["totals"]["employees"], 2)
        # ...and if the "Employees attended" role loses its permission, so does the receptionist
        page_role = Role.objects.get(code="COMPANY_EMPLOYEES_ATTENDED")
        page_role.permissions.set(Permission.objects.filter(code="manage_company_services"))
        self.assertEqual(self.report(self.fit_desk).status_code, 403)


class CompanyAccountTests(EuclTestCase):
    """A new company comes with its own login (the company boss) and dashboard."""

    def new_company(self, **changes):
        data = {
            "name": "Gold Gym",
            "email": "info@goldgym.test",
            "phone": "+250788111222",
            "address": "KN 5 Rd, Kigali",
            "account_username": "goldgym",
            "account_email": "eric@goldgym.test",
            "account_password": "Strong@2026",
            "account_password_confirm": "Strong@2026",
        }
        data.update(changes)
        return self.as_user(self.admin).post("/api/companies/", data, format="json")

    def test_company_is_created_with_a_boss_login(self):
        response = self.new_company()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn("account_password", response.data)
        company = Company.objects.get(pk=response.data["id"])

        user = User.objects.get(username="goldgym")
        self.assertTrue(user.check_password("Strong@2026"))
        self.assertEqual(user.userprofile.company, company)
        self.assertEqual([r.code for r in user.userprofile.roles.all()], ["COMPANY_BOSS"])
        self.assertEqual(user.get_full_name(), "Gold Gym")  # shown under the company's name

        self.client.force_authenticate(None)
        login = self.client.post("/api/login/", {"username": "goldgym", "password": "Strong@2026"}, format="json")
        self.assertEqual(login.status_code, 200)
        me = self.as_user(user).get("/api/me/").data
        self.assertIn("manage_company_services", me["permissions"])
        self.assertEqual(me["company"]["id"], company.id)

    def test_the_new_company_lists_services_and_eucl_chooses(self):
        company_id = self.new_company().data["id"]
        boss = User.objects.get(username="goldgym")
        service = self.as_user(boss).post(
            "/api/services/", {"name": "Sauna", "price": "6000", "is_approved": True, "eucl_price": "1"}, format="json"
        )
        self.assertEqual(service.status_code, 201, service.data)
        self.assertFalse(service.data["is_approved"])  # only EUCL decides

        response = self.as_user(self.admin).post(
            f"/api/companies/{company_id}/covered-services/",
            {"services": [{"id": service.data["id"], "eucl_price": "5000"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        sauna = Service.objects.get(pk=service.data["id"])
        self.assertTrue(sauna.is_approved)
        self.assertEqual(sauna.eucl_price, Decimal("5000"))

    def test_login_details_are_required(self):
        response = self.new_company(account_username="", account_password="")
        self.assertEqual(response.status_code, 400)
        self.assertIn("account_username", response.data)
        self.assertIn("account_password", response.data)
        self.assertFalse(Company.objects.filter(name="Gold Gym").exists())

    def test_bad_login_details_create_nothing(self):
        for changes, field in [
            ({"account_username": "fit_boss"}, "account_username"),
            ({"account_email": "fit_desk@test.test"}, "account_email"),
            ({"account_password_confirm": "Other@2026"}, "account_password_confirm"),
            ({"account_password": "123", "account_password_confirm": "123"}, "account_password"),
        ]:
            response = self.new_company(**changes)
            self.assertEqual(response.status_code, 400, changes)
            self.assertIn(field, response.data)
        self.assertFalse(Company.objects.filter(name="Gold Gym").exists())
        self.assertFalse(User.objects.filter(username="goldgym").exists())

    def test_editing_a_company_needs_no_login_details(self):
        response = self.as_user(self.admin).patch(
            f"/api/companies/{self.fitzone.id}/", {"phone": "+250788999000"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)


class OwedAndStatementTests(EuclTestCase):
    """What EUCL owes each company, and the statement used for the PDF / Excel export."""

    def setUp(self):
        super().setUp()
        self.record(self.fit_desk, self.john, self.gym, self.pool)   # 8,000 at FitZone
        self.record(self.fit_desk, self.mary, self.gym)              # 3,000 at FitZone
        self.past_visit(self.mary, self.massage)                     # 15,000 at BlueSpa (yesterday)

    def test_balances_show_employees_attended(self):
        rows = {row["company_name"]: row for row in self.as_user(self.admin).get("/api/payments/balances/").data}
        self.assertEqual(rows["FitZone"]["employees"], 2)
        self.assertEqual(rows["FitZone"]["unpaid"], Decimal("11000"))
        self.assertEqual(rows["BlueSpa"]["employees"], 1)

    def test_eucl_statement_per_company_and_employee(self):
        data = self.as_user(self.admin).get("/api/payments/statement/").data
        companies = {c["company_name"]: c for c in data["companies"]}
        fitzone = {e["employee_code"]: e["amount"] for e in companies["FitZone"]["employees"]}
        self.assertEqual(fitzone, {self.john.employee_id: Decimal("8000"), self.mary.employee_id: Decimal("3000")})
        self.assertEqual(companies["FitZone"]["amount"], Decimal("11000"))
        self.assertEqual(companies["FitZone"]["employee_count"], 2)
        self.assertEqual(data["totals"]["amount"], Decimal("26000"))
        self.assertEqual(data["totals"]["employees"], 2)  # Mary counted once
        self.assertEqual(data["totals"]["companies"], 2)

    def test_company_statement_is_only_its_own(self):
        data = self.as_user(self.fit_boss).get("/api/payments/statement/").data
        self.assertEqual([c["company_name"] for c in data["companies"]], ["FitZone"])
        self.assertEqual(data["totals"]["amount"], Decimal("11000"))
        # even when asking for another company
        data = self.as_user(self.fit_boss).get("/api/payments/statement/", {"company": self.spa.id}).data
        self.assertEqual(data["companies"], [])

    def test_statement_can_show_only_what_is_owed(self):
        self.as_user(self.admin).post(
            "/api/payments/",
            {"company": self.fitzone.id, "period_start": str(self.today), "period_end": str(self.today)},
            format="json",
        )
        data = self.as_user(self.admin).get("/api/payments/statement/", {"paid": "no"}).data
        self.assertEqual([c["company_name"] for c in data["companies"]], ["BlueSpa"])
        self.assertEqual(data["totals"]["amount"], Decimal("15000"))

    def test_employees_cannot_read_statements(self):
        self.assertEqual(self.as_user(self.john.user).get("/api/payments/statement/").status_code, 403)


class DeactivatedCompanyTests(EuclTestCase):
    MESSAGE = COMPANY_DEACTIVATED

    def setUp(self):
        super().setUp()
        self.fit_desk.set_password("Test@12345")
        self.fit_desk.save()
        self.as_user(self.admin).post(f"/api/companies/{self.fitzone.id}/deactivate/")
        self.client.force_authenticate(None)

    def login(self, username):
        return self.client.post("/api/login/", {"username": username, "password": "Test@12345"}, format="json")

    def test_staff_login_shows_the_message(self):
        response = self.login("fit_desk")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["detail"], self.MESSAGE)
        self.assertEqual(response.data["code"], "company_deactivated")

    def test_open_sessions_get_the_message(self):
        for url in ["/api/me/", "/api/visits/", "/api/payments/"]:
            response = self.as_user(self.fit_boss).get(url)
            self.assertEqual(response.status_code, 403, url)
            self.assertEqual(response.data["detail"], self.MESSAGE)

    def test_other_companies_are_not_affected(self):
        self.assertEqual(self.login("spa_desk").status_code, 200)

    def test_staff_who_are_also_employees_keep_their_employee_access(self):
        both = self.make_user("both", *DESK_ROLES, "EMPLOYEE", company=self.fitzone)
        Employee.objects.create(user=both, phone="+250788000001", department="IT", position="Engineer")
        me = self.as_user(both).get("/api/me/").data
        self.assertIn("use_services", me["permissions"])
        self.assertNotIn("record_visits", me["permissions"])
        self.assertNotIn("record_visits", me["role_permissions"])

    def test_activating_again_gives_access_back(self):
        self.as_user(self.admin).post(f"/api/companies/{self.fitzone.id}/activate/")
        self.client.force_authenticate(None)
        self.assertEqual(self.login("fit_desk").status_code, 200)


class PageRoleTests(EuclTestCase):
    """Each company page is a role the boss switches on or off for a staff member."""

    def staff(self, *roles):
        return self.make_user("desk_" + "_".join(r.lower() for r in roles)[:20], *roles, company=self.fitzone)

    def test_the_page_roles_exist_and_the_old_receptionist_role_is_gone(self):
        codes = set(Role.objects.filter(is_company_role=True).values_list("code", flat=True))
        self.assertTrue(set(DESK_ROLES) <= codes)
        self.assertNotIn("COMPANY_RECEPTIONIST", codes)

    def test_record_visits_only(self):
        desk = self.staff("COMPANY_RECORD_VISITS")
        self.assertEqual(self.record(desk, self.john, self.gym).status_code, 201)
        self.assertEqual(self.as_user(desk).get("/api/stats/", {"scope": "company"}).status_code, 403)
        self.assertEqual(self.as_user(desk).get("/api/visits/by-employee/").status_code, 403)
        self.assertEqual(self.as_user(desk).get("/api/payments/").status_code, 403)

    def test_dashboard_only(self):
        desk = self.staff("COMPANY_DASHBOARD")
        self.assertEqual(self.as_user(desk).get("/api/stats/", {"scope": "company"}).status_code, 200)
        self.assertEqual(self.record(desk, self.john, self.gym).status_code, 403)

    def test_employees_attended_only(self):
        self.record(self.fit_desk, self.john, self.gym)
        desk = self.staff("COMPANY_EMPLOYEES_ATTENDED")
        self.assertEqual(self.as_user(desk).get("/api/visits/by-employee/").data["totals"]["employees"], 1)
        self.assertEqual(self.record(desk, self.mary, self.gym).status_code, 403)

    def test_attendance_lists_employees_and_records_their_services(self):
        desk = self.staff("COMPANY_ATTENDANCE")
        self.assertEqual(self.as_user(desk).get("/api/employees/").status_code, 200)
        self.assertEqual(self.record(desk, self.john, self.gym, self.pool).status_code, 201)
        self.assertEqual(self.record(desk, self.mary, self.gym).status_code, 201)
        today = self.as_user(desk).get("/api/visits/", {"today": "yes"}).data
        self.assertEqual(len(today), 3)
        self.assertEqual(self.as_user(desk).get("/api/visits/by-employee/").status_code, 403)

    def test_boss_has_every_page_except_attendance(self):
        perms = set(self.as_user(self.fit_boss).get("/api/me/").data["permissions"])
        self.assertTrue({"view_company_dashboard", "record_visits", "view_company_services",
                         "view_employees_attended"} <= perms)
        # Employees attendance is the receptionist's page, not the boss's
        self.assertNotIn("take_attendance", perms)

    def test_boss_gives_several_page_roles(self):
        response = self.as_user(self.fit_boss).post(
            "/api/users/",
            {"username": "reception1", "first_name": "Reception", "last_name": "One", "email": "r1@test.test",
             "roles": ["COMPANY_DASHBOARD", "COMPANY_RECORD_VISITS", "COMPANY_ATTENDANCE"],
             "password": "Reception@2026", "password_confirm": "Reception@2026"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(sorted(response.data["roles"]), ["COMPANY_ATTENDANCE", "COMPANY_DASHBOARD", "COMPANY_RECORD_VISITS"])


class CompanyOwnRoleTests(EuclTestCase):
    """A company boss adds roles for their own company, from the staff form."""

    def create_role(self, boss=None, **data):
        payload = {"name": "Cashier", "description": "Takes payments at the desk", "permissions": ["record_visits", "view_company_dashboard"]}
        payload.update(data)
        return self.as_user(boss or self.fit_boss).post("/api/roles/", payload, format="json")

    def test_boss_creates_a_role_for_their_company(self):
        response = self.create_role()
        self.assertEqual(response.status_code, 201, response.data)
        role = Role.objects.get(pk=response.data["id"])
        self.assertEqual(role.company, self.fitzone)
        self.assertTrue(role.is_company_role)
        self.assertFalse(role.is_system)

    def test_the_role_is_only_seen_and_given_inside_that_company(self):
        role_id = self.create_role().data["id"]
        spa_boss = self.make_user("spa_boss", "COMPANY_BOSS", company=self.spa)
        self.assertNotIn(role_id, [r["id"] for r in self.as_user(spa_boss).get("/api/roles/").data])
        self.assertIn(role_id, [r["id"] for r in self.as_user(self.fit_boss).get("/api/roles/").data])
        # BlueSpa can't give FitZone's role
        code = Role.objects.get(pk=role_id).code
        response = self.as_user(spa_boss).post(
            "/api/users/",
            {"username": "cash2", "first_name": "C", "last_name": "T", "email": "c2@test.test", "roles": [code],
             "password": "Reception@2026", "password_confirm": "Reception@2026"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        # ...and the same name is free for BlueSpa's own role
        self.assertEqual(self.create_role(boss=spa_boss).status_code, 201)

    def test_new_role_gives_its_pages(self):
        code = Role.objects.get(pk=self.create_role().data["id"]).code
        response = self.as_user(self.fit_boss).post(
            "/api/users/",
            {"username": "cashier1", "first_name": "Cash", "last_name": "Ier", "email": "cashier1@test.test", "roles": [code],
             "password": "Reception@2026", "password_confirm": "Reception@2026"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        cashier = User.objects.get(username="cashier1")
        perms = set(self.as_user(cashier).get("/api/me/").data["permissions"])
        self.assertEqual(perms, {"record_visits", "view_company_dashboard"})

    def test_boss_cannot_give_staff_management_or_change_eucl_roles(self):
        self.assertEqual(self.create_role(permissions=["manage_company_staff"]).status_code, 400)
        shared = Role.objects.get(code="COMPANY_DASHBOARD")
        response = self.as_user(self.fit_boss).patch(f"/api/roles/{shared.id}/", {"permissions": ["record_visits"]}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_boss_only_sees_company_permissions(self):
        codes = {p["code"] for p in self.as_user(self.fit_boss).get("/api/permissions/").data}
        self.assertIn("take_attendance", codes)
        self.assertNotIn("manage_company_staff", codes)
        self.assertNotIn("manage_users", codes)

    def test_duplicate_name_in_the_same_company(self):
        self.create_role()
        self.assertEqual(self.create_role().status_code, 400)
        self.assertEqual(self.create_role(name="Dashboard").status_code, 400)  # EUCL's shared role


class OneCompanyPerDayTests(EuclTestCase):
    """Several services a day, but only at one company."""

    def test_second_company_the_same_day_is_refused(self):
        self.assertEqual(self.record(self.fit_desk, self.john, self.gym).status_code, 201)
        response = self.record(self.spa_desk, self.john, self.massage)
        self.assertEqual(response.status_code, 400)
        self.assertIn("only one company per day", str(response.data["employee"]))
        self.assertNotIn("FitZone", str(response.data))  # BlueSpa isn't told where John went

    def test_more_services_at_the_same_company_later_that_day(self):
        self.record(self.fit_desk, self.john, self.gym)
        self.assertEqual(self.record(self.fit_desk, self.john, self.pool).status_code, 201)

    def test_another_company_on_another_day(self):
        self.past_visit(self.john, self.gym)
        self.assertEqual(self.record(self.spa_desk, self.john, self.massage).status_code, 201)

    def test_attendance_list_shows_who_went_elsewhere_today(self):
        self.record(self.fit_desk, self.john, self.gym)
        rows = {row["id"]: row["elsewhere_today"] for row in self.as_user(self.spa_desk).get("/api/employees/").data}
        self.assertTrue(rows[self.john.id])
        self.assertFalse(rows[self.mary.id])


class CompanySeesOnlyItsVisitorsTests(EuclTestCase):
    """Companies only see the EUCL employees who came to them; the attendance page lists everyone."""

    def setUp(self):
        super().setUp()
        self.record(self.fit_desk, self.john, self.gym)
        self.desk = self.make_user("desk_only", "COMPANY_RECORD_VISITS", company=self.fitzone)

    def ids(self, user, **params):
        return {row["id"] for row in self.as_user(user).get("/api/employees/", params).data}

    def test_without_the_attendance_page_only_visitors_are_listed(self):
        self.assertEqual(self.ids(self.desk), {self.john.id})

    def test_reception_can_still_search_anyone_to_record_them(self):
        self.assertEqual(self.ids(self.desk, search=self.mary.employee_id), {self.mary.id})

    def test_the_attendance_page_lists_every_employee(self):
        self.assertEqual(self.ids(self.fit_desk), {self.john.id, self.mary.id})

    def test_eucl_sees_everyone(self):
        self.assertEqual(self.ids(self.admin), {self.john.id, self.mary.id})


class ExportForMETests(EuclTestCase):
    """The read-only export the M&E tool syncs from."""

    def setUp(self):
        super().setUp()
        self.sync = self.make_user("me_sync", "ME_SYNC")
        self.record(self.fit_desk, self.john, self.gym, self.pool)
        self.record(self.spa_desk, self.mary, self.massage)

    def test_only_the_export_permission_can_read_it(self):
        for user in (self.fit_boss, self.hr, self.john.user):
            self.assertEqual(self.as_user(user).get("/api/export/snapshot/").status_code, 403)
        self.assertEqual(self.as_user(self.sync).get("/api/export/snapshot/").status_code, 200)
        # read-only: writing is refused
        self.assertIn(self.as_user(self.sync).post("/api/export/snapshot/").status_code, (403, 405))

    def test_snapshot_has_every_small_table(self):
        data = self.as_user(self.sync).get("/api/export/snapshot/").data
        self.assertEqual({c["name"] for c in data["companies"]}, {"FitZone", "BlueSpa"})
        self.assertEqual(len(data["services"]), 3)
        self.assertEqual({e["employee_id"] for e in data["employees"]}, {self.john.employee_id, self.mary.employee_id})
        self.assertIn("is_active", data["employees"][0])

    def test_visits_are_paged_with_a_cursor_without_gaps(self):
        client = self.as_user(self.sync)
        page = client.get("/api/export/visits/", {"limit": 2}).data
        self.assertEqual(len(page["results"]), 2)
        self.assertIsNotNone(page["next"])
        rest = client.get("/api/export/visits/", {"limit": 2, **page["next"]}).data
        self.assertEqual(len(rest["results"]), 1)
        self.assertIsNone(rest["next"])
        ids = [v["id"] for v in page["results"] + rest["results"]]
        self.assertEqual(sorted(ids), sorted(Visit.objects.values_list("id", flat=True)))

    def test_paying_a_visit_marks_it_changed(self):
        client = self.as_user(self.sync)
        cursor = client.get("/api/export/visits/").data["results"][-1]["updated_at"]
        self.assertEqual(client.get("/api/export/visits/", {"updated_since": cursor, "after_id": 10**6}).data["results"], [])
        self.as_user(self.admin).post(
            "/api/payments/",
            {"company": self.fitzone.id, "period_start": str(self.today), "period_end": str(self.today)},
            format="json",
        )
        client = self.as_user(self.sync)
        changed = client.get("/api/export/visits/", {"updated_since": cursor, "after_id": 10**6}).data["results"]
        self.assertEqual(len(changed), 2)
        self.assertTrue(all(v["payment_id"] for v in changed))

    def test_visit_ids_show_undone_visits(self):
        client = self.as_user(self.sync)
        before = set(client.get("/api/export/visit-ids/", {"date_from": str(self.today)}).data["ids"])
        undone = Visit.objects.filter(employee=self.mary).first()
        self.as_user(self.spa_desk).delete(f"/api/visits/{undone.id}/")
        client = self.as_user(self.sync)
        after = set(client.get("/api/export/visit-ids/", {"date_from": str(self.today)}).data["ids"])
        self.assertEqual(before - after, {undone.id})

    def test_bad_parameters(self):
        client = self.as_user(self.sync)
        self.assertEqual(client.get("/api/export/visits/", {"updated_since": "yesterday"}).status_code, 400)
        self.assertEqual(client.get("/api/export/visit-ids/").status_code, 400)

    def test_me_roles(self):
        self.assertIn("view_me_dashboards", self.as_user(self.hr).get("/api/me/").data["permissions"])
        officer = self.make_user("officer", "ME_OFFICER")
        self.assertTrue({"view_me_dashboards", "manage_me_targets"} <= set(self.as_user(officer).get("/api/me/").data["permissions"]))
