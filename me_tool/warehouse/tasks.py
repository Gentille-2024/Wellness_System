from celery import shared_task
from django.conf import settings

from .sync import run_sync


@shared_task
def sync_wellness(full=False):
    """Every SYNC_INTERVAL_MINUTES (Celery beat): new and changed data."""
    return run_sync(full=full).status


@shared_task
def reconcile_wellness():
    """Nightly: also remove visits that were undone in the wellness system."""
    return run_sync(reconcile_days=settings.RECONCILE_DAYS).status
