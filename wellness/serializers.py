import re

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import (
    validate_password as django_validate_password,
)
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import (
    PriceChange,
    display_name,
    Company,
    Employee,
    Payment,
    Permission,
    Role,
    Service,
    UserProfile,
    Visit,
)
from .permissions import COMPANY_DEACTIVATED, company_deactivated, company_role_permissions, get_company, get_permissions, has_perm


# ---------------------------------------------------------------- helpers

def validate_phone(value):
    """Accept numbers like +250 788 123 456 or 0788123456 (9-15 digits)."""
    digits = re.sub(r"[\s-]", "", value)
    if not re.fullmatch(r"\+?\d{9,15}", digits):
        raise serializers.ValidationError(
            "Enter a valid phone number, e.g. +250 788 123 456."
        )
    return value


def check_unique_username(value, exclude_user=None):
    users = User.objects.filter(username__iexact=value)
    if exclude_user is not None:
        users = users.exclude(pk=exclude_user.pk)
    if users.exists():
        raise serializers.ValidationError("This username is already taken.")
    return value


def clean_employee_id(value, exclude=None):
    """HR types the Employee ID: trimmed, upper case, unique, also free as a username."""
    value = "".join(str(value).split()).upper()
    if not value:
        raise serializers.ValidationError("Enter the Employee ID.")
    if len(value) > 20:
        raise serializers.ValidationError("The Employee ID can have at most 20 characters.")
    taken = Employee.objects.filter(employee_id__iexact=value)
    if exclude is not None:
        taken = taken.exclude(pk=exclude.pk)
    if taken.exists():
        raise serializers.ValidationError(f"Employee ID {value} is already used.")
    return value


def check_unique_email(value, exclude_user=None):
    if not value:
        return value  # email is optional for employees
    users = User.objects.filter(email__iexact=value)
    if exclude_user is not None:
        users = users.exclude(pk=exclude_user.pk)
    if users.exists():
        raise serializers.ValidationError("This email is already used by another account.")
    return value


def check_new_password(password, confirm, user=None):
    """Both passwords must match and pass Django's password rules."""
    if password != confirm:
        raise serializers.ValidationError(
            {"password_confirm": "The two passwords do not match."}
        )
    try:
        django_validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({"password": list(exc.messages)})


def role_names(user):
    profile = getattr(user, "userprofile", None)
    names = [role.name for role in profile.roles.all()] if profile is not None else []
    if user.is_superuser and not any(code == Role.SUPER_ADMIN for code in (profile.roles.values_list("code", flat=True) if profile else [])):
        names.insert(0, "Super admin")
    return names


# -------------------------------------------------------- roles & permissions

class PermissionSerializer(serializers.ModelSerializer):
    """Permissions. The super admin can add new ones (name, description, area)."""

    class Meta:
        model = Permission
        fields = ["id", "code", "name", "description", "area", "is_builtin"]
        read_only_fields = ["code", "is_builtin"]

    def validate_name(self, value):
        value = " ".join(value.split())
        taken = Permission.objects.filter(name__iexact=value)
        if self.instance is not None:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise serializers.ValidationError("A permission with this name already exists.")
        return value

    def validate_area(self, value):
        value = " ".join(value.split()).title() if value else "Custom"
        return value[:20]

    @transaction.atomic
    def create(self, validated_data):
        # A stable code from the name: "Approve refunds" -> "approve_refunds"
        base = (slugify(validated_data["name"]).replace("-", "_") or "permission")[:44]
        code, number = base, 2
        while Permission.objects.filter(code=code).exists():
            code, number = f"{base}_{number}", number + 1
        permission = Permission.objects.create(code=code, is_builtin=False, **validated_data)
        # The super admin role always has every permission
        super_admin = Role.objects.filter(code=Role.SUPER_ADMIN).first()
        if super_admin is not None:
            super_admin.permissions.add(permission)
        return permission


