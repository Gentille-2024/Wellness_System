import time
from unittest import mock
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import Company, Employee, Payment, Permission, Role, Service, UserProfile, Visit
from .permissions import COMPANY_DEACTIVATED


# The built-in receptionist (see migration 0018)
DESK_ROLES = ("COMPANY_RECEPTIONIST",)

# One-page roles used by some tests to check single permissions. They are
# not built in any more (migration 0018), so the tests create them.
PAGE_ROLES = [
    ("COMPANY_DASHBOARD", "Dashboard", "view_company_dashboard"),
    ("COMPANY_RECORD_VISITS", "Record services", "record_visits"),
    ("COMPANY_SERVICES", "Services & prices", "view_company_services"),
    ("COMPANY_EMPLOYEES_ATTENDED", "Employees attended", "view_employees_attended"),
    ("COMPANY_ATTENDANCE", "Employees attendance", "take_attendance"),
]


class EuclTestCase(APITestCase):
    """
    Every test starts from the same small world:
    two service providers (FitZone, BlueSpa) with services, prices and staff,
    an EUCL HR officer, two EUCL employees and a super admin.
    """

    def setUp(self):
        self.today = timezone.localdate()
        self.admin = User.objects.create_superuser("boss_admin", "admin@eucl.test", "Test@12345")
        for code, name, permission in PAGE_ROLES:
            role = Role.objects.create(code=code, name=f"{name} only", is_company_role=True)
            role.permissions.set(Permission.objects.filter(code=permission))

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
        return Employee.objects.create(user=user, employee_id=username.upper(), phone="+250788000000", department="IT", position="Engineer")

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

    def test_me_lists_the_permissions_of_the_role(self):
        perms = self.as_user(self.hr).get("/api/me/").data["permissions"]
        self.assertIn("manage_employees", perms)
        self.assertNotIn("record_visits", perms)

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

    def test_receptionist_can_change_prices_only(self):
        desk = self.as_user(self.fit_desk)
        response = desk.patch(f"/api/services/{self.gym.id}/", {"price": "3200"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.gym.refresh_from_db()
        self.assertEqual(self.gym.price, Decimal("3200"))
        # ...but not add services, rename them or switch them off
        self.assertEqual(desk.post("/api/services/", {"name": "Yoga", "price": "1"}, format="json").status_code, 403)
        self.assertEqual(desk.patch(f"/api/services/{self.gym.id}/", {"is_active": False}, format="json").status_code, 403)
        self.assertEqual(desk.patch(f"/api/services/{self.gym.id}/", {"name": "X", "price": "1"}, format="json").status_code, 403)

    def test_receptionist_cannot_change_another_companys_price(self):
        other = Service.objects.filter(company=self.spa).first()
        response = self.as_user(self.fit_desk).patch(f"/api/services/{other.id}/", {"price": "1"}, format="json")
        self.assertEqual(response.status_code, 404)

    def test_receptionist_without_the_permission_cannot_change_prices(self):
        Role.objects.get(code="COMPANY_RECEPTIONIST").permissions.remove(Permission.objects.get(code="edit_service_prices"))
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
        self.assertEqual(count(self.hr), 0)         # HR is like an employee: only their own
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
            "employee_id": "emp0101", "first_name": "New", "last_name": "Person", "username": "newperson",
            "email": "new@eucl.test", "phone": "+250 788 123 456",
            "department": "Finance", "position": "Accountant",
            "password": "Wellness@2026", "password_confirm": "Wellness@2026",
        }
        data.update(overrides)
        return self.as_user(user).post("/api/employees/register/", data, format="json")

    def test_hr_onboards_an_employee(self):
        response = self.register(self.hr)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["employee_id"], "EMP0101")  # typed by HR, tidied
        user = User.objects.get(username="newperson")
        self.assertEqual(list(user.userprofile.roles.values_list("code", flat=True)), ["EMPLOYEE"])

    def test_required_fields(self):
        for field in ["employee_id", "first_name", "last_name", "department", "position"]:
            with self.subTest(missing=field):
                self.assertEqual(self.register(self.hr, **{field: ""}).status_code, 400)
        # passwords that don't match
        self.assertEqual(self.register(self.hr, password_confirm="Other@2026").status_code, 400)

    def test_no_automatic_id_and_ids_are_unique(self):
        self.assertEqual(self.register(self.hr, employee_id=self.john.employee_id, username="x2").status_code, 400)

    def test_username_is_the_last_name_and_the_password_comes_at_first_login(self):
        response = self.register(self.hr, employee_id="EMP0200", last_name="Charlotte", username="",
                                 password="", password_confirm="", email="c1@eucl.test", phone="0788 000 222")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["username"], "Charlotte")
        # a second Charlotte gets Charlotte2
        second = self.register(self.hr, employee_id="EMP0201", last_name="Charlotte", username="",
                               password="", password_confirm="", email="c2@eucl.test")
        self.assertEqual(second.data["username"], "Charlotte2")
        # no password yet: the Employee ID does not work as a password
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post("/api/login/", {"username": "Charlotte", "password": "EMP0200"}, format="json").status_code, 401)

    def test_email_and_phone_are_required(self):
        for field in ["email", "phone"]:
            with self.subTest(missing=field):
                response = self.register(self.hr, username="", password="", password_confirm="", **{field: ""})
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)

    def test_hr_department_gets_the_hr_role(self):
        response = self.register(self.hr, department="hr")
        employee = Employee.objects.get(pk=response.data["id"])
        roles = set(employee.user.userprofile.roles.values_list("code", flat=True))
        self.assertEqual(roles, {"EUCL_HR"})  # one role: HR instead of Employee
        perms = set(self.as_user(employee.user).get("/api/me/").data["permissions"])
        self.assertTrue({"view_my_overview", "view_places", "view_my_services", "manage_employees", "import_employees"} <= perms)
        self.assertNotIn("view_all_visits", perms)
        # moving out of HR gives the Employee role back instead
        self.as_user(self.admin).patch(f"/api/employees/{employee.id}/", {"department": "Finance"}, format="json")
        self.assertEqual(list(employee.user.userprofile.roles.values_list("code", flat=True)), ["EMPLOYEE"])


