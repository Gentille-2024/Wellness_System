# Load Celery with Django so @shared_task uses this project's app
from .celery import app as celery_app

__all__ = ("celery_app",)