class RoleSerializer(serializers.ModelSerializer):
    """
    Roles and their permissions.
    - EUCL (manage_users): any role; roles EUCL creates are shared by every company.
    - A company boss (manage_company_staff): roles for their own company only,
      with company page permissions only.
    """

    permissions = serializers.SlugRelatedField(
        many=True, slug_field="code", queryset=Permission.objects.all()
    )
    user_count = serializers.IntegerField(read_only=True, default=0)
    company_name = serializers.CharField(source="company.name", read_only=True, default=None)

    class Meta:
        model = Role
        fields = [
            "id",
            "code",
            "name",
            "description",
            "is_company_role",
            "is_system",
            "company",
            "company_name",
            "permissions",
            "user_count",
        ]
        read_only_fields = ["code", "is_system", "company"]

    def _is_admin(self):
        return has_perm(self.context["request"].user, "manage_users")

    def _company(self):
        """The company this role belongs to (None for the shared roles)."""
        if self.instance is not None:
            return self.instance.company
        return None if self._is_admin() else get_company(self.context["request"].user)

    def validate_name(self, value):
        value = " ".join(value.split())
        company = self._company()
        roles = Role.objects.filter(name__iexact=value)
        if company is None:
            # A shared role's name can't be used by any other role
            pass
        else:
            # A company's role: unique among the shared roles and its own roles
            roles = roles.filter(Q(company__isnull=True) | Q(company=company))
        if self.instance is not None:
            roles = roles.exclude(pk=self.instance.pk)
        if roles.exists():
            raise serializers.ValidationError("A role with this name already exists.")
        return value

    def validate_permissions(self, value):
        # EUCL may make an empty role and switch its permissions on afterwards
        if not value and not self._is_admin():
            raise serializers.ValidationError("Choose at least one permission.")
        if not self._is_admin():
            allowed = company_role_permissions()
            not_allowed = [p.name for p in value if p.code not in allowed]
            if not_allowed:
                raise serializers.ValidationError(f"You can't give: {', '.join(not_allowed)}.")
        return value

    def validate(self, attrs):
        if self.instance is not None and self.instance.code == Role.SUPER_ADMIN:
            # Never a company role. Every permission, "Manage users & roles"
            # included, may be switched off (the app asks first for that one).
            attrs.pop("is_company_role", None)
        if self.instance is not None and self.instance.code == Role.EMPLOYEE:
            if attrs.get("is_company_role"):
                raise serializers.ValidationError("The Employee role can't be a company role.")
        if not self._is_admin():
            # A boss's roles are always company roles of their own company
            attrs["is_company_role"] = True
            if self.instance is None:
                attrs["company"] = get_company(self.context["request"].user)
                if attrs["company"] is None:
                    raise serializers.ValidationError("Your account is not linked to a company.")
        return attrs

    def create(self, validated_data):
        # A stable internal code from the name: "Finance officer" -> "FINANCE_OFFICER"
        base = (slugify(validated_data["name"]).replace("-", "_").upper() or "ROLE")[:44]
        code, number = base, 2
        while Role.objects.filter(code=code).exists():
            code, number = f"{base}_{number}", number + 1
        validated_data["code"] = code
        return self._set_kind(super().create(validated_data))

    def update(self, instance, validated_data):
        return self._set_kind(super().update(instance, validated_data))

    @staticmethod
    def _set_kind(role):
        """
        Nobody ticks "company role" any more: a role whose permissions are all
        company permissions is a company role (its users must work for a
        company). Employee and Super admin never are; a company's own roles
        always are.
        """
        if role.code in (Role.EMPLOYEE, Role.SUPER_ADMIN):
            kind = False
        elif role.company_id is not None:
            kind = True
        else:
            areas = set(role.permissions.values_list("area", flat=True))
            kind = bool(areas) and areas == {"Company"}
        if role.is_company_role != kind:
            role.is_company_role = kind
            role.save(update_fields=["is_company_role"])
        return role


# ------------------------------------------------------------- companies