class FirstLoginTests(EuclTestCase):
    """An employee HR added creates their own account (password) at first login."""

    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        cache.clear()  # the first-login throttle counts tries per address
        self.as_user(self.hr).post("/api/employees/register/", {
            "employee_id": "EMP0700", "first_name": "NATUKUNDA", "last_name": "Charlotte",
            "email": "cnatukunda@eucl.test", "phone": "+250787778849", "department": "HR", "position": "Manager",
        }, format="json")
        self.client.force_authenticate(None)

    def first_login(self, **overrides):
        data = {"employee_id": "emp0700", "contact": "cnatukunda@eucl.test",
                "password": "MyWellness@26", "password_confirm": "MyWellness@26"}
        data.update(overrides)
        return self.client.post("/api/first-login/", data, format="json")

    def login(self, username, password):
        return self.client.post("/api/login/", {"username": username, "password": password}, format="json")

    def test_with_email_then_sign_in(self):
        response = self.first_login()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["username"], "Charlotte")
        self.assertEqual(self.login("Charlotte", "MyWellness@26").status_code, 200)

    def test_with_phone_written_another_way(self):
        self.assertEqual(self.first_login(contact="0787 778 849").status_code, 200)

    def test_wrong_details_or_twice_are_refused(self):
        self.assertEqual(self.first_login(contact="someone@else.test").status_code, 400)
        self.assertEqual(self.first_login(employee_id="NOPE").status_code, 400)
        self.assertEqual(self.first_login().status_code, 200)
        again = self.first_login(password="Other@Pass26", password_confirm="Other@Pass26")
        self.assertEqual(again.status_code, 400)  # the account exists: sign in instead
        self.assertEqual(self.login("Charlotte", "MyWellness@26").status_code, 200)

    def test_password_rules(self):
        self.assertEqual(self.first_login(password="123", password_confirm="123").status_code, 400)
        self.assertEqual(self.first_login(password_confirm="Different@26").status_code, 400)


