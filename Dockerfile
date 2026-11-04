# EUCL Wellness system (Django API) for Railway or any Docker host.
# The React frontend (frontend/) and the M&E tool (me_tool/) deploy separately.
FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# mysqlclient is compiled here: it needs the MySQL client library and a compiler
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        default-libmysqlclient-dev build-essential pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
# Static files for the Django admin, served by WhiteNoise
RUN DJANGO_SECRET_KEY=collectstatic-only DATABASE_URL=sqlite:////tmp/build.sqlite3 \
    python manage.py collectstatic --noinput

# Railway gives the port in $PORT. Migrations run at every start (they are
# safe to repeat), then gunicorn serves the API.
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn backend.wsgi:application --bind 0.0.0.0:${PORT} --workers ${GUNICORN_WORKERS:-3} --timeout 120 --access-logfile -"]