class CompanySerializer(serializers.ModelSerializer):
    # Filled in by the view with .annotate(...)
    service_count = serializers.IntegerField(read_only=True, default=0)
    covered_count = serializers.IntegerField(read_only=True, default=0)
    staff_count = serializers.IntegerField(read_only=True, default=0)
    is_deleted = serializers.BooleanField(read_only=True)

    # New company only: its login (the company boss), so it gets its own dashboard.
    # The login is shown under the company's name.
    account_username = serializers.CharField(write_only=True, required=False, max_length=150)
    account_email = serializers.EmailField(write_only=True, required=False)
    account_password = serializers.CharField(write_only=True, required=False)
    account_password_confirm = serializers.CharField(write_only=True, required=False)

    ACCOUNT_FIELDS = [
        "account_username",
        "account_email",
        "account_password",
        "account_password_confirm",
    ]

    class Meta:
        model = Company
        fields = [
            "id",
            "name",
            "email",
            "phone",
            "address",
            "description",
            "created_at",
            "is_active",
            "is_deleted",
            "deleted_at",
            "service_count",
            "covered_count",
            "staff_count",
            "account_username",
            "account_email",
            "account_password",
            "account_password_confirm",
        ]
        read_only_fields = ["is_active", "deleted_at"]

    def validate_phone(self, value):
        return validate_phone(value) if value else value

    def validate_account_username(self, value):
        value = value.strip()
        if not re.fullmatch(r"[\w.@+-]+", value):
            raise serializers.ValidationError("Use letters, numbers and @ . + - _ only (no spaces).")
        return check_unique_username(value)

    def validate_account_email(self, value):
        return check_unique_email(value)

    def validate(self, attrs):
        if self.instance is not None:
            # Logins of an existing company are managed on its Staff tab
            for field in self.ACCOUNT_FIELDS:
                attrs.pop(field, None)
            return attrs

        missing = {field: "This field is required." for field in self.ACCOUNT_FIELDS if not attrs.get(field)}
        if missing:
            raise serializers.ValidationError(missing)
        try:
            check_new_password(attrs["account_password"], attrs["account_password_confirm"])
        except serializers.ValidationError as exc:
            raise serializers.ValidationError({f"account_{key}": value for key, value in exc.detail.items()})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        account = {field[len("account_"):]: validated_data.pop(field) for field in self.ACCOUNT_FIELDS}
        company = super().create(validated_data)

        user = User(
            username=account["username"],
            first_name=company.name[:150],
            email=account["email"],
        )
        user.set_password(account["password"])
        user.save()
        profile = UserProfile.objects.create(user=user, company=company)
        profile.roles.set(Role.objects.filter(code=Role.COMPANY_BOSS))
        return company


class ServiceSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True)
    visit_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Service
        fields = [
            "id",
            "company",
            "company_name",
            "name",
            "description",
            "price",
            "is_active",
            "is_approved",
            "eucl_price",
            "visit_count",
        ]
        # eucl_price always equals the company's price (set in validate)
        extra_kwargs = {"company": {"required": False}, "eucl_price": {"read_only": True}}
        # Our validate() gives a clearer duplicate-name message
        validators = []

    def validate_price(self, value):
        if value < 0:
            raise serializers.ValidationError("The price can't be negative.")
        return value

    def validate_eucl_price(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("The amount can't be negative.")
        return value

    def validate(self, attrs):
        user = self.context["request"].user
        if not has_perm(user, "manage_companies"):
            # Only EUCL decides which services its employees may use, and for how much
            attrs.pop("is_approved", None)
            attrs.pop("eucl_price", None)
            # Company staff can only manage their own company's services
            attrs["company"] = get_company(user)
            if attrs["company"] is None:
                raise serializers.ValidationError("Your account is not linked to a company.")
        company = attrs.get("company", getattr(self.instance, "company", None))
        if company is None:
            raise serializers.ValidationError({"company": "Choose the company that offers this service."})
        if self.instance is not None and company != self.instance.company:
            raise serializers.ValidationError({"company": "A service can't move to another company."})

        name = " ".join(attrs.get("name", getattr(self.instance, "name", "")).split())
        if "name" in attrs:
            attrs["name"] = name
        duplicates = Service.objects.filter(company=company, name__iexact=name)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError({"name": f"{company.name} already offers a service with this name."})

        # EUCL pays the company's own price: eucl_price simply mirrors it
        # (kept because the M&E tool still reads it)
        covered = attrs.get("is_approved", getattr(self.instance, "is_approved", False))
        price = attrs.get("price", getattr(self.instance, "price", None))
        attrs["eucl_price"] = price if covered else None
        return attrs


class PriceChangeSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source="service.name", read_only=True)
    company_name = serializers.CharField(source="company.name", read_only=True)
    difference = serializers.SerializerMethodField()

    class Meta:
        model = PriceChange
        fields = [
            "id", "service", "service_name", "company", "company_name", "old_price", "new_price", "difference",
            "changed_by_name", "changed_by_username", "changed_by_roles", "changed_at",
        ]

    def get_difference(self, change):
        return None if change.old_price is None else change.new_price - change.old_price


