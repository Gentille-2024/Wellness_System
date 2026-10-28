"""A small world for the tests: two companies, three employees, some visits."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import Access
from indicators.periods import Month
from warehouse.models import Company, Employee, Payment, Service, Visit


def aware(day, hour=10):
    return timezone.make_aware(datetime.combine(day, time(hour)))


class World:
    def __init__(self, month=None):
        self.month = month or Month(2026, 10)
        start = self.month.start
        before = self.month.previous().start
        long_ago = aware(start - timedelta(days=200))

        self.fitzone = Company.objects.create(id=1, name="FitZone", created_at=long_ago)
        self.spa = Company.objects.create(id=2, name="BlueSpa", created_at=long_ago)
        self.gym = Service.objects.create(id=11, company=self.fitzone, name="Gym", price=Decimal("3000"), is_covered=True, eucl_price=Decimal("3000"))
        self.pool = Service.objects.create(id=12, company=self.fitzone, name="Swimming", price=Decimal("5000"), is_covered=True, eucl_price=Decimal("5000"))
        self.sauna = Service.objects.create(id=13, company=self.fitzone, name="Sauna", price=Decimal("6000"), is_covered=False)
        self.massage = Service.objects.create(id=21, company=self.spa, name="Massage", price=Decimal("15000"), is_covered=True, eucl_price=Decimal("15000"))

        self.john = Employee.objects.create(id=101, code="EMP0001", first_name="John", last_name="Doe", department="Finance", created_at=long_ago)
        self.mary = Employee.objects.create(id=102, code="EMP0002", first_name="Mary", last_name="Uwase", department="IT", created_at=long_ago)
        self.paul = Employee.objects.create(id=103, code="EMP0003", first_name="Paul", last_name="Mugabo", department="IT", created_at=long_ago)
        # Active but never came: participation is 3 of 4
        self.grace = Employee.objects.create(id=105, code="EMP0005", first_name="Grace", last_name="Ineza", department="Finance", created_at=long_ago)
        # Left EUCL: not counted as an active employee
        Employee.objects.create(id=104, code="EMP0004", first_name="Old", last_name="Staff", department="HR", is_active=False, created_at=long_ago)

        self.paid_last_month = Payment.objects.create(
            id=501, company=self.fitzone, period_start=before, period_end=self.month.previous().end,
            amount=Decimal("3000"), paid_at=aware(start + timedelta(days=4)),
        )
        self._id = 1000
        # Last month: John at FitZone (paid), Mary at BlueSpa
        self.visit(self.john, self.gym, before + timedelta(days=2), payment=self.paid_last_month)
        self.visit(self.mary, self.massage, before + timedelta(days=3))
        # This month: John 2 visits at FitZone, Mary 1 at FitZone, Paul 1 at BlueSpa
        self.visit(self.john, self.gym, start + timedelta(days=1))
        self.visit(self.john, self.pool, start + timedelta(days=1))
        self.visit(self.mary, self.gym, start + timedelta(days=5))
        self.visit(self.paul, self.massage, start + timedelta(days=6))

    def visit(self, employee, service, day, payment=None):
        self._id += 1
        return Visit.objects.create(
            id=self._id, employee=employee, service=service, company=service.company,
            price=service.eucl_price or service.price, visit_date=day, visited_at=aware(day),
            payment=payment, updated_at=aware(day, 12),
        )


def make_user(username, permissions=(), company=None, superuser=False, roles=("Test role",)):
    user = get_user_model().objects.create(username=username)
    Access.objects.create(
        user=user, full_name=username.title(), permissions=list(permissions), role_names=list(roles),
        is_wellness_superuser=superuser, company_id=company.id if company else None,
        company_name=company.name if company else "",
    )
    return user
