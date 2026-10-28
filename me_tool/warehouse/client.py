"""Talks to the wellness system's API."""

import requests
from django.conf import settings


class WellnessError(Exception):
    """The wellness system could not be reached or refused the request."""


def _message(response):
    try:
        data = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    if isinstance(data, dict) and data.get("detail"):
        return str(data["detail"])
    return f"HTTP {response.status_code}: {str(data)[:200]}"


def sign_in(username, password, base_url=None, session=None):
    """
    Check a person's wellness login.
    Returns (profile, None) with the /api/me/ data, or (None, message).
    """
    base = (base_url or settings.WELLNESS_API_URL).rstrip("/")
    http = session or requests
    timeout = settings.WELLNESS_API_TIMEOUT
    try:
        response = http.post(f"{base}/api/login/", json={"username": username, "password": password}, timeout=timeout)
        if response.status_code != 200:
            # e.g. "No active account found..." or "This company has been deactivated!..."
            return None, _message(response)
        access = response.json()["access"]
        me = http.get(f"{base}/api/me/", headers={"Authorization": f"Bearer {access}"}, timeout=timeout)
        if me.status_code != 200:
            return None, _message(me)
        return me.json(), None
    except requests.RequestException:
        return None, "The wellness system can't be reached right now. Please try again later."


class WellnessClient:
    """The M&E tool's service account (role "M&E sync service")."""

    def __init__(self, base_url=None, username=None, password=None, session=None):
        self.base = (base_url or settings.WELLNESS_API_URL).rstrip("/")
        self.username = username if username is not None else settings.WELLNESS_SYNC_USERNAME
        self.password = password if password is not None else settings.WELLNESS_SYNC_PASSWORD
        self.http = session or requests.Session()
        self.timeout = settings.WELLNESS_API_TIMEOUT
        self._token = None

    def _login(self):
        if not self.username or not self.password:
            raise WellnessError("WELLNESS_SYNC_USERNAME and WELLNESS_SYNC_PASSWORD are not set.")
        try:
            response = self.http.post(
                f"{self.base}/api/login/", json={"username": self.username, "password": self.password}, timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise WellnessError(f"Can't reach the wellness system at {self.base}: {exc}") from exc
        if response.status_code != 200:
            raise WellnessError(f"The service account can't sign in: {_message(response)}")
        self._token = response.json()["access"]

    def get(self, path, params=None):
        if self._token is None:
            self._login()
        for attempt in (1, 2):
            try:
                response = self.http.get(
                    f"{self.base}{path}",
                    params=params,
                    headers={"Authorization": f"Bearer {self._token}"},
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                raise WellnessError(f"Can't reach the wellness system at {self.base}: {exc}") from exc
            if response.status_code == 401 and attempt == 1:
                self._login()  # the access token expired: sign in again once
                continue
            if response.status_code != 200:
                raise WellnessError(f"{path}: {_message(response)}")
            return response.json()
        raise WellnessError(f"{path}: not authorised")

    # ---- the export API (wellness/export.py in the wellness system)

    def snapshot(self):
        return self.get("/api/export/snapshot/")

    def visits(self, updated_since=None, after_id=0, limit=1000):
        params = {"limit": limit}
        if updated_since:
            params["updated_since"] = updated_since
            params["after_id"] = after_id
        return self.get("/api/export/visits/", params)

    def visit_ids(self, date_from):
        return self.get("/api/export/visit-ids/", {"date_from": date_from.isoformat()})["ids"]
