# TravelMind Agent — Backend image (multi-stage build)
# Phase 14d: Builder stage for pip, prod stage with non-root user
# Phase 18 M5.4: Added HEALTHCHECK + OCI metadata labels
FROM python:3.11-slim AS builder

LABEL org.opencontainers.image.title="TravelMind Agent Backend" \
      org.opencontainers.image.description="羊城智游 — 广州 AI 旅行规划智能体后端(广州 AI+旅游休闲大赛)" \
      org.opencontainers.image.source="https://github.com/travelmind-agent" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="1.0.0"

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

# Install only pg_isready for entrypoint healthcheck (Phase 18 M5.4: small footprint)
RUN apt-get update -qq && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Entrypoint
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Create non-root user
RUN addgroup --system --gid 1001 $APP_USER && \
    adduser --system --uid 1001 --gid 1001 $APP_USER && \
    chown -R $APP_USER:$APP_USER /app

EXPOSE 8000

# Phase 18 M5.4: Healthcheck (also defined in docker-compose for compose-level orchestration)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health').read()" || exit 1

USER $APP_USER
ENTRYPOINT ["/docker-entrypoint.sh"]
