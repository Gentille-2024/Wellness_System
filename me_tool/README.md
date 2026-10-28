# EUCL Wellness M&E tool

A separate **Monitoring & Evaluation** application for the EUCL Wellness
Management System. It copies the wellness system's data every 30 minutes and
shows dashboards, service performance, indicators (targets vs actuals) and
monthly PDF / Excel reports.

| Part | Technology |
|---|---|
| Web app | Django 6, server-rendered pages, Chart.js, HTMX (saved in `static/vendor`, no internet needed) |
| Database | PostgreSQL 17 (SQLite for local development and tests) |
| Background jobs | Celery + Redis: the sync every 30 min, a nightly check, report building |
| Reports | WeasyPrint (PDF), openpyxl (Excel) |
| Running | Docker Compose, on its own subnets |

## How it fits with the wellness system

```
 wellness system (Django + MySQL)                 M&E tool (Docker)
 ┌──────────────────────────────┐   every 30 min  ┌───────────────────────────────┐
 │ /api/export/snapshot/        │ ◄────────────── │ beat ─► worker: sync          │
 │ /api/export/visits/          │   service       │           │                   │
 │ /api/export/visit-ids/       │   account       │           ▼                   │
 │ /api/login/ + /api/me/  ◄────┼──── sign-in ─── │ web ◄─► PostgreSQL (warehouse)│
 └──────────────────────────────┘                 └───────────────────────────────┘
```

* **One set of logins.** People sign in to the M&E tool with their wellness
  username and password. Their roles and permissions are read from the wellness
  system at every sign-in, so access is managed in one place: *Users & roles*.
* **Incremental sync.** Small tables (companies, services, employees, payments)
  are copied in full each run. Visits are read only when changed since the last
  run (a cursor on `updated_at`, with a 2-minute overlap so nothing is missed).
  Every night the last 14 days are compared, so visits undone at reception
  disappear here too. Re-running a sync never duplicates anything.
* **Figures are calculated from the synced visits**, so dashboards, indicators
  and reports always agree with each other.

## Who sees what

| Wellness permission | In the M&E tool |
|---|---|
| super admin, *Manage users & roles* | everything, plus the *Data sync* page |
| *See M&E dashboards* (roles **M&E officer**, **EUCL HR**), *See all visits*, *Manage payments* | all companies, all EUCL employees (with names) |
| *Manage M&E targets* (role **M&E officer**) | can set targets |
| company staff with *See company visits*, *Company dashboard* or *See employees attended* | **only their own company**: its services, visits and amounts, with no employee names |
| anyone else | no access |

## Indicators

Created by a migration; targets are set on the **Targets** page, per month,
for EUCL overall or for one company (optionally repeated for the next months).

| Indicator | Calculation | Better when |
|---|---|---|
| Participation rate | % of active EUCL employees who used a service | higher |
| Services used | number of visits | higher |
| Employees who used a service | different employees | higher |
| Visits per participating employee | visits ÷ participants | higher |
| Repeat use | % of last month's participants who came again | higher |
| Amount spent | sum of what EUCL pays | lower (budget) |
| Cost per visit / per participant | amount ÷ visits / participants | lower |
| Service coverage | % of offered services EUCL covers | higher |
| Still owed for the month | unpaid amount for the month's visits | lower |
| Payment delay | days from the end of a paid period to the payment | lower |

Status: **on track** when the target is met, **at risk** within 10 % of it,
**off track** beyond. To add an indicator, add a function to
`indicators/calculations.py`, then the indicator in *Django admin*.

## System resources (admins)

The **System resources** page (menu: Settings) watches what the tool runs on:

* **Server:** CPU usage, cores and speed (MHz), load, memory, disk, uptime.
  In Docker these are the Docker host's figures as the container sees them.
* **Database growth:** a snapshot every night (size and rows of every table),
  the average growth per day, the expected size in 30 / 90 days and roughly
  when the disk would be full; the tables that grew most this week.
* **Services:** database and Redis response times, tasks waiting in the
  queue, Celery workers online, the wellness API, and the last sync.
* **Report files:** space used by generated reports.
* **History:** a sample every `MONITOR_INTERVAL_MINUTES` (10), kept
  `MONITOR_RETENTION_DAYS` (30), shown for the last 24 hours / 7 / 30 days.
* **Health checks** turn to *Attention* or *Down* at the limits set in `.env`
  (`MONITOR_ALERT_CPU`, `_MEMORY`, `_DISK`, `_DB_MS`, `_API_MS`, `_QUEUE`, `_SYNC_HOURS`).

## Set up

### 1. In the wellness system

1. Apply the new migration (adds the export API's change tracking and the M&E roles):
   ```bash
   python manage.py migrate
   ```
2. In **Users & roles**, create a user for the M&E tool, e.g. `me_sync`, with
   the role **M&E sync service**. Give **M&E officer** to whoever follows the
   indicators (EUCL HR can already open the M&E tool).
3. Let Docker reach the API: in the wellness `.env`, add
   `host.docker.internal` to `DJANGO_ALLOWED_HOSTS`, then run Django on all
   interfaces:
   ```bash
   python manage.py runserver 0.0.0.0:8000
   ```

### 2. Start the M&E tool

```bash
cd me_tool
copy .env.example .env      # then edit .env: secret key, database password, me_sync password
docker compose up -d --build
```

Open <http://localhost:8100> and sign in with a wellness account. The first
sync runs within 30 minutes; to run it now, use **Data sync → Sync now**
(super admin) or:

```bash
docker compose exec web python manage.py sync_wellness
```

Useful commands:

```bash
docker compose ps                                   # what is running
docker compose logs -f web worker beat              # logs
docker compose exec web python manage.py createsuperuser   # emergency local admin
docker compose exec web python manage.py test --settings=config.settings_test
docker compose down                                  # stop (data is kept in volumes)
```

### Networks

* `me_internal` (172.28.10.0/24, **internal**): PostgreSQL, Redis and the app
  containers. Nothing outside Docker can reach the database or Redis.
* `me_edge` (172.28.20.0/24): the web app's published port (8100) and the way
  out to the wellness API.

## Local development without Docker

```bash
cd me_tool
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
set DJANGO_DEBUG=1
set CELERY_TASK_ALWAYS_EAGER=1
set WELLNESS_API_URL=http://127.0.0.1:8000
set WELLNESS_SYNC_USERNAME=me_sync
set WELLNESS_SYNC_PASSWORD=...
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py sync_wellness
.venv\Scripts\python manage.py runserver 8100
```

Without `POSTGRES_HOST` it uses SQLite; with `CELERY_TASK_ALWAYS_EAGER=1`
background jobs run immediately (no Redis needed). PDF reports need
WeasyPrint's system libraries, which the Docker image has; on Windows they
need the GTK runtime, and Excel reports work everywhere.

Tests: `python manage.py test --settings=config.settings_test`

## Project layout

```
config/       settings, URLs, Celery and its schedule
accounts/     sign-in through the wellness API, who sees what (scope.py)
warehouse/    the synced copy of the data, the API client and the sync
indicators/   indicators, targets and their calculations
dashboards/   overview, companies, company, services and indicators pages
reports/      daily, weekly and monthly PDF / Excel reports, built by Celery
monitoring/   system resources: server, database growth, services health
templates/    the pages and the PDF layout
docker/       the container's start script
```
