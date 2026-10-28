"""
Settings for the EUCL Wellness M&E tool.

Everything that changes between computers comes from environment variables
(in Docker: the .env file read by docker-compose). Without POSTGRES_HOST the
tool uses SQLite, which is handy for development and the tests.
"""

import os
from datetime import timedelta
from pathlib import Path

from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    return env(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-not-secret-change-me")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "accounts",
    "warehouse",
    "indicators",
    "dashboards",
    "reports",
    "monitoring",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.access",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

if env("POSTGRES_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": env("POSTGRES_HOST"),
            "PORT": env("POSTGRES_PORT", "5432"),
            "NAME": env("POSTGRES_DB", "me_tool"),
            "USER": env("POSTGRES_USER", "me_tool"),
            "PASSWORD": env("POSTGRES_PASSWORD", ""),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": env("SQLITE_PATH", str(BASE_DIR / "db.sqlite3")),
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Sign-in is checked by the wellness system (see accounts/wellness.py);
# ModelBackend only serves local accounts such as an emergency superuser.
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboards:overview"
SESSION_COOKIE_AGE = int(env("SESSION_HOURS", "8")) * 3600
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = env_bool("SECURE_COOKIES", False)
CSRF_COOKIE_SECURE = env_bool("SECURE_COOKIES", False)

LANGUAGE_CODE = "en-gb"
TIME_ZONE = env("TIME_ZONE", "Africa/Kigali")
USE_I18N = True
USE_TZ = True
USE_THOUSAND_SEPARATOR = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", str(BASE_DIR / "media")))

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if not DEBUG
        else "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}

# ------------------------------------------------------------- wellness system
# The wellness system's API (in Docker: http://host.docker.internal:8000)
WELLNESS_API_URL = env("WELLNESS_API_URL", "http://127.0.0.1:8000").rstrip("/")
WELLNESS_API_TIMEOUT = int(env("WELLNESS_API_TIMEOUT", "20"))
# The service account (role "M&E sync service" in the wellness system)
WELLNESS_SYNC_USERNAME = env("WELLNESS_SYNC_USERNAME", "")
WELLNESS_SYNC_PASSWORD = env("WELLNESS_SYNC_PASSWORD", "")

# How often new and changed visits are pulled, and how many recent days the
# nightly check compares (to remove visits undone in the wellness system)
SYNC_INTERVAL_MINUTES = int(env("SYNC_INTERVAL_MINUTES", "30"))
RECONCILE_DAYS = int(env("RECONCILE_DAYS", "14"))
# Re-read this much before the last cursor: a visit saved just before a sync
# but committed just after it is not missed (re-reading is harmless)
SYNC_OVERLAP = timedelta(minutes=2)

# ------------------------------------------------------------------- Celery
CELERY_BROKER_URL = env("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = None
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TIME_LIMIT = 15 * 60
CELERY_BEAT_SCHEDULE = {
    "sync-wellness": {
        "task": "warehouse.tasks.sync_wellness",
        "schedule": timedelta(minutes=SYNC_INTERVAL_MINUTES),
    },
    "nightly-reconcile": {
        "task": "warehouse.tasks.reconcile_wellness",
        "schedule": crontab(hour=1, minute=30),
    },
}

# Automatic reports for all companies (PDF + Excel), after the nightly check:
#   daily   every morning, for yesterday
#   weekly  every Monday, for last week (Monday-Sunday)
#   monthly on the 1st, for last month
if env_bool("AUTO_REPORTS", True):
    CELERY_BEAT_SCHEDULE.update({
        "daily-report": {"task": "reports.tasks.scheduled_reports", "schedule": crontab(hour=6, minute=0), "args": ("day",)},
        "weekly-report": {"task": "reports.tasks.scheduled_reports", "schedule": crontab(hour=6, minute=15, day_of_week="mon"), "args": ("week",)},
        "monthly-report": {"task": "reports.tasks.scheduled_reports", "schedule": crontab(hour=6, minute=30, day_of_month="1"), "args": ("month",)},
    })

# ------------------------------------------------------- resource monitoring
# Samples (CPU, memory, disk, database, Redis, Celery, wellness API) every N
# minutes, kept N days; a database snapshot (size and rows per table) every day.
MONITOR_INTERVAL_MINUTES = int(env("MONITOR_INTERVAL_MINUTES", "10"))
MONITOR_RETENTION_DAYS = int(env("MONITOR_RETENTION_DAYS", "30"))
# The disk whose space is watched (in Docker: the container's view of the host disk)
MONITOR_DISK_PATH = Path(env("MONITOR_DISK_PATH", str(BASE_DIR.anchor or "/")))
# When a check turns to "Attention"
MONITOR_ALERTS = {
    "cpu": float(env("MONITOR_ALERT_CPU", "85")),          # % CPU
    "memory": float(env("MONITOR_ALERT_MEMORY", "90")),    # % memory
    "disk": float(env("MONITOR_ALERT_DISK", "85")),        # % disk
    "db_ms": float(env("MONITOR_ALERT_DB_MS", "200")),     # database answer time
    "api_ms": float(env("MONITOR_ALERT_API_MS", "2000")),  # wellness API answer time
    "queue": int(env("MONITOR_ALERT_QUEUE", "50")),        # tasks waiting
    "sync_hours": float(env("MONITOR_ALERT_SYNC_HOURS", "2")),  # last successful sync
}
CELERY_BEAT_SCHEDULE.update({
    "collect-resources": {"task": "monitoring.tasks.collect_resources", "schedule": timedelta(minutes=MONITOR_INTERVAL_MINUTES)},
    "database-snapshot": {"task": "monitoring.tasks.database_snapshot", "schedule": crontab(hour=0, minute=5)},
})

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
