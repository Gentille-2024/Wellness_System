"""Settings for the tests: in-memory SQLite, Celery tasks run immediately."""

import tempfile

from .settings import *  # noqa: F401,F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_BROKER_URL = "memory://"
MEDIA_ROOT = tempfile.mkdtemp(prefix="me_tool_media_")
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
WELLNESS_API_URL = "http://wellness.test"
WELLNESS_SYNC_USERNAME = "me_sync"
WELLNESS_SYNC_PASSWORD = "secret"
