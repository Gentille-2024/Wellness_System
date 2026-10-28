import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("me_tool")
# Every CELERY_* setting in settings.py configures Celery
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
