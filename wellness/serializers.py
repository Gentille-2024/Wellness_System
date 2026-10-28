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
    Company,
    Employee,
    Payment,
    Permission,
    Role,
    Service,
    UserProfile,
    Visit,
)
from .permissions import COMPANY_DEACTIVATED, COMPANY_ROLE_PERMISSIONS, company_deactivated, get_company, get_permissions, has_perm


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


def check_unique_email(value, exclude_user=None):
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
    names = ["Super admin"] if user.is_superuser else []
    if profile is not None:
        names += [role.name for role in profile.roles.all()]
    return names


# -------------------------------------------------------- roles & permissions

class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ["id", "code", "name", "description", "area"]


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
        if not value:
            raise serializers.ValidationError("Choose at least one permission.")
        if not self._is_admin():
            not_allowed = [p.name for p in value if p.code not in COMPANY_ROLE_PERMISSIONS]
            if not_allowed:
                raise serializers.ValidationError(f"You can't give: {', '.join(not_allowed)}.")
        return value

    def validate(self, attrs):
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
        return super().create(validated_data)


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
        extra_kwargs = {"company": {"required": False}}
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

        # A covered service needs the amount EUCL agreed to pay
        covered = attrs.get("is_approved", getattr(self.instance, "is_approved", False))
        amount = attrs.get("eucl_price", getattr(self.instance, "eucl_price", None))
        if covered and amount is None:
            raise serializers.ValidationError({"eucl_price": "Set the amount EUCL pays per visit."})
        return attrs


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
    user_name = serializers.CharField(source="user.get_full_name", read_only=True)
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
        read_only_fields = ["employee_id"]
        extra_kwargs = {
            # "Full credentials": these can't be left empty
            "phone": {"allow_blank": False},
            "department": {"allow_blank": False},
            "position": {"allow_blank": False},
        }

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
        return super().update(instance, validated_data)


class EmployeeRegistrationSerializer(serializers.Serializer):
    """Creates the login, the Employee role and the Employee record together."""

    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    password_confirm = serializers.CharField(write_only=True)
    phone = serializers.CharField(max_length=20)
    department = serializers.CharField(max_length=100)
    position = serializers.CharField(max_length=100)

    def validate_username(self, value):
        return check_unique_username(value)

    def validate_email(self, value):
        return check_unique_email(value)

    def validate_phone(self, value):
        return validate_phone(value)

    def validate(self, attrs):
        check_new_password(attrs["password"], attrs["password_confirm"])
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["username"],
            password=validated_data["password"],
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            email=validated_data["email"],
        )
        profile = UserProfile.objects.create(user=user)
        profile.roles.add(Role.objects.get(code=Role.EMPLOYEE))
        return Employee.objects.create(
            user=user,
            phone=validated_data["phone"],
            department=validated_data["department"],
            position=validated_data["position"],
        )


# ---------------------------------------------------------------- visits

class VisitSerializer(serializers.ModelSerializer):
    employee_code = serializers.CharField(source="employee.employee_id", read_only=True)
    employee_name = serializers.CharField(source="employee.user.get_full_name", read_only=True)
    department = serializers.CharField(source="employee.department", read_only=True)
    service_name = serializers.CharField(source="service.name", read_only=True)
    company_name = serializers.CharField(source="company.name", read_only=True)
    recorded_by_name = serializers.CharField(source="recorded_by.username", read_only=True, allow_null=True)
    is_paid = serializers.SerializerMethodField()

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
                raise serializers.ValidationError({"services": f"{service.company} is not open for visits."})
            if not service.is_active:
                raise serializers.ValidationError({"services": f"{service.name} is currently not offered."})
            if not service.is_approved:
                raise serializers.ValidationError({"services": f"{service.name} is not covered by EUCL."})
            if service.eucl_price is None:
                raise serializers.ValidationError({"services": f"EUCL hasn't set the amount for {service.name} yet."})

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
            name = employee.user.get_full_name() or employee.employee_id
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
    Create and edit logins with one or more roles.
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

        # ---- the roles this user will end up with
        if "roles" in attrs:
            roles = set(attrs["roles"])
        else:
            roles = set(profile.roles.all()) if profile else set()
        employee_role = Role.objects.get(code=Role.EMPLOYEE)
        if employee_role in roles and employee is None:
            raise serializers.ValidationError(
                {"roles": "The Employee role comes with onboarding on the EUCL employees page."}
            )
        if employee is not None:
            roles.add(employee_role)  # employees always keep it

        is_superuser = attrs.get("is_superuser", getattr(self.instance, "is_superuser", False))
        if not roles and not is_superuser:
            raise serializers.ValidationError({"roles": "Choose at least one role."})

        # ---- a company boss works only inside their own company
        if not is_platform_admin:
            if attrs.get("is_superuser") or any(not role.is_company_role for role in roles - {employee_role}):
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
