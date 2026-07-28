# TravelMind Agent — Backend image (multi-stage build)
# Phase 14d: Builder stage for pip, prod stage with non-root user
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements-prod.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt


FROM python:3.11-slim AS prod

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ANONYMIZED_TELEMETRY=False \
    APP_USER=travelmind

WORKDIR /app

# Copy only runtime dependencies from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/uvicorn /usr/local/bin/uvicorn

# Copy application code
COPY app ./app
COPY scripts ./scripts
COPY data ./data
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

# Entrypoint
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Create non-root user
RUN addgroup --system --gid 1001 $APP_USER && \
    adduser --system --uid 1001 --gid 1001 $APP_USER && \
    chown -R $APP_USER:$APP_USER /app

EXPOSE 8000

USER $APP_USER
ENTRYPOINT ["/docker-entrypoint.sh"]