def record_price_change(service, old_price, user):
    """Note who gave this service its price (old_price None: just added)."""
    if old_price is not None and old_price == service.price:
        return None
    return PriceChange.objects.create(
        service=service,
        company=service.company,
        old_price=old_price,
        new_price=service.price,
        changed_by=user,
        changed_by_name=display_name(user) or user.username,
        changed_by_username=user.username,
        changed_by_roles=", ".join(role_names(user)),
    )


class PublicCompanySerializer(serializers.ModelSerializer):
    """What EUCL employees see when choosing where to go: the place and its services."""

    services = serializers.SerializerMethodField()
    covered_count = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = ["id", "name", "phone", "address", "description", "covered_count", "services"]

    def _offered(self, company):
        return [s for s in company.services.all() if s.is_active]

    def get_services(self, company):
        # Everything the place offers, marked covered by EUCL or not, so
        # employees know before they go. Covered ones show EUCL's amount;
        # the others show the company's own price (what they'd pay).
        return [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "is_covered": s.is_approved,
                "eucl_price": s.eucl_price if s.is_approved else None,
                "price": s.price,
            }
            for s in sorted(self._offered(company), key=lambda s: (not s.is_approved, s.name.lower()))
        ]

    def get_covered_count(self, company):
        return sum(1 for s in self._offered(company) if s.is_approved)


# ----------------------------------------------------------- EUCL employees

class EmployeeSerializer(serializers.ModelSerializer):
    # Login details live on the User; these fields read and edit them
    first_name = serializers.CharField(source="user.first_name", max_length=150)
    last_name = serializers.CharField(source="user.last_name", max_length=150)
    email = serializers.EmailField(source="user.email")
    username = serializers.CharField(source="user.username", read_only=True)
    user_name = serializers.CharField(source="name", read_only=True)
    is_active = serializers.BooleanField(source="user.is_active", read_only=True)
    # For company staff: already used services at another company today
    elsewhere_today = serializers.BooleanField(read_only=True, default=False)

    class Meta:
        model = Employee
        fields = [
            "id",
            "employee_id",
            "username",
            "first_name",
            "last_name",
            "user_name",
            "email",
            "is_active",
            "elsewhere_today",
            "phone",
            "department",
            "position",
            "created_at",
        ]
        extra_kwargs = {
            "employee_id": {"validators": []},  # clean_employee_id gives a clearer message
            "phone": {"allow_blank": False},
            "department": {"allow_blank": False},
            "position": {"allow_blank": False},
        }

    def validate_employee_id(self, value):
        return clean_employee_id(value, exclude=self.instance)

    def validate_phone(self, value):
        return validate_phone(value)

    def validate_email(self, value):
        exclude = self.instance.user if self.instance else None
        return check_unique_email(value, exclude_user=exclude)

    @transaction.atomic
    def update(self, instance, validated_data):
        # Dotted fields (user.first_name, ...) arrive as {"user": {...}}
        for field, value in validated_data.pop("user", {}).items():
            setattr(instance.user, field, value)
        instance.user.save()
        employee = super().update(instance, validated_data)
        employee.sync_hr_role()  # moving in or out of HR changes the role
        return employee


