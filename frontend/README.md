EUCL Wellness Management System
EUCL employees use wellness services (gym, pool, massage, yoga…) at partner companies. Each company lists its services and the price per visit that EUCL pays. Employees browse the places before they go; the company's receptionist ticks the services they used; EUCL sees every visit and marks each company's amounts as paid.

Backend: Django 6 + Django REST Framework + JWT, MySQL
Frontend: React 19 + Vite + React Router, jsPDF for PDF export
Who does what
Access is controlled by permissions. A role is a named set of permissions, and a user can have several roles. The super admin can create new roles and change permissions under Users & roles → Roles & permissions.

Built-in role	Belongs to	Can do
Super admin	EUCL	Everything
EUCL HR	EUCL	Onboard and manage EUCL employees; see all visits
Company boss	A company	Services & prices, staff logins, visits and payments of their company
Company receptionist	A company	Record (tick) the services an employee used; see the company's visits
Employee	EUCL	See partner places and services, see and export own visits
Companies can be deactivated (paused: hidden from employees, no new visits) or deleted (archived: staff can't log in). Nothing is ever erased and both can be undone.

Setup
Backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # then fill in DJANGO_SECRET_KEY and DB_PASSWORD
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
Frontend (second terminal)
cd frontend
npm install
npm run dev
Open http://localhost:5173

First steps after installing
Log in as the super admin.
Companies → Add company, open it, add its services & prices, then add a Company boss and a Company receptionist under Staff.
Users & roles → Add user with the EUCL HR role.
HR onboards EUCL employees under EUCL employees.
Tests
python manage.py test wellness
API overview
Endpoint	Purpose
POST /api/login/ · POST /api/token/refresh/	JWT tokens
GET/PATCH /api/me/ · POST /api/me/password/	Who am I, my profile, my password
/api/companies/ (+ /deactivate/, /activate/, /restore/)	Partner companies
GET /api/places/	Open companies and their services (for employees)
/api/services/	Services and prices
/api/employees/ · POST /api/employees/register/	EUCL employees
/api/visits/ (filters: dates, company, service, department, paid, search)	Usage records; POST records ticked services
/api/payments/ · GET /api/payments/balances/	Payments; amounts owed per company
/api/roles/ · GET /api/permissions/ · /api/users/	Roles, permissions, logins
`GET /api/stats/?scope=platform	company`