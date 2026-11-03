# EUCL Wellness Management System

EUCL employees use wellness services (gym, pool, massage, yoga…) at **partner companies**.
Each company lists its services and the **price per visit** that EUCL pays.
Employees browse the places before they go; the company's receptionist ticks the services
they used; EUCL sees every visit and marks each company's amounts as **paid**.

- **Backend:** Django 6 + Django REST Framework + JWT, MySQL
- **Frontend:** React 19 + Vite + React Router, jsPDF for PDF export

## Who does what

Access is controlled by **permissions**. A **role** is a named set of permissions, and a
user can have several roles. The super admin can create new roles and change permissions
under **Users & roles → Roles & permissions**.

| Built-in role | Belongs to | Can do |
|---|---|---|
| Super admin | EUCL | Everything, including permissions added later |
| Company boss | A company | Every company page: dashboard, record services, attendance, services & prices, employees attended, services, payments and staff |
| Receptionist | A company | Dashboard, record services, employees attendance, services & prices, employees attended |
| HR | EUCL | What an employee can do, plus EUCL employees: onboard, Excel template and upload. Given automatically to employees of the HR department |
| Employee (automatic) | EUCL | See partner places and services, see and export own services |
| M&E officer | EUCL | M&E dashboards, targets, and exporting the data (the M&E tool's sync account has this role) |

Employee IDs are typed by HR (no automatic numbering). The username is the employee's last (family) name
(NATUKUNDA, or NATUKUNDA2 if taken), and names are shown family name first: NATUKUNDA Charlotte. New employees have no password: on the sign-in page they click
**First time here? Create your account**, type their Employee ID and the email or phone HR saved,
and choose their password. The Excel template columns are EmpID, Last name, First name, Email,
Phone, Department, Position (Email or Phone required).

Companies can be **deactivated** (paused: hidden from employees, no new visits) or
**deleted** (archived: staff can't log in). Nothing is ever erased and both can be undone.

## Setup

### Backend
```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt   # includes openpyxl for the Excel upload
copy .env.example .env      # then fill in DJANGO_SECRET_KEY and DB_PASSWORD
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

### Frontend (second terminal)
```powershell
cd frontend
npm install
npm run dev
```
Open http://localhost:5173

## First steps after installing
1. Log in as the super admin.
2. **Companies → Add company**, open it, add its **services & prices**, then add a
   **Company boss** and a **Company receptionist** under *Staff*.
3. Onboard the first HR employee under **EUCL employees** with department **HR**: they get the **HR** role.
4. HR adds the other employees one by one, or downloads the **Excel template** and uploads it.

## Tests
```powershell
python manage.py test wellness
```

## API overview
| Endpoint | Purpose |
|---|---|
| `POST /api/login/` · `POST /api/token/refresh/` | JWT tokens |
| `GET/PATCH /api/me/` · `POST /api/me/password/` | Who am I, my profile, my password |
| `/api/companies/` (+ `/deactivate/`, `/activate/`, `/restore/`) | Partner companies |
| `GET /api/places/` | Open companies and their services (for employees) |
| `/api/services/` | Services and prices |
| `/api/employees/` · `POST /api/employees/register/` | EUCL employees |
| `/api/visits/` (filters: dates, company, service, department, paid, search) | Usage records; `POST` records ticked services |
| `/api/payments/` · `GET /api/payments/balances/` | Payments; amounts owed per company |
| `/api/roles/` · `GET /api/permissions/` · `/api/users/` | Roles, permissions, logins |
| `GET /api/stats/?scope=platform|company` | Dashboard numbers |
