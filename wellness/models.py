from django.contrib.auth.models import User
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone


def display_name(user):
    """Names are shown family name first, as in Rwanda: "NATUKUNDA Charlotte"."""
    return f"{user.last_name} {user.first_name}".strip()


# =====================================================================
#  Roles & permissions
#  A Permission is one thing the app can check ("record_visits").
#  A Role is a named bundle of permissions that the super admin can
#  create and change from the app. A user has exactly one role.
# =====================================================================

class Permission(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)
    # Groups the permissions on screen: "Platform", "EUCL", "Company", "Employee"
    area = models.CharField(max_length=20)
    # Built-in permissions are checked by the code. The super admin can add
    # more; those are labels until a developer makes a page check them.
    is_builtin = models.BooleanField(default=True)

    class Meta:
        ordering = ["area", "name"]

    def __str__(self):
        return self.name


class Role(models.Model):
    # System roles (created by the migrations) can't be deleted
    EMPLOYEE = "EMPLOYEE"
    SUPER_ADMIN = "SUPER_ADMIN"  # every permission; goes with the super admin switch
    ME_OFFICER = "ME_OFFICER"
    COMPANY_BOSS = "COMPANY_BOSS"  # given to the login created with a new company
    RECEPTIONIST = "COMPANY_RECEPTIONIST"
    HR = "EUCL_HR"  # given automatically to employees of the HR department

    code = models.CharField(max_length=50, unique=True)
    # Unique among the roles one company can see (checked by the serializer):
    # two companies may each have their own "Cashier"
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)
    # A company role (Boss, Receptionist...) belongs to one service provider:
    # anyone given it must be linked to a company.
    is_company_role = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False)
    permissions = models.ManyToManyField(Permission, blank=True, related_name="roles")
    # Set when a company boss created the role: only that company sees and uses it.
    # Empty for roles EUCL created, which every company can use.
    company = models.ForeignKey(
        "Company", null=True, blank=True, on_delete=models.CASCADE, related_name="own_roles"
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    roles = models.ManyToManyField(Role, blank=True, related_name="profiles")

    # Only for company staff (Boss, Receptionist...): the service provider
    # they work for. EUCL staff and employees leave it empty.
    company = models.ForeignKey(
        "Company",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="staff",
    )

    def __str__(self):
        return self.user.username


# =====================================================================
#  Service providers
# =====================================================================

class Company(models.Model):
    """A place (gym, spa, pool...) where EUCL employees can use services."""

    name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Deactivated: temporarily paused. Hidden from employees and no new
    # visits can be recorded, but the company and its staff stay.
    is_active = models.BooleanField(default=True)
    # Deleted: archived. Hidden everywhere and its staff can't log in,
    # but every visit and payment is kept. It can be restored.
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    @property
    def is_open(self):
        """Can EUCL employees use it right now?"""
        return self.is_active and not self.is_deleted

    def staff_users(self):
        return User.objects.filter(userprofile__company=self)

    @transaction.atomic
    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])
        self.staff_users().update(is_active=False)

    @transaction.atomic
    def restore(self):
        self.deleted_at = None
        self.save(update_fields=["deleted_at"])
        self.staff_users().update(is_active=True)


class Service(models.Model):
    """Something a company offers EUCL employees, at a price per visit."""

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="services")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    # The company's own list price per visit (RWF)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    # The company's own on/off switch ("we offer this right now")
    is_active = models.BooleanField(default=True)
    # EUCL's choice: may EUCL employees use this service? A company can offer
    # many services; EUCL ticks the ones it covers for its employees...
    is_approved = models.BooleanField(default=False)
    # ...and agrees the amount it pays the company per visit (RWF).
    # Visits are charged at this amount; employees pay nothing.
    eucl_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["company__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="unique_service_name_per_company"),
        ]

    @property
    def is_available(self):
        """Can EUCL employees use it today? Offered, covered by EUCL, company open."""
        return self.is_active and self.is_approved and self.company.is_open

    def __str__(self):
        return f"{self.name} ({self.company})"


