"""
HR's Excel template and upload of EUCL employees.

Columns: EmpID, Last name, First name, Email, Phone, Department, Position.
- A new Employee ID creates the employee. The username is the last name
  (the family name: NATUKUNDA, or NATUKUNDA2 if taken). There is no password yet: the employee
  creates it at first login with their Employee ID and the email or phone
  given here. Every column is required.
- An Employee ID that already exists updates that employee's details.
- Employees of the HR department get the HR role.
The whole file is checked first: if any row has a problem nothing is saved
and every problem is reported with its row number.
"""

import csv
import io
import re

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .models import Employee

COLUMNS = ["EmpID", "Last name", "First name", "Email", "Phone", "Department", "Position"]
FIELDS = ["employee_id", "last_name", "first_name", "email", "phone", "department", "position"]
# Every column must be filled in, on every row
REQUIRED = list(FIELDS)
# Header spellings we accept (lower case, without spaces, dots, dashes or underscores)
HEADERS = {
    "empid": "employee_id", "employeeid": "employee_id", "id": "employee_id", "empno": "employee_id",
    "firstname": "first_name", "lastname": "last_name", "surname": "last_name",
    "email": "email", "emailaddress": "email", "mail": "email",
    "phone": "phone", "phonenumber": "phone", "telephone": "phone", "tel": "phone", "mobile": "phone",
    "department": "department", "dept": "department", "position": "position", "title": "position",
}
MAX_ROWS = 5000
# Longest value the database accepts for each column
LIMITS = {"employee_id": 20, "last_name": 150, "first_name": 150, "email": 254, "phone": 20, "department": 100, "position": 100}


def _join(names):
    """Turns ["Email", "Phone", "Position"] into "Email, Phone and Position"."""
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


class ImportError_(Exception):
    """The file itself can't be read (not the rows)."""


