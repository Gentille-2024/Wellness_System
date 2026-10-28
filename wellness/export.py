"""
Read-only export API for the M&E tool (a separate application).

The M&E tool signs in with a service account whose role has the
"export_data" permission, then pulls:

  GET /api/export/snapshot/     companies, services, employees and payments
                                (small tables: sent in full every sync)
  GET /api/export/visits/       visits changed since a cursor, oldest first
                                ?updated_since=<ISO datetime>&after_id=<id>&limit=<n>
  GET /api/export/visit-ids/    ids of every visit since a date
                                ?date_from=YYYY-MM-DD
                                (visits can be undone, i.e. deleted, so the M&E
                                tool compares these ids with its own copy)
"""

from django.db.models import F, Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Company, Employee, Payment, Service, Visit

DEFAULT_LIMIT = 1000
MAX_LIMIT = 5000


class ExportView(APIView):
    read_perms = ("export_data",)


class SnapshotExportView(ExportView):
    def get(self, request):
        return Response({
            "server_time": timezone.now(),
            "companies": list(
                Company.objects.order_by("id").values("id", "name", "is_active", "deleted_at", "created_at")
            ),
            "services": list(
                Service.objects.order_by("id").values(
                    "id", "company_id", "name", "price", "is_active", "is_approved", "eucl_price", "created_at"
                )
            ),
            "employees": list(
                Employee.objects.order_by("id").values(
                    "id",
                    "employee_id",
                    "department",
                    "position",
                    "created_at",
                    first_name=F("user__first_name"),
                    last_name=F("user__last_name"),
                    is_active=F("user__is_active"),
                )
            ),
            "payments": list(
                Payment.objects.order_by("id").values(
                    "id", "company_id", "period_start", "period_end", "amount", "reference", "paid_at"
                )
            ),
        })


class VisitsExportView(ExportView):
    def get(self, request):
        params = request.query_params
        try:
            limit = min(int(params.get("limit", DEFAULT_LIMIT)), MAX_LIMIT)
            after_id = int(params.get("after_id", 0))
        except ValueError:
            raise ValidationError("limit and after_id must be numbers.")
        if limit < 1:
            raise ValidationError("limit must be at least 1.")

        visits = Visit.objects.all()
        since_text = params.get("updated_since")
        if since_text:
            since = parse_datetime(since_text)
            if since is None:
                raise ValidationError("updated_since must be an ISO date and time.")
            if timezone.is_naive(since):
                since = timezone.make_aware(since)
            # Keyset paging on (updated_at, id): nothing is skipped or repeated
            # even when many visits share the same updated_at
            visits = visits.filter(Q(updated_at__gt=since) | Q(updated_at=since, id__gt=after_id))

        rows = list(
            visits.order_by("updated_at", "id").values(
                "id", "employee_id", "service_id", "company_id", "price",
                "visit_date", "visited_at", "payment_id", "updated_at",
            )[: limit + 1]
        )
        more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = None
        if more:
            last = rows[-1]
            next_cursor = {"updated_since": last["updated_at"], "after_id": last["id"]}
        return Response({"server_time": timezone.now(), "results": rows, "next": next_cursor})


class VisitIdsExportView(ExportView):
    def get(self, request):
        date_from = parse_date(request.query_params.get("date_from", "") or "")
        if date_from is None:
            raise ValidationError("date_from (YYYY-MM-DD) is required.")
        ids = Visit.objects.filter(visit_date__gte=date_from).order_by("id").values_list("id", flat=True)
        return Response({"date_from": date_from, "ids": list(ids)})