class PriceChange(models.Model):
    """
    Every time a service gets a price (added) or a new price, who did it.
    The person's name and roles are copied at that moment, so the history
    stays right even if their roles change later.
    """

    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="price_changes")
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="price_changes")
    old_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)  # empty: service added
    new_price = models.DecimalField(max_digits=12, decimal_places=2)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    changed_by_name = models.CharField(max_length=310, blank=True)
    changed_by_username = models.CharField(max_length=150, blank=True)
    changed_by_roles = models.CharField(max_length=255, blank=True)  # e.g. "Company boss"
    changed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-changed_at", "-id"]

    def __str__(self):
        return f"{self.service}: {self.old_price} -> {self.new_price}"


# =====================================================================
#  EUCL employees and their visits
# =====================================================================

class Employee(models.Model):
    """An EUCL employee who can use the services."""

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    # Given by HR (no automatic numbering); also the login username for
    # employees uploaded from Excel
    employee_id = models.CharField(max_length=20, unique=True)
    phone = models.CharField(max_length=20, blank=True)
    department = models.CharField(max_length=100, blank=True)
    position = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Employees of this department get the HR role automatically
    HR_DEPARTMENT = "HR"

    @property
    def is_hr(self):
        return self.department.strip().upper() == self.HR_DEPARTMENT

    def sync_hr_role(self):
        """
        One role per person: an employee of the HR department gets HR instead of
        Employee, and goes back to Employee when they leave HR. Any other role
        the super admin gave them (M&E officer, Super admin...) is left alone.
        """
        profile = UserProfile.objects.filter(user=self.user).first()
        hr = Role.objects.filter(code=Role.HR).first()
        employee = Role.objects.filter(code=Role.EMPLOYEE).first()
        if profile is None or hr is None or employee is None:
            return
        codes = set(profile.roles.values_list("code", flat=True))
        if self.is_hr and codes <= {Role.EMPLOYEE}:
            profile.roles.set([hr])
        elif not self.is_hr and codes == {Role.HR}:
            profile.roles.set([employee])

    def __str__(self):
        return f"{self.name} - {self.employee_id}"

    @property
    def name(self):
        return display_name(self.user)


class Payment(models.Model):
    """EUCL paying a company for the visits in a period."""

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="payments")
    period_start = models.DateField()
    period_end = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reference = models.CharField(max_length=100, blank=True)  # e.g. bank transfer number
    note = models.CharField(max_length=255, blank=True)
    paid_at = models.DateTimeField(auto_now_add=True)
    recorded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-paid_at"]

    def __str__(self):
        return f"{self.company}: {self.amount} ({self.period_start} to {self.period_end})"


class Visit(models.Model):
    """One service used by one employee, ticked by the company's receptionist."""

    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="visits")
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="visits")
    # Copied from the service when the visit is recorded, so history stays
    # correct even if the company changes its name or prices later.
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="visits")
    price = models.DecimalField(max_digits=12, decimal_places=2)

    visit_date = models.DateField(default=timezone.localdate)
    visited_at = models.DateTimeField(default=timezone.now)
    recorded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="recorded_visits"
    )
    # Filled in when the admin marks the period as paid
    payment = models.ForeignKey(
        Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name="visits"
    )
    # Changes whenever the visit changes (e.g. when it is paid): the M&E tool
    # syncs only the visits changed since its last sync
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    # Optional feedback from the employee about this service (seen by HR,
    # the super admin and the company's boss and receptionists)
    FEEDBACK_COMMENT = "comment"
    FEEDBACK_COMPLAINT = "complaint"
    FEEDBACK_KINDS = [
        (FEEDBACK_COMMENT, "Comment"),
        (FEEDBACK_COMPLAINT, "Complaint"),
    ]
    feedback_kind = models.CharField(max_length=20, choices=FEEDBACK_KINDS, blank=True)
    feedback_message = models.TextField(blank=True)
    feedback_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-visited_at"]
        constraints = [
            # Many services per day are fine, but the same service only once
            # a day (stops accidental double ticks)
            models.UniqueConstraint(
                fields=["employee", "service", "visit_date"], name="one_visit_per_service_per_day"
            ),
        ]

    def __str__(self):
        return f"{self.employee} - {self.service} - {self.visit_date}"


# Helpful filters reused by the views
UNPAID = Q(payment__isnull=True)
