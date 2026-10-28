#!/bin/sh
# One image, three jobs:  web | worker | beat  (anything else runs as a command)
set -e

wait_for_db() {
  python - <<'PY'
import os, sys, time
import psycopg
for attempt in range(30):
    try:
        psycopg.connect(
            host=os.environ["POSTGRES_HOST"], port=os.environ.get("POSTGRES_PORT", "5432"),
            dbname=os.environ.get("POSTGRES_DB", "me_tool"), user=os.environ.get("POSTGRES_USER", "me_tool"),
            password=os.environ.get("POSTGRES_PASSWORD", ""), connect_timeout=3,
        ).close()
        sys.exit(0)
    except psycopg.OperationalError:
        print("Waiting for PostgreSQL...", flush=True)
        time.sleep(2)
sys.exit("PostgreSQL did not become ready")
PY
}

case "$1" in
  web)
    wait_for_db
    python manage.py migrate --noinput
    exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-3}" --timeout 120 --access-logfile -
    ;;
  worker)
    wait_for_db
    exec celery -A config worker --loglevel "${LOG_LEVEL:-INFO}" --concurrency "${CELERY_CONCURRENCY:-2}"
    ;;
  beat)
    wait_for_db
    exec celery -A config beat --loglevel "${LOG_LEVEL:-INFO}" --schedule /tmp/celerybeat-schedule
    ;;
  *)
    exec "$@"
    ;;
esac