def template_bytes():
    """The empty Excel template with the five columns and a short guide."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Employees"
    ws.append(COLUMNS)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F7A55")
        cell.alignment = Alignment(vertical="center")
    for letter, width in zip("ABCDEFG", [14, 22, 20, 28, 18, 22, 26]):
        ws.column_dimensions[letter].width = width
    ws.freeze_panes = "A2"
    # Employee IDs and phone numbers stay text (keeps leading zeros: 00123, 0788…)
    for row in range(2, 1002):
        ws.cell(row=row, column=1).number_format = "@"
        ws.cell(row=row, column=5).number_format = "@"

    guide = wb.create_sheet("How to fill")
    for line in [
        ["How to fill the Employees sheet"],
        [],
        ["All columns", "Every column must be filled in on every row; otherwise nothing is saved."],
        ["EmpID", "Required. The employee's EUCL ID, e.g. EMP0101. Must be unique."],
        ["Last name", "Required. The family name, e.g. NATUKUNDA. It becomes the username (NATUKUNDA2 if already taken)."],
        ["First name", "Required, e.g. Charlotte."],
        ["Email", "Required, e.g. name@example.com."],
        ["Phone", "Required, e.g. +250788123456 or 0788123456."],
        ["Department", "Required. Employees in the HR department get the HR role."],
        ["Position", "Required."],
        [],
        ["First login", "On the sign-in page the employee clicks \"First time here? Create your account\","],
        ["", "types their EmpID and the email or phone from this file, and chooses a password."],
        ["Existing EmpID", "Uploading an EmpID that already exists updates that employee's details."],
    ]:
        guide.append(line)
    guide["A1"].font = Font(bold=True, size=13)
    guide.column_dimensions["A"].width = 18
    guide.column_dimensions["B"].width = 80

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)  # 123.0 from Excel -> "123"
    return " ".join(str(value).split())


def _key(header):
    return re.sub(r"[\s._\-]", "", _text(header).lower())


def read_rows(upload):
    """[(row number, [cells…]), …] from an .xlsx or .csv upload."""
    name = (getattr(upload, "name", "") or "").lower()
    data = upload.read()
    if name.endswith(".csv"):
        text = data.decode("utf-8-sig", errors="replace")
        return list(enumerate(csv.reader(io.StringIO(text)), start=1))
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # not an Excel file, or damaged
        raise ImportError_("This file can't be read. Upload the Excel template (.xlsx) or a .csv file.") from exc
    ws = wb["Employees"] if "Employees" in wb.sheetnames else wb.worksheets[0]
    return [(number, list(row)) for number, row in enumerate(ws.iter_rows(values_only=True), start=1)]


def parse(upload):
    """
    Returns (records, errors). records: [{"row", "employee_id", "first_name", …}]
    errors: [{"row", "message"}]
    """
    rows = read_rows(upload)
    header_at, columns = None, {}
    for number, cells in rows[:10]:  # the header is near the top
        found = {HEADERS[_key(c)]: i for i, c in enumerate(cells) if _key(c) in HEADERS}
        if "employee_id" in found:
            header_at, columns = number, found
            break
    if header_at is None:
        raise ImportError_(
            "The header row was not found in the first 10 rows. Use the template's headers: "
            "EmpID, Last name, First name, Email, Phone, Department, Position."
        )
    missing = [COLUMNS[FIELDS.index(f)] for f in REQUIRED if f not in columns]
    if missing:
        raise ImportError_(f"The file has no {_join(missing)} column. Use the template's headers.")

    records, errors, seen = [], [], {}

    def problem(row, message):
        # Each message names its Excel row, so HR knows exactly where to look
        errors.append({"row": row, "message": f"Row {row}: {message}"})

    for number, cells in rows:
        if number <= header_at:
            continue
        values = {f: _text(cells[columns[f]]) if f in columns and columns[f] < len(cells) else "" for f in FIELDS}
        if not any(values.values()):
            continue  # empty line
        values["employee_id"] = values["employee_id"].replace(" ", "").upper()
        before = len(errors)

        # Every problem of the row, not just the first one
        empty = [COLUMNS[FIELDS.index(f)] for f in REQUIRED if not values[f]]
        if empty:
            problem(number, f"missing data in {_join(empty)}.")
        if values["email"]:
            try:
                validate_email(values["email"])
            except DjangoValidationError:
                problem(number, f"invalid email “{values['email']}”. Use the form name@example.com.")
        if values["phone"]:
            if re.match(r"^\d{9}$", values["phone"]):
                values["phone"] = "0" + values["phone"]  # Excel dropped the leading 0
            if not re.fullmatch(r"\+?\d{9,15}", re.sub(r"[\s-]", "", values["phone"])):
                problem(number, f"invalid phone number “{values['phone']}”. Use 9 to 15 digits, e.g. 0788123456 or +250788123456.")
        for field, limit in LIMITS.items():
            if len(values[field]) > limit:
                problem(number, f"{COLUMNS[FIELDS.index(field)]} is too long ({len(values[field])} characters, at most {limit}).")
        if values["employee_id"] and values["employee_id"] in seen:
            problem(number, f"EmpID {values['employee_id']} is used twice: also on row {seen[values['employee_id']]}.")
        elif values["employee_id"]:
            seen[values["employee_id"]] = number  # even if this row has other problems

        if len(errors) > before:
            continue
        records.append({"row": number, **values})
        if len(records) > MAX_ROWS:
            raise ImportError_(f"Upload at most {MAX_ROWS} employees at a time.")

    if not records and not errors:
        raise ImportError_("The file has no employees: the rows under the header are empty.")

    # Emails: one account per email, in the file and in the system
    existing = {e.employee_id.upper(): e for e in Employee.objects.select_related("user").filter(
        employee_id__in=[r["employee_id"] for r in records])}
    emails = {}
    for record in records:
        email = record["email"].lower()
        if not email:
            continue
        if email in emails:
            problem(record["row"], f"email {record['email']} is used twice: also on row {emails[email]}.")
            continue
        emails[email] = record["row"]
        own = existing.get(record["employee_id"])
        others = User.objects.filter(email__iexact=email)
        if own is not None:
            others = others.exclude(pk=own.user_id)
        if others.exists():
            problem(record["row"], f"email {record['email']} already belongs to another account.")
    errors.sort(key=lambda e: e["row"])
    return records, errors


@transaction.atomic
def apply(records):
    """Create new employees and update existing ones. Returns (created, updated)."""
    from .serializers import create_employee, username_from_last_name

    existing = {e.employee_id.upper(): e for e in Employee.objects.select_related("user").filter(
        employee_id__in=[r["employee_id"] for r in records])}
    created = updated = 0
    for r in records:
        employee = existing.get(r["employee_id"])
        if employee is None:
            create_employee(
                r["employee_id"], r["first_name"], r["last_name"], r["department"], r["position"],
                username=username_from_last_name(r["last_name"]), email=r["email"], phone=r["phone"],
            )
            created += 1
            continue
        employee.user.first_name, employee.user.last_name = r["first_name"], r["last_name"]
        if r["email"]:
            employee.user.email = r["email"]
        employee.user.save(update_fields=["first_name", "last_name", "email"])
        employee.department, employee.position = r["department"], r["position"]
        if r["phone"]:
            employee.phone = r["phone"]
        employee.save(update_fields=["department", "position", "phone"])
        employee.sync_hr_role()
        updated += 1
    return created, updated