class EmployeeImportTests(EuclTestCase):
    """HR downloads the Excel template and uploads employees."""

    def xlsx(self, rows, header=("EmpID", "First name", "Last name", "Email", "Phone", "Department", "Position")):
        import io
        from django.core.files.uploadedfile import SimpleUploadedFile
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Employees"
        ws.append(list(header))
        for row in rows:
            ws.append(list(row))
        out = io.BytesIO()
        wb.save(out)
        return SimpleUploadedFile("employees.xlsx", out.getvalue())

    def upload(self, user, rows, **kwargs):
        return self.as_user(user).post("/api/employees/import/", {"file": self.xlsx(rows, **kwargs)}, format="multipart")

    def test_template_download(self):
        response = self.as_user(self.hr).get("/api/employees/template/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])
        self.assertEqual(self.as_user(self.fit_desk).get("/api/employees/template/").status_code, 403)

    def test_upload_creates_employees_named_by_last_name(self):
        response = self.upload(self.hr, [
            ("EMP0301", "NATUKUNDA", "Charlotte", "cn@eucl.test", "+250787778849", "Finance", "Accountant"),
            (302, "UWASE", "Charlotte", "cu@eucl.test", 788123456, "HR", "HR Officer"),  # numbers in Excel
        ])
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data, {"created": 2, "updated": 0})
        first = Employee.objects.get(employee_id="EMP0301")
        self.assertEqual((first.user.username, first.user.email, first.phone), ("Charlotte", "cn@eucl.test", "+250787778849"))
        second = Employee.objects.get(employee_id="302")
        self.assertEqual((second.user.username, second.phone), ("Charlotte2", "0788123456"))
        self.assertEqual(list(second.user.userprofile.roles.values_list("code", flat=True)), ["EUCL_HR"])
        self.assertFalse(first.user.has_usable_password())  # created at first login
        # ...which works with the phone from the file
        from django.core.cache import cache
        cache.clear()
        self.client.force_authenticate(None)
        done = self.client.post("/api/first-login/", {"employee_id": "302", "contact": "0788123456",
                                "password": "MyWellness@26", "password_confirm": "MyWellness@26"}, format="json")
        self.assertEqual(done.data["username"], "Charlotte2")

    def test_family_name_first_is_the_username(self):
        header = ("EmpID", "Last name", "First name", "Email", "Phone", "Department", "Position")
        response = self.upload(self.hr, [("EMP0009", "NATUKUNDA", "Charlotte", "cn9@eucl.test", "0788000009", "HR", "Manager")], header=header)
        self.assertEqual(response.status_code, 200, response.data)
        employee = Employee.objects.get(employee_id="EMP0009")
        self.assertEqual(employee.user.username, "NATUKUNDA")
        data = self.as_user(self.hr).get(f"/api/employees/{employee.id}/").data
        self.assertEqual(data["user_name"], "NATUKUNDA Charlotte")  # family name shown first

    def test_existing_ids_are_updated(self):
        response = self.upload(self.hr, [(self.john.employee_id, "John", "Newname", "john@new.test", "0788000010", "Legal", "Lawyer")])
        self.assertEqual(response.data, {"created": 0, "updated": 1})
        self.john.refresh_from_db()
        self.assertEqual((self.john.user.last_name, self.john.department, self.john.user.email), ("Newname", "Legal", "john@new.test"))

    def test_any_bad_row_saves_nothing(self):
        response = self.upload(self.hr, [
            ("EMP0401", "Ok", "Row", "ok@eucl.test", "0788000001", "IT", "Dev"),
            ("EMP0402", "", "Missing", "m@eucl.test", "0788000002", "IT", "Dev"),
            ("EMP0401", "Twice", "Same", "t@eucl.test", "0788000003", "IT", "Dev"),
            ("EMP0403", "No", "Contact", "", "", "IT", "Dev"),
            ("EMP0404", "Bad", "Email", "not-an-email", "0788000004", "IT", "Dev"),
            ("EMP0405", "Same", "Email", "OK@eucl.test", "0788000005", "IT", "Dev"),
        ])
        self.assertEqual(response.status_code, 400)
        self.assertEqual([e["row"] for e in response.data["errors"]], [3, 4, 5, 6, 7])
        messages = [e["message"] for e in response.data["errors"]]
        self.assertEqual(messages[0], "Row 3: missing data in First name.")
        self.assertTrue(messages[1].startswith("Row 4: EmpID EMP0401 is used twice: also on row 2."))
        self.assertEqual(messages[2], "Row 5: missing data in Email and Phone.")
        self.assertTrue(messages[3].startswith("Row 6: invalid email “not-an-email”."))
        self.assertEqual(messages[4], "Row 7: email OK@eucl.test is used twice: also on row 2.")
        self.assertIn("rows 3, 4, 5, 6 and 7", response.data["detail"])
        self.assertFalse(Employee.objects.filter(employee_id="EMP0401").exists())

    def test_every_problem_of_a_row_is_listed(self):
        response = self.upload(self.hr, [("EMP0501", "", "", "bad", "12", "", "Dev")])
        messages = [e["message"] for e in response.data["errors"]]
        self.assertEqual(messages[0], "Row 2: missing data in Last name, First name and Department.")
        self.assertTrue(any("invalid email" in m for m in messages))
        self.assertTrue(any("invalid phone number “12”" in m for m in messages))

    def test_a_duplicate_id_is_reported_even_if_the_first_row_has_problems(self):
        response = self.upload(self.hr, [
            ("EMP0701", "A", "", "a@b.test", "0788000011", "IT", "Dev"),
            ("EMP0701", "C", "D", "c@d.test", "0788000012", "IT", "Dev"),
        ])
        messages = [e["message"] for e in response.data["errors"]]
        self.assertIn("Row 3: EmpID EMP0701 is used twice: also on row 2.", messages)

    def test_missing_email_or_phone_is_refused(self):
        # what happened before: rows without email or phone were saved
        response = self.upload(self.hr, [
            ("1012364", "ITEKA", "Beca", "", "0787654328", "IT", "Technician"),
            ("1002354", "Nobel", "Jordy", "jonobel@eucl.test", "", "Software", "Developer"),
        ])
        self.assertEqual(response.status_code, 400)
        messages = [e["message"] for e in response.data["errors"]]
        self.assertEqual(messages, ["Row 2: missing data in Email.", "Row 3: missing data in Phone."])
        self.assertFalse(Employee.objects.filter(employee_id__in=["1012364", "1002354"]).exists())

    def test_too_long_values_are_reported_not_crashing(self):
        response = self.upload(self.hr, [("EMP0601", "A", "B", "a@b.test", "0788000013", "D" * 120, "Dev")])
        self.assertEqual(response.status_code, 400)
        self.assertIn("Department is too long (120 characters, at most 100)", response.data["errors"][0]["message"])

    def test_wrong_columns(self):
        response = self.upload(self.hr, [("x",)], header=("Name",))
        self.assertEqual(response.status_code, 400)
        self.assertIn("header", response.data["detail"])

    def test_only_with_the_permission(self):
        row = ("E1", "A", "B", "a@b.test", "0788000014", "C", "D")
        self.assertEqual(self.upload(self.fit_desk, [row]).status_code, 403)
        self.assertEqual(self.upload(self.john.user, [row]).status_code, 403)


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

    def test_eucl_can_make_an_empty_role_but_a_boss_cannot(self):
        # EUCL names the role first, then switches its permissions on
        response = self.as_user(self.admin).post("/api/roles/", {"name": "Empty", "permissions": []}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        response = self.as_user(self.fit_boss).post("/api/roles/", {"name": "Empty2", "permissions": []}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_built_in_and_used_roles_cannot_be_deleted(self):
        boss_role = Role.objects.get(code="COMPANY_BOSS")
        self.assertEqual(self.as_user(self.admin).delete(f"/api/roles/{boss_role.id}/").status_code, 400)
        custom = Role.objects.create(code="TEMP", name="Temp")
        self.assertEqual(self.as_user(self.admin).delete(f"/api/roles/{custom.id}/").status_code, 204)

    def test_boss_cannot_make_roles_with_eucl_permissions(self):
        response = self.as_user(self.fit_boss).post("/api/roles/", {"name": "X", "permissions": ["view_places"]}, format="json")
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

    def test_only_one_role_per_user(self):
        response = self.as_user(self.admin).post(
            "/api/users/",
            {"username": "two", "first_name": "T", "last_name": "W", "email": "two@test.test",
             "roles": ["EUCL_HR", "ME_OFFICER"], "password": "Reception@2026", "password_confirm": "Reception@2026"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("roles", response.data)
        response = self.as_user(self.admin).patch(
            f"/api/users/{self.john.user.id}/", {"roles": ["EMPLOYEE", "EUCL_HR"]}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.as_user(self.admin).patch(f"/api/users/{self.john.user.id}/", {"roles": []}, format="json").status_code, 400)

    def test_an_employee_can_get_another_role_and_the_employee_role_back(self):
        url = f"/api/users/{self.john.user.id}/"
        response = self.as_user(self.admin).patch(url, {"roles": ["ME_OFFICER"]}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["roles"], ["ME_OFFICER"])  # Employee is replaced, not added
        self.assertEqual(response.data["employee_id"], "JOHN")  # the Employee record stays
        response = self.as_user(self.admin).patch(url, {"roles": ["EMPLOYEE"]}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["roles"], ["EMPLOYEE"])


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
    services its employees may use and pays the company's own price.
    """

    def setUp(self):
        super().setUp()
        # FitZone also offers a sauna, which EUCL hasn't chosen yet
        self.sauna = Service.objects.create(company=self.fitzone, name="Sauna", price=Decimal("8000"))

    def choose(self, user, company, chosen):
        """chosen: [service, ...]"""
        return self.as_user(user).post(
            f"/api/companies/{company.id}/covered-services/",
            {"services": [{"id": s.id} for s in chosen]},
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
        self.assertEqual(self.choose(self.fit_boss, self.fitzone, [self.sauna]).status_code, 403)

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

    def test_eucl_chooses_several_services_at_the_company_price(self):
        response = self.choose(self.admin, self.fitzone, [self.gym, self.sauna])
        self.assertEqual(response.status_code, 200)
        # Money comes back as text ("2500.00"), so compare it as a Decimal
        covered = {
            s["name"]: (s["is_approved"], Decimal(s["eucl_price"]) if s["eucl_price"] else None)
            for s in response.data
        }
        self.assertEqual(covered["Gym"], (True, Decimal("3000")))
        self.assertEqual(covered["Sauna"], (True, Decimal("8000")))
        self.assertFalse(covered["Swimming"][0])
        # Takes effect straight away for reception
        self.assertEqual(self.record(self.fit_desk, self.john, self.sauna).status_code, 201)
        self.assertEqual(self.record(self.fit_desk, self.john, self.pool).status_code, 400)

    def test_visits_are_charged_at_the_company_price(self):
        self.choose(self.admin, self.fitzone, [self.sauna])
        self.record(self.fit_desk, self.john, self.sauna)
        visit = Visit.objects.get(service=self.sauna)
        self.assertEqual(visit.price, Decimal("8000"))

    def test_a_new_company_price_applies_to_new_visits(self):
        self.as_user(self.fit_boss).patch(f"/api/services/{self.gym.id}/", {"price": "3500"}, format="json")
        self.gym.refresh_from_db()
        self.assertEqual(self.gym.eucl_price, Decimal("3500"))  # mirrors the price
        self.record(self.fit_desk, self.john, self.gym)
        self.assertEqual(Visit.objects.get(service=self.gym).price, Decimal("3500"))

    def test_eucl_can_cover_a_service_without_an_amount(self):
        response = self.as_user(self.admin).patch(f"/api/services/{self.sauna.id}/", {"is_approved": True}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Decimal(response.data["eucl_price"]), Decimal("8000"))

    def test_another_companys_service_cannot_be_chosen(self):
        self.assertEqual(self.choose(self.admin, self.fitzone, [self.massage]).status_code, 400)

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
        # ...and if the Receptionist role loses the permission, so do receptionists
        receptionist = Role.objects.get(code="COMPANY_RECEPTIONIST")
        receptionist.permissions.remove(*Permission.objects.filter(code="view_employees_attended"))
        self.assertEqual(self.report(self.fit_desk).status_code, 403)


class HrEmployeesAttendedTests(EuclTestCase):
    """EUCL HR sees the employees attended at every company (permission view_all_employees_attended)."""

    def setUp(self):
        super().setUp()
        self.record(self.fit_desk, self.john, self.gym, self.pool)   # FitZone: 3,000 + 5,000
        self.past_visit(self.mary, self.massage)                     # BlueSpa: 15,000

    def report(self, user, **params):
        return self.as_user(user).get("/api/visits/by-employee/", params)

    def test_hr_sees_every_company(self):
        response = self.report(self.hr)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["totals"], {"employees": 2, "visits": 3, "amount": Decimal("23000")})
        mary = next(row for row in response.data["employees"] if row["employee"] == self.mary.id)
        self.assertEqual([(s["service"], s["company"]) for s in mary["services"]], [("Massage", "BlueSpa")])

    def test_hr_can_narrow_to_one_company(self):
        data = self.report(self.hr, company=self.spa.id).data
        self.assertEqual(data["totals"], {"employees": 1, "visits": 1, "amount": Decimal("15000")})

    def test_hr_can_list_companies_for_the_filter(self):
        response = self.as_user(self.hr).get("/api/companies/")
        self.assertEqual(response.status_code, 200)

    def test_hr_still_only_sees_own_usage_records(self):
        # The permission opens the summary, not every usage record
        response = self.as_user(self.hr).get("/api/visits/")
        self.assertEqual(response.status_code, 200)
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(rows), 0)

    def test_switching_it_off_for_hr_closes_the_report(self):
        Role.objects.get(code="EUCL_HR").permissions.remove(*Permission.objects.filter(code="view_all_employees_attended"))
        self.assertEqual(self.report(self.hr).status_code, 403)


class EachPermissionWorksOnItsOwnTests(EuclTestCase):
    """A role with just one permission switched on can use what that permission opens."""

    def only(self, code, company=None):
        role = Role.objects.create(code=f"ONLY_{code.upper()}", name=f"Only {code}", is_company_role=company is not None)
        role.permissions.set(Permission.objects.filter(code=code))
        return self.make_user(f"only_{code}", role.code, company=company)

    def test_switching_a_permission_on_takes_effect_straight_away(self):
        boss_role = Role.objects.get(code="COMPANY_BOSS")
        self.assertEqual(self.as_user(self.fit_boss).get("/api/price-changes/").status_code, 403)
        codes = list(boss_role.permissions.values_list("code", flat=True)) + ["view_price_changes"]
        self.assertEqual(self.as_user(self.admin).patch(f"/api/roles/{boss_role.id}/", {"permissions": codes}, format="json").status_code, 200)
        self.assertIn("view_price_changes", self.as_user(self.fit_boss).get("/api/me/").data["permissions"])
        self.assertEqual(self.as_user(self.fit_boss).get("/api/price-changes/").status_code, 200)

    def test_upload_employees_without_manage_employees(self):
        user = self.only("import_employees")
        self.assertEqual(self.as_user(user).get("/api/employees/template/").status_code, 200)
        self.assertEqual(self.as_user(user).get("/api/employees/").status_code, 403)  # not the list

    def test_manage_users_can_list_companies(self):
        self.assertEqual(self.as_user(self.only("manage_users")).get("/api/companies/").status_code, 200)

    def test_visit_lists_can_read_department_names(self):
        for code, company in (("manage_payments", None), ("view_company_visits", self.fitzone)):
            with self.subTest(code=code):
                response = self.as_user(self.only(code, company)).get("/api/employees/departments/")
                self.assertEqual(response.status_code, 200)


class UserAccessTests(EuclTestCase):
    """Users & roles shows what one login may do and which role gives each permission."""

    def access(self, user, account):
        return self.as_user(user).get(f"/api/users/{account.id}/access/")

    def test_each_permission_names_the_role_that_gives_it(self):
        data = self.access(self.admin, self.hr).data
        sources = {p["code"]: p["roles"] for p in data["permissions"]}
        self.assertEqual(sources["view_feedback"], ["HR"])
        self.assertEqual(sources["view_my_overview"], ["HR"])

    def test_switching_it_off_in_the_role_takes_it_away(self):
        hr_role = Role.objects.get(code="EUCL_HR")
        codes = [c for c in hr_role.permissions.values_list("code", flat=True) if c != "view_feedback"]
        self.assertEqual(self.as_user(self.admin).patch(f"/api/roles/{hr_role.id}/", {"permissions": codes}, format="json").status_code, 200)
        self.assertNotIn("view_feedback", {p["code"] for p in self.access(self.admin, self.hr).data["permissions"]})
        self.assertNotIn("view_feedback", self.as_user(self.hr).get("/api/me/").data["permissions"])
        self.assertEqual(self.as_user(self.hr).get("/api/feedback/").status_code, 403)

    def test_only_user_managers_may_look(self):
        self.assertEqual(self.access(self.hr, self.fit_boss).status_code, 403)


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
            {"services": [{"id": service.data["id"]}]},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        sauna = Service.objects.get(pk=service.data["id"])
        self.assertTrue(sauna.is_approved)
        self.assertEqual(sauna.eucl_price, Decimal("6000"))  # the company's price

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

    def test_activating_again_gives_access_back(self):
        self.as_user(self.admin).post(f"/api/companies/{self.fitzone.id}/activate/")
        self.client.force_authenticate(None)
        self.assertEqual(self.login("fit_desk").status_code, 200)


class PageRoleTests(EuclTestCase):
    """Each company page is a role the boss switches on or off for a staff member."""

    def staff(self, *roles):
        return self.make_user("desk_" + "_".join(r.lower() for r in roles)[:20], *roles, company=self.fitzone)

    def test_the_three_built_in_roles(self):
        def perms(code):
            return set(Role.objects.get(code=code).permissions.values_list("code", flat=True))
        self.assertEqual(perms("COMPANY_BOSS"), {
            "view_company_dashboard", "record_visits", "take_attendance", "view_company_services",
            "manage_company_services", "view_employees_attended", "view_company_visits", "manage_company_staff",
            "view_company_feedback", "edit_service_prices"})
        self.assertEqual(perms("COMPANY_RECEPTIONIST"), {
            "view_company_dashboard", "record_visits", "take_attendance", "view_company_services", "view_employees_attended",
            "edit_service_prices"})
        self.assertTrue({"view_my_overview", "view_places", "view_my_services", "manage_employees", "import_employees"} <= perms("EUCL_HR"))
        self.assertEqual(Role.objects.get(code="EUCL_HR").name, "HR")
        self.assertEqual(Role.objects.get(code="COMPANY_RECEPTIONIST").name, "Receptionist")

    def test_receptionist_cannot_see_payments_or_manage_staff(self):
        self.assertEqual(self.as_user(self.fit_desk).get("/api/payments/").status_code, 403)
        self.assertEqual(self.as_user(self.fit_desk).get("/api/users/").status_code, 403)
        self.assertEqual(self.record(self.fit_desk, self.john, self.gym).status_code, 201)

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

    def test_boss_has_every_page_including_attendance(self):
        perms = set(self.as_user(self.fit_boss).get("/api/me/").data["permissions"])
        self.assertTrue({"view_company_dashboard", "record_visits", "view_company_services",
                         "view_employees_attended", "take_attendance"} <= perms)

    def test_boss_gives_one_role(self):
        data = {"username": "reception1", "first_name": "Reception", "last_name": "One", "email": "r1@test.test",
                "roles": ["COMPANY_DASHBOARD", "COMPANY_RECORD_VISITS"],
                "password": "Reception@2026", "password_confirm": "Reception@2026"}
        response = self.as_user(self.fit_boss).post("/api/users/", data, format="json")
        self.assertEqual(response.status_code, 400)  # never two roles
        response = self.as_user(self.fit_boss).post("/api/users/", {**data, "roles": ["COMPANY_RECEPTIONIST"]}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["roles"], ["COMPANY_RECEPTIONIST"])


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
        self.assertEqual(self.create_role(name="Receptionist").status_code, 400)  # EUCL's shared role


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
        self.sync = self.make_user("me_sync", "ME_OFFICER")  # M&E officers can export
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
        self.assertTrue({"view_me_dashboards", "manage_me_targets", "export_data"} <= set(self.as_user(officer).get("/api/me/").data["permissions"]))


class PlatformDashboardTests(EuclTestCase):
    """The EUCL dashboard lists companies with their id, so each one can be opened."""

    def test_by_company_gives_the_company_id(self):
        self.record(self.fit_desk, self.john, self.gym, self.pool)
        rows = self.as_user(self.admin).get("/api/stats/", {"scope": "platform"}).data["by_company"]
        self.assertEqual(rows[0]["company_id"], self.fitzone.id)
        self.assertEqual(rows[0]["visits"], 2)
        # ...and the company's services used, for one month
        month = self.today.strftime("%Y-%m")
        visits = self.as_user(self.admin).get(
            "/api/visits/", {"company": self.fitzone.id, "date_from": f"{month}-01", "date_to": self.today.isoformat()}
        ).data
        self.assertEqual(sorted(v["service_name"] for v in visits), ["Gym", "Swimming"])


class RolesAndPermissionsTests(EuclTestCase):
    """The built-in roles, the Super admin role, and permissions the super admin adds."""

    def test_employees_have_one_permission_per_page(self):
        pages = {"view_my_overview", "view_places", "view_my_services"}
        self.assertEqual(set(Role.objects.get(code="EMPLOYEE").permissions.values_list("code", flat=True)), pages)
        self.assertFalse(Permission.objects.filter(code="use_services").exists())
        # without "My services" or "Overview", an employee doesn't get their visits
        role = Role.objects.get(code="EMPLOYEE")
        role.permissions.set(Permission.objects.filter(code="view_places"))
        self.assertEqual(self.as_user(self.john.user).get("/api/visits/").status_code, 403)

    def test_the_built_in_roles(self):
        built_in = set(Role.objects.filter(is_system=True).values_list("name", flat=True))
        self.assertEqual(built_in, {"Super admin", "Company boss", "Receptionist", "HR", "M&E officer", "Employee"})
        self.assertFalse(Role.objects.filter(code="ME_SYNC").exists())

    def test_super_admin_switches_decide_what_super_admins_do(self):
        role = Role.objects.get(code="SUPER_ADMIN")
        self.assertEqual(role.permissions.count(), Permission.objects.count())  # everything to start with
        # switch "Manage companies" off: super admins can no longer add companies
        codes = [c for c in role.permissions.values_list("code", flat=True) if c != "manage_companies"]
        self.assertEqual(self.as_user(self.admin).patch(f"/api/roles/{role.id}/", {"permissions": codes}, format="json").status_code, 200)
        self.assertEqual(self.as_user(self.admin).post("/api/companies/", {"name": "X", "email": "x@x.test"}, format="json").status_code, 403)
        self.assertNotIn("manage_companies", self.as_user(self.admin).get("/api/me/").data["permissions"])

    def test_super_admin_can_switch_manage_users_off_and_on(self):
        role = Role.objects.get(code="SUPER_ADMIN")
        response = self.as_user(self.admin).patch(f"/api/roles/{role.id}/", {"permissions": ["view_places"]}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["permissions"], ["view_places"])
        # Super admins no longer manage users & roles...
        self.assertNotIn("manage_users", self.as_user(self.admin).get("/api/me/").data["permissions"])
        self.assertEqual(self.as_user(self.admin).get("/api/roles/").status_code, 403)
        # ...until it is switched back on (from the Django admin)
        role.permissions.add(Permission.objects.get(code="manage_users"))
        self.assertEqual(self.as_user(self.admin).get("/api/roles/").status_code, 200)

    def test_super_admin_role_gives_no_employee_or_company_menus(self):
        chief = User.objects.create_superuser("chief2", "c2@eucl.test", "x")
        UserProfile.objects.create(user=chief).roles.add(Role.objects.get(code="SUPER_ADMIN"))
        me = self.as_user(chief).get("/api/me/").data
        self.assertEqual(me["role_permissions"], [])
        self.assertIn("view_my_overview", me["permissions"])

    def test_giving_the_super_admin_role_makes_a_super_admin(self):
        response = self.as_user(self.admin).post("/api/users/", {
            "username": "chief", "first_name": "C", "last_name": "H", "email": "chief@eucl.test",
            "roles": ["SUPER_ADMIN"], "password": "Chief@Wellness26", "password_confirm": "Chief@Wellness26",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        chief = User.objects.get(username="chief")
        self.assertTrue(chief.is_superuser)
        self.assertEqual(response.data["role_names"], ["Super admin"])
        # taking the role away takes the super admin access away
        self.as_user(self.admin).patch(f"/api/users/{chief.id}/", {"roles": ["EUCL_HR"]}, format="json")
        chief.refresh_from_db()
        self.assertFalse(chief.is_superuser)

    def test_add_a_permission_and_give_it_to_a_role(self):
        response = self.as_user(self.admin).post("/api/permissions/", {
            "name": "Approve refunds", "description": "Approve refund requests", "area": "EUCL"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["code"], "approve_refunds")
        self.assertFalse(response.data["is_builtin"])
        self.assertTrue(Role.objects.get(code="SUPER_ADMIN").permissions.filter(code="approve_refunds").exists())
        hr = Role.objects.get(code="EUCL_HR")
        codes = list(hr.permissions.values_list("code", flat=True)) + ["approve_refunds"]
        self.assertEqual(self.as_user(self.admin).patch(f"/api/roles/{hr.id}/", {"permissions": codes}, format="json").status_code, 200)
        self.assertIn("approve_refunds", self.as_user(self.hr).get("/api/me/").data["permissions"])
        # it can be deleted; built-in ones can't
        self.assertEqual(self.as_user(self.admin).delete("/api/permissions/approve_refunds/").status_code, 204)
        self.assertEqual(self.as_user(self.admin).delete("/api/permissions/view_places/").status_code, 400)

    def test_only_the_super_admin_adds_permissions(self):
        response = self.as_user(self.fit_boss).post("/api/permissions/", {"name": "X", "area": "Company"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_the_super_admin_chooses_who_a_new_role_is_for(self):
        response = self.as_user(self.admin).post("/api/roles/", {"name": "Cashier", "permissions": [], "is_company_role": True}, format="json")
        role = Role.objects.get(pk=response.data["id"])
        self.assertTrue(role.is_company_role)
        # a company role may also get EUCL permissions, and stays a company role
        response = self.as_user(self.admin).patch(f"/api/roles/{role.id}/", {"permissions": ["record_visits", "view_price_changes"]}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        role.refresh_from_db()
        self.assertTrue(role.is_company_role)
        # an EUCL role by default
        response = self.as_user(self.admin).post("/api/roles/", {"name": "Auditor", "permissions": ["view_all_visits"]}, format="json")
        self.assertFalse(response.data["is_company_role"])

    def test_built_in_roles_keep_their_kind(self):
        boss = Role.objects.get(code="COMPANY_BOSS")
        codes = list(boss.permissions.values_list("code", flat=True)) + ["view_price_changes", "view_my_overview"]
        self.assertEqual(self.as_user(self.admin).patch(f"/api/roles/{boss.id}/", {"permissions": codes}, format="json").status_code, 200)
        boss.refresh_from_db()
        self.assertTrue(boss.is_company_role)  # still a company role: bosses keep their company
        hr = Role.objects.get(code="EUCL_HR")
        self.as_user(self.admin).patch(f"/api/roles/{hr.id}/", {"is_company_role": True}, format="json")
        hr.refresh_from_db()
        self.assertFalse(hr.is_company_role)

    def test_who_a_role_is_for_only_changes_while_nobody_has_it(self):
        role = Role.objects.create(code="AUDITOR", name="Auditor")
        self.make_user("aud", "AUDITOR")
        response = self.as_user(self.admin).patch(f"/api/roles/{role.id}/", {"is_company_role": True}, format="json")
        self.assertEqual(response.status_code, 400)


class FeedbackTests(EuclTestCase):
    """Employees send optional feedback on services they used; HR, admin and the company see it."""

    def setUp(self):
        super().setUp()
        self.record(self.fit_desk, self.john, self.gym)
        self.visit = Visit.objects.get(employee=self.john, service=self.gym)

    def send(self, user, **data):
        return self.as_user(user).post(f"/api/visits/{self.visit.id}/feedback/", data, format="json")

    def test_employee_sends_a_complaint(self):
        response = self.send(self.john.user, kind="complaint", message="I did not attend: I was at work that day")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["feedback_kind_label"], "Complaint")
        self.assertIsNotNone(response.data["feedback_at"])

    def test_only_comment_or_complaint_with_a_message(self):
        self.assertEqual(self.send(self.john.user, kind="complaint").status_code, 400)
        self.assertEqual(self.send(self.john.user, kind="not_attended", message="x").status_code, 400)
        self.assertEqual(self.send(self.john.user, kind="comment", message="Great trainer").status_code, 200)

    def test_only_the_employee_who_used_it(self):
        self.assertEqual(self.send(self.mary.user, kind="complaint", message="x").status_code, 404)  # not in Mary's list
        self.assertEqual(self.send(self.fit_desk, kind="complaint", message="x").status_code, 403)

    def test_who_sees_it(self):
        self.send(self.john.user, kind="complaint", message="The trainer was absent")
        for user in (self.admin, self.hr, self.fit_boss):
            data = self.as_user(user).get("/api/feedback/").data
            self.assertEqual([row["feedback_message"] for row in data], ["The trainer was absent"], user.username)
        # another company's boss doesn't
        spa_boss = self.make_user("spa_boss", "COMPANY_BOSS", company=self.spa)
        self.assertEqual(self.as_user(spa_boss).get("/api/feedback/").data, [])
        # receptionists don't read feedback (only the boss does)
        self.assertEqual(self.as_user(self.fit_desk).get("/api/feedback/").status_code, 403)
        # and employees don't read the list
        self.assertEqual(self.as_user(self.mary.user).get("/api/feedback/").status_code, 403)

    def test_taking_it_back(self):
        self.send(self.john.user, kind="comment", message="Great")
        response = self.as_user(self.john.user).delete(f"/api/visits/{self.visit.id}/feedback/")
        self.assertEqual(response.data["feedback_kind"], "")
        self.assertEqual(self.as_user(self.hr).get("/api/feedback/").data, [])


class PriceChangeTests(EuclTestCase):
    """Admin and HR see who changed a service price (boss, receptionist…) and when."""

    def test_the_boss_changes_a_price_and_hr_sees_who(self):
        response = self.as_user(self.fit_boss).patch(f"/api/services/{self.gym.id}/", {"price": "3500"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        changes = self.as_user(self.hr).get("/api/price-changes/").data
        self.assertEqual(len(changes), 1)
        change = changes[0]
        self.assertEqual((change["service_name"], change["company_name"]), ("Gym", "FitZone"))
        self.assertEqual((Decimal(change["old_price"]), Decimal(change["new_price"]), Decimal(change["difference"])),
                         (Decimal("3000"), Decimal("3500"), Decimal("500")))
        self.assertEqual(change["changed_by_username"], "fit_boss")
        self.assertEqual(change["changed_by_roles"], "Company boss")

    def test_a_receptionist_with_the_permission_is_named_too(self):
        desk = self.make_user("desk_prices", "COMPANY_RECEPTIONIST", company=self.fitzone)
        self.as_user(desk).patch(f"/api/services/{self.pool.id}/", {"price": "4500"}, format="json")
        change = self.as_user(self.admin).get("/api/price-changes/", {"changed": "yes"}).data[0]
        self.assertEqual((change["changed_by_username"], change["changed_by_roles"]), ("desk_prices", "Receptionist"))

    def test_new_services_and_unchanged_prices(self):
        self.as_user(self.fit_boss).post("/api/services/", {"name": "Yoga", "price": "4000"}, format="json")
        self.as_user(self.fit_boss).patch(f"/api/services/{self.gym.id}/", {"description": "Morning classes"}, format="json")
        changes = self.as_user(self.hr).get("/api/price-changes/").data
        self.assertEqual([(c["service_name"], c["old_price"]) for c in changes], [("Yoga", None)])  # added, no old price
        self.assertEqual(self.as_user(self.hr).get("/api/price-changes/", {"changed": "yes"}).data, [])

    def test_hr_can_pick_a_company(self):
        names = {c["name"] for c in self.as_user(self.hr).get("/api/companies/").data}
        self.assertEqual(names, {"FitZone", "BlueSpa"})
        self.assertEqual(self.as_user(self.hr).post("/api/companies/", {"name": "X", "email": "x@x.test"}, format="json").status_code, 403)

    def test_only_admin_and_hr(self):
        self.assertEqual(self.as_user(self.fit_boss).get("/api/price-changes/").status_code, 403)
        self.assertEqual(self.as_user(self.fit_desk).get("/api/price-changes/").status_code, 403)
        self.assertEqual(self.as_user(self.john.user).get("/api/price-changes/").status_code, 403)


class MeToolSignInTests(EuclTestCase):
    """The wellness system hands an M&E user a one-time ticket that signs them in to the M&E tool."""

    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        cache.clear()
        self.officer = self.make_user("me_officer", "ME_OFFICER")

    def ticket(self, user):
        return self.as_user(user).post("/api/me-tool/ticket/")

    def redeem(self, ticket):
        self.client.force_authenticate(None)
        return self.client.post("/api/me-tool/redeem/", {"ticket": ticket}, format="json")

    def test_the_ticket_signs_in_as_that_person_once(self):
        response = self.ticket(self.officer)
        self.assertEqual(response.status_code, 200)
        ticket = response.data["ticket"]
        me = self.redeem(ticket)
        self.assertEqual(me.status_code, 200, me.data)
        self.assertEqual(me.data["username"], "me_officer")
        self.assertFalse(me.data["is_superuser"])
        self.assertIn("view_me_dashboards", me.data["permissions"])
        self.assertEqual(self.redeem(ticket).status_code, 400)  # used already

    def test_only_m_and_e_users_get_a_ticket(self):
        self.assertEqual(self.ticket(self.john.user).status_code, 403)
        self.assertEqual(self.ticket(self.fit_desk).status_code, 403)

    def test_bad_or_old_tickets(self):
        self.assertEqual(self.redeem("nonsense").status_code, 400)
        ticket = self.ticket(self.officer).data["ticket"]
        with mock.patch("django.core.signing.time.time", return_value=time.time() + 120):
            self.assertEqual(self.redeem(ticket).status_code, 400)

    def test_blocked_users_cannot_use_their_ticket(self):
        ticket = self.ticket(self.officer).data["ticket"]
        User.objects.filter(pk=self.officer.pk).update(is_active=False)
        self.assertEqual(self.redeem(ticket).status_code, 400)


class AnyRoleAnyPermissionTests(EuclTestCase):
    """Any role may have any permission: HR (not linked to a company) chooses which company the company pages are for."""

    def setUp(self):
        super().setUp()
        self.hr_role = Role.objects.get(code="EUCL_HR")
        self.hr_role.permissions.add(*Permission.objects.filter(
            code__in=["take_attendance", "record_visits", "view_company_services", "view_company_dashboard",
                      "view_company_feedback", "view_employees_attended"]))

    def acting(self, company):
        self.client.force_authenticate(self.hr)
        self.client.credentials(HTTP_X_ACTING_COMPANY=str(company.id))
        return self.client

    def test_me_lists_the_companies_to_choose_from(self):
        me = self.as_user(self.hr).get("/api/me/").data
        self.assertIsNone(me["company"])  # HR still isn't linked to a company
        self.assertEqual([c["name"] for c in me["company_choices"]], ["BlueSpa", "FitZone"])
        self.assertIn("take_attendance", me["role_permissions"])

    def test_hr_records_services_at_the_chosen_company(self):
        client = self.acting(self.fitzone)
        response = client.post("/api/visits/", {"employee": self.john.id, "services": [self.gym.id]}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Visit.objects.get(employee=self.john).company, self.fitzone)
        # ...and can't record another company's service while FitZone is chosen
        response = client.post("/api/visits/", {"employee": self.mary.id, "services": [self.massage.id]}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_company_pages_show_the_chosen_company(self):
        self.record(self.fit_desk, self.john, self.gym)
        # without the all-companies permission, so only the chosen company counts
        self.hr_role.permissions.remove(*Permission.objects.filter(code="view_all_employees_attended"))
        fit = self.acting(self.fitzone)
        self.assertEqual(fit.get("/api/stats/", {"scope": "company"}).status_code, 200)
        self.assertEqual(fit.get("/api/visits/by-employee/").data["totals"]["employees"], 1)
        spa = self.acting(self.spa)
        self.assertEqual(spa.get("/api/visits/by-employee/").data["totals"]["employees"], 0)

    def test_the_choice_only_counts_with_a_company_permission(self):
        self.hr_role.permissions.remove(*Permission.objects.filter(area="Company"))
        self.assertEqual(self.as_user(self.hr).get("/api/me/").data["company_choices"], [])
        response = self.acting(self.fitzone).post("/api/visits/", {"employee": self.john.id, "services": [self.gym.id]}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_company_staff_cannot_switch_company(self):
        self.client.force_authenticate(self.fit_desk)
        self.client.credentials(HTTP_X_ACTING_COMPANY=str(self.spa.id))
        response = self.client.post("/api/visits/", {"employee": self.john.id, "services": [self.massage.id]}, format="json")
        self.assertEqual(response.status_code, 400)  # still FitZone's receptionist

    def test_archived_companies_cannot_be_chosen(self):
        self.spa.deleted_at = timezone.now()
        self.spa.save()
        self.assertEqual([c["name"] for c in self.as_user(self.hr).get("/api/me/").data["company_choices"]], ["FitZone"])
        response = self.acting(self.spa).get("/api/stats/", {"scope": "company"})
        self.assertNotEqual(response.status_code, 200)