def username_from_last_name(last_name, taken=()):
    """
    The default username: the last (family) name ("NATUKUNDA"). If that name is
    already used, a number is added: NATUKUNDA2, NATUKUNDA3...
    `taken`: names already chosen in the same upload.
    """
    base = re.sub(r"[^\w.@+-]", "", last_name.strip())[:140] or "employee"
    taken = {name.lower() for name in taken}
    name, number = base, 2
    while name.lower() in taken or User.objects.filter(username__iexact=name).exists():
        name, number = f"{base}{number}", number + 1
    return name


def create_employee(employee_id, first_name, last_name, department, position,
                    username=None, password=None, email="", phone=""):
    """
    The login, the Employee role (plus HR for the HR department) and the
    Employee record. The username defaults to the last name. Without a
    password the account has none yet: the employee creates it at first login
    (Employee ID + the email or phone HR saved).
    """
    user = User.objects.create_user(
        username=username or username_from_last_name(last_name),
        password=password or None,  # None -> no usable password until first login
        first_name=first_name,
        last_name=last_name,
        email=email or "",
    )
    profile = UserProfile.objects.create(user=user)
    profile.roles.add(Role.objects.get(code=Role.EMPLOYEE))
    employee = Employee.objects.create(
        user=user, employee_id=employee_id, phone=phone or "", department=department, position=position
    )
    employee.sync_hr_role()
    return employee


class EmployeeRegistrationSerializer(serializers.Serializer):
    """
    Creates the login, the Employee role and the Employee record together.
    HR types the Employee ID. The username defaults to the last name. Without
    a password the employee creates it at first login, using their Employee ID
    and the email or phone saved here. Every field is required.
    """

    employee_id = serializers.CharField(max_length=40)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    username = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    password_confirm = serializers.CharField(write_only=True, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20)
    department = serializers.CharField(max_length=100)
    position = serializers.CharField(max_length=100)

    def validate_employee_id(self, value):
        return clean_employee_id(value)

    def validate_email(self, value):
        return check_unique_email(value)

    def validate_phone(self, value):
        return validate_phone(value)

    def validate(self, attrs):
        attrs["username"] = (attrs.get("username") or "").strip()
        if attrs["username"]:
            try:
                check_unique_username(attrs["username"])
            except serializers.ValidationError as exc:
                raise serializers.ValidationError({"username": exc.detail})
        else:
            attrs["username"] = username_from_last_name(attrs["last_name"])
        if attrs.get("password") or attrs.get("password_confirm"):
            check_new_password(attrs.get("password", ""), attrs.get("password_confirm", ""))
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        return create_employee(
            validated_data["employee_id"],
            validated_data["first_name"],
            validated_data["last_name"],
            validated_data["department"],
            validated_data["position"],
            username=validated_data["username"],
            password=validated_data.get("password"),
            email=validated_data.get("email", ""),
            phone=validated_data.get("phone", ""),
        )


# ---------------------------------------------------------------- visits

class VisitSerializer(serializers.ModelSerializer):
    employee_code = serializers.CharField(source="employee.employee_id", read_only=True)
    employee_name = serializers.CharField(source="employee.name", read_only=True)
    department = serializers.CharField(source="employee.department", read_only=True)
    service_name = serializers.CharField(source="service.name", read_only=True)
    company_name = serializers.CharField(source="company.name", read_only=True)
    recorded_by_name = serializers.CharField(source="recorded_by.username", read_only=True, allow_null=True)
    is_paid = serializers.SerializerMethodField()
    feedback_kind_label = serializers.CharField(source="get_feedback_kind_display", read_only=True)

    class Meta:
        model = Visit
        fields = [
            "id",
            "employee",
            "employee_code",
            "employee_name",
            "department",
            "service",
            "service_name",
            "company",
            "company_name",
            "price",
            "visit_date",
            "visited_at",
            "recorded_by_name",
            "is_paid",
            "feedback_kind",
            "feedback_kind_label",
            "feedback_message",
            "feedback_at",
        ]
        read_only_fields = fields

    def get_is_paid(self, visit):
        return visit.payment_id is not None


