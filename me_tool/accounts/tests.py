from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from config.testing import World

User = get_user_model()

HR_PROFILE = {
    "id": 7, "username": "hr", "first_name": "Grace", "last_name": "Uwera", "full_name": "Grace Uwera",
    "email": "hr@eucl.test", "is_superuser": False, "role_names": ["EUCL HR"],
    "permissions": ["manage_employees", "view_all_visits", "view_me_dashboards"], "company": None,
}
BOSS_PROFILE = {
    "id": 8, "username": "fit_boss", "first_name": "FitZone", "last_name": "", "full_name": "FitZone",
    "email": "boss@fitzone.test", "is_superuser": False, "role_names": ["Company boss"],
    "permissions": ["view_company_visits", "view_company_dashboard", "manage_company_staff"],
    "company": {"id": 1, "name": "FitZone"},
}


class LoginTests(TestCase):
    def setUp(self):
        World()

    def login(self, profile=None, error=None, **data):
        with mock.patch("accounts.views.sign_in", return_value=(profile, error)) as sign_in:
            response = self.client.post("/accounts/login/", {"username": "someone", "password": "pw", **data})
        return response, sign_in

    def test_wellness_login_copies_roles_and_permissions(self):
        response, sign_in = self.login(HR_PROFILE)
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        sign_in.assert_called_once_with("someone", "pw")
        user = User.objects.get(username="hr")
        self.assertFalse(user.has_usable_password())  # passwords stay in the wellness system
        self.assertTrue(user.access.sees_all)
        self.assertEqual(user.access.full_name, "Grace Uwera")

    def test_company_boss_gets_their_company(self):
        self.login(BOSS_PROFILE)
        access = User.objects.get(username="fit_boss").access
        self.assertFalse(access.sees_all)
        self.assertEqual(access.own_company_id, 1)

    def test_permissions_are_refreshed_at_every_login(self):
        self.login(HR_PROFILE)
        self.client.logout()
        self.login({**HR_PROFILE, "permissions": ["manage_employees"]})
        self.assertFalse(User.objects.get(username="hr").access.has_access)

    def test_wellness_errors_are_shown(self):
        response, _ = self.login(None, "This company has been deactivated! Please contact EUCL for more information.")
        self.assertContains(response, "This company has been deactivated!")

    def test_no_m_and_e_role(self):
        response, _ = self.login({**HR_PROFILE, "username": "john", "permissions": ["use_services"]})
        self.assertContains(response, "no access to the M&amp;E tool")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_local_superuser_when_wellness_is_down(self):
        User.objects.create_superuser("rescue", "r@x.test", "Rescue@2026")
        with mock.patch("accounts.views.sign_in", return_value=(None, "can't be reached")):
            response = self.client.post("/accounts/login/", {"username": "rescue", "password": "Rescue@2026"})
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_next_url_must_be_local(self):
        response, _ = self.login(HR_PROFILE, next="https://evil.example/")
        self.assertEqual(response["Location"], "/")

    def test_logout_needs_post(self):
        self.login(HR_PROFILE)
        self.assertEqual(self.client.get("/accounts/logout/").status_code, 405)
        self.assertRedirects(self.client.post("/accounts/logout/"), "/accounts/login/")


class SignInClientTests(TestCase):
    def test_sign_in_calls_login_then_me(self):
        from warehouse.client import sign_in

        class R:
            def __init__(self, status, data):
                self.status_code, self._data = status, data

            def json(self):
                return self._data

        session = mock.Mock()
        session.post.return_value = R(200, {"access": "abc"})
        session.get.return_value = R(200, HR_PROFILE)
        profile, error = sign_in("hr", "pw", base_url="http://w", session=session)
        self.assertEqual(profile["username"], "hr")
        self.assertIsNone(error)
        session.get.assert_called_once()
        self.assertEqual(session.get.call_args.kwargs["headers"]["Authorization"], "Bearer abc")

        session.post.return_value = R(401, {"detail": "No active account found with the given credentials"})
        profile, error = sign_in("hr", "bad", base_url="http://w", session=session)
        self.assertIsNone(profile)
        self.assertIn("No active account", error)
