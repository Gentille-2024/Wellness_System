# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

EUCL Wellness Management System: EUCL employees use wellness services (gym, pool, massage…) at partner companies; company receptionists tick the services used; EUCL pays each company per visit. The repo holds **two separate Django applications**:

| Part | Path | Stack |
|---|---|---|
| Wellness system (API) | `backend/` (project), `wellness/` (the only app), `manage.py` at repo root | Django 6 + DRF + SimpleJWT, MySQL |
| Wellness frontend | `frontend/` | React 19 + Vite + React Router 7, axios, jsPDF / write-excel-file for exports |
| M&E tool | `me_tool/` (own `manage.py`, `.venv`, `.env`, requirements) | Django 6 server-rendered + HTMX + Chart.js, PostgreSQL (SQLite locally), Celery + Redis, WeasyPrint/openpyxl, Docker Compose |

The M&E tool has **no shared code or database** with the wellness system — it talks to it only over HTTP (see "How the two apps connect").

Note: both `requirements.txt` files are UTF-16 encoded; read them with `iconv -f utf-16` if `cat` shows garbage.

## Commands

### Wellness system (repo root, venv in `venv/`)
```powershell
venv\Scripts\activate
python manage.py migrate
python manage.py runserver              # use 0.0.0.0:8000 when the Dockerized M&E tool must reach it
python manage.py test wellness          # all tests (needs MySQL: Django creates a test DB)
python manage.py test wellness.tests.SomeTestCase.test_method   # a single test
```
Settings read `.env` at repo root via a small loader in `backend/settings.py` (real env vars win). `DJANGO_SECRET_KEY` and `DB_PASSWORD` are required — settings raise `KeyError` without them.

### Frontend (`frontend/`)
```powershell
npm install
npm run dev      # http://localhost:5173; Vite proxies /api -> http://127.0.0.1:8000
npm run lint
npm run build
```
No frontend test suite exists.

### M&E tool (`me_tool/`)
```powershell
# Local, without Docker (SQLite, Celery tasks run inline):
.venv\Scripts\python manage.py test --settings=config.settings_test        # tests always use config.settings_test
.venv\Scripts\python manage.py test reports --settings=config.settings_test # one app
.venv\Scripts\python manage.py sync_wellness     # pull data from the wellness API now
.venv\Scripts\python manage.py runserver 8100
```
Local dev env vars: `DJANGO_DEBUG=1`, `CELERY_TASK_ALWAYS_EAGER=1`, `WELLNESS_API_URL=http://127.0.0.1:8000`, `WELLNESS_SYNC_USERNAME/PASSWORD`. No `POSTGRES_HOST` → SQLite. PDF reports need WeasyPrint's GTK libs (present in the Docker image, not on plain Windows).

Docker: `docker compose up -d --build` (web on :8100), `docker compose exec web python manage.py <cmd>`. One image runs `web` / `worker` / `beat` via `docker/entrypoint.sh`; `web` runs migrations on start.

## Wellness system architecture

**Permissions, not roles, drive everything.** `wellness/permissions.py` holds the canonical `PERMISSIONS` list (code, name, description, area). Roles are DB rows bundling permissions, created by the super admin in the app; a user may have several. Never check role names in code.
- Backend: the global DRF permission class `PermissionRequired` reads `read_perms` / `write_perms` / `open_read` attributes declared on each view. Superusers bypass it.
- Row-level visibility is done in each viewset's `get_queryset` (e.g. `visits_for(user)` in `wellness/views.py` unions what each permission allows: all visits / own company's / own visits). `filter_visits` holds the shared query-param filters used by lists, stats and exports.
- Adding a permission: add it to `PERMISSIONS`, add a data migration that creates it (see existing migrations such as `0014`/`0016`), and mirror it in the frontend (`src/auth/access.js`, `src/navigation.js`, routes in `src/App.jsx`).
- Company roles (`Role.is_company_role`) stop counting while the user's company is deactivated (`active_roles`); such users get a 403 with `code: "company_deactivated"`, which the frontend axios client turns into a forced sign-out with a notice.
- Companies are never erased: `is_active=False` = deactivated (paused), `deleted_at` set = archived. Both are reversible.
- `Visit` copies `company` and `price` at record time so history survives price/name changes; one visit per employee+service+day (DB constraint). `Visit.updated_at` is indexed and exists for the M&E incremental sync — keep it `auto_now`.

**Frontend:** `src/api/client.js` is the only HTTP layer (JWT in localStorage, single-flight token refresh on 401, `errorMessage`/`parseErrors` to map DRF errors to forms). `can(user, ...perms)` treats superusers as having everything, but company and employee pages check `user.role_permissions` (the `exact` prop on `<Allow>` / `ProtectedRoute`) so a super admin does not see company/employee areas. The app has three areas — `/eucl`, `/company`, `/my-wellness` — and `homeFor(user)` picks the landing page.

## How the two apps connect

- **Sign-in:** the M&E tool has no own user management. `accounts/views.py` signs users in against the wellness `/api/login/` + `/api/me/` (`warehouse/client.py: sign_in`) and caches roles/permissions in `accounts.models.Access` on every login. A local Django superuser still works as an emergency fallback when the wellness API is down.
- **Who sees what:** `accounts/scope.py` — `Scope` (all companies vs one company) and the `@me_view(test)` decorator that every page view uses; it sets `request.access` and `request.scope`. Always filter querysets via `request.scope`. Company staff never see employee names (`Access.can_see_names`).
- **Data sync:** a service account with the `export_data` permission pulls `wellness/export.py` endpoints. `warehouse/sync.py: run_sync` upserts small tables in full from `/api/export/snapshot/`, pulls visits incrementally by an `(updated_at, id)` cursor with a 2-minute overlap, and a nightly `reconcile` compares visit ids for the last `RECONCILE_DAYS` to drop visits deleted upstream. Syncs must stay idempotent. Changing the export payload means changing both `wellness/export.py` and `me_tool/warehouse/sync.py`.
- **Schedules** are all in `CELERY_BEAT_SCHEDULE` in `me_tool/config/settings.py` (sync, nightly reconcile, daily/weekly/monthly reports when `AUTO_REPORTS=1`, resource sampling, DB snapshots).

## M&E tool internals

- Every figure (dashboards, indicators, reports) is computed from the synced `warehouse` models so they always agree; don't add a second source of numbers.
- Indicators: definitions are DB rows (seeded by `indicators/migrations/0002_default_indicators.py`); each `code` maps to a function in `indicators/calculations.py` taking `(month, scope)`. Months come from `indicators/periods.Month`. Status: on track when target met, at risk within 10 %, off track beyond; each indicator says whether higher or lower is better.
- `reports/` builds PDF (`pdf.py`, template `templates/reports/report_pdf.html`) and Excel (`excel.py`) via Celery tasks; files go to `MEDIA_ROOT`.
- `monitoring/` collects server/DB/Redis/Celery/API health samples; alert thresholds come from `MONITOR_ALERT_*` env vars.
- Tests build a shared fixture with `config.testing.World` (two companies, employees, visits for October 2026) and `make_user(username, permissions, company=...)`; the wellness API is mocked at `http://wellness.test`.
- Front-end assets (HTMX, Chart.js) are vendored in `static/vendor` on purpose — the tool must work without internet access.