class RecordVisitsSerializer(serializers.Serializer):
    """
    The receptionist ticks one or more services an employee used.
    POST {"employee": 3, "services": [5, 7]}
    """
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.select_related("user"))
    services = serializers.PrimaryKeyRelatedField(
        queryset=Service.objects.select_related("company"), many=True
    )

    def validate_services(self, services):
        if not services:
            raise serializers.ValidationError("Tick at least one service.")
        return list(dict.fromkeys(services))  # ignore the same tick sent twice

    def validate(self, attrs):
        user = self.context["request"].user
        employee = attrs["employee"]
        if not employee.user.is_active:
            raise serializers.ValidationError({"employee": f"{employee.employee_id}'s account is deactivated."})

        company = get_company(user)
        for service in attrs["services"]:
            if not user.is_superuser and service.company != company:
                raise serializers.ValidationError({"services": "You can only record services of your own company."})
            if not service.company.is_open:
                raise serializers.ValidationError({"services": f"{service.company} is not open right now."})
            if not service.is_active:
                raise serializers.ValidationError({"services": f"{service.name} is currently not offered."})
            if not service.is_approved:
                raise serializers.ValidationError({"services": f"{service.name} is not covered by EUCL."})

        # Several services a day are fine, but all at ONE company
        companies = {service.company_id for service in attrs["services"]}
        if len(companies) > 1:
            raise serializers.ValidationError({"services": "An employee can use services at only one company per day."})
        went_elsewhere = (
            Visit.objects.filter(employee=employee, visit_date=timezone.localdate())
            .exclude(company_id__in=companies)
            .exists()
        )
        if went_elsewhere:
            name = employee.name or employee.employee_id
            raise serializers.ValidationError({
                "employee": f"{name} already used services at another company today. "
                            "An EUCL employee can visit only one company per day."
            })
        return attrs


# --------------------------------------------------------------- payments

class PaymentSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True)
    recorded_by_name = serializers.CharField(source="recorded_by.username", read_only=True, allow_null=True)
    visit_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Payment
        fields = [
            "id",
            "company",
            "company_name",
            "period_start",
            "period_end",
            "amount",
            "reference",
            "note",
            "paid_at",
            "recorded_by_name",
            "visit_count",
        ]
        read_only_fields = ["amount", "paid_at", "recorded_by_name", "visit_count"]

    def validate(self, attrs):
        if attrs["period_end"] < attrs["period_start"]:
            raise serializers.ValidationError({"period_end": "The end date must be on or after the start date."})
        return attrs


# ----------------------------------------------------------------- users

