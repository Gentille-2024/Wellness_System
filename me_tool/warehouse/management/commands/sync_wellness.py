from django.core.management.base import BaseCommand

from warehouse.sync import run_sync


class Command(BaseCommand):
    help = "Copy the wellness system's data into the M&E warehouse (what Celery beat runs on a schedule)."

    def add_arguments(self, parser):
        parser.add_argument("--full", action="store_true", help="Read every visit again, not only changed ones.")
        parser.add_argument("--reconcile-days", type=int, default=0, help="Also remove visits undone in the last N days.")

    def handle(self, *args, **options):
        run = run_sync(full=options["full"], reconcile_days=options["reconcile_days"] or None)
        self.stdout.write(self.style.SUCCESS(f"Sync {run.status}: {run.counts or run.message}"))
