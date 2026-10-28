# EUCL Wellness M&E tool: one image for the web app, the Celery worker and Celery beat.
# Debian slim (not Alpine): WeasyPrint needs Pango and HarfBuzz from Debian.
FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 libharfbuzz0b \
        fonts-dejavu-core shared-mime-info curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN chmod +x docker/entrypoint.sh \
    && DJANGO_SECRET_KEY=collectstatic-only python manage.py collectstatic --noinput \
    && useradd --create-home --uid 1000 metool \
    && mkdir -p /app/media \
    && chown -R metool:metool /app/media

USER metool
EXPOSE 8000
ENTRYPOINT ["docker/entrypoint.sh"]
CMD ["web"]