class UserAccountSerializer(serializers.ModelSerializer):
    """
    Create and edit logins. Every login has exactly one role.
    - Users with manage_users (the super admin) can give any role.
    - A company boss (manage_company_staff) can only give company roles,
      and only inside their own company.
    """

    roles = serializers.SlugRelatedField(
        many=True, slug_field="code", queryset=Role.objects.all(), required=False
    )
    is_superuser = serializers.BooleanField(required=False)
    company = serializers.PrimaryKeyRelatedField(
        queryset=Company.objects.filter(deleted_at__isnull=True),
        required=False,
        allow_null=True,
    )
    password = serializers.CharField(write_only=True, required=False)
    password_confirm = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "is_active",
            "is_superuser",
            "roles",
            "company",
            "password",
            "password_confirm",
            "last_login",
            "date_joined",
        ]
        read_only_fields = ["last_login", "date_joined"]
        extra_kwargs = {
            "first_name": {"required": True, "allow_blank": False},
            # A company login has only the company's name
            "last_name": {"required": False, "allow_blank": True},
            "email": {"required": True, "allow_blank": False},
        }

    def to_representation(self, user):
        profile = getattr(user, "userprofile", None)
        employee = getattr(user, "employee", None)
        company = profile.company if profile else None
        return {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "is_active": user.is_active,
            "is_superuser": user.is_superuser,
            "roles": [role.code for role in profile.roles.all()] if profile else [],
            "role_names": role_names(user),
            "company": company.id if company else None,
            "company_name": company.name if company else None,
            "employee_id": employee.employee_id if employee else None,
            "last_login": user.last_login,
            "date_joined": user.date_joined,
        }

    def validate_username(self, value):
        return check_unique_username(value, exclude_user=self.instance)

    def validate_email(self, value):
        return check_unique_email(value, exclude_user=self.instance)

    def validate(self, attrs):
        request_user = self.context["request"].user
        creating = self.instance is None
        is_platform_admin = has_perm(request_user, "manage_users")
        employee = getattr(self.instance, "employee", None) if self.instance else None
        profile = getattr(self.instance, "userprofile", None) if self.instance else None

        # ---- the role this user will end up with: exactly one, because
        # every role has its own permissions
        super_role = Role.objects.filter(code=Role.SUPER_ADMIN).first()
        if "roles" in attrs:
            roles = set(attrs["roles"])
            if attrs.get("is_superuser") and super_role is not None and not roles:
                roles = {super_role}
        elif attrs.get("is_superuser") and super_role is not None:
            roles = {super_role}
        else:
            roles = set(profile.roles.all()) if profile else set()
            if not roles and getattr(self.instance, "is_superuser", False) and super_role is not None:
                roles = {super_role}  # a super admin made with createsuperuser
        if not roles:
            raise serializers.ValidationError({"roles": "Choose a role."})
        if len(roles) > 1:
            raise serializers.ValidationError(
                {"roles": "Choose only one role. Each role has its own permissions, so a person can't have two."}
            )
        employee_role = Role.objects.get(code=Role.EMPLOYEE)
        if employee_role in roles and employee is None:
            raise serializers.ValidationError(
                {"roles": "The Employee role is only for EUCL employees: add them on the EUCL employees page."}
            )

        # The Super admin role and the super admin switch always go together
        is_superuser = super_role is not None and super_role in roles
        if attrs.get("is_superuser") and not is_superuser:
            raise serializers.ValidationError(
                {"roles": "A super admin has the Super admin role only. Choose only one role."}
            )

        # ---- a company boss works only inside their own company
        if not is_platform_admin:
            if is_superuser or any(not role.is_company_role for role in roles):
                raise serializers.ValidationError({"roles": "You can only give company roles."})
            attrs["company"] = get_company(request_user)

        # ---- company roles need the company the person works for
        company = attrs.get("company", profile.company if profile else None)
        if any(role.is_company_role for role in roles):
            if company is None:
                raise serializers.ValidationError({"company": "Choose the company this person works for."})
        else:
            company = None

        # ---- a company's own role only goes to that company's staff
        for role in roles:
            if role.company_id is not None and (company is None or role.company_id != company.id):
                raise serializers.ValidationError({"roles": f"The role {role.name} belongs to another company."})

        attrs["roles"] = roles
        attrs["company"] = company
        attrs["is_superuser"] = is_superuser

        # ---- passwords: required when creating, separate action when editing
        if creating:
            if not attrs.get("password"):
                raise serializers.ValidationError({"password": "This field is required."})
            check_new_password(attrs["password"], attrs.get("password_confirm"))
        else:
            attrs.pop("password", None)
            attrs.pop("password_confirm", None)

        # ---- nobody can lock themselves out
        if self.instance is not None and self.instance == request_user:
            if attrs.get("is_active") is False:
                raise serializers.ValidationError("You can't deactivate your own account.")
            if request_user.is_superuser and not is_superuser:
                raise serializers.ValidationError("You can't remove your own super admin access.")

        return attrs

    @staticmethod
    def save_roles(user, roles, company, is_superuser):
        user.is_superuser = is_superuser
        user.is_staff = is_superuser  # super admins can also open Django admin
        user.save()
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.company = company
        profile.save()
        profile.roles.set(roles)

    @transaction.atomic
    def create(self, validated_data):
        roles = validated_data.pop("roles")
        company = validated_data.pop("company", None)
        is_superuser = validated_data.pop("is_superuser", False)
        password = validated_data.pop("password")
        validated_data.pop("password_confirm", None)

        user = User(**validated_data)
        user.set_password(password)
        user.save()
        self.save_roles(user, roles, company, is_superuser)
        return user

    @transaction.atomic
    def update(self, instance, validated_data):
        roles = validated_data.pop("roles")
        company = validated_data.pop("company", None)
        is_superuser = validated_data.pop("is_superuser", instance.is_superuser)
        instance = super().update(instance, validated_data)
        self.save_roles(instance, roles, company, is_superuser)
        return instance


class FeedbackSerializer(serializers.Serializer):
    """An employee's feedback on one service they used: a comment or a complaint."""

    kind = serializers.ChoiceField(
        choices=Visit.FEEDBACK_KINDS,
        error_messages={"invalid_choice": "Choose Comment or Complaint."},
    )
    message = serializers.CharField(max_length=1000, required=False, allow_blank=True)  # checked in validate()

    def validate(self, attrs):
        attrs["message"] = attrs.get("message", "").strip()
        if not attrs["message"]:
            raise serializers.ValidationError({"message": "Write your comment or complaint."})
        return attrs


def same_phone(a, b):
    """+250 788 123 456, 0788123456 and 250788123456 are the same number."""
    digits_a, digits_b = re.sub(r"\D", "", a or ""), re.sub(r"\D", "", b or "")
    return len(digits_a) >= 9 and len(digits_b) >= 9 and digits_a[-9:] == digits_b[-9:]


class FirstLoginSerializer(serializers.Serializer):
    """
    An employee HR added creates their account: Employee ID + the email or
    phone HR saved, then their own password. Only for accounts without a
    password yet.
    """

    NO_MATCH = (
        "These details don't match an employee waiting to create their account. "
        "Check your Employee ID and the email or phone you gave HR. "
        "If you already created your account, sign in instead."
    )

    employee_id = serializers.CharField(max_length=40)
    contact = serializers.CharField(max_length=254)
    password = serializers.CharField(write_only=True)
    password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs):
        employee_id = "".join(attrs["employee_id"].split()).upper()
        employee = Employee.objects.select_related("user").filter(employee_id__iexact=employee_id).first()
        contact = attrs["contact"].strip()
        matches = employee is not None and (
            (employee.user.email and employee.user.email.lower() == contact.lower())
            or same_phone(employee.phone, contact)
        )
        # One message for every failure: it doesn't reveal which IDs exist
        if not matches or not employee.user.is_active or employee.user.has_usable_password():
            raise serializers.ValidationError({"detail": self.NO_MATCH})
        check_new_password(attrs["password"], attrs["password_confirm"], user=employee.user)
        attrs["employee"] = employee
        return attrs

    def save(self):
        user = self.validated_data["employee"].user
        user.set_password(self.validated_data["password"])
        user.save(update_fields=["password"])
        return user


class SetPasswordSerializer(serializers.Serializer):
    """Someone with the right permission sets a new password for another user."""
    password = serializers.CharField(write_only=True)
    password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs):
        check_new_password(attrs["password"], attrs["password_confirm"], self.context.get("user"))
        return attrs


# ---------------------------------------------------------------- my account

class ProfileUpdateSerializer(serializers.Serializer):
    """What any user may change about themselves (employees also have a phone)."""
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20, required=False)

    def validate_email(self, value):
        return check_unique_email(value, exclude_user=self.context["request"].user)

    def validate_phone(self, value):
        return validate_phone(value)

    def validate(self, attrs):
        is_employee = Employee.objects.filter(user=self.context["request"].user).exists()
        if is_employee and not attrs.get("phone"):
            raise serializers.ValidationError({"phone": "This field is required."})
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True)
    password_confirm = serializers.CharField(write_only=True)

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Your current password is incorrect.")
        return value

    def validate(self, attrs):
        check_new_password(
            attrs["password"], attrs["password_confirm"], self.context["request"].user
        )
        return attrs


# ----------------------------------------------------------------- login

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["username"] = user.username
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        if company_deactivated(self.user):
            raise AuthenticationFailed({"detail": COMPANY_DEACTIVATED, "code": "company_deactivated"})
        data["username"] = self.user.username
        data["user_id"] = self.user.id
        data["permissions"] = sorted(get_permissions(self.user))
        return data
